"""Single-worker Console authorizer/control plane. All SSH lives behind private IPC."""

import asyncio
import base64
from contextlib import contextmanager
from datetime import timedelta
import hashlib

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.console_broker.ipc import BrokerClient, BrokerError, private_key_file
from app.core.database import clock_now, unit_of_work
from app.models.console import ConsoleGrant, ConsoleRevocation, ConsoleSession
from app.models.domain import LoginSession, SUT, User
from app.services.accounts import token_hash
from app.services.console import foundation as f


class ConsoleRuntime:
    def __init__(self, app, settings, *, broker=None):
        self.app, self.settings = app, settings
        self.broker = broker or BrokerClient(
            settings.console_broker_socket,
            private_key_file(settings.console_broker_ipc_key_file),
            expected_uid=settings.console_broker_uid,
        )
        self.recovery_gate = asyncio.Lock()
        self.gate = asyncio.Lock()  # short authorization/fencing barrier, NOT a writer lease
        self.active = {}
        self.handshakes = asyncio.Semaphore(32)
        self.ready = False
        from app.services.console.validation import ValidationRegistry

        self.validation = ValidationRegistry(self)

    @contextmanager
    def db(self, *, write=False):
        with unit_of_work(self.app.state.engine, write=write) as db:
            db.info["clock"] = self.app.state.clock
            yield db

    def actor(self, db, login_digest):
        login = db.get(LoginSession, login_digest)
        actor = db.get(User, login.user_id) if login and login.expires_at > clock_now(db) else None
        if actor is None or not actor.is_active:
            f.fail(401, "console_login_required")
        if actor.must_change_password:
            f.fail(403, "password_change_required")
        return actor, login

    def authenticate(self, scope):
        raw = scope.session.get("login")
        if not raw:
            f.fail(401, "console_login_required")
        login_digest = token_hash(raw)
        with self.db() as db:
            self.actor(db, login_digest)
        return login_digest

    def origin(self, scope):
        if scope.scope.get("query_string"):
            f.fail(403, "console_query_not_allowed")
        origin = scope.headers.get("origin", "")
        f.normalize_origin(origin, self.settings)
        scheme = "https" if scope.url.scheme in ("https", "wss") else "http"
        if origin != scheme + "://" + scope.headers.get("host", ""):
            f.fail(403, "console_origin_invalid")
        if self.settings.console_allowed_origins and origin not in self.settings.console_allowed_origins:
            f.fail(403, "console_origin_invalid")
        return origin

    async def start(self):
        try:
            await self.broker.call(
                "status",
                login_key_digest=hashlib.sha256(
                    self.settings.secret_key.get_secret_value().encode()
                ).hexdigest(),
            )
            async with self.gate:
                for active in self.active.values():
                    active.revoked = "gateway_restarted"
                await self.broker.call("fence_all")
                with self.db(write=True) as db:
                    for row in db.scalars(select(ConsoleSession).where(ConsoleSession.state != "closed")):
                        f.close_session(db, row, "gateway_restarted")
                await self.synchronize()
            self.ready = True
        except BrokerError:
            self.ready = False  # coordination stays readable; no Console success without Broker

    async def stop(self):
        async with self.gate:
            for active in self.active.values():
                active.revoked = "gateway_stopped"
            try:
                await self.before_mutation()
                with self.db(write=True) as db:
                    for row in db.scalars(select(ConsoleSession).where(ConsoleSession.state != "closed")):
                        f.close_session(db, row, "gateway_stopped")
                await self.synchronize()
            except BrokerError:
                pass  # leases fail closed; never mark unacknowledged delivery
        self.ready = False

    def require_ready(self):
        if not self.ready:
            f.fail(503, "broker_unavailable")

    async def before_mutation(self):
        with self.db() as db:
            rows = [
                (row.id, row.attachment_generation)
                for row in db.scalars(select(ConsoleSession).where(ConsoleSession.state == "connected"))
            ]
        with self.db() as db:
            rows.extend(
                (row.session_id, row.attachment_generation)
                for row in db.scalars(
                    select(ConsoleRevocation).where(ConsoleRevocation.delivered_at.is_(None))
                )
            )
        rows = list(dict.fromkeys(rows))
        for identity, generation in rows:
            ack = await self.broker.call("fence", session_id=identity, generation=generation)
            if ack.get("generation") != generation or not ack.get("fenced"):
                raise BrokerError("session_fenced")
        await self.broker.call("fence_all")

    async def http_barrier(self, request, call_next):
        # Bound secret/admin JSON without logging or multipart temp-file handling.
        if request.url.path.startswith("/api/v1/console") and request.method not in (
            "GET",
            "HEAD",
            "OPTIONS",
        ):
            total = 0
            body = []
            async for chunk in request.stream():
                total += len(chunk)
                if total > 131072:
                    return JSONResponse({"detail": {"code": "payload_too_large"}}, status_code=413)
                body.append(chunk)
            request._body = b"".join(body)
        # These prepare operations do no DB writes and can take10s; fence only at commit.
        prepare = request.url.path in (
            "/api/v1/console/client-validations",
            "/api/v1/console/trust/challenges",
            "/api/v1/console/sessions",
        )
        if request.method in ("GET", "HEAD", "OPTIONS") or prepare:
            return await call_next(request)
        # Rejecting an unauthenticated mutation must not fence other users' terminals.
        raw = request.session.get("login")
        try:
            with self.db() as db:
                self.actor(db, token_hash(raw) if raw else "")
        except HTTPException:
            return await call_next(request)
        try:
            async with self.gate:
                with self.db() as db:
                    live = db.scalar(
                        select(ConsoleSession.id)
                        .where(ConsoleSession.state.in_(("connecting", "connected", "reconnecting")))
                        .limit(1)
                    )
                with self.db() as db:
                    pending = db.scalar(
                        select(ConsoleRevocation.id).where(ConsoleRevocation.delivered_at.is_(None)).limit(1)
                    )
                if live or pending or self.active:
                    await self.before_mutation()
                response = await call_next(request)  # DB dependencies commit BEFORE returning
                try:
                    await self.synchronize()
                except BrokerError:
                    # Precommit fencing already succeeded. Commit stays truthful even
                    # if postcommit close delivery is interrupted; outbox remains pending.
                    response.headers["X-Console-Revocation"] = "pending"
                return response
        except BrokerError:
            return JSONResponse(
                {"detail": {"code": "broker_fence_unavailable", "retryable": True}}, status_code=503
            )

    @staticmethod
    def envelope(credential):
        result = {
            key: getattr(credential, key)
            for key in (
                "ciphertext",
                "nonce",
                "wrapped_data_key",
                "wrap_nonce",
                "key_id",
                "algorithm",
                "crypto_revision",
            )
        }
        for key in ("ciphertext", "nonce", "wrapped_data_key", "wrap_nonce"):
            result[key] = base64.b64encode(result[key]).decode()
        return result

    def proof(self, db, identity, login_digest, *, refresh=False):
        actor, login = self.actor(db, login_digest)
        row = db.get(ConsoleSession, identity)
        now = clock_now(db)
        if (
            not row
            or row.user_id != actor.id
            or row.login_session_digest != login_digest
            or row.state == "closed"
            or row.lease_until <= now
        ):
            f.fail(403, "session_revoked")
        sut = db.get(SUT, row.sut_id)
        auth = f.authorization(db, actor, login_digest, sut, self.settings)
        if auth["mode"] == "deny":
            f.fail(403, "console_access_denied")
        if row.grant_id is not None and auth["grant_id"] is not None and row.grant_id != auth["grant_id"]:
            f.fail(403, "grant_expired")
        mapping, client, credential, key = f.endpoint_context(db, sut, row.transport, self.settings)
        if (
            mapping.endpoint_epoch != row.endpoint_epoch
            or key.trust_revision != row.trust_revision
            or client
            and (
                client.connection_epoch != row.client_epoch
                or credential.generation != row.credential_generation
            )
        ):
            f.fail(403, "session_revoked")
        until = login.expires_at
        if auth["grant_id"]:
            until = min(until, db.get(ConsoleGrant, auth["grant_id"]).expires_at)
        if refresh:
            row.lease_until = min(now + timedelta(seconds=45), until)
            row.mode = auth["mode"]
        return {
            "row": row,
            "actor": actor,
            "mode": auth["mode"],
            "until": min(now + timedelta(seconds=2), until).timestamp(),
            "target": {
                "host": client.ipv4 if client else mapping.ipv4,
                "port": client.ssh_port if client else 22,
                "transport": row.transport,
                "public_key": key.public_key,
                **({"tmux_session": mapping.tmux_session} if client else {}),
            },
            "credential_args": {
                "envelope": self.envelope(credential),
                "aad": [client.security_id, credential.security_id, credential.method, credential.generation],
                "method": client.auth_method,
                "username": client.ssh_username,
            }
            if client
            else {},
        }

    async def synchronize(self):
        """Called under gate after a commit. No DB transaction awaits IPC."""
        for identity, active in list(self.active.items()):
            try:
                with self.db(write=True) as db:
                    proof = self.proof(db, identity, active.login_digest, refresh=True)
                    generation = proof["row"].attachment_generation
                    until, mode = proof["until"], proof["mode"]
                if generation != active.generation:
                    active.revoked = "attachment_replaced"
                    continue
                try:
                    await self.broker.call(
                        "lease_refresh",
                        session_id=identity,
                        generation=generation,
                        lease_until=until,
                        mode=mode,
                        resume=True,
                    )
                except BrokerError as error:
                    if error.code != "session_stale" or active.phase == "connected":
                        raise
            except HTTPException:
                with self.db(write=True) as db:
                    row = db.get(ConsoleSession, identity)
                    if row and row.state != "closed":
                        f.close_session(db, row, "authorization_revoked")
                active.revoked = "session_revoked"
        with self.db() as db:
            pending = [
                (r.id, r.session_id, r.attachment_generation)
                for r in db.scalars(select(ConsoleRevocation).where(ConsoleRevocation.delivered_at.is_(None)))
            ]
        for outbox_id, identity, generation in pending:
            ack = await self.broker.call("fence", session_id=identity, generation=generation)
            if not ack.get("fenced") or ack.get("generation") != generation:
                raise BrokerError("session_fenced")
            closed = await self.broker.call("close", session_id=identity, generation=generation)
            if not closed.get("fenced") or closed.get("generation") != generation:
                raise BrokerError("session_fenced")
            with self.db(write=True) as db:
                row = db.get(ConsoleRevocation, outbox_id)
                if row and row.delivered_at is None:
                    row.delivered_at = clock_now(db)
            active = self.active.get(identity)
            if active and active.generation == generation:
                active.revoked = "session_revoked"

    async def issue(self, scope, data):
        login_digest = self.authenticate(scope)
        origin = self.origin(scope)
        # Only an explicit authenticated Connect can bind a new Broker incarnation.
        # Existing attachments fail closed and never regain authority/replay input.
        async with self.recovery_gate:
            try:
                await self.broker.call("status")
            except BrokerError as error:
                self.ready = False
                if error.code == "broker_restarted":
                    self.broker.boot_id = None
                else:
                    raise
            if not self.ready:
                await self.start()
        self.require_ready()
        async with self.gate:
            with self.db(write=True) as db:
                actor, _ = self.actor(db, login_digest)
                sut = db.get(SUT, data.sut_id)
                if not sut:
                    f.fail(404, "sut_not_found")
                mapping = f.mapping_row(db, sut.id, data.transport)
                if not mapping or mapping.revision != data.expected_revision:
                    f.fail(409, "mapping_stale")
                row, token = f.reserve_session(
                    db, actor, login_digest, sut.id, data.transport, data.tab_id, origin, self.settings
                )
                result = {
                    "session_id": row.id,
                    "ticket": token,
                    "attachment_generation": row.attachment_generation,
                    "expires_at": row.lease_until,
                    "state": "Connecting",
                    "mode": row.mode,
                    "transport_warning": "plaintext_http" if scope.url.scheme == "http" else None,
                }
            return result

    async def attach(self, scope, identity, data):
        self.require_ready()
        login_digest = self.authenticate(scope)
        origin = self.origin(scope)
        # HTTP middleware already owns gate and precommit fence here.
        with self.db(write=True) as db:
            actor, _ = self.actor(db, login_digest)
            row = db.get(ConsoleSession, identity)
            if not row or row.user_id != actor.id or row.instance_id != data.tab_id:
                f.fail(403, "console_access_denied")
            if row.state == "connected" and not data.confirm_connected:
                f.fail(409, "reconnect_confirmation_required")
            row, token = f.reconnect_reservation(
                db, actor, login_digest, identity, data.attachment_generation, origin, self.settings
            )
            result = {
                "session_id": row.id,
                "ticket": token,
                "attachment_generation": row.attachment_generation,
                "expires_at": row.lease_until,
                "state": "Connecting",
                "mode": row.mode,
            }
        old = self.active.get(identity)
        if old:
            ack = await self.broker.call("fence", session_id=identity, generation=old.generation)
            if not ack.get("fenced"):
                raise BrokerError("session_fenced")
            await self.broker.call("close", session_id=identity, generation=old.generation)
            old.revoked = "attachment_replaced"
        return result

    async def websocket(self, websocket, identity):
        from app.services.console.websocket import TerminalLink

        await TerminalLink(self, websocket, identity).serve()
