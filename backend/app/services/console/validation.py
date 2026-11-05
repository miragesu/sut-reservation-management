"""Bounded RAM challenges/candidates. Remote authentication is outside DB locks."""

import base64
from dataclasses import dataclass
from datetime import timedelta
import secrets
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select

from app.console_broker.ipc import BrokerError
from app.core.database import clock_now
from app.models.console import (
    ConsoleBmcEndpoint,
    ConsoleClient,
    ConsoleCredential,
    ConsoleHostKey,
    ConsoleUartMapping,
)
from app.models.domain import Lab
from app.schemas.console_live import TrustAccept
from app.services.common import get_or_404, require_role
from app.services.console import foundation as f
from app.services.console.credentials import HostEvidence, PreparedCredential, store_credential
from app.services.console.crypto import Envelope
from app.services.console.targets import validate_ipv4


@dataclass(repr=False)
class ChallengeRecord:
    actor_id: int
    login_digest: str
    target: dict
    owner: dict
    old_revision: int
    observed: dict
    expires_at: object
    accepted: bool = False


@dataclass(repr=False)
class Candidate:
    actor_id: int
    login_digest: str
    client_id: int | None
    expected_version: int | None
    connection_epoch: int
    trust_revision: int
    metadata: dict
    prepared: PreparedCredential
    expires_at: object


