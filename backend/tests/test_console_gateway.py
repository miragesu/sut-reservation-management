"""Protocol/transaction tests with an explicitly fake SSH transport and real Unix IPC.

These are NOT SSH/tmux/device acceptance. Separate disposable OpenSSH tests cover it.
"""

import asyncio
from contextlib import contextmanager
import base64
import os
from pathlib import Path
import secrets
import threading
import time

import asyncssh
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.console_broker.executor import Executor
from app.console_broker.ipc import BrokerClient, BrokerError, BrokerServer
from app.core.database import unit_of_work
from app.main import create_app
from app.models.console import ConsoleClient, ConsoleCredential, ConsoleRevocation
from app.services.console.crypto import EnvelopeCipher
from conftest import create_inventory, csrf, sign_in


class FakeProcess:
    def __init__(self, transport):
        self.transport = transport
        self.queue = asyncio.Queue()
        self.stdout = self
        self.stdin = self
        self.exit_status = None
        self.received = []
        self.size = None

    async def read(self, n):
        return await self.queue.get()

    def write(self, data):
        self.received.append(data)
        for process in self.transport.processes:
            process.queue.put_nowait(b"ECHO:" + data)

    async def drain(self):
        await asyncio.sleep(0)

    async def wait_closed(self):
        return

    def change_terminal_size(self, cols, rows):
        self.size = (cols, rows)


class FakeConnection:
    def __init__(self, process=None):
        self.process = process

    def close(self):
        if self.process:
            self.process.queue.put_nowait(b"")

    async def wait_closed(self):
        return


class FakeSSH:
    def __init__(self):
        self.host_key = asyncssh.generate_private_key("ssh-ed25519")
        self.password = secrets.token_urlsafe(24)
        self.processes = []
        self.auth_count = 0
        self.probe_count = 0
        self.open_count = 0
        self.failure = None
        self.attempts = 0
        self.delay = 0
        self.waiting = False
        self.failures = []

    @property
    def public(self):
        return self.host_key.export_public_key().decode().strip()

    async def probe(self, host, port, transport):
        self.probe_count += 1
        return {
            "public_key": self.public,
            "algorithm": "ssh-ed25519",
            "fingerprint": self.host_key.get_fingerprint("sha256"),
        }

    async def authenticate(self, target, credential):
        if target["public_key"] != self.public:
            raise BrokerError("host_key_changed")
        self.auth_count += 1
        if credential["method"] == "password" and credential["secret"] != self.password:
            credential.clear()
            raise BrokerError("credential_auth_failed")
        credential.clear()
        return FakeConnection()

    async def open(self, target, credential, *, cols, rows, readonly):
        self.attempts += 1
        if self.delay:
            self.waiting = True
            await asyncio.sleep(self.delay)
        if self.failures:
            failure = self.failures.pop(0)
            if failure:
                raise BrokerError(failure)
        if self.failure:
            raise BrokerError(self.failure)
        await self.authenticate(target, credential)
        if target.get("tmux_session") == "missing":
            raise BrokerError("tmux_not_found")
        self.open_count += 1
        process = FakeProcess(self)
        process.size = (cols, rows)
        self.processes.append(process)
        return FakeConnection(process), process, b"MOCK_READY"


@contextmanager
def broker_thread(directory, transport):
    directory = Path(directory)
    directory.mkdir(mode=0o700)
    ipc_key = os.urandom(32)
    key_file = directory / "ipc.key"
    key_file.write_bytes(ipc_key)
    key_file.chmod(0o600)
    socket_path = directory / "broker.sock"
    ready = threading.Event()
    stopped = None
    loop = None
    server = None

    def run():
        async def serve():
            nonlocal stopped, loop, server
            loop = asyncio.get_running_loop()
            stopped = asyncio.Event()
            executor = Executor(
                EnvelopeCipher({"synthetic": os.urandom(32)}, "synthetic"), transport=transport
            )
            server = BrokerServer(socket_path, ipc_key, executor, allowed_uid=os.getuid())
            await server.start()
            ready.set()
            await stopped.wait()
            await server.stop()

        asyncio.run(serve())

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert ready.wait(5)
    try:
        yield socket_path, key_file, ipc_key, server
    finally:
        loop.call_soon_threadsafe(stopped.set)
        thread.join(timeout=5)
        assert not thread.is_alive()


def mutate_c(client, method, path, data=None):
    return client.request(
        method,
        "/api/v1/console" + path,
        json=data,
        headers={"X-CSRF-Token": csrf(client), "Origin": "http://testserver"},
    )


def until(predicate, seconds=4):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.03)
    return False


@pytest.fixture
def live(application, tmp_path):
    fake = FakeSSH()
    with broker_thread(tmp_path / "broker", fake) as (socket_path, key_file, secret, server):
        settings = application.state.settings.model_copy(
            update={
                "console_enabled": True,
                "console_allow_insecure_http": True,
                "console_access_policy": "all_authenticated",
                "console_broker_socket": str(socket_path),
                "console_broker_ipc_key_file": str(key_file),
                "console_broker_uid": os.getuid(),
                "console_allowed_origins": ["http://testserver"],
            }
        )
        app = create_app(settings)
        with TestClient(app) as root:
            assert app.state.console_runtime.ready
            sign_in(root)
            lab, sut = create_inventory(root, "Live synthetic SUT", "Live mock Lab")
            clients = {"root": root}
            for name in ("rd", "lab"):
                client = TestClient(app)
                client.portal = root.portal  # one ASGI loop, separate cookies, no duplicate lifespans
                sign_in(client, name)
                clients[name] = client
            try:
                yield app, clients, lab, sut, fake, server
            finally:
                for name, client in clients.items():
                    if name != "root":
                        client.close()
        app.state.engine.dispose()


