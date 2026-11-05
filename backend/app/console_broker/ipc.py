"""Bounded authenticated Unix RPC. Never log frames, secrets or remote exceptions."""

import asyncio
from collections import OrderedDict
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import stat
import struct
import time

MAX_FRAME = 196608  # private admin/key-envelope messages; public WS has smaller limits


class BrokerError(Exception):
    CODES = frozenset(
        {
            "broker_unavailable",
            "broker_restarted",
            "ipc_denied",
            "ipc_invalid",
            "ipc_oversize",
            "target_denied",
            "host_key_unknown",
            "host_key_changed",
            "credential_auth_failed",
            "credential_invalid",
            "ssh_timeout",
            "ssh_unavailable",
            "tmux_not_found",
            "session_stale",
            "session_fenced",
            "session_expired",
            "read_only",
            "input_invalid",
            "input_sequence",
            "output_backpressure",
            "rate_limited",
            "resource_limit",
            "keyring_unavailable",
            "unsupported_operation",
        }
    )

    def __init__(self, code):
        self.code = code if code in self.CODES else "broker_unavailable"
        super().__init__(self.code)


def private_key_file(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as file:
            mode = os.fstat(file.fileno())
            if not stat.S_ISREG(mode.st_mode) or stat.S_IMODE(mode.st_mode) & 0o027:
                raise BrokerError("ipc_denied")
            value = file.read(33)
        if len(value) != 32:
            raise BrokerError("ipc_denied")
        return value
    except OSError:
        raise BrokerError("ipc_denied") from None


def body_mac(secret, data):
    return hmac.new(
        secret,
        json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
        hashlib.sha256,
    ).hexdigest()


def sign(secret, data):
    return {**data, "mac": body_mac(secret, data)}


def verify(secret, value):
    if not isinstance(value, dict) or not isinstance(value.get("mac"), str):
        raise BrokerError("ipc_denied")
    body = {key: item for key, item in value.items() if key != "mac"}
    try:
        if not hmac.compare_digest(body_mac(secret, body), value["mac"]):
            raise BrokerError("ipc_denied")
    except (ValueError, TypeError):
        raise BrokerError("ipc_invalid") from None
    return body


async def receive(reader):
    size = struct.unpack("!I", await reader.readexactly(4))[0]
    if not 0 < size <= MAX_FRAME:
        raise BrokerError("ipc_oversize")
    try:
        return json.loads(await reader.readexactly(size))
    except (ValueError, UnicodeError):
        raise BrokerError("ipc_invalid") from None


async def send(writer, value):
    encoded = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > MAX_FRAME:
        raise BrokerError("ipc_oversize")
    writer.write(struct.pack("!I", len(encoded)) + encoded)
    await writer.drain()


def peer_uid(writer):
    try:
        data = writer.get_extra_info("socket").getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        return struct.unpack("3i", data)[1]
    except (AttributeError, OSError):
        raise BrokerError("ipc_denied") from None


class BrokerClient:
    def __init__(self, path, secret, *, expected_uid=10002):
        self.path, self.secret, self.expected_uid = str(path), secret, expected_uid
        self.boot_id = None

    async def call(self, operation, **arguments):
        if operation != "status" and self.boot_id is None:
            await self.call("status")
        nonce = secrets.token_hex(16)
        request = {
            "v": 1,
            "boot": self.boot_id,
            "nonce": nonce,
            "deadline": time.time() + 5,
            "op": operation,
            "args": arguments,
        }
        writer = None
        try:
            async with asyncio.timeout(12):
                reader, writer = await asyncio.open_unix_connection(self.path, limit=MAX_FRAME)
                if peer_uid(writer) != self.expected_uid:
                    raise BrokerError("ipc_denied")
                await send(writer, sign(self.secret, request))
                response = verify(self.secret, await receive(reader))
                if response.get("nonce") != nonce or response.get("v") != 1:
                    raise BrokerError("ipc_denied")
                if self.boot_id is not None and response.get("boot") != self.boot_id:
                    raise BrokerError("broker_restarted")
                if response.get("error"):
                    raise BrokerError(response["error"])
                if not isinstance(response.get("result"), dict):
                    raise BrokerError("ipc_invalid")
                self.boot_id = response["boot"]
                return response["result"]
        except (OSError, TimeoutError, asyncio.IncompleteReadError, ConnectionError):
            raise BrokerError("broker_unavailable") from None
        finally:
            if writer:
                writer.close()
                try:
                    await writer.wait_closed()
                except (OSError, ConnectionError):
                    pass


class BrokerServer:
    def __init__(self, path, secret, executor, *, allowed_uid=10001):
        self.path, self.secret, self.executor = Path(path), secret, executor
        self.allowed_uid = allowed_uid
        self.boot_id = secrets.token_hex(16)
        self.seen = OrderedDict()
        self.server = None
        self.connections = asyncio.Semaphore(32)

    async def start(self):
        # Operator owns this private directory; do not chmod arbitrary existing dirs.
        parent = self.path.parent.stat()
        if (
            not self.path.parent.is_dir()
            or self.path.parent.is_symlink()
            or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) & 0o027
            or self.path.is_symlink()
        ):
            raise BrokerError("ipc_denied")
        if self.path.exists():
            info = self.path.stat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
                raise BrokerError("ipc_denied")
            try:
                async with asyncio.timeout(0.2):
                    _, active = await asyncio.open_unix_connection(str(self.path))
                    active.close()
                    await active.wait_closed()
                raise BrokerError("ipc_denied")
            except ConnectionRefusedError:
                self.path.unlink()
        self.server = await asyncio.start_unix_server(self.handle, path=str(self.path), limit=MAX_FRAME)
        os.chmod(self.path, 0o660)
        await self.executor.start()
        return self

    async def handle(self, reader, writer):
        nonce = ""
        try:
            if self.connections.locked():
                raise BrokerError("resource_limit")
            async with self.connections:
                async with asyncio.timeout(3):
                    if peer_uid(writer) != self.allowed_uid:
                        raise BrokerError("ipc_denied")
                    body = verify(self.secret, await receive(reader))
                    nonce = body.get("nonce", "")
                    now = time.time()
                    if (
                        set(body) != {"v", "boot", "nonce", "deadline", "op", "args"}
                        or body["v"] != 1
                        or not isinstance(nonce, str)
                        or len(nonce) != 32
                        or not isinstance(body["deadline"], (float, int))
                        or not now <= body["deadline"] <= now + 6
                        or nonce in self.seen
                        or not isinstance(body["args"], dict)
                    ):
                        raise BrokerError("ipc_denied")
                    if body["op"] != "status" and body["boot"] != self.boot_id:
                        raise BrokerError("broker_restarted")
                    while self.seen and next(iter(self.seen.values())) < now - 30:
                        self.seen.popitem(last=False)
                    if len(self.seen) >= 4096:
                        raise BrokerError("resource_limit")
                    self.seen[nonce] = now
                result = await self.executor.dispatch(body["op"], body["args"])
                await send(
                    writer,
                    sign(self.secret, {"v": 1, "boot": self.boot_id, "nonce": nonce, "result": result}),
                )
        except BrokerError as error:
            try:
                await send(
                    writer,
                    sign(self.secret, {"v": 1, "boot": self.boot_id, "nonce": nonce, "error": error.code}),
                )
            except (OSError, ConnectionError):
                pass
        except (OSError, ValueError, TypeError, asyncio.IncompleteReadError, TimeoutError):
            pass  # bounded malformed client; never print frame/exception
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, ConnectionError):
                pass

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        await self.executor.stop()
        self.path.unlink(missing_ok=True)
