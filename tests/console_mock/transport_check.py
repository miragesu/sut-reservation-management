"""Real SSHTransport tests, executed as Broker UID against mock OpenSSH only."""

import asyncio
import json
import sys
import time

import asyncssh

from app.console_broker.ipc import BrokerError
from app.console_broker.ssh import SSHTransport


async def main():
    fixture = json.load(sys.stdin)
    host = fixture.pop("host")
    transport = SSHTransport()
    target = {
        "host": host,
        "port": 22,
        "transport": "uart",
        "public_key": fixture["public_key"],
        "tmux_session": "existing",
    }

    def credential(method="password", wrong=False):
        return {
            "username": fixture["username"],
            "method": method,
            "secret": ("deliberately-incorrect" if wrong else fixture[method]),
            **({"passphrase": fixture["passphrase"]} if method == "private_key" else {}),
        }

    async def denied(code, action):
        try:
            await action
        except BrokerError as error:
            assert error.code == code, (error.code, code)
        else:
            raise AssertionError("expected sanitized failure")

    async def contains(process, marker):
        data = b""
        try:
            async with asyncio.timeout(5):
                while marker not in data:
                    chunk = await process.stdout.read(8192)
                    if not chunk:
                        raise AssertionError("synthetic peer closed")
                    data = (data + chunk)[-65536:]
        except TimeoutError:
            # Fixture output contains only synthetic tokens, never credentials.
            raise AssertionError(repr(data[-1000:])) from None
        return data

    observed = await transport.probe(host, 22, "uart")
    expected = asyncssh.import_public_key(fixture["public_key"])
    assert observed["fingerprint"] == expected.get_fingerprint("sha256")
    print("PASS: unauthenticated host-key discovery; independent fingerprint matches", flush=True)
    target["public_key"] = observed["public_key"]
    await denied(
        "host_key_changed",
        transport.authenticate(
            {
                **target,
                "public_key": asyncssh.generate_private_key("ssh-ed25519")
                .export_public_key()
                .decode()
                .strip(),
            },
            credential(),
        ),
    )
    await denied("host_key_unknown", transport.authenticate({**target, "public_key": None}, credential()))
    await denied("credential_auth_failed", transport.authenticate(target, credential(wrong=True)))
    print("PASS: unknown/wrong host key and invalid credentials rejected", flush=True)
    for method in ("password", "private_key"):
        connection = await transport.authenticate(target, credential(method))
        connection.close()
        await connection.wait_closed()
    print("PASS: password and encrypted private-key authentication", flush=True)
    c1, p1, _ = await transport.open(target, credential(), cols=100, rows=30)
    c2, p2, _ = await transport.open(target, credential("private_key"), cols=100, rows=30)
    try:
        p1.stdin.write(b"FIRST_WRITER")
        await contains(p2, b"FIRST_WRITER")
        p2.stdin.write(b"SECOND_WRITER")
        await contains(p1, b"SECOND_WRITER")
        print("PASS: concurrent UART readers and writers", flush=True)
        # Native detach must preserve SSH and land in the fixed account shell.
        await asyncio.sleep(0.2)
        p1.stdin.write(b"\x02")
        await asyncio.sleep(0.15)
        p1.stdin.write(b"d")
        await asyncio.sleep(0.3)
        p1.stdin.write(b"printf 'SHELL_READY:%s\\n' \"$TERM\"\r")
        await contains(p1, b"SHELL_READY:xterm-256color")
        p1.change_terminal_size(111, 37)
        await asyncio.sleep(0.2)
        p1.stdin.write(b"stty size\r")
        await contains(p1, b"37 111")
        print("PASS: native detach to ordinary shell, TERM and PTY resize", flush=True)
        c1.close()
        await c1.wait_closed()
        p2.stdin.write(b"SURVIVING_WRITER")
        await contains(p2, b"SURVIVING_WRITER")
        print("PASS: disconnect closes only its SSH attachment", flush=True)
    finally:
        c1.close()
        c2.close()
        await c1.wait_closed()
        await c2.wait_closed()
    await denied(
        "tmux_not_found",
        transport.open({**target, "tmux_session": "missing"}, credential(), cols=80, rows=24),
    )
    print("PASS: missing existing session fails without shell", flush=True)
    bmc = {k: v for k, v in target.items() if k != "tmux_session"}
    bmc["transport"] = "bmc"
    connection, process, _ = await transport.open(bmc, credential(), cols=80, rows=24)
    process.stdin.write(b"printf BMC_SYNTHETIC_OK\\n\r")
    await contains(process, b"BMC_SYNTHETIC_OK")
    connection.close()
    await connection.wait_closed()
    await denied("target_denied", transport.authenticate({**bmc, "host": "127.0.0.1"}, credential()))
    await denied("target_denied", transport.authenticate({**bmc, "port": 2222}, credential()))
    print("PASS: direct BMC shell; sensitive destinations and non-22 BMC port denied", flush=True)
    # Blackhole is a synthetic listener in the mock container, never a real endpoint.
    started = time.monotonic()
    await denied("ssh_timeout", transport.open({**target, "port": 2224}, credential(), cols=80, rows=24))
    assert 9.5 <= time.monotonic() - started < 12
    print("PASS: real SSH establishment bounded at 10 seconds", flush=True)


asyncio.run(main())