def onboard(live, *, method="password"):
    app, clients, lab, sut, fake, _ = live
    credential = (
        asyncssh.generate_private_key("ssh-ed25519").export_private_key().decode()
        if method == "private_key"
        else fake.password
    )
    data = {
        "lab_id": lab,
        "name": "Synthetic Console",
        "ipv4": "192.168.234.10",
        "ssh_username": "synthetic",
        "auth_method": method,
        "secret": credential,
    }
    response = mutate_c(clients["root"], "POST", "/client-validations", data)
    assert response.status_code == 200, response.text
    challenge = response.json()["challenge"]
    assert fake.auth_count == 0
    accept = {
        "challenge_id": challenge["challenge_id"],
        "expected_trust_revision": 0,
        "fingerprint": challenge["fingerprint"],
        "out_of_band_verified": True,
    }
    response = mutate_c(clients["root"], "POST", "/trust/accept", accept)
    assert response.status_code == 200, response.text
    data["trust_challenge_id"] = challenge["challenge_id"]
    validated = mutate_c(clients["root"], "POST", "/client-validations", data)
    assert validated.status_code == 200, validated.text
    assert validated.json()["validated"] is True
    assert credential not in validated.text
    created = mutate_c(
        clients["root"], "POST", "/clients", {"validation_id": validated.json()["validation_id"]}
    )
    assert created.status_code == 201, created.text
    client_id = created.json()["id"]
    response = mutate_c(
        clients["rd"],
        "PUT",
        f"/suts/{sut}/uart",
        {"expected_revision": 0, "client_id": client_id, "tmux_session": "existing"},
    )
    assert response.status_code == 200, response.text
    return client_id, credential


def ticket(client, sut, *, transport="uart", revision=1, tab="synthetic-tab"):
    response = mutate_c(
        client,
        "POST",
        "/sessions",
        {"sut_id": sut, "transport": transport, "expected_revision": revision, "tab_id": tab},
    )
    assert response.status_code == 201, response.text
    return response.json()


def connect(client, data, *, tab="synthetic-tab", origin="http://testserver"):
    return client.websocket_connect(
        "/ws/console/v1/sessions/" + data["session_id"],
        headers={"Origin": origin},
        subprotocols=["sut-console.v1"],
    )


def hello(ws, data, tab="synthetic-tab"):
    ws.send_json(
        {
            "v": 1,
            "type": "hello",
            "ticket": data["ticket"],
            "tab_id": tab,
            "attachment_generation": data["attachment_generation"],
            "cols": 100,
            "rows": 30,
        }
    )


def message(ws, kind):
    for _ in range(30):
        packet = ws.receive()
        if packet["type"] == "websocket.close":
            raise AssertionError("closed:" + str(packet.get("reason")))
        if packet.get("text"):
            import json

            result = json.loads(packet["text"])
            if result["type"] == kind:
                return result
    raise AssertionError("expected " + kind)


def test_onboarding_real_boundary_and_broker_owned_cipher(live):
    app, clients, _, _, fake, _ = live
    client_id, credential = onboard(live)
    assert fake.auth_count == 1 and fake.open_count == 0
    with unit_of_work(app.state.engine) as db:
        assert db.scalar(select(ConsoleClient)).id == client_id
        stored = db.scalar(select(ConsoleCredential))
        assert credential.encode() not in stored.ciphertext
    assert credential not in clients["root"].get("/api/v1/console/clients").text


def test_ws_input_resize_disconnect_and_replay(live):
    app, clients, _, sut, fake, _ = live
    onboard(live)
    data = ticket(clients["rd"], sut)
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        assert message(ws, "connected")["mode"] == "write"
        payload = secrets.token_bytes(20)
        ws.send_json(
            {
                "type": "input",
                "attachment_generation": 1,
                "seq": 1,
                "data": base64.b64encode(payload).decode(),
            }
        )
        assert message(ws, "input_ack")["stage"] == "broker_written"
        assert fake.processes[0].received == [payload]
        ws.send_json({"type": "resize", "cols": 131, "rows": 41})
        assert until(lambda: fake.processes[0].size == (131, 41))
        ws.send_json({"type": "disconnect"})
    assert until(lambda: clients["rd"].get("/api/v1/console/sessions/me").json()["usage"] == 0)
    with pytest.raises((WebSocketDisconnect, AssertionError)):
        with connect(clients["rd"], data) as ws:
            hello(ws, data)
            message(ws, "connected")
    assert len(fake.processes) == 1


def test_ws_origin_login_ticket_binding_and_no_generic_exec(live):
    app, clients, _, sut, fake, _ = live
    onboard(live)
    data = ticket(clients["rd"], sut)
    with pytest.raises(WebSocketDisconnect):
        with connect(clients["rd"], data, origin="http://evil.invalid"):
            pass
    with pytest.raises((WebSocketDisconnect, AssertionError)):
        with connect(clients["lab"], data) as ws:
            hello(ws, data)
            message(ws, "connected")
    assert fake.open_count == 0
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        message(ws, "connected")
        ws.send_json({"type": "exec", "command": "id"})
        assert ws.receive()["type"] == "websocket.close"
    assert not fake.processes[0].received


