"""Versioned authenticated terminal data plane. Buffers are bounded RAM only."""

import asyncio
import anyio
import base64
from datetime import timedelta
import hashlib
import json
import time

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.console_broker.ipc import BrokerError
from app.core.database import clock_now
from app.models.console import ConsoleAuthFlow, ConsoleSession
from app.models.domain import LoginSession, User
from app.schemas.console_live import (
    AuthFrame,
    DisconnectFrame,
    Hello,
    InputFrame,
    KeyFrame,
    PasteBegin,
    PasteChunk,
    ResizeFrame,
)
from app.services.console import foundation as f

KEYS = {"esc": b"\x1b", "tab": b"\t", "ctrl_c": b"\x03", "ctrl_d": b"\x04", "ctrl_z": b"\x1a"}
FRAMES = {
    "authenticate": AuthFrame,
    "disconnect": DisconnectFrame,
    "input": InputFrame,
    "send_key": KeyFrame,
    "resize": ResizeFrame,
    "paste_begin": PasteBegin,
    "paste_chunk": PasteChunk,
}


class TerminalLink:
    def __init__(self, runtime, websocket, identity):
        self.rt, self.ws, self.identity = runtime, websocket, identity
        self.login_digest = None
        self.generation = 0
        self.phase = "connecting"
        self.mode = "read"
        self.transport = None
        self.revoked = None
        self.operation = None
        self.pump_task = None
        self.send_lock = asyncio.Lock()
        self.attached = False
        self.handshake_slot = False
        self.last_client_seq = 0
        self.broker_seq = 0
        self.paste = None
        self.last_resize = 0
        self.flow_id = None
        self.reconnect_notice = False
        self.retry_count = 0
        self.last_db_refresh = 0

    async def emit(self, kind, **data):
        async with self.send_lock:
            async with asyncio.timeout(2):
                await self.ws.send_json({"type": kind, **data})

    async def state(self, name, reason=None, retryable=False):
        await self.emit(
            "state",
            state=name,
            reason_code=reason,
            retryable=retryable,
            effective_mode=self.mode,
            attachment_generation=self.generation,
        )

    async def serve(self):
        try:
            self.rt.require_ready()
            self.login_digest = self.rt.authenticate(self.ws)
            origin = self.rt.origin(self.ws)
            if "sut-console.v1" not in self.ws.scope.get("subprotocols", []):
                f.fail(403, "console_protocol_invalid")
            if self.rt.handshakes.locked():
                await self.close_socket(1013, "resource_limit")
                return
            await self.rt.handshakes.acquire()
            self.handshake_slot = True
            # No terminal output or participant data before one-use ticket redemption.
            await self.ws.accept(subprotocol="sut-console.v1")
            async with asyncio.timeout(3):
                raw = await self.ws.receive_text()
                if len(raw.encode()) > 16384:
                    raise BrokerError("input_invalid")
                hello = Hello.model_validate_json(raw)
                raw = None
            async with self.rt.gate:
                with self.rt.db(write=True) as db:
                    actor, _ = self.rt.actor(db, self.login_digest)
                    row = f.consume_ticket(
                        db,
                        actor,
                        self.login_digest,
                        self.identity,
                        hello.ticket.get_secret_value(),
                        origin,
                        hello.attachment_generation,
                        self.rt.settings,
                    )
                    if row.instance_id != hello.tab_id:
                        f.fail(403, "console_tab_mismatch")
                    row.state = "connecting"
                    self.generation, self.mode, self.transport = (
                        row.attachment_generation,
                        row.mode,
                        row.transport,
                    )
                    self.rt.proof(db, self.identity, self.login_digest, refresh=True)
                prior = self.rt.active.get(self.identity)
                if prior and not prior.revoked:
                    f.fail(409, "console_attachment_exists")
                self.rt.active[self.identity] = self
                self.attached = True
            self.rt.handshakes.release()
            self.handshake_slot = False
            self.cols, self.rows = hello.cols, hello.rows
            hello = None
            await self.state("Connecting")
            self.pump_task = asyncio.create_task(self.pump())
            if self.transport == "uart":
                self.operation = asyncio.create_task(self.establish())
            else:
                await self.new_flow()
            frame_tokens, byte_tokens, token_time = 128.0, 65536.0, time.monotonic()
            while not self.revoked:
                raw = await self.ws.receive_text()
                now = time.monotonic()
                frame_tokens = min(128, frame_tokens + (now - token_time) * 64)
                byte_tokens = min(65536, byte_tokens + (now - token_time) * 32768)
                token_time = now
                size = len(raw.encode())
                if size > 16384 or frame_tokens < 1 or byte_tokens < size:
                    raise BrokerError("rate_limited")
                frame_tokens -= 1
                byte_tokens -= size
                value = json.loads(raw)
                if not isinstance(value, dict) or value.get("type") not in FRAMES:
                    raise BrokerError("input_invalid")
                frame = FRAMES[value["type"]].model_validate(value)
                value.clear()
                raw = None
                if isinstance(frame, DisconnectFrame):
                    self.revoked = "explicit_disconnect"
                    await self.state("Disconnected", "explicit_disconnect")
                    break
                if isinstance(frame, AuthFrame):
                    if (
                        self.transport != "bmc"
                        or self.phase != "auth_required"
                        or self.operation
                        and not self.operation.done()
                    ):
                        raise BrokerError("input_invalid")
                    credential = {
                        "username": frame.username.get_secret_value(),
                        "secret": frame.password.get_secret_value(),
                        "method": "password",
                    }
                    flow_id = frame.flow_id
                    frame = None
                    self.operation = asyncio.create_task(self.establish(credential, flow_id))
                    continue
                if isinstance(frame, ResizeFrame):
                    self.cols, self.rows = frame.cols, frame.rows
                    if self.phase == "connected" and now - self.last_resize >= 0.1:
                        async with self.rt.gate:
                            with self.rt.db() as db:
                                self.rt.proof(db, self.identity, self.login_digest)
                            await self.rt.broker.call(
                                "resize",
                                session_id=self.identity,
                                generation=self.generation,
                                cols=self.cols,
                                rows=self.rows,
                            )
                        self.last_resize = now
                    continue
                if self.phase != "connected":
                    raise BrokerError("input_invalid")
                if frame.attachment_generation != self.generation:
                    raise BrokerError("session_stale")
                if isinstance(frame, PasteBegin):
                    if self.mode != "write":
                        await self.emit("input_rejected", reason_code="read_only")
                        continue
                    self.paste = {
                        "id": frame.paste_id,
                        "count": frame.byte_count,
                        "hash": frame.sha256,
                        "approved": frame.multiline_approved,
                        "data": bytearray(),
                        "expires": now + 30,
                    }
                    continue
                if isinstance(frame, PasteChunk):
                    if not self.paste or self.paste["id"] != frame.paste_id or self.paste["expires"] <= now:
                        raise BrokerError("input_invalid")
                    self.sequence(frame.seq)
                    chunk = base64.b64decode(frame.data, validate=True)
                    if len(chunk) > 8192 or len(self.paste["data"]) + len(chunk) > self.paste["count"]:
                        raise BrokerError("input_invalid")
                    self.paste["data"].extend(chunk)
                    if not frame.final:
                        continue
                    data = bytes(self.paste["data"])
                    valid = (
                        len(data) == self.paste["count"]
                        and hashlib.sha256(data).hexdigest() == self.paste["hash"]
                    )
                    controls = any(byte < 32 and byte not in (9,) for byte in data)
                    if not valid or b"\x00" in data or controls and not self.paste["approved"]:
                        self.paste = None
                        raise BrokerError("input_invalid")
                    self.paste = None
                    await self.write(data, frame.seq, sequenced=True)
                elif isinstance(frame, InputFrame):
                    data = base64.b64decode(frame.data, validate=True)
                    if not 0 < len(data) <= 8192:
                        raise BrokerError("input_invalid")
                    await self.write(data, frame.seq)
                elif isinstance(frame, KeyFrame):
                    await self.write(KEYS[frame.key], frame.seq)
                frame = None
        except (HTTPException, ValidationError, ValueError, KeyError, TypeError):
            await self.close_socket(1008, "console_protocol_or_authorization_denied")
        except BrokerError as error:
            await self.close_socket(1008, error.code)
        except TimeoutError:
            await self.close_socket(1008, "console_timeout")
        except WebSocketDisconnect:
            pass
        except (OSError, RuntimeError):
            pass
        finally:
            # ASGI/TestClient cancellation must not interrupt logical quota release.
            # Network cleanup remains bounded; unacknowledged rows stay durable.
            with anyio.CancelScope(shield=True):
                try:
                    async with asyncio.timeout(5):
                        await self.cleanup()
                except TimeoutError:
                    pass

    async def cleanup(self):
        if self.handshake_slot:
            self.rt.handshakes.release()
            self.handshake_slot = False
        self.revoked = self.revoked or "browser_disconnected"
        tasks = [
            task for task in (self.operation, self.pump_task) if task and task is not asyncio.current_task()
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.paste = None
        if self.attached:
            async with self.rt.gate:
                with self.rt.db(write=True) as db:
                    row = db.get(ConsoleSession, self.identity)
                    current = row and row.attachment_generation == self.generation
                    if current:
                        f.close_session(db, row, self.revoked)
                    for flow in db.scalars(
                        select(ConsoleAuthFlow).where(
                            ConsoleAuthFlow.session_id == self.identity,
                            ConsoleAuthFlow.attachment_generation == self.generation,
                            ConsoleAuthFlow.closed_at.is_(None),
                        )
                    ):
                        flow.closed_at = clock_now(db)
                if current:
                    try:
                        await self.rt.broker.call(
                            "fence", session_id=self.identity, generation=self.generation
                        )
                        await self.rt.synchronize()
                    except BrokerError:
                        pass  # remains pending, independent Broker lease closes the transport
                if self.rt.active.get(self.identity) is self:
                    self.rt.active.pop(self.identity, None)
        await self.close_socket(1000, "disconnected")

    async def close_socket(self, code, reason):
        try:
            async with self.send_lock:
                async with asyncio.timeout(2):
                    await self.ws.close(code=code, reason=reason)
        except (RuntimeError, OSError, WebSocketDisconnect, TimeoutError):
            pass

    def sequence(self, seq):
        if seq != self.last_client_seq + 1:
            raise BrokerError("input_sequence")
        self.last_client_seq = seq

    async def write(self, data, seq, *, sequenced=False):
        async with self.rt.gate:
            with self.rt.db() as db:
                proof = self.rt.proof(db, self.identity, self.login_digest)
                allowed = proof["mode"] == "write" and self.mode == "write" and not self.revoked
            if not allowed:
                await self.emit("input_rejected", reason_code="read_only")
                return
            if not sequenced:
                self.sequence(seq)
            async with asyncio.timeout(2):
                for offset in range(0, len(data), 8192):
                    self.broker_seq += 1
                    await self.rt.broker.call(
                        "input",
                        session_id=self.identity,
                        generation=self.generation,
                        seq=self.broker_seq,
                        data=base64.b64encode(data[offset : offset + 8192]).decode(),
                    )
            await self.emit("input_ack", seq=seq, stage="broker_written")

    async def new_flow(self):
        self.phase = "auth_required"
        with self.rt.db(write=True) as db:
            proof = self.rt.proof(db, self.identity, self.login_digest, refresh=True)
            flow = ConsoleAuthFlow(
                session_id=self.identity,
                user_id=proof["actor"].id,
                login_session_digest=self.login_digest,
                attachment_generation=self.generation,
                expires_at=min(
                    clock_now(db) + timedelta(minutes=2),
                    db.get(
                        LoginSession,
                        self.login_digest,
                    ).expires_at,
                ),
                created_at=clock_now(db),
            )
            db.add(flow)
            db.flush()
            self.flow_id = flow.id
        await self.emit("auth_required", flow_id=self.flow_id, remaining_attempts=3)

    async def establish(self, credential=None, flow_id=None):
        try:
            if credential is not None:
                with self.rt.db(write=True) as db:
                    self.rt.proof(db, self.identity, self.login_digest, refresh=True)
                    flow = db.get(ConsoleAuthFlow, flow_id)
                    if (
                        not flow
                        or flow.id != self.flow_id
                        or flow.closed_at is not None
                        or flow.in_flight
                        or flow.expires_at <= clock_now(db)
                        or flow.attempt_count >= 3
                        or flow.login_session_digest != self.login_digest
                        or flow.session_id != self.identity
                        or flow.attachment_generation != self.generation
                    ):
                        f.fail(403, "authentication_flow_invalid")
                    flow.attempt_count += 1
                    flow.in_flight = True
            self.phase = "connecting"
            while not self.revoked:
                async with self.rt.gate:
                    with self.rt.db(write=True) as db:
                        proof = self.rt.proof(db, self.identity, self.login_digest, refresh=True)
                        proof["row"].state = "connecting" if self.retry_count == 0 else "reconnecting"
                        args = {
                            "session_id": self.identity,
                            "generation": self.generation,
                            "user_id": proof["actor"].id,
                            "target": proof["target"],
                            "lease_until": proof["until"],
                            "mode": proof["mode"],
                            "cols": self.cols,
                            "rows": self.rows,
                            **proof["credential_args"],
                        }
                        if credential is not None:
                            args["credential"] = credential
                try:
                    await self.rt.broker.call("open", **args)
                    async with self.rt.gate:
                        with self.rt.db(write=True) as db:
                            proof = self.rt.proof(db, self.identity, self.login_digest, refresh=True)
                            proof["row"].state = "connected"
                            proof["row"].connected_at = clock_now(db)
                            self.mode = proof["mode"]
                            f.event(
                                db,
                                proof["actor"],
                                "console_connected",
                                sut_id=proof["row"].sut_id,
                                session_id=self.identity,
                            )
                        lease_ack = await self.rt.broker.call(
                            "lease_refresh",
                            session_id=self.identity,
                            generation=self.generation,
                            lease_until=proof["until"],
                            mode=self.mode,
                            resume=True,
                        )
                    self.mode = lease_ack.get("mode", self.mode)
                    self.phase = "connected"
                    await self.state("Connected")
                    await self.emit(
                        "connected",
                        transport=self.transport,
                        mode=self.mode,
                        attachment_generation=self.generation,
                    )
                    return
                except BrokerError as error:
                    if self.transport == "bmc" and error.code == "credential_auth_failed":
                        with self.rt.db(write=True) as db:
                            flow = db.get(ConsoleAuthFlow, flow_id)
                            flow.in_flight = False
                            remaining = 3 - flow.attempt_count
                            if remaining == 0:
                                flow.closed_at = clock_now(db)
                        if remaining:
                            self.phase = "auth_required"
                            await self.emit(
                                "auth_required",
                                flow_id=flow_id,
                                remaining_attempts=remaining,
                                reason_code="credential_auth_failed",
                            )
                            return
                    if (
                        self.transport == "bmc"
                        and error.code in ("ssh_unavailable", "ssh_timeout")
                        and self.retry_count < 3
                    ):
                        if credential is not None:
                            credential.clear()
                        await self.retry(error.code)
                        await self.new_flow()
                        return
                    if (
                        error.code not in ("ssh_unavailable", "ssh_timeout")
                        or self.transport != "uart"
                        or self.retry_count >= 3
                    ):
                        raise
                    await self.retry(error.code)
                finally:
                    if "credential" in args:
                        args["credential"].clear()
        except HTTPException:
            self.revoked = "session_revoked"
            await self.emit("revoked", reason_code="session_revoked", manual_connect_required=True)
            await self.close_socket(1008, "session_revoked")
        except BrokerError as error:
            self.revoked = error.code
            await self.state("Failed", error.code)
            await self.close_socket(1011, error.code)
        finally:
            if credential is not None:
                credential.clear()
            if flow_id:
                with self.rt.db(write=True) as db:
                    flow = db.get(ConsoleAuthFlow, flow_id)
                    if flow:
                        flow.in_flight = False

    async def retry(self, reason):
        self.retry_count += 1
        self.phase = "reconnecting"
        self.paste = None
        await self.state("Reconnecting", reason, retryable=True)
        await asyncio.sleep((1, 2, 4)[self.retry_count - 1])
        async with self.rt.gate:
            with self.rt.db(write=True) as db:
                actor, _ = self.rt.actor(db, self.login_digest)
                row, _ = f.reconnect_reservation(
                    db,
                    actor,
                    self.login_digest,
                    self.identity,
                    self.generation,
                    self.rt.origin(self.ws),
                    self.rt.settings,
                )
                previous = self.generation
                self.generation = row.attachment_generation
                self.rt.proof(db, self.identity, self.login_digest, refresh=True)
            await self.rt.broker.call("close", session_id=self.identity, generation=previous)
        self.last_client_seq = self.broker_seq = 0

    async def pump(self):
        try:
            while not self.revoked:
                async with self.rt.gate:
                    refresh = time.monotonic() - self.last_db_refresh >= 1
                    with self.rt.db(write=refresh) as db:
                        proof = self.rt.proof(db, self.identity, self.login_digest, refresh=refresh)
                        generation = proof["row"].attachment_generation
                        if generation != self.generation:
                            f.fail(403, "attachment_replaced")
                        until, mode = proof["until"], proof["mode"]
                        if self.phase == "auth_required" and self.flow_id:
                            flow = db.get(ConsoleAuthFlow, self.flow_id)
                            if not flow or flow.expires_at <= clock_now(db):
                                f.fail(403, "authentication_flow_expired")
                        if refresh:
                            self.last_db_refresh = time.monotonic()
                        participant_rows = db.execute(
                            select(User.id, User.display_name, ConsoleSession.mode)
                            .join(ConsoleSession, ConsoleSession.user_id == User.id)
                            .where(
                                ConsoleSession.sut_id == proof["row"].sut_id,
                                ConsoleSession.transport == self.transport,
                                ConsoleSession.state.in_(("connected", "reconnecting")),
                            )
                        ).all()
                        members = {}
                        for user_id, name, access in participant_rows:
                            previous = members.get(user_id)
                            if previous is None or access == "write":
                                members[user_id] = {"display_name": name, "mode": access}
                        participants = list(members.values())
                    try:
                        lease_ack = await self.rt.broker.call(
                            "lease_refresh",
                            session_id=self.identity,
                            generation=self.generation,
                            lease_until=until,
                            mode=mode,
                            resume=True,
                        )
                        mode = lease_ack.get("mode", mode)
                        if lease_ack.get("reconnect_required") and not self.reconnect_notice:
                            self.reconnect_notice = True
                            await self.emit(
                                "reconnect_required",
                                reason_code="readonly_attachment",
                                manual_connect_required=True,
                            )
                        if self.phase == "connected":
                            output = await self.rt.broker.call(
                                "read", session_id=self.identity, generation=self.generation
                            )
                            data = base64.b64decode(output["data"], validate=True)
                            if data:
                                async with self.send_lock:
                                    async with asyncio.timeout(2):
                                        await self.ws.send_bytes(data)
                        else:
                            output = None
                    except BrokerError as error:
                        if error.code == "session_stale" and self.phase in (
                            "connecting",
                            "auth_required",
                            "reconnecting",
                        ):
                            output = None
                        else:
                            raise
                    if self.mode != mode:
                        self.mode = mode
                        await self.state("Connected" if self.phase == "connected" else "Connecting")
                if refresh and self.phase == "connected":
                    await self.emit(
                        "participants",
                        users=participants,
                        unique_user_count=len(participants),
                        shared_console=self.transport == "uart" and len(participants) > 1,
                    )
                if output and output.get("ended"):
                    ended = output["ended"]
                    if ended == "remote_closed":
                        self.revoked = "remote_closed"
                        await self.state("Disconnected", "remote_closed")
                        break
                    if ended in ("ssh_unavailable", "ssh_timeout") and self.retry_count < 3:
                        async with self.rt.gate:
                            await self.rt.broker.call(
                                "close", session_id=self.identity, generation=self.generation
                            )
                        await self.retry(ended)
                        if self.transport == "uart":
                            self.operation = asyncio.create_task(self.establish())
                        else:
                            await self.new_flow()
                    else:
                        raise BrokerError(ended)
                await asyncio.sleep(0.1)
        except HTTPException:
            self.revoked = "session_revoked"
        except BrokerError as error:
            self.revoked = error.code
        except (RuntimeError, OSError, TimeoutError, WebSocketDisconnect):
            self.revoked = "browser_disconnected"
        if self.revoked:
            try:
                await self.emit("revoked", reason_code=self.revoked, manual_connect_required=True)
            except (RuntimeError, OSError, TimeoutError, WebSocketDisconnect):
                pass
            await self.close_socket(1008, self.revoked)
