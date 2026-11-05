"""Full real HTTP/WebSocket -> separate Broker -> mock SSH/tmux, isolated SQLite."""

import asyncio
import base64
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import sys
import urllib.error
import urllib.request

from alembic import command
from alembic.config import Config
from sqlalchemy import select
import uvicorn
from websockets.asyncio.client import connect

from app.core.config import Settings
from app.core.database import unit_of_work
from app.main import create_app
from app.models.domain import User
from app.models.console import ConsoleSession
from app.services.accounts import HASHER


async def main():
    fixture = json.load(sys.stdin)
    assert os.getuid() == 10001 and not Path("/keys/keyring").exists()
    url = "sqlite:////db/integration.db"
    os.environ["DATABASE_URL"] = url
    command.upgrade(Config("/app/alembic.ini"), "head")
    settings = Settings(
        secret_key=secrets.token_urlsafe(48),
        database_url=url,
        cookie_secure=False,
        console_enabled=True,
        console_allow_insecure_http=True,
        console_access_policy="all_authenticated",
        console_broker_socket="/ipc/broker.sock",
        console_broker_ipc_key_file="/ipc/auth",
        deadline_processor_enabled=False,
    )
    app = create_app(settings)
    password = secrets.token_urlsafe(32)
    with unit_of_work(app.state.engine, write=True) as db:
        db.add(
            User(
                username="synthetic",
                display_name="Synthetic",
                email="synthetic@example.test",
                team="Mock",
                role="super_admin",
                password_hash=HASHER.hash(password),
                must_change_password=False,
            )
        )
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=8080, access_log=False, log_level="critical")
    )
    serving = asyncio.create_task(server.serve())
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar)
    )
    origin = "http://127.0.0.1:8080"

    def http_request(method, path, value=None):
        headers = {"Origin": origin}
        if method != "GET":
            csrf = json.load(opener.open(origin + "/api/v1/auth/csrf"))["csrf_token"]
            headers.update({"X-CSRF-Token": csrf, "Content-Type": "application/json"})
        req = urllib.request.Request(
            origin + path,
            data=json.dumps(value).encode() if value is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with opener.open(req, timeout=15) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            # Do not print request, credentials, cookies or server body.
            raise AssertionError(f"synthetic {method} {path} status {error.code}") from None

    async def request(method, path, value=None):
        return await asyncio.to_thread(http_request, method, path, value)

    async def packet(ws, kind):
        async with asyncio.timeout(15):
            while True:
                value = await ws.recv()
                if isinstance(value, str):
                    value = json.loads(value)
                    if value["type"] == kind:
                        return value

    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.05)
        assert server.started and app.state.console_runtime.ready
        await request("POST", "/api/v1/auth/login", {"username": "synthetic", "password": password})
        lab = await request("POST", "/api/v1/labs", {"name": "Mock Lab", "location": "Synthetic"})
        sut = await request(
            "POST",
            "/api/v1/suts",
            {"name": "Mock UART", "lab_id": lab["id"], "platform": "Mock", "owner_team": "Mock"},
        )
        data = {
            "lab_id": lab["id"],
            "name": "Mock Client",
            "ipv4": fixture["host"],
            "ssh_username": fixture["username"],
            "auth_method": "password",
            "secret": fixture["password"],
        }
        draft = await request("POST", "/api/v1/console/client-validations", data)
        challenge = draft["challenge"]
        import asyncssh

        assert challenge["fingerprint"] == asyncssh.import_public_key(fixture["public_key"]).get_fingerprint(
            "sha256"
        )
        await request(
            "POST",
            "/api/v1/console/trust/accept",
            {
                "challenge_id": challenge["challenge_id"],
                "expected_trust_revision": 0,
                "fingerprint": challenge["fingerprint"],
                "out_of_band_verified": True,
            },
        )
        data["trust_challenge_id"] = challenge["challenge_id"]
        validated = await request("POST", "/api/v1/console/client-validations", data)
        client = await request(
            "POST", "/api/v1/console/clients", {"validation_id": validated["validation_id"]}
        )
        await request(
            "PUT",
            f"/api/v1/console/suts/{sut['id']}/uart",
            {"expected_revision": 0, "client_id": client["id"], "tmux_session": "existing"},
        )
        reservation = await request(
            "POST",
            "/api/v1/console/sessions",
            {"sut_id": sut["id"], "transport": "uart", "expected_revision": 1, "tab_id": "real-pipeline"},
        )
        cookie = "; ".join(c.name + "=" + c.value for c in jar)
        async with connect(
            "ws://127.0.0.1:8080/ws/console/v1/sessions/" + reservation["session_id"],
            origin=origin,
            subprotocols=["sut-console.v1"],
            additional_headers={"Cookie": cookie},
            proxy=None,
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "v": 1,
                        "type": "hello",
                        "ticket": reservation["ticket"],
                        "tab_id": "real-pipeline",
                        "attachment_generation": 1,
                        "cols": 100,
                        "rows": 30,
                    }
                )
            )
            assert (await packet(ws, "connected"))["mode"] == "write"
            marker = b"FULL_PIPELINE_SYNTHETIC"
            await ws.send(
                json.dumps(
                    {
                        "type": "input",
                        "attachment_generation": 1,
                        "seq": 1,
                        "data": base64.b64encode(marker).decode(),
                    }
                )
            )
            assert (await packet(ws, "input_ack"))["stage"] == "broker_written"
            async with asyncio.timeout(5):
                seen = b""
                while marker not in seen:
                    value = await ws.recv()
                    if isinstance(value, bytes):
                        seen += value
            await ws.send(json.dumps({"type": "disconnect"}))
            while (await packet(ws, "state"))["state"] != "Disconnected":
                pass
        await asyncio.sleep(0.2)
        with unit_of_work(app.state.engine) as db:
            assert db.scalar(select(ConsoleSession)).state == "closed"
            dump = "\n".join(db.connection().connection.driver_connection.iterdump())
            assert fixture["password"] not in dump and password not in dump and marker.decode() not in dump
        print(
            "PASS: real HTTP CSRF/login -> trust challenge/ack -> verified Client -> one-use ticket -> WebSocket -> private Broker -> OpenSSH/tmux -> input ACK/output/disconnect"
        )
        print("PASS: no SSH/login plaintext password or synthetic terminal input in SQLite dump")
    finally:
        server.should_exit = True
        await serving
        app.state.engine.dispose()


asyncio.run(main())