def test_readonly_rejected_by_gateway_and_broker(live):
    app, clients, _, sut, fake, server = live
    onboard(live)
    app.state.settings.console_access_policy = "shared_readonly"
    data = ticket(clients["rd"], sut)
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        message(ws, "connected")
        ws.send_json(
            {
                "type": "input",
                "attachment_generation": 1,
                "seq": 1,
                "data": base64.b64encode(b"BLOCKED").decode(),
            }
        )
        assert message(ws, "input_rejected")["reason_code"] == "read_only"
        assert not fake.processes[0].received
        secret = app.state.console_runtime.broker.secret

        async def attack():
            client = BrokerClient(server.path, secret, expected_uid=os.getuid())
            await client.call("status")
            with pytest.raises(BrokerError) as error:
                await client.call(
                    "input",
                    session_id=data["session_id"],
                    generation=1,
                    seq=1,
                    data=base64.b64encode(b"NO").decode(),
                )
            assert error.value.code == "read_only"

        asyncio.run(attack())
        ws.send_json({"type": "disconnect"})


def test_mapping_revocation_requires_generation_fence_ack(live):
    app, clients, _, sut, fake, _ = live
    onboard(live)
    data = ticket(clients["rd"], sut)
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        message(ws, "connected")
        change = {"expected_revision": 1, "clear": True}
        assert mutate_c(clients["rd"], "PUT", f"/suts/{sut}/uart", change).status_code == 409
        preview = mutate_c(clients["rd"], "POST", f"/suts/{sut}/uart/preview", change).json()
        change["confirmation_id"] = preview["confirmation_id"]
        response = mutate_c(clients["rd"], "PUT", f"/suts/{sut}/uart", change)
        assert response.status_code == 200, response.text
        assert message(ws, "revoked")["manual_connect_required"] is True
    with unit_of_work(app.state.engine) as db:
        outbox = db.scalar(
            select(ConsoleRevocation).where(ConsoleRevocation.session_id == data["session_id"])
        )
        assert outbox.delivered_at is not None
    assert fake.open_count == 1


def test_host_key_changed_never_sends_credentials_and_failure_keeps_rows(live):
    app, clients, _, sut, fake, _ = live
    client_id, secret = onboard(live)
    before = fake.auth_count
    fake.host_key = asyncssh.generate_private_key("ssh-ed25519")
    candidate = {"client_id": client_id, "expected_version": 1, "secret": secrets.token_urlsafe(25)}
    response = mutate_c(clients["root"], "POST", "/client-validations", candidate)
    assert response.status_code == 200 and response.json()["validated"] is False
    assert fake.auth_count == before
    with unit_of_work(app.state.engine) as db:
        assert db.get(ConsoleClient, client_id).metadata_version == 1
        assert db.scalar(select(ConsoleCredential)).replaced_at is None


def test_ipc_bad_capability_and_operation_allowlist(live):
    app, _, _, _, _, server = live

    async def attack():
        wrong = BrokerClient(server.path, os.urandom(32), expected_uid=os.getuid())
        with pytest.raises(BrokerError):
            await wrong.call("status")
        client = BrokerClient(server.path, app.state.console_runtime.broker.secret, expected_uid=os.getuid())
        for operation in ("exec", "forward", "sftp", "kill_session"):
            with pytest.raises(BrokerError) as error:
                await client.call(operation)
            assert error.value.code == "unsupported_operation"

    asyncio.run(attack())


def test_bmc_three_attempts_no_cross_flow_lockout_or_secret_persistence(live):
    app, clients, _, sut, fake, _ = live
    response = mutate_c(
        clients["rd"], "PUT", f"/suts/{sut}/bmc", {"expected_revision": 0, "ipv4": "192.168.234.11"}
    )
    assert response.status_code == 200
    challenge = mutate_c(clients["rd"], "POST", "/trust/challenges", {"sut_id": sut}).json()
    response = mutate_c(
        clients["rd"],
        "POST",
        "/trust/accept",
        {
            "challenge_id": challenge["challenge_id"],
            "expected_trust_revision": 0,
            "fingerprint": challenge["fingerprint"],
            "out_of_band_verified": True,
        },
    )
    assert response.status_code == 200, response.text
    password = secrets.token_urlsafe(30)
    data = ticket(clients["rd"], sut, transport="bmc")
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        flow = message(ws, "auth_required")
        for index in range(3):
            ws.send_json(
                {
                    "type": "authenticate",
                    "flow_id": flow["flow_id"],
                    "username": "synthetic-bmc",
                    "password": password,
                }
            )
            if index < 2:
                flow = message(ws, "auth_required")
                assert flow["remaining_attempts"] == 2 - index
            else:
                failed = message(ws, "state")
                assert failed["state"] == "Failed"
    # No rolling-window account lockout: an explicit fresh flow can authenticate.
    next_data = ticket(clients["rd"], sut, transport="bmc")
    with connect(clients["rd"], next_data) as ws:
        hello(ws, next_data)
        flow = message(ws, "auth_required")
        ws.send_json(
            {
                "type": "authenticate",
                "flow_id": flow["flow_id"],
                "username": "synthetic-bmc",
                "password": fake.password,
            }
        )
        assert message(ws, "connected")["transport"] == "bmc"
        ws.send_json({"type": "disconnect"})
    with unit_of_work(app.state.engine) as db:
        for table in ("console_auth_flows", "console_audits", "console_sessions"):
            from sqlalchemy import text

            assert password not in str(db.execute(text("SELECT * FROM " + table)).all())


