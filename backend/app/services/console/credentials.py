"""Fail-closed Phase C validation boundary, plus offline mockable commit primitives.

There is NO HTTP test-success hook, environmental bypass or real SSH implementation.
Prepare must run before BEGIN IMMEDIATE; only a trusted internal validator can
supply evidence. Tests inject a synthetic validator; production always refuses.
"""

import base64
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from uuid import uuid4

from cryptography.hazmat.primitives.serialization import load_ssh_public_key
from sqlalchemy import select

from app.core.database import clock_now
from app.models.console import ConsoleClient, ConsoleCredential, ConsoleHostKey
from app.models.domain import Lab
from app.services.common import get_or_404, require_role
from app.services.console.crypto import Envelope
from app.services.console.foundation import (
    ADMIN,
    affected,
    canonical_hash,
    client_view,
    event,
    fail,
    require_actor,
    revoke,
)
from app.services.console.targets import validate_ipv4


@dataclass(frozen=True, repr=False)
class HostEvidence:
    actor_id: int
    candidate_hash: str
    ipv4: str
    port: int
    algorithm: str
    public_key: str
    expires_at: datetime


class UnavailableValidation:
    def verify(self, candidate_hash, actor_id, ipv4, port):
        fail(503, "client_validation_unavailable")


@dataclass(frozen=True, repr=False)
class PreparedCredential:
    client_security_id: str
    credential_security_id: str
    generation: int
    expected_version: int | None
    candidate_hash: str
    envelope: Envelope
    evidence: HostEvidence


def fingerprint(public_key, algorithm):
    try:
        pieces = public_key.split()
        if pieces[0] != algorithm or len(pieces) < 2:
            raise ValueError()
        load_ssh_public_key((" ".join(pieces[:2])).encode())
        raw = base64.b64decode(pieces[1], validate=True)
        return "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")
    except (ValueError, IndexError, TypeError):
        fail(422, "host_key_invalid")


def candidate_hash(data):
    # RAM-only digest binds candidate, including secret, without storing its hash.
    values = data.model_dump(mode="json", exclude={"secret"})
    values["secret"] = data.secret.get_secret_value()
    return canonical_hash(values)


def prepare(
    data, actor_id, cipher, *, verifier=None, client_security_id=None, generation=1, expected_version=None
):
    validate_ipv4(data.ipv4)
    evidence = (verifier or UnavailableValidation()).verify(
        candidate_hash(data), actor_id, data.ipv4, data.ssh_port
    )
    security_id, credential_id = client_security_id or uuid4().hex, uuid4().hex
    secret = json.dumps({"secret": data.secret.get_secret_value()}, separators=(",", ":")).encode()
    envelope = cipher.encrypt(secret, cipher.aad(security_id, credential_id, data.auth_method, generation))
    return PreparedCredential(
        security_id, credential_id, generation, expected_version, candidate_hash(data), envelope, evidence
    )


def verify_prepared(db, actor, data, prepared):
    evidence = prepared.evidence
    if (
        evidence.actor_id != actor.id
        or evidence.expires_at <= clock_now(db)
        or evidence.candidate_hash != candidate_hash(data)
        or prepared.candidate_hash != candidate_hash(data)
        or evidence.ipv4 != data.ipv4
        or evidence.port != data.ssh_port
    ):
        fail(409, "validation_stale")
    fingerprint(evidence.public_key, evidence.algorithm)


def create_verified_client(db, actor, data, prepared):
    require_actor(actor)
    require_role(actor, *ADMIN)
    verify_prepared(db, actor, data, prepared)
    validate_ipv4(data.ipv4)
    get_or_404(db, Lab, data.lab_id)
    client = ConsoleClient(
        security_id=prepared.client_security_id,
        lab_id=data.lab_id,
        name=data.name.strip(),
        normalized_name=data.name.strip().casefold(),
        ipv4=data.ipv4,
        ssh_port=data.ssh_port,
        ssh_username=data.ssh_username,
        auth_method=data.auth_method,
        notes=data.notes,
        enabled=True,
        updated_by=actor.id,
        created_at=clock_now(db),
        updated_at=clock_now(db),
    )
    db.add(client)
    db.flush()
    store_credential(db, actor, client, data, prepared)
    return client_view(client, admin=True)


def store_credential(db, actor, client, data, prepared):
    credential = ConsoleCredential(
        security_id=prepared.credential_security_id,
        client_security_id=client.security_id,
        method=data.auth_method,
        generation=prepared.generation,
        created_by=actor.id,
        created_at=clock_now(db),
        **asdict(prepared.envelope),
    )
    db.add(credential)
    db.flush()
    client.active_credential_id = credential.id
    evidence = prepared.evidence
    previous = db.scalar(
        select(ConsoleHostKey).where(
            ConsoleHostKey.client_id == client.id, ConsoleHostKey.is_current.is_(True)
        )
    )
    old_revision = previous.trust_revision if previous else 0
    old_fingerprint = previous.fingerprint if previous else None
    if previous:
        previous.is_current, previous.replaced_at = False, clock_now(db)
        db.flush()
    db.add(
        ConsoleHostKey(
            client_id=client.id,
            ipv4=client.ipv4,
            port=client.ssh_port,
            endpoint_epoch=client.connection_epoch,
            algorithm=evidence.algorithm,
            public_key=evidence.public_key,
            fingerprint=fingerprint(evidence.public_key, evidence.algorithm),
            trust_revision=old_revision + 1,
            previous_id=previous.id if previous else None,
            accepted_by=actor.id,
            created_at=clock_now(db),
        )
    )
    event(db, actor, "credential_stored", client_id=client.id, revision=prepared.generation)
    event(
        db,
        actor,
        "host_key_accepted",
        client_id=client.id,
        old_fingerprint=old_fingerprint,
        new_fingerprint=fingerprint(evidence.public_key, evidence.algorithm),
    )
    db.flush()


def replace_verified_credential(db, actor, client_id, data, prepared):
    """Offline foundation primitive; no route can furnish validation/confirmation evidence."""
    require_actor(actor)
    require_role(actor, *ADMIN)
    client = get_or_404(db, ConsoleClient, client_id)
    if (
        client.metadata_version != prepared.expected_version
        or client.security_id != prepared.client_security_id
        or data.ipv4 != client.ipv4
        or data.ssh_port != client.ssh_port
        or data.lab_id != client.lab_id
    ):
        fail(409, "client_stale")
    verify_prepared(db, actor, data, prepared)
    old = db.get(ConsoleCredential, client.active_credential_id)
    if not old or prepared.generation != old.generation + 1:
        fail(409, "credential_generation_stale")
    rows = affected(db, client_id=client.id)
    # Production replacement preview/proof and broker fence belong to C; never allow
    # callers to treat a Boolean as live-session confirmation in this primitive.
    if rows:
        fail(503, "credential_live_replacement_requires_phase_c")
    old.replaced_at = clock_now(db)
    client.auth_method, client.ssh_username = data.auth_method, data.ssh_username
    client.connection_epoch += 1
    client.metadata_version += 1
    store_credential(db, actor, client, data, prepared)
    revoke(db, rows, "credential_changed", epoch=client.connection_epoch)
    return client_view(client, admin=True)
