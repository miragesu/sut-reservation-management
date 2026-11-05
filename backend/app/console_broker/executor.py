"""Broker operation allowlist, independent leases/fences and bounded terminal RAM."""

import asyncio
import base64
from dataclasses import asdict, dataclass, field
import hashlib
import hmac
import json
import time

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from app.console_broker.ipc import BrokerError
from app.console_broker.ssh import SSHTransport
from app.services.console.crypto import Envelope, SecretUnavailable


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    session_id: str = Field(min_length=1, max_length=64)
    generation: StrictInt = Field(ge=1)


@dataclass(repr=False)
class Live:
    generation: int
    user_id: int
    connection: object
    process: object
    lease_until: float
    mode: str
    readonly_attachment: bool = False
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=128))
    gate: asyncio.Lock = field(default_factory=asyncio.Lock)
    fenced: bool = False
    last_seq: int = 0
    error: str | None = None
    task: object = None
    tokens: float = 65536
    token_time: float = field(default_factory=time.monotonic)


class Executor:
    def __init__(self, cipher, *, transport=None):
        self.cipher = cipher
        self.transport = transport or SSHTransport()
        self.sessions = {}
        self.pending = {}
        self.tombstones = {}
        self.global_auth = asyncio.Semaphore(16)
        self.user_auth = {}
        self.watchdog = None

    async def start(self):
        self.watchdog = asyncio.create_task(self.expire())

    async def stop(self):
        if self.watchdog:
            self.watchdog.cancel()
            await asyncio.gather(self.watchdog, return_exceptions=True)
        pending = [item["task"] for item in self.pending.values()]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for identity in list(self.sessions):
            await self.close(identity)

    async def expire(self):
        while True:
            await asyncio.sleep(0.1)
            for identity, item in list(self.pending.items()):
                if item["lease_until"] <= time.time():
                    item["task"].cancel()
            for identity, live in list(self.sessions.items()):
                if live.lease_until <= time.time():
                    live.error = "session_expired"
                    await self.close(identity)

    @staticmethod
    def shape(arguments, allowed, required=()):
        if set(arguments) - set(allowed) or any(key not in arguments for key in required):
            raise BrokerError("ipc_invalid")

    def credential(self, args):
        if "envelope" in args:
            envelope_args = dict(args["envelope"])
            for key in ("ciphertext", "nonce", "wrapped_data_key", "wrap_nonce"):
                envelope_args[key] = base64.b64decode(envelope_args[key], validate=True)
            aad = self.cipher.aad(*args["aad"])
            bundle = json.loads(self.cipher.decrypt(Envelope(**envelope_args), aad))
            return {"username": args["username"], "method": args["method"], **bundle}
        return dict(args["credential"])

    async def dispatch(self, op, args):
        try:
            if op == "status":
                self.shape(args, {"login_key_digest"})
                supplied = args.get("login_key_digest")
                if supplied and any(
                    hmac.compare_digest(hashlib.sha256(k).hexdigest(), supplied)
                    for k in self.cipher._keys.values()
                ):
                    raise BrokerError("keyring_unavailable")
                return {"protocol": "console-broker.v1", "sessions": len(self.sessions)}
            if op == "verify_credential":
                self.shape(args, {"envelope", "aad"}, {"envelope", "aad"})
                value = dict(args["envelope"])
                for key in ("ciphertext", "nonce", "wrapped_data_key", "wrap_nonce"):
                    value[key] = base64.b64decode(value[key], validate=True)
                self.cipher.decrypt(Envelope(**value), self.cipher.aad(*args["aad"]))
                return {"verified": True}  # Never return decrypted credentials.
            if op == "probe_key":
                self.shape(args, {"host", "port", "transport"}, {"host", "port", "transport"})
                return await self.transport.probe(**args)
            if op == "validate_client":
                self.shape(
                    args,
                    {
                        "target",
                        "user_id",
                        "credential",
                        "envelope",
                        "aad",
                        "username",
                        "method",
                        "client_security_id",
                        "credential_security_id",
                        "generation",
                    },
                    {"target", "user_id"},
                )
                return await self.validate_client(args)
            if op == "open":
                self.shape(
                    args,
                    {
                        "session_id",
                        "generation",
                        "user_id",
                        "target",
                        "lease_until",
                        "mode",
                        "cols",
                        "rows",
                        "credential",
                        "envelope",
                        "aad",
                        "username",
                        "method",
                    },
                    {"session_id", "generation", "user_id", "target", "lease_until", "mode", "cols", "rows"},
                )
                return await self.open(args)
            if op == "fence_all":
                self.shape(args, set())
                result = []
                for identity, live in list(self.sessions.items()):
                    async with live.gate:
                        live.fenced = True
                    result.append({"session_id": identity, "generation": live.generation})
                return {"fenced": True, "sessions": result}
            if op in ("fence", "close", "read", "lease_refresh", "input", "resize"):
                allowed = {"session_id", "generation"}
                if op == "lease_refresh":
                    allowed |= {"lease_until", "mode", "resume"}
                if op == "input":
                    allowed |= {"data", "seq"}
                if op == "resize":
                    allowed |= {"cols", "rows"}
                self.shape(args, allowed, {"session_id", "generation"})
                identity = Request.model_validate({k: args[k] for k in ("session_id", "generation")})
                pending = self.pending.get(identity.session_id)
                if pending and pending["generation"] != identity.generation:
                    raise BrokerError("session_stale")
                if op in ("fence", "close"):
                    self.tombstones[(identity.session_id, identity.generation)] = time.time() + 15
                    if pending:
                        pending["task"].cancel()
                        await asyncio.gather(pending["task"], return_exceptions=True)
                if pending and op == "lease_refresh":
                    self.lease(args["lease_until"])
                    pending["lease_until"] = args["lease_until"]
                    return {"refreshed": True, "pending": True}
                live = self.sessions.get(identity.session_id)
                if live and live.generation != identity.generation:
                    raise BrokerError("session_stale")
                if op in ("close", "fence") and live is None:
                    return {
                        "session_id": identity.session_id,
                        "generation": identity.generation,
                        "fenced": True,
                        "absent": True,
                    }
                if not live:
                    raise BrokerError("session_stale")
                async with live.gate:
                    if op == "fence":
                        live.fenced = True
                        return {
                            "session_id": identity.session_id,
                            "generation": identity.generation,
                            "fenced": True,
                        }
                    if op == "close":
                        live.fenced = True
                    elif op == "lease_refresh":
                        self.lease(args["lease_until"])
                        if args["mode"] not in ("read", "write"):
                            raise BrokerError("ipc_invalid")
                        live.lease_until = args["lease_until"]
                        live.mode = "read" if live.readonly_attachment else args["mode"]
                        if args.get("resume"):
                            live.fenced = False
                        return {
                            "refreshed": True,
                            "mode": live.mode,
                            "reconnect_required": live.readonly_attachment and args["mode"] == "write",
                        }
                    elif op == "read":
                        self.active(live)
                        chunks = []
                        for _ in range(4):
                            if live.queue.empty():
                                break
                            chunks.append(live.queue.get_nowait())
                        return {"data": base64.b64encode(b"".join(chunks)).decode(), "ended": live.error}
                    elif op == "input":
                        self.active(live, write=True)
                        data = base64.b64decode(args["data"], validate=True)
                        if not 0 < len(data) <= 8192 or type(args["seq"]) is not int:
                            raise BrokerError("input_invalid")
                        if args["seq"] != live.last_seq + 1:
                            raise BrokerError("input_sequence")
                        now = time.monotonic()
                        live.tokens = min(65536, live.tokens + (now - live.token_time) * 32768)
                        live.token_time = now
                        if len(data) > live.tokens:
                            raise BrokerError("rate_limited")
                        live.tokens -= len(data)
                        live.last_seq = args["seq"]
                        live.process.stdin.write(data)
                        async with asyncio.timeout(2):
                            await live.process.stdin.drain()
                        return {"seq": args["seq"], "stage": "broker_written"}
                    elif op == "resize":
                        self.active(live)
                        self.size(args["cols"], args["rows"])
                        live.process.change_terminal_size(args["cols"], args["rows"])
                        return {"resized": True}
                await self.close(identity.session_id)
                return {
                    "session_id": identity.session_id,
                    "generation": identity.generation,
                    "fenced": True,
                    "closed": True,
                }
            raise BrokerError("unsupported_operation")
        except BrokerError:
            raise
        except SecretUnavailable:
            raise BrokerError("keyring_unavailable") from None
        except (ValueError, TypeError, KeyError, ValidationError):
            raise BrokerError("ipc_invalid") from None
        except TimeoutError:
            raise BrokerError("ssh_timeout") from None
        except Exception:
            raise BrokerError("ssh_unavailable") from None

    @staticmethod
    def lease(until):
        if not isinstance(until, (float, int)) or not time.time() < until <= time.time() + 2.1:
            raise BrokerError("session_expired")

    @staticmethod
    def size(cols, rows):
        if type(cols) is not int or type(rows) is not int or not 2 <= cols <= 500 or not 1 <= rows <= 200:
            raise BrokerError("input_invalid")

    @staticmethod
    def active(live, write=False):
        if live.fenced:
            raise BrokerError("session_fenced")
        if live.lease_until <= time.time():
            raise BrokerError("session_expired")
        if write and live.mode != "write":
            raise BrokerError("read_only")

    async def authenticated(self, args, action):
        user = args["user_id"]
        semaphore = self.user_auth.setdefault(user, asyncio.Semaphore(2))
        if self.global_auth.locked() or semaphore.locked():
            raise BrokerError("resource_limit")
        async with self.global_auth, semaphore:
            return await action()

    async def validate_client(self, args):
        async def action():
            connection = None
            credential = self.credential(args)
            # Envelope candidate is created in Broker RAM before the secret is discarded.
            aad = self.cipher.aad(
                args["client_security_id"],
                args["credential_security_id"],
                credential["method"],
                args["generation"],
            )
            bundle = {k: credential[k] for k in ("secret", "passphrase") if k in credential}
            envelope = self.cipher.encrypt(json.dumps(bundle, separators=(",", ":")).encode(), aad)
            bundle.clear()
            try:
                async with asyncio.timeout(10):
                    connection = await self.transport.authenticate(args["target"], credential)
                result = asdict(envelope)
                for key in ("ciphertext", "nonce", "wrapped_data_key", "wrap_nonce"):
                    result[key] = base64.b64encode(result[key]).decode()
                return {"envelope": result, "validated": True}
            finally:
                credential.clear()
                if connection:
                    connection.close()
                    await connection.wait_closed()

        return await self.authenticated(args, action)

    async def open(self, args):
        Request.model_validate({k: args[k] for k in ("session_id", "generation")})
        self.lease(args["lease_until"])
        self.size(args["cols"], args["rows"])
        now = time.time()
        self.tombstones = {key: expiry for key, expiry in self.tombstones.items() if expiry > now}
        identity = args["session_id"]
        if (
            identity in self.sessions
            or identity in self.pending
            or len(self.sessions) + len(self.pending) >= 128
            or args["mode"] not in ("read", "write")
            or (identity, args["generation"]) in self.tombstones
        ):
            raise BrokerError("session_stale")
        pending = {
            "task": asyncio.current_task(),
            "generation": args["generation"],
            "lease_until": args["lease_until"],
        }
        self.pending[identity] = pending

        async def action():
            credential = self.credential(args)
            connection, process, initial = await self.transport.open(
                args["target"],
                credential,
                cols=args["cols"],
                rows=args["rows"],
                readonly=args["mode"] == "read",
            )
            if pending["lease_until"] <= time.time():
                connection.close()
                raise BrokerError("session_expired")
            live = Live(
                args["generation"], args["user_id"], connection, process, pending["lease_until"], args["mode"]
            )
            live.readonly_attachment = args["target"]["transport"] == "uart" and args["mode"] == "read"
            self.sessions[identity] = live
            if initial:
                live.queue.put_nowait(initial)
            live.task = asyncio.create_task(self.read_output(live))
            return {"connected": True, "generation": live.generation}

        try:
            return await self.authenticated(args, action)
        finally:
            if self.pending.get(identity) is pending:
                self.pending.pop(identity, None)

    async def read_output(self, live):
        try:
            while True:
                data = await live.process.stdout.read(8192)
                if not data:
                    await live.process.wait_closed()
                    live.error = (
                        "tmux_not_found"
                        if live.process.exit_status == 44
                        else ("remote_closed" if live.process.exit_status == 0 else "ssh_unavailable")
                    )
                    break
                await asyncio.wait_for(live.queue.put(data), timeout=2)
        except TimeoutError:
            live.error = "output_backpressure"
            live.connection.close()
        except Exception:
            live.error = "ssh_unavailable"
        # Do not log/output/store any exception or terminal bytes.

    async def close(self, identity):
        live = self.sessions.pop(identity, None)
        if not live:
            return
        if live.task:
            live.task.cancel()
            await asyncio.gather(live.task, return_exceptions=True)
        live.connection.close()  # no remote kill command/signal or tmux server action
        try:
            async with asyncio.timeout(2):
                await live.connection.wait_closed()
        except (TimeoutError, Exception):
            pass
        while not live.queue.empty():
            live.queue.get_nowait()