def test_concurrent_live_ticket_quota_and_slot_cleanup(live):
    from concurrent.futures import ThreadPoolExecutor

    app, clients, _, sut, _, _ = live
    onboard(live)
    token = csrf(clients["rd"])

    def reserve(index):
        return clients["rd"].post(
            "/api/v1/console/sessions",
            json={"sut_id": sut, "transport": "uart", "expected_revision": 1, "tab_id": f"race-{index}"},
            headers={"X-CSRF-Token": token, "Origin": "http://testserver"},
        )

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(reserve, range(12)))
    assert sum(r.status_code == 201 for r in results) == 10
    assert sum(r.status_code == 429 for r in results) == 2
    assert clients["rd"].get("/api/v1/console/sessions/me").json()["usage"] == 10


@pytest.mark.parametrize("failure", ["tmux_not_found", "credential_auth_failed", "host_key_changed"])
def test_uart_permanent_failure_no_retry_and_quota_released(live, failure):
    app, clients, _, sut, fake, _ = live
    onboard(live)
    fake.failure = failure
    data = ticket(clients["rd"], sut)
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        while True:
            state = message(ws, "state")
            if state["state"] == "Failed":
                assert state["reason_code"] == failure
                break
    assert fake.open_count == 0
    assert until(lambda: clients["rd"].get("/api/v1/console/sessions/me").json()["usage"] == 0)


def test_expired_login_cannot_consume_ticket(live):
    from datetime import timedelta
    from app.models.domain import LoginSession, User
    from app.core.database import clock_now

    app, clients, _, sut, fake, _ = live
    onboard(live)
    data = ticket(clients["rd"], sut)
    with unit_of_work(app.state.engine, write=True) as db:
        user = db.scalar(select(User).where(User.username == "rd"))
        login = db.scalar(select(LoginSession).where(LoginSession.user_id == user.id))
        login.expires_at = clock_now(db) - timedelta(seconds=1)
    with pytest.raises(WebSocketDisconnect):
        with connect(clients["rd"], data):
            pass
    assert fake.open_count == 0


def test_live_grant_revocation_fences_before_next_input(live):
    from app.models.domain import User

    app, clients, _, sut, fake, _ = live
    onboard(live)
    app.state.settings.console_access_policy = "claim_only"
    with unit_of_work(app.state.engine) as db:
        user = db.scalar(select(User.id).where(User.username == "rd"))
    from conftest import mutate

    response = mutate(
        clients["root"],
        "PATCH",
        f"/api/v1/suts/{sut}/operational-state",
        {"state": "maintenance", "reason": "synthetic grant fixture"},
    )
    assert response.status_code == 200
    grant = mutate_c(
        clients["root"], "POST", f"/suts/{sut}/grants", {"user_id": user, "duration_hours": 1}
    ).json()
    data = ticket(clients["rd"], sut)
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        message(ws, "connected")
        response = mutate_c(
            clients["root"], "POST", f"/grants/{grant['id']}/revoke", {"expected_revision": 1}
        )
        assert response.status_code == 200, response.text
        assert message(ws, "revoked")["manual_connect_required"]
        assert not fake.processes[0].received
    with unit_of_work(app.state.engine) as db:
        assert all(r.delivered_at for r in db.scalars(select(ConsoleRevocation)))


def test_broker_lease_expiry_and_generation_fence_tombstone(live):
    app, clients, _, sut, fake, server = live
    onboard(live)

    # Exercise Broker independently: a paused Gateway cannot keep SSH alive.
    async def check():
        executor = server.executor
        args = {
            "session_id": "lease-proof",
            "generation": 1,
            "user_id": 99,
            "target": {
                "host": "192.168.234.11",
                "port": 22,
                "transport": "uart",
                "tmux_session": "existing",
                "public_key": fake.public,
            },
            "credential": {"method": "password", "username": "mock", "secret": fake.password},
            "mode": "write",
            "cols": 80,
            "rows": 24,
            "lease_until": time.time() + 0.25,
        }
        # Run on Broker loop, not a foreign event loop.
        await executor.dispatch("open", args)
        await asyncio.sleep(0.5)
        assert "lease-proof" not in executor.sessions
        ack = await executor.dispatch("fence", {"session_id": "late-open", "generation": 1})
        assert ack["absent"] and ack["fenced"]
        args.update(session_id="late-open", lease_until=time.time() + 2)
        with pytest.raises(BrokerError) as error:
            await executor.dispatch("open", args)
        assert error.value.code == "session_stale"

    asyncio.run_coroutine_threadsafe(check(), server.executor.watchdog.get_loop()).result(timeout=3)