class ValidationRegistry:
    def __init__(self, runtime):
        self.runtime = runtime
        self.challenges = {}
        self.candidates = {}

    def prune(self):
        now = self.runtime.app.state.clock()
        self.challenges = {key: value for key, value in self.challenges.items() if value.expires_at > now}
        self.candidates = {key: value for key, value in self.candidates.items() if value.expires_at > now}
        if len(self.challenges) >= 256 or len(self.candidates) >= 128:
            f.fail(429, "console_validation_limit")

    async def new_challenge(self, login_digest, target, owner, *, draft=False):
        self.prune()
        with self.runtime.db() as db:
            actor, _ = self.runtime.actor(db, login_digest)
            if draft:
                require_role(actor, *f.ADMIN)
            if owner.get("client_id"):
                client = get_or_404(db, ConsoleClient, owner["client_id"])
                old = f.current_key(db, client_id=client.id)
                version = client.metadata_version
                rows = f.affected(db, client_id=client.id)
            elif owner.get("sut_id"):
                mapping = get_or_404(db, ConsoleBmcEndpoint, owner["sut_id"])
                old = f.current_key(db, sut_id=owner["sut_id"])
                version = mapping.revision
                rows = f.affected(db, sut_id=owner["sut_id"], transport="bmc")
            else:
                old, version, rows = None, None, []
            actor_id = actor.id
            old_fingerprint = old.fingerprint if old else None
            trust_revision = old.trust_revision if old else 0
            owner = {**owner, "version": version, "draft": draft, "sessions_hash": f.sessions_hash(rows)}
        observed = await self.runtime.broker.call(
            "probe_key", **{k: target[k] for k in ("host", "port", "transport")}
        )
        identity = secrets.token_urlsafe(32)
        expires = self.runtime.app.state.clock() + timedelta(minutes=2)
        record = ChallengeRecord(
            actor_id, login_digest, dict(target), owner, trust_revision, observed, expires
        )
        self.challenges[identity] = record
        result = {
            "challenge_id": identity,
            "algorithm": observed["algorithm"],
            "fingerprint": observed["fingerprint"],
            "old_fingerprint": old_fingerprint,
            "public_key": observed["public_key"],
            "expires_at": expires,
            "expected_trust_revision": trust_revision,
            "scope": "candidate_only" if draft else "existing_endpoint",
        }
        # Re-read after probe: stale target/versions may not acquire a reusable proof.
        with self.runtime.db(write=True) as db:
            actor, _ = self.runtime.actor(db, login_digest)
            self.check_owner(db, record)
            accept = TrustAccept(
                challenge_id=identity,
                expected_trust_revision=trust_revision,
                fingerprint=observed["fingerprint"],
                out_of_band_verified=True,
            )
            rows = self.rows(db, record)
            preview = (
                f.preview(db, actor, login_digest, "trust:" + identity, accept, rows)
                if not draft
                else {
                    "affected": {
                        "sut_count": len({r.sut_id for r in rows}),
                        "rd_count": len({r.user_id for r in rows}),
                        "session_count": len(rows),
                    },
                    "requires_confirmation": bool(rows),
                    "confirmation_id": None,
                }
            )
        return {**result, **preview}

    @staticmethod
    def rows(db, record):
        if record.owner.get("client_id"):
            return f.affected(db, client_id=record.owner["client_id"])
        if record.owner.get("sut_id"):
            return f.affected(db, sut_id=record.owner["sut_id"], transport="bmc")
        return []

    def check_owner(self, db, record):
        if record.owner.get("client_id"):
            row = get_or_404(db, ConsoleClient, record.owner["client_id"])
            key = f.current_key(db, client_id=row.id)
            version = row.metadata_version
            if not record.owner["draft"] and (
                row.ipv4 != record.target["host"] or row.ssh_port != record.target["port"]
            ):
                f.fail(409, "trust_target_stale")
        elif record.owner.get("sut_id"):
            from app.models.console import ConsoleBmcEndpoint

            row = get_or_404(db, ConsoleBmcEndpoint, record.owner["sut_id"])
            key = f.current_key(db, sut_id=row.sut_id)
            version = row.revision
            if row.ipv4 != record.target["host"]:
                f.fail(409, "trust_target_stale")
        else:
            key, version = None, None
        if version != record.owner["version"] or (key.trust_revision if key else 0) != record.old_revision:
            f.fail(409, "trust_target_stale")

    async def challenge(self, scope, data):
        self.runtime.require_ready()
        login_digest = self.runtime.authenticate(scope)
        if (data.client_id is None) == (data.sut_id is None):
            f.fail(422, "trust_owner_invalid")
        with self.runtime.db() as db:
            if data.client_id:
                client = get_or_404(db, ConsoleClient, data.client_id)
                target = {"host": client.ipv4, "port": client.ssh_port, "transport": "uart"}
                owner = {"client_id": client.id}
            else:
                from app.models.console import ConsoleBmcEndpoint

                mapping = get_or_404(db, ConsoleBmcEndpoint, data.sut_id)
                if not mapping.ipv4:
                    f.fail(409, "not_configured")
                target = {"host": mapping.ipv4, "port": 22, "transport": "bmc"}
                owner = {"sut_id": mapping.sut_id}
            validate_ipv4(
                target["host"],
                bmc=target["transport"] == "bmc",
                sensitive=self.runtime.settings.console_sensitive_ipv4,
            )
        return await self.new_challenge(login_digest, target, owner)

    async def accept(self, scope, data):
        self.runtime.require_ready()
        login_digest = self.runtime.authenticate(scope)
        record = self.challenges.get(data.challenge_id)
        with self.runtime.db(write=True) as db:
            actor, _ = self.runtime.actor(db, login_digest)
            if (
                not record
                or record.expires_at <= clock_now(db)
                or record.login_digest != login_digest
                or record.actor_id != actor.id
                or data.expected_trust_revision != record.old_revision
                or data.fingerprint != record.observed["fingerprint"]
                or data.out_of_band_verified is not True
            ):
                f.fail(409, "trust_challenge_stale")
            self.check_owner(db, record)
            if record.owner["draft"]:
                require_role(actor, *f.ADMIN)
                record.accepted = True
                return {"accepted": True, "candidate_only": True, "challenge_id": data.challenge_id}
            rows = self.rows(db, record)
            f.confirm(db, actor, login_digest, "trust:" + data.challenge_id, data, rows)
            if record.owner.get("client_id"):
                client = get_or_404(db, ConsoleClient, record.owner["client_id"])
                previous = f.current_key(db, client_id=client.id)
                client.connection_epoch += 1
                epoch = client.connection_epoch
                owner = {"client_id": client.id}
            else:
                from app.models.console import ConsoleBmcEndpoint

                endpoint = get_or_404(db, ConsoleBmcEndpoint, record.owner["sut_id"])
                previous = f.current_key(db, sut_id=endpoint.sut_id)
                endpoint.endpoint_epoch += 1
                epoch = endpoint.endpoint_epoch
                owner = {"bmc_sut_id": endpoint.sut_id}
            if previous:
                previous.is_current = False
                previous.replaced_at = clock_now(db)
                db.flush()
            db.add(
                ConsoleHostKey(
                    **owner,
                    ipv4=record.target["host"],
                    port=record.target["port"],
                    endpoint_epoch=epoch,
                    algorithm=record.observed["algorithm"],
                    public_key=record.observed["public_key"],
                    fingerprint=record.observed["fingerprint"],
                    trust_revision=record.old_revision + 1,
                    previous_id=previous.id if previous else None,
                    accepted_by=actor.id,
                    created_at=clock_now(db),
                )
            )
            f.revoke(db, rows, "host_key_changed", epoch=epoch)
            f.event(
                db,
                actor,
                "host_key_accepted",
                sut_id=record.owner.get("sut_id"),
                client_id=record.owner.get("client_id"),
                old_fingerprint=previous.fingerprint if previous else None,
                new_fingerprint=record.observed["fingerprint"],
            )
        self.challenges.pop(data.challenge_id, None)
        return {
            "accepted": True,
            "candidate_only": False,
            "trust_revision": record.old_revision + 1,
            "revocation_delivery": "pending" if rows else "none",
        }

    async def validate(self, scope, data):
        self.runtime.require_ready()
        self.prune()
        login_digest = self.runtime.authenticate(scope)
        self.runtime.origin(scope)
        with self.runtime.db() as db:
            actor, _ = self.runtime.actor(db, login_digest)
            require_role(actor, *f.ADMIN)
            client = get_or_404(db, ConsoleClient, data.client_id) if data.client_id else None
            if client and data.expected_version != client.metadata_version:
                f.fail(409, "client_stale")
            fields = ("lab_id", "name", "ipv4", "ssh_port", "ssh_username", "auth_method", "notes")
            metadata = {
                key: getattr(data, key)
                if getattr(data, key) is not None
                else getattr(client, key)
                if client
                else (22 if key == "ssh_port" else "" if key == "notes" else None)
                for key in fields
            }
            if (
                any(metadata[key] is None for key in fields)
                or not metadata["name"].strip()
                or not metadata["ssh_username"]
            ):
                f.fail(422, "client_fields_required")
            metadata["name"] = metadata["name"].strip()
            validate_ipv4(metadata["ipv4"], sensitive=self.runtime.settings.console_sensitive_ipv4)
            get_or_404(db, Lab, metadata["lab_id"])
            if (
                client
                and metadata["lab_id"] != client.lab_id
                and db.scalar(
                    select(ConsoleUartMapping.sut_id)
                    .where(ConsoleUartMapping.client_id == client.id)
                    .limit(1)
                )
            ):
                f.fail(409, "client_has_retained_bindings")
            collision = db.scalar(
                select(ConsoleClient.id)
                .where(
                    ConsoleClient.id != (client.id if client else -1),
                    (ConsoleClient.ipv4 == metadata["ipv4"])
                    | (
                        (ConsoleClient.lab_id == metadata["lab_id"])
                        & (ConsoleClient.normalized_name == metadata["name"].casefold())
                    ),
                )
                .limit(1)
            )
            if collision:
                f.fail(409, "client_name_or_ip_conflict")
            credential = (
                db.get(ConsoleCredential, client.active_credential_id)
                if client and client.active_credential_id
                else None
            )
            current = f.current_key(db, client_id=client.id) if client else None
            client_id, version = client.id if client else None, client.metadata_version if client else None
            security_id = client.security_id if client else uuid4().hex
            generation = credential.generation + 1 if credential else 1
            actor_id = actor.id
            connection_epoch = client.connection_epoch if client else 0
            trust_revision = current.trust_revision if current else 0
            target = {"host": metadata["ipv4"], "port": metadata["ssh_port"], "transport": "uart"}
            args = {
                "target": target,
                "user_id": actor.id,
                "client_security_id": security_id,
                "credential_security_id": uuid4().hex,
                "generation": generation,
            }
            if data.secret:
                args["credential"] = {
                    "username": metadata["ssh_username"],
                    "method": metadata["auth_method"],
                    "secret": data.secret.get_secret_value(),
                }
                if data.passphrase:
                    args["credential"]["passphrase"] = data.passphrase.get_secret_value()
            elif credential and metadata["auth_method"] == client.auth_method:
                args.update(
                    envelope=self.runtime.envelope(credential),
                    aad=[security_id, credential.security_id, credential.method, credential.generation],
                    username=metadata["ssh_username"],
                    method=metadata["auth_method"],
                )
            else:
                f.fail(422, "credential_required")
            trusted = (
                current.public_key
                if current and current.ipv4 == metadata["ipv4"] and current.port == metadata["ssh_port"]
                else None
            )
        record = self.challenges.get(data.trust_challenge_id) if data.trust_challenge_id else None
        if record:
            if (
                not record.accepted
                or not record.owner["draft"]
                or record.login_digest != login_digest
                or record.actor_id != actor_id
                or record.expires_at <= self.runtime.app.state.clock()
                or {k: record.target[k] for k in ("host", "port", "transport")} != target
                or record.owner.get("client_id") != client_id
            ):
                f.fail(409, "trust_challenge_stale")
            with self.runtime.db() as db:
                self.check_owner(db, record)
            trusted = record.observed["public_key"]
        if not trusted:
            challenge = await self.new_challenge(
                login_digest, target, {"client_id": client_id} if client_id else {}, draft=True
            )
            return {"validated": False, "challenge": challenge}
        args["target"]["public_key"] = trusted
        try:
            result = await self.runtime.broker.call("validate_client", **args)
        except BrokerError as error:
            with self.runtime.db(write=True) as db:
                actor, _ = self.runtime.actor(db, login_digest)
                f.event(db, actor, "client_validation_failed", client_id=client_id, reason_code=error.code)
            if error.code == "host_key_changed":
                challenge = await self.new_challenge(
                    login_digest, target, {"client_id": client_id} if client_id else {}, draft=True
                )
                return {"validated": False, "challenge": challenge}
            raise
        finally:
            if "credential" in args:
                args["credential"].clear()
        envelope_data = dict(result["envelope"])
        for key in ("ciphertext", "nonce", "wrapped_data_key", "wrap_nonce"):
            envelope_data[key] = base64.b64decode(envelope_data[key], validate=True)
        expires = self.runtime.app.state.clock() + timedelta(minutes=2)
        public = trusted
        algorithm = public.split()[0]
        proof = PreparedCredential(
            security_id,
            args["credential_security_id"],
            generation,
            version,
            "broker_verified",
            Envelope(**envelope_data),
            HostEvidence(
                actor_id,
                "broker_verified",
                metadata["ipv4"],
                metadata["ssh_port"],
                algorithm,
                public,
                expires,
            ),
        )
        identity = secrets.token_urlsafe(32)
        self.candidates[identity] = Candidate(
            actor_id,
            login_digest,
            client_id,
            version,
            connection_epoch,
            trust_revision,
            metadata,
            proof,
            expires,
        )
        return {"validated": True, "validation_id": identity, "expires_at": expires}

    def candidate(self, db, actor, login_digest, identity, client_id=None, data=None):
        candidate = self.candidates.get(identity)
        if (
            not candidate
            or candidate.actor_id != actor.id
            or candidate.login_digest != login_digest
            or candidate.expires_at <= clock_now(db)
            or candidate.client_id != client_id
        ):
            f.fail(409, "validation_stale")
        require_role(actor, *f.ADMIN)
        if data is not None:
            # A validation ID is authority for one exact candidate, not a blanket
            # bypass for additional unvalidated fields or a silently ignored secret.
            if data.secret is not None or data.enabled is not None:
                f.fail(409, "validation_payload_mismatch")
            for key, value in candidate.metadata.items():
                if key in data.model_fields_set and getattr(data, key) != value:
                    f.fail(409, "validation_payload_mismatch")
        if client_id:
            client = get_or_404(db, ConsoleClient, client_id)
            current = f.current_key(db, client_id=client.id)
            if (
                client.metadata_version != candidate.expected_version
                or client.connection_epoch != candidate.connection_epoch
                or (current.trust_revision if current else 0) != candidate.trust_revision
            ):
                f.fail(409, "client_stale")
        return candidate

    def commit(self, scope, identity, *, client_id=None, data=None):
        self.runtime.require_ready()
        login_digest = self.runtime.authenticate(scope)
        with self.runtime.db(write=True) as db:
            actor, _ = self.runtime.actor(db, login_digest)
            candidate = self.candidate(db, actor, login_digest, identity, client_id, data)
            values = candidate.metadata
            get_or_404(db, Lab, values["lab_id"])
            validate_ipv4(values["ipv4"], sensitive=self.runtime.settings.console_sensitive_ipv4)
            if client_id:
                client = get_or_404(db, ConsoleClient, client_id)
                if data.expected_version != client.metadata_version:
                    f.fail(409, "client_stale")
                rows = f.affected(db, client_id=client_id)
                f.confirm(db, actor, login_digest, "validated-client:" + str(client_id), data, rows)
                if client.lab_id != values["lab_id"] and db.scalar(
                    select(ConsoleUartMapping.sut_id)
                    .where(ConsoleUartMapping.client_id == client.id)
                    .limit(1)
                ):
                    f.fail(409, "client_has_retained_bindings")
                old = db.get(ConsoleCredential, client.active_credential_id)
                if old:
                    old.replaced_at = clock_now(db)
                client.connection_epoch += 1
                client.metadata_version += 1
            else:
                rows = []
                client = ConsoleClient(
                    security_id=candidate.prepared.client_security_id,
                    updated_by=actor.id,
                    created_at=clock_now(db),
                    updated_at=clock_now(db),
                    **values,
                    normalized_name=values["name"].casefold(),
                )
                db.add(client)
                db.flush()
            for key, value in values.items():
                setattr(client, key, value)
            client.normalized_name = client.name.casefold()
            client.updated_at, client.updated_by = clock_now(db), actor.id
            store_credential(db, actor, client, SimpleNamespace(**values), candidate.prepared)
            f.revoke(db, rows, "client_changed", epoch=client.connection_epoch)
            output = f.client_view(client, admin=True)
        self.candidates.pop(identity, None)
        return output
