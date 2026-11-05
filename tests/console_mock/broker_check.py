"""Actual UID10001 Gateway -> UID10002 Broker -> disposable OpenSSH."""

import asyncio
import base64
import json
import os
from pathlib import Path
import sys
import time

from app.console_broker.ipc import BrokerClient, BrokerError, private_key_file


async def main():
    fixture = json.load(sys.stdin)
    assert os.getuid() == 10001
    assert not Path("/keys/keyring").exists()
    assert Path("/db/marker").read_bytes().startswith(b"synthetic")
    client = BrokerClient("/ipc/broker.sock", private_key_file("/ipc/auth"))
    await client.call("status")
    observed = await client.call("probe_key", host=fixture["host"], port=22, transport="uart")
    # Compare independently provisioned mock host key before credentials are sent.
    import asyncssh

    assert observed["fingerprint"] == asyncssh.import_public_key(fixture["public_key"]).get_fingerprint(
        "sha256"
    )
    target = {
        "host": fixture["host"],
        "port": 22,
        "transport": "uart",
        "public_key": observed["public_key"],
        "tmux_session": "existing",
    }
    verified = await client.call(
        "validate_client",
        target=target,
        user_id=1,
        client_security_id="synthetic-client",
        credential_security_id="synthetic-credential",
        generation=1,
        credential={"method": "password", "username": fixture["username"], "secret": fixture["password"]},
    )
    assert verified["validated"]
    args = {
        "session_id": "custody",
        "generation": 1,
        "user_id": 1,
        "target": target,
        "envelope": verified["envelope"],
        "aad": ["synthetic-client", "synthetic-credential", "password", 1],
        "username": fixture["username"],
        "method": "password",
        "lease_until": time.time() + 2,
        "mode": "write",
        "cols": 80,
        "rows": 24,
    }
    opened = await client.call("open", **args)
    assert opened["connected"]
    await client.call(
        "input", session_id="custody", generation=1, seq=1, data=base64.b64encode(b"CUSTODY_PROOF").decode()
    )
    seen = b""
    for _ in range(10):
        await client.call(
            "lease_refresh",
            session_id="custody",
            generation=1,
            lease_until=time.time() + 2,
            mode="write",
            resume=True,
        )
        output = await client.call("read", session_id="custody", generation=1)
        seen += base64.b64decode(output["data"])
        if b"CUSTODY_PROOF" in seen:
            break
        await asyncio.sleep(0.1)
    assert b"CUSTODY_PROOF" in seen
    ack = await client.call("fence", session_id="custody", generation=1)
    assert ack["fenced"] and ack["generation"] == 1
    try:
        await client.call(
            "input", session_id="custody", generation=1, seq=2, data=base64.b64encode(b"FORBIDDEN").decode()
        )
    except BrokerError as error:
        assert error.code == "session_fenced"
    else:
        raise AssertionError("fenced input was accepted")
    await client.call("close", session_id="custody", generation=1)
    for op in ("exec", "forward", "sftp"):
        try:
            await client.call(op)
        except BrokerError as error:
            assert error.code == "unsupported_operation"
        else:
            raise AssertionError("generic operation exposed")
    print(
        "PASS: actual UID10001 -> authenticated private IPC -> UID10002 Broker -> OpenSSH/tmux; encrypted credential, terminal IO, acknowledged fence"
    )
    print("PASS: Gateway has database-only mount and no KEK; generic exec/forward/SFTP absent")


asyncio.run(main())