def test_pending_open_fence_ack_cancels_before_late_connect(live):
    app, clients, _, sut, fake, server = live
    onboard(live)

    async def check():
        original = fake.open
        entered = asyncio.Event()

        async def delayed(*args, **kwargs):
            entered.set()
            await asyncio.sleep(5)
            return await original(*args, **kwargs)

        fake.open = delayed
        args = {
            "session_id": "pending-fence",
            "generation": 1,
            "user_id": 99,
            "target": {
                "host": "192.168.234.11",
                "port": 22,
                "transport": "uart",
                "tmux_session": "existing",
                "public_key": fake.public,
            },
            "credential": {"method": "password", "username": "mock", "secret": fake.password},
            "mode": "write",
            "cols": 80,
            "rows": 24,
            "lease_until": time.time() + 2,
        }
        task = asyncio.create_task(server.executor.dispatch("open", args))
        await entered.wait()
        ack = await server.executor.dispatch("fence", {"session_id": "pending-fence", "generation": 1})
        assert ack["fenced"] and task.cancelled()
        assert "pending-fence" not in server.executor.sessions
        assert fake.open_count == 0
        fake.open = original

    asyncio.run_coroutine_threadsafe(check(), server.executor.watchdog.get_loop()).result(timeout=3)


def test_ipc_replay_and_peer_uid_rejected(live):
    from app.console_broker.ipc import receive, send, sign, verify

    app, _, _, _, _, server = live
    secret = app.state.console_runtime.broker.secret

    async def check():
        wrong_peer = BrokerClient(server.path, secret, expected_uid=os.getuid() + 1)
        with pytest.raises(BrokerError) as error:
            await wrong_peer.call("status")
        assert error.value.code == "ipc_denied"
        request = sign(
            secret,
            {
                "v": 1,
                "boot": None,
                "nonce": secrets.token_hex(16),
                "deadline": time.time() + 5,
                "op": "status",
                "args": {},
            },
        )
        results = []
        for _ in range(2):
            reader, writer = await asyncio.open_unix_connection(str(server.path))
            await send(writer, request)
            results.append(verify(secret, await receive(reader)))
            writer.close()
            await writer.wait_closed()
        assert "result" in results[0] and results[1]["error"] == "ipc_denied"

    asyncio.run(check())


def test_broker_incarnation_change_requires_explicit_new_connect(live):
    app, clients, _, sut, fake, server = live
    onboard(live)
    data = ticket(clients["rd"], sut)
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        message(ws, "connected")
        server.boot_id = secrets.token_hex(16)
        assert message(ws, "revoked")["manual_connect_required"]
    new = ticket(clients["rd"], sut, tab="explicit-after-restart")
    with connect(clients["rd"], new) as ws:
        hello(ws, new, tab="explicit-after-restart")
        message(ws, "connected")
        ws.send_json({"type": "disconnect"})
    assert fake.open_count == 2
    assert all(not p.received for p in fake.processes)


def test_expired_ticket_and_wrong_tab_never_open_ssh(live):
    from datetime import timedelta
    from app.core.database import clock_now
    from app.models.console import ConsoleTicket

    app, clients, _, sut, fake, _ = live
    onboard(live)
    data = ticket(clients["rd"], sut)
    with pytest.raises((WebSocketDisconnect, AssertionError)):
        with connect(clients["rd"], data) as ws:
            hello(ws, data, tab="wrong-tab")
            message(ws, "connected")
    next_data = ticket(clients["rd"], sut, tab="expired")
    with unit_of_work(app.state.engine, write=True) as db:
        for row in db.scalars(select(ConsoleTicket)):
            row.expires_at = clock_now(db) - timedelta(seconds=1)
    with pytest.raises((WebSocketDisconnect, AssertionError)):
        with connect(clients["rd"], next_data) as ws:
            hello(ws, next_data, tab="expired")
            message(ws, "connected")
    assert fake.open_count == 0


def test_sensitive_validation_errors_and_unauthenticated_fencing(live):
    app, clients, _, sut, fake, server = live
    onboard(live)
    data = ticket(clients["rd"], sut)
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        message(ws, "connected")
        secret = secrets.token_urlsafe(30)
        response = mutate_c(
            clients["root"], "POST", "/client-validations", {"secret": secret, "unexpected": secret}
        )
        assert response.status_code == 422 and secret not in response.text
        anonymous = TestClient(app)
        anonymous.portal = clients["root"].portal
        try:
            response = anonymous.post(
                "/api/v1/console/clients",
                json={"validation_id": "forged"},
                headers={"Origin": "http://testserver"},
            )
            assert response.status_code in (401, 403)
            assert not server.executor.sessions[data["session_id"]].fenced
        finally:
            anonymous.portal = None
            anonymous.close()
        ws.send_json({"type": "disconnect"})


def test_live_claim_release_revokes_before_another_input(live):
    from conftest import mutate

    app, clients, _, sut, fake, _ = live
    onboard(live)
    app.state.settings.console_access_policy = "claim_only"
    claim = mutate(
        clients["rd"],
        "POST",
        f"/api/v1/suts/{sut}/claim",
        {
            "duration_minutes": 60,
            "purpose": "synthetic console test",
        },
    )
    assert claim.status_code == 201, claim.text
    data = ticket(clients["rd"], sut)
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        message(ws, "connected")
        released = mutate(
            clients["rd"], "POST", f"/api/v1/suts/{sut}/release", {"usage_key": claim.json()["usage_key"]}
        )
        assert released.status_code == 200, released.text
        assert message(ws, "revoked")["manual_connect_required"]
    assert fake.open_count == 1 and not fake.processes[0].received


def prepare_bmc(clients, sut):
    assert (
        mutate_c(
            clients["rd"], "PUT", f"/suts/{sut}/bmc", {"expected_revision": 0, "ipv4": "192.168.234.11"}
        ).status_code
        == 200
    )
    challenge = mutate_c(clients["rd"], "POST", "/trust/challenges", {"sut_id": sut}).json()
    accepted = mutate_c(
        clients["rd"],
        "POST",
        "/trust/accept",
        {
            "challenge_id": challenge["challenge_id"],
            "expected_trust_revision": 0,
            "fingerprint": challenge["fingerprint"],
            "out_of_band_verified": True,
        },
    )
    assert accepted.status_code == 200


def test_client_trust_replacement_revokes_uart_peers_but_not_bmc(live):
    app, clients, _, sut, fake, _ = live
    client_id, _ = onboard(live)
    prepare_bmc(clients, sut)
    one, two = ticket(clients["rd"], sut), ticket(clients["lab"], sut)
    direct = ticket(clients["root"], sut, transport="bmc")
    with (
        connect(clients["rd"], one) as w1,
        connect(clients["lab"], two) as w2,
        connect(clients["root"], direct) as bmc,
    ):
        hello(w1, one)
        message(w1, "connected")
        hello(w2, two)
        message(w2, "connected")
        hello(bmc, direct)
        flow = message(bmc, "auth_required")
        bmc.send_json(
            {
                "type": "authenticate",
                "flow_id": flow["flow_id"],
                "username": "synthetic-bmc",
                "password": fake.password,
            }
        )
        message(bmc, "connected")
        fake.host_key = asyncssh.generate_private_key("ssh-ed25519")
        challenge = mutate_c(clients["rd"], "POST", "/trust/challenges", {"client_id": client_id}).json()
        accepted = mutate_c(
            clients["rd"],
            "POST",
            "/trust/accept",
            {
                "challenge_id": challenge["challenge_id"],
                "expected_trust_revision": 1,
                "fingerprint": challenge["fingerprint"],
                "out_of_band_verified": True,
                "confirmation_id": challenge["confirmation_id"],
            },
        )
        assert accepted.status_code == 200, accepted.text
        assert message(w1, "revoked")["manual_connect_required"]
        assert message(w2, "revoked")["manual_connect_required"]
        bmc.send_json(
            {
                "type": "input",
                "attachment_generation": 1,
                "seq": 1,
                "data": base64.b64encode(b"BMC_STILL_AUTHORIZED").decode(),
            }
        )
        assert message(bmc, "input_ack")["stage"] == "broker_written"
        bmc.send_json({"type": "disconnect"})
    with unit_of_work(app.state.engine) as db:
        rows = list(
            db.scalars(select(ConsoleRevocation).where(ConsoleRevocation.reason == "host_key_changed"))
        )
        assert len(rows) == 2 and all(r.delivered_at for r in rows)


def test_failed_candidate_auth_preserves_active_connection(live):
    app, clients, _, sut, fake, _ = live
    client_id, _ = onboard(live)
    data = ticket(clients["rd"], sut)
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        message(ws, "connected")
        failed = mutate_c(
            clients["root"],
            "POST",
            "/client-validations",
            {"client_id": client_id, "expected_version": 1, "secret": secrets.token_urlsafe(25)},
        )
        assert failed.status_code == 422 and failed.json()["detail"]["code"] == "credential_auth_failed"
        ws.send_json(
            {
                "type": "input",
                "attachment_generation": 1,
                "seq": 1,
                "data": base64.b64encode(b"OLD_CREDENTIAL_RETAINED").decode(),
            }
        )
        assert message(ws, "input_ack")["stage"] == "broker_written"
        ws.send_json({"type": "disconnect"})
    with unit_of_work(app.state.engine) as db:
        assert db.get(ConsoleClient, client_id).metadata_version == 1
        assert db.scalar(select(ConsoleCredential)).replaced_at is None


def test_transient_uart_retry_same_quota_no_input_replay(live):
    app, clients, _, sut, fake, _ = live
    onboard(live)
    fake.failures = ["ssh_unavailable", None]
    data = ticket(clients["rd"], sut)
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        connected = message(ws, "connected")
        assert connected["attachment_generation"] == 2
        assert clients["rd"].get("/api/v1/console/sessions/me").json()["usage"] == 1
        assert fake.attempts == 2 and not fake.processes[0].received
        ws.send_json({"type": "disconnect"})


def test_explicit_disconnect_during_retry_cancels_future_attempt(live):
    app, clients, _, sut, fake, _ = live
    onboard(live)
    fake.failure = "ssh_unavailable"
    data = ticket(clients["rd"], sut)
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        while message(ws, "state")["state"] != "Reconnecting":
            pass
        ws.send_json({"type": "disconnect"})
    time.sleep(1.1)
    assert fake.attempts == 1 and not fake.processes
    assert clients["rd"].get("/api/v1/console/sessions/me").json()["usage"] == 0


def test_unrelated_mutation_preserves_pending_ssh(live):
    from conftest import mutate

    app, clients, _, sut, fake, _ = live
    onboard(live)
    fake.delay = 0.7
    data = ticket(clients["rd"], sut)
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        assert until(lambda: fake.waiting)
        response = mutate(
            clients["root"], "POST", "/api/v1/labs", {"name": "Unrelated synthetic Lab", "location": "Mock"}
        )
        assert response.status_code == 201
        message(ws, "connected")
        assert fake.attempts == 1
        ws.send_json({"type": "disconnect"})


def test_readonly_attachment_requires_manual_reconnect_to_upgrade(live):
    app, clients, _, sut, fake, _ = live
    onboard(live)
    app.state.settings.console_access_policy = "shared_readonly"
    data = ticket(clients["rd"], sut)
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        assert message(ws, "connected")["mode"] == "read"
        app.state.settings.console_access_policy = "all_authenticated"
        assert message(ws, "reconnect_required")["reason_code"] == "readonly_attachment"
        ws.send_json(
            {
                "type": "input",
                "attachment_generation": 1,
                "seq": 1,
                "data": base64.b64encode(b"STILL_READONLY").decode(),
            }
        )
        assert message(ws, "input_rejected")["reason_code"] == "read_only"
        assert not fake.processes[0].received
        ws.send_json({"type": "disconnect"})


def test_bmc_trust_replacement_does_not_close_uart(live):
    app, clients, _, sut, fake, _ = live
    onboard(live)
    prepare_bmc(clients, sut)
    one = ticket(clients["rd"], sut)
    direct = ticket(clients["root"], sut, transport="bmc")
    with connect(clients["rd"], one) as uart, connect(clients["root"], direct) as bmc:
        hello(uart, one)
        message(uart, "connected")
        hello(bmc, direct)
        flow = message(bmc, "auth_required")
        bmc.send_json(
            {
                "type": "authenticate",
                "flow_id": flow["flow_id"],
                "username": "synthetic",
                "password": fake.password,
            }
        )
        message(bmc, "connected")
        fake.host_key = asyncssh.generate_private_key("ssh-ed25519")
        challenge = mutate_c(clients["rd"], "POST", "/trust/challenges", {"sut_id": sut}).json()
        accepted = mutate_c(
            clients["rd"],
            "POST",
            "/trust/accept",
            {
                "challenge_id": challenge["challenge_id"],
                "expected_trust_revision": 1,
                "fingerprint": challenge["fingerprint"],
                "out_of_band_verified": True,
                "confirmation_id": challenge["confirmation_id"],
            },
        )
        assert accepted.status_code == 200, accepted.text
        message(bmc, "revoked")
        uart.send_json(
            {
                "type": "input",
                "attachment_generation": 1,
                "seq": 1,
                "data": base64.b64encode(b"UART_UNCHANGED").decode(),
            }
        )
        message(uart, "input_ack")
        uart.send_json({"type": "disconnect"})


def test_same_rd_multiple_tabs_count_as_one_participant(live):
    app, clients, _, sut, fake, _ = live
    onboard(live)
    first = ticket(clients["rd"], sut, tab="tab-one")
    second = ticket(clients["rd"], sut, tab="tab-two")
    with connect(clients["rd"], first) as one, connect(clients["rd"], second) as two:
        hello(one, first, tab="tab-one")
        message(one, "connected")
        hello(two, second, tab="tab-two")
        message(two, "connected")
        participants = message(two, "participants")
        assert participants["unique_user_count"] == 1
        assert participants["shared_console"] is False
        assert clients["rd"].get("/api/v1/console/sessions/me").json()["usage"] == 2
        one.send_json({"type": "disconnect"})
        two.send_json({"type": "disconnect"})


def test_uart_retry_exhaustion_is_finite_and_releases_quota(live):
    app, clients, _, sut, fake, _ = live
    onboard(live)
    fake.failure = "ssh_timeout"
    data = ticket(clients["rd"], sut)
    with connect(clients["rd"], data) as ws:
        hello(ws, data)
        while True:
            state = message(ws, "state")
            if state["state"] == "Failed":
                assert state["reason_code"] == "ssh_timeout"
                break
    assert fake.attempts == 4 and not fake.processes
    assert clients["rd"].get("/api/v1/console/sessions/me").json()["usage"] == 0


def test_verified_candidate_cannot_commit_other_fields_and_rotates_once(live):
    app, clients, _, sut, fake, _ = live
    client_id, _ = onboard(live)
    validated = mutate_c(
        clients["root"],
        "POST",
        "/client-validations",
        {"client_id": client_id, "expected_version": 1, "secret": fake.password},
    ).json()
    change = {"expected_version": 1, "validation_id": validated["validation_id"]}
    for extra in ({"ipv4": "192.168.234.99"}, {"secret": "unexpected-password"}, {"enabled": False}):
        response = mutate_c(clients["root"], "PATCH", f"/clients/{client_id}", {**change, **extra})
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "validation_payload_mismatch"
    response = mutate_c(clients["root"], "PATCH", f"/clients/{client_id}", change)
    assert response.status_code == 200, response.text
    assert mutate_c(clients["root"], "PATCH", f"/clients/{client_id}", change).status_code == 409
    with unit_of_work(app.state.engine) as db:
        client = db.get(ConsoleClient, client_id)
        assert client.metadata_version == 2 and client.ipv4 == "192.168.234.10" and client.enabled
        credentials = list(db.scalars(select(ConsoleCredential).order_by(ConsoleCredential.generation)))
        assert len(credentials) == 2
        assert credentials[0].replaced_at and credentials[1].generation == 2
        assert client.active_credential_id == credentials[1].id


def test_fence_ack_serializes_against_inflight_terminal_input(live):
    app, clients, _, sut, fake, server = live
    onboard(live)

    async def race():
        args = {
            "session_id": "input-race",
            "generation": 1,
            "user_id": 99,
            "target": {
                "host": "192.168.234.11",
                "port": 22,
                "transport": "uart",
                "tmux_session": "existing",
                "public_key": fake.public,
            },
            "credential": {"method": "password", "username": "mock", "secret": fake.password},
            "mode": "write",
            "cols": 80,
            "rows": 24,
            "lease_until": time.time() + 2,
        }
        await server.executor.dispatch("open", args)
        entered, finish = asyncio.Event(), asyncio.Event()

        async def drain():
            entered.set()
            await finish.wait()

        fake.processes[-1].drain = drain
        data = {
            "session_id": "input-race",
            "generation": 1,
            "seq": 1,
            "data": base64.b64encode(b"PRE_FENCE").decode(),
        }
        writing = asyncio.create_task(server.executor.dispatch("input", data))
        await entered.wait()
        fencing = asyncio.create_task(
            server.executor.dispatch("fence", {"session_id": "input-race", "generation": 1})
        )
        await asyncio.sleep(0.05)
        assert not fencing.done()  # no delivery ACK while old input still in flight
        finish.set()
        assert (await writing)["stage"] == "broker_written"
        assert (await fencing)["fenced"]
        with pytest.raises(BrokerError) as error:
            await server.executor.dispatch("input", {**data, "seq": 2})
        assert error.value.code == "session_fenced"
        assert fake.processes[-1].received == [b"PRE_FENCE"]
        await server.executor.dispatch("close", {"session_id": "input-race", "generation": 1})

    asyncio.run_coroutine_threadsafe(race(), server.executor.watchdog.get_loop()).result(timeout=3)


def test_new_live_session_invalidates_mapping_confirmation_and_preserves_links(live):
    app, clients, _, sut, fake, _ = live
    onboard(live)
    first = ticket(clients["rd"], sut)
    with connect(clients["rd"], first) as one:
        hello(one, first)
        message(one, "connected")
        change = {"expected_revision": 1, "clear": True}
        preview = mutate_c(clients["rd"], "POST", f"/suts/{sut}/uart/preview", change).json()
        second = ticket(clients["lab"], sut)
        with connect(clients["lab"], second) as two:
            hello(two, second)
            message(two, "connected")
            response = mutate_c(
                clients["rd"],
                "PUT",
                f"/suts/{sut}/uart",
                {**change, "confirmation_id": preview["confirmation_id"]},
            )
            assert response.status_code == 409
            for ws in (one, two):
                ws.send_json(
                    {
                        "type": "input",
                        "attachment_generation": 1,
                        "seq": 1,
                        "data": base64.b64encode(b"STILL_AUTHORIZED").decode(),
                    }
                )
                message(ws, "input_ack")
                ws.send_json({"type": "disconnect"})


def test_participant_pump_does_not_starve_loop_on_competing_sqlite_writer(live):
    """A threaded login owns BEGIN IMMEDIATE while the Console pump refreshes.

    The writer can commit only after the ASGI loop resumes the route. Acquiring
    another write reservation on that same loop must not block its completion.
    """
    app, clients, _, sut, _, _ = live
    onboard(live)
    data = ticket(clients["root"], sut)
    acquired, release = threading.Event(), threading.Event()

    def writer():
        with unit_of_work(app.state.engine, write=True):
            acquired.set()
            assert release.wait(8), "test writer was not released"

    with connect(clients["root"], data) as ws:
        hello(ws, data)
        message(ws, "connected")

        async def route_completion():
            while not acquired.is_set():
                await asyncio.sleep(0.005)
            app.state.console_runtime.active[data["session_id"]].last_db_refresh = 0
            started = time.monotonic()
            await asyncio.sleep(0.2)
            release.set()  # Represents the route/dependency being able to commit.
            return time.monotonic() - started

        future = clients["root"].portal.start_task_soon(route_completion)
        thread = threading.Thread(target=writer)
        thread.start()
        try:
            elapsed = future.result(timeout=7)
            assert elapsed < 1, f"ASGI loop blocked by competing SQLite writer for {elapsed:.2f}s"
            peer = ticket(clients["rd"], sut, tab="r1-peer")
            with connect(clients["rd"], peer) as viewer:
                hello(viewer, peer, tab="r1-peer")
                message(viewer, "connected")
                counts = []
                for _ in range(3):
                    counts.append(message(ws, "participants")["unique_user_count"])
                    if counts[-1] == 2:
                        break
                assert counts[-1] == 2
                viewer.send_json({"type": "disconnect"})
            ws.send_json({"type": "disconnect"})
        finally:
            release.set()
            thread.join(timeout=3)
            assert not thread.is_alive()


def test_participant_snapshot_database_failure_closes_live_socket(live, monkeypatch):
    from app.services.console.websocket import TerminalLink
    from sqlalchemy.exc import OperationalError

    app, clients, _, sut, _, _ = live
    onboard(live)
    failed = threading.Event()
    original = TerminalLink.participant_snapshot

    def snapshot(self, *args):
        if failed.is_set():
            raise OperationalError("synthetic unavailable database", (), Exception("synthetic"))
        return original(self, *args)

    monkeypatch.setattr(TerminalLink, "participant_snapshot", snapshot)
    data = ticket(clients["root"], sut)
    with connect(clients["root"], data) as ws:
        hello(ws, data)
        message(ws, "connected")
        failed.set()
        assert message(ws, "revoked")["reason_code"] == "session_revoked"
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 1008
    assert until(lambda: clients["root"].get("/api/v1/console/sessions/me").json()["usage"] == 0)
