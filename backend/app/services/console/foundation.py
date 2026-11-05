"""Short SQLite transactions for metadata only. No network/executor or fake connect."""

from datetime import timedelta
import hashlib
import json
import secrets
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import select

from app.core.database import clock_now
from app.models.console import (
    ConsoleAudit,
    ConsoleBmcEndpoint,
    ConsoleClient,
    ConsoleConfirmation,
    ConsoleCredential,
    ConsoleGrant,
    ConsoleHostKey,
    ConsoleMappingEvent,
    ConsoleRevocation,
    ConsoleSession,
    ConsoleTicket,
    ConsoleUartMapping,
)
from app.models.domain import CurrentUsage, Lab, LoginSession, SUT, User
from app.services.common import get_or_404, require_role
from app.services.console.targets import validate_ipv4

ADMIN = ("lab_admin", "super_admin")


def fail(status, code, **context):
    raise HTTPException(
        status, {"code": code, "message": code.replace("_", " "), "retryable": False, **context}
    )


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def canonical_hash(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")))


def require_actor(actor):
    if not actor.is_active or actor.must_change_password:
        fail(403, "console_account_denied")


def event(db, actor, kind, *, sut_id=None, **details):
    # Explicit metadata-only projection. Never forward a request/model/exception.
    allowed = {
        "client_id",
        "grant_id",
        "revision",
        "old_expiry",
        "new_expiry",
        "reason_code",
        "old_fingerprint",
        "new_fingerprint",
        "session_id",
        "key_id",
        "crypto_revision",
    }
    if set(details) - allowed:
        raise ValueError("Unapproved Console audit fields")
    db.add(
        ConsoleAudit(
            actor_id=actor.id if actor else None,
            sut_id=sut_id,
            event_type=kind,
            details=details,
            created_at=clock_now(db),
        )
    )


def client_view(client, *, admin=False):
    fields = (
        "id",
        "lab_id",
        "name",
        "ipv4",
        "ssh_port",
        "enabled",
        "notes",
        "metadata_version",
        "connection_epoch",
        "auth_method",
    )
    result = {field: getattr(client, field) for field in fields}
    result["credential_configured"] = client.active_credential_id is not None
    if admin:
        result["ssh_username"] = client.ssh_username
    return result


def mapping_view(row, transport):
    result = {"revision": row.revision if row else 0, "endpoint_epoch": row.endpoint_epoch if row else 0}
    if transport == "uart":
        result.update(
            client_id=row.client_id if row else None, tmux_session=row.tmux_session if row else None
        )
    else:
        result.update(ipv4=row.ipv4 if row else None, port=22)
    return result


def mapping_row(db, sut_id, transport):
    return db.get(ConsoleUartMapping if transport == "uart" else ConsoleBmcEndpoint, sut_id)


def affected(db, *, sut_id=None, transport=None, client_id=None):
    query = select(ConsoleSession).where(ConsoleSession.state != "closed")
    if sut_id is not None:
        query = query.where(ConsoleSession.sut_id == sut_id)
    if transport:
        query = query.where(ConsoleSession.transport == transport)
    if client_id is not None:
        query = query.where(ConsoleSession.client_id == client_id)
    return list(db.scalars(query.order_by(ConsoleSession.id)))


def sessions_hash(rows):
    return canonical_hash(
        [
            (r.id, r.attachment_generation, r.endpoint_epoch, r.client_epoch, r.trust_revision)
            for r in sorted(rows, key=lambda x: x.id)
        ]
    )


def payload(data):
    return data.model_dump(mode="json", exclude={"confirmation_id"})


def preview(db, actor, login_digest, subject, data, rows):
    require_actor(actor)
    result = {
        "affected": {
            "sut_count": len({r.sut_id for r in rows}),
            "rd_count": len({r.user_id for r in rows}),
            "session_count": len(rows),
        },
        "requires_confirmation": bool(rows),
        "confirmation_id": None,
    }
    if rows:
        token = secrets.token_urlsafe(32)
        expires = clock_now(db) + timedelta(minutes=2)
        db.add(
            ConsoleConfirmation(
                token_digest=digest(token),
                actor_id=actor.id,
                login_session_digest=login_digest,
                subject=subject,
                payload_hash=canonical_hash(payload(data)),
                sessions_hash=sessions_hash(rows),
                expires_at=expires,
                created_at=clock_now(db),
            )
        )
        result.update(confirmation_id=token, expires_at=expires)
    return result


def confirm(db, actor, login_digest, subject, data, rows):
    if not rows:
        # A supplied proof still must not be silently reused with a different operation.
        if data.confirmation_id is None:
            return
    if data.confirmation_id is None:
        fail(409, "confirmation_required")
    proof = db.get(ConsoleConfirmation, digest(data.confirmation_id.get_secret_value()))
    if (
        not proof
        or proof.used_at is not None
        or proof.expires_at <= clock_now(db)
        or proof.actor_id != actor.id
        or proof.login_session_digest != login_digest
        or proof.subject != subject
        or proof.payload_hash != canonical_hash(payload(data))
        or proof.sessions_hash != sessions_hash(rows)
    ):
        fail(409, "confirmation_stale")
    proof.used_at = clock_now(db)


def close_session(db, row, reason, *, epoch=None):
    if row.state == "closed":
        return
    db.add(
        ConsoleRevocation(
            session_id=row.id,
            attachment_generation=row.attachment_generation,
            target_epoch=epoch if epoch is not None else row.endpoint_epoch,
            reason=reason,
            created_at=clock_now(db),
        )
    )
    row.state, row.slot = "closed", None
    row.closed_at, row.close_reason = clock_now(db), reason
    # delivered_at remains NULL: no broker/network delivery is claimed in Phase B.


def revoke(db, rows, reason, *, epoch=None):
    for row in rows:
        close_session(db, row, reason, epoch=epoch)


def validate_mapping(db, sut, transport, data, settings):
    row = mapping_row(db, sut.id, transport)
    if data.expected_revision != (row.revision if row else 0):
        fail(409, "mapping_stale")
    if transport == "uart" and not data.clear:
        client = get_or_404(db, ConsoleClient, data.client_id)
        if not client.enabled:
            fail(409, "client_disabled")
        if client.lab_id != sut.lab_id:
            fail(422, "client_lab_mismatch")
        collision = db.scalar(
            select(ConsoleUartMapping.sut_id).where(
                ConsoleUartMapping.client_id == client.id,
                ConsoleUartMapping.tmux_session == data.tmux_session,
                ConsoleUartMapping.active_slot.is_(True),
                ConsoleUartMapping.sut_id != sut.id,
            )
        )
        if collision and not sut.is_archived:
            fail(409, "uart_pair_conflict", conflicting_sut_id=collision)
    if transport == "bmc" and not data.clear:
        validate_ipv4(data.ipv4, bmc=True, sensitive=settings.console_sensitive_ipv4)
    return row


def mapping_preview(db, actor, login_digest, sut_id, transport, data, settings):
    require_actor(actor)
    sut = get_or_404(db, SUT, sut_id)
    validate_mapping(db, sut, transport, data, settings)
    return preview(
        db,
        actor,
        login_digest,
        f"{transport}:{sut_id}",
        data,
        affected(db, sut_id=sut_id, transport=transport),
    )


def save_mapping(db, actor, login_digest, sut_id, transport, data, settings):
    require_actor(actor)
    sut = get_or_404(db, SUT, sut_id)
    row = validate_mapping(db, sut, transport, data, settings)
    rows = affected(db, sut_id=sut_id, transport=transport)
    confirm(db, actor, login_digest, f"{transport}:{sut_id}", data, rows)
    old = mapping_view(row, transport)
    old_keys = (
        list(
            db.scalars(
                select(ConsoleHostKey).where(
                    ConsoleHostKey.bmc_sut_id == sut_id, ConsoleHostKey.is_current.is_(True)
                )
            )
        )
        if transport == "bmc"
        else []
    )
    if row is None:
        row = ConsoleUartMapping(sut_id=sut_id) if transport == "uart" else ConsoleBmcEndpoint(sut_id=sut_id)
        row.revision, row.endpoint_epoch = 0, 0
        db.add(row)
    if transport == "uart":
        row.client_id = None if data.clear else data.client_id
        row.tmux_session = None if data.clear else data.tmux_session
        row.active_slot = not data.clear and not sut.is_archived
    else:
        row.ipv4 = None if data.clear else data.ipv4
        for key in old_keys:
            key.is_current, key.replaced_at = False, clock_now(db)
    row.revision += 1
    row.endpoint_epoch += 1
    row.updated_at, row.updated_by = clock_now(db), actor.id
    db.flush()
    new = mapping_view(row, transport)
    db.add(
        ConsoleMappingEvent(
            sut_id=sut_id,
            transport=transport,
            actor_id=actor.id,
            old=old,
            new=new,
            reason=data.reason,
            created_at=clock_now(db),
        )
    )
    revoke(db, rows, "mapping_changed", epoch=row.endpoint_epoch)
    event(db, actor, "mapping_changed", sut_id=sut_id, revision=row.revision)
    return {**new, "revocation_delivery": "pending" if rows else "none"}


def client_preview(db, actor, login_digest, client_id, data):
    require_actor(actor)
    require_role(actor, *ADMIN)
    client = get_or_404(db, ConsoleClient, client_id)
    if client.metadata_version != data.expected_version:
        fail(409, "client_stale")
    if {"ipv4", "ssh_port", "ssh_username", "auth_method", "secret"} & data.model_fields_set:
        fail(503, "client_validation_unavailable")
    rows = affected(db, client_id=client.id) if data.enabled is False and client.enabled else []
    return preview(db, actor, login_digest, f"client:{client.id}", data, rows)


def save_client_metadata(db, actor, login_digest, client_id, data):
    require_actor(actor)
    require_role(actor, *ADMIN)
    client = get_or_404(db, ConsoleClient, client_id)
    if client.metadata_version != data.expected_version:
        fail(409, "client_stale")
    if {"ipv4", "ssh_port", "ssh_username", "auth_method", "secret"} & data.model_fields_set:
        fail(503, "client_validation_unavailable")
    rows = affected(db, client_id=client.id) if data.enabled is False and client.enabled else []
    confirm(db, actor, login_digest, f"client:{client.id}", data, rows)
    if data.lab_id is not None and data.lab_id != client.lab_id:
        bindings = list(
            db.scalars(select(ConsoleUartMapping.sut_id).where(ConsoleUartMapping.client_id == client.id))
        )
        if bindings:
            fail(409, "client_has_retained_bindings", sut_ids=bindings)
        get_or_404(db, Lab, data.lab_id)
        client.lab_id = data.lab_id
    if data.name is not None:
        if not data.name.strip():
            fail(422, "client_name_blank")
        client.name, client.normalized_name = data.name.strip(), data.name.strip().casefold()
    if data.notes is not None:
        client.notes = data.notes
    if data.enabled is not None and data.enabled != client.enabled:
        if data.enabled and not client.active_credential_id:
            fail(409, "client_validation_required")
        client.enabled = data.enabled
        client.connection_epoch += 1
        revoke(db, rows, "client_disabled", epoch=client.connection_epoch)
    client.metadata_version += 1
    client.updated_at, client.updated_by = clock_now(db), actor.id
    db.flush()  # triggers update active slots; collisions rollback whole transaction
    event(db, actor, "client_metadata_changed", client_id=client.id, revision=client.metadata_version)
    return client_view(client, admin=True)


def authorization(db, user, login_digest, sut, settings, *, now=None):
    """Pure, no writes: mapping/settings editing deliberately has a different guard."""
    now = now or clock_now(db)
    login = db.get(LoginSession, login_digest)
    if (
        not settings.console_enabled
        or not user.is_active
        or user.must_change_password
        or sut.is_archived
        or not login
        or login.user_id != user.id
        or login.expires_at <= now
    ):
        return {"mode": "deny", "grant_id": None, "usage_key": None}
    usage = db.scalar(
        select(CurrentUsage).where(CurrentUsage.sut_id == sut.id, CurrentUsage.user_id == user.id)
    )
    grant = db.scalar(
        select(ConsoleGrant).where(
            ConsoleGrant.sut_id == sut.id,
            ConsoleGrant.user_id == user.id,
            ConsoleGrant.state == "active",
            ConsoleGrant.created_at <= now,
            ConsoleGrant.expires_at > now,
        )
    )
    if sut.operational_state == "normal":
        grant = None
    independent = (
        user.role in ADMIN or usage is not None or settings.console_access_policy == "all_authenticated"
    )
    mode = (
        "write"
        if independent or grant
        else ("read" if settings.console_access_policy == "shared_readonly" else "deny")
    )
    return {
        "mode": mode,
        "grant_id": grant.id if grant and not independent else None,
        "usage_key": usage.usage_key if usage else None,
    }


def grant_view(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "sut_id",
            "user_id",
            "admin_id",
            "created_at",
            "expires_at",
            "reason",
            "state",
            "revision",
            "closed_at",
            "close_reason",
        )
    }


def settle_grants(db, now):
    for row in db.scalars(select(ConsoleGrant).where(ConsoleGrant.state == "active")):
        sut = db.get(SUT, row.sut_id)
        reason = (
            "grant_expired"
            if row.expires_at <= now
            else "sut_normal"
            if sut.operational_state == "normal"
            else "sut_archived"
            if sut.is_archived
            else None
        )
        if reason:
            row.state = "expired" if reason == "grant_expired" else "revoked"
            row.closed_at, row.close_reason, row.revision = now, reason, row.revision + 1
            event(db, None, reason, sut_id=row.sut_id, grant_id=row.id)
            reevaluate_grant_sessions(db, row, reason, now)
    db.flush()


def reevaluate_grant_sessions(db, grant, reason, now):
    from types import SimpleNamespace

    sut = db.get(SUT, grant.sut_id)
    for session in db.scalars(
        select(ConsoleSession).where(ConsoleSession.grant_id == grant.id, ConsoleSession.state != "closed")
    ):
        user = db.get(User, session.user_id)
        # Exclude the closing grant; another source must independently authorize.
        settings = SimpleNamespace(console_enabled=True, console_access_policy=session.policy)
        auth = authorization(db, user, session.login_session_digest, sut, settings, now=now)
        if auth["mode"] == "deny":
            close_session(db, session, reason)
        else:
            session.grant_id, session.mode = None, auth["mode"]


def create_grant(db, actor, sut_id, data):
    require_actor(actor)
    require_role(actor, *ADMIN)
    now = clock_now(db)
    settle_grants(db, now)
    sut, target = get_or_404(db, SUT, sut_id), get_or_404(db, User, data.user_id)
    if (
        sut.is_archived
        or sut.operational_state == "normal"
        or not target.is_active
        or target.must_change_password
    ):
        fail(409, "grant_target_ineligible")
    row = ConsoleGrant(
        sut_id=sut_id,
        user_id=target.id,
        admin_id=actor.id,
        created_at=now,
        expires_at=now + timedelta(hours=data.duration_hours),
        reason=data.reason,
    )
    db.add(row)
    db.flush()
    event(db, actor, "grant_created", sut_id=sut_id, grant_id=row.id)
    return grant_view(row)


def extend_grant(db, actor, grant_id, data):
    require_actor(actor)
    require_role(actor, *ADMIN)
    row = get_or_404(db, ConsoleGrant, grant_id)
    now = clock_now(db)
    sut = db.get(SUT, row.sut_id)
    if (
        row.revision != data.expected_revision
        or row.state != "active"
        or row.expires_at <= now
        or sut.is_archived
        or sut.operational_state == "normal"
    ):
        fail(409, "grant_stale_or_expired")
    if not row.expires_at < data.new_expires_at <= row.created_at + timedelta(hours=24):
        fail(422, "grant_extension_out_of_bounds")
    old = row.expires_at
    row.expires_at, row.revision = data.new_expires_at, row.revision + 1
    event(
        db,
        actor,
        "grant_extended",
        sut_id=row.sut_id,
        grant_id=row.id,
        old_expiry=old.isoformat(),
        new_expiry=row.expires_at.isoformat(),
    )
    return grant_view(row)


def revoke_grant(db, actor, grant_id, expected_revision):
    require_actor(actor)
    require_role(actor, *ADMIN)
    row = get_or_404(db, ConsoleGrant, grant_id)
    if row.revision != expected_revision or row.state != "active" or row.expires_at <= clock_now(db):
        fail(409, "grant_stale_or_expired")
    # Preserve original expiry and creation time; revocation is a separate transition.
    row.state, row.closed_at, row.close_reason = "revoked", clock_now(db), "admin_revoked"
    row.revision += 1
    event(db, actor, "grant_revoked", sut_id=row.sut_id, grant_id=row.id)
    reevaluate_grant_sessions(db, row, "grant_revoked", clock_now(db))
    return grant_view(row)


def current_key(db, *, client_id=None, sut_id=None):
    query = select(ConsoleHostKey).where(ConsoleHostKey.is_current.is_(True))
    return db.scalar(
        query.where(ConsoleHostKey.client_id == client_id)
        if client_id is not None
        else query.where(ConsoleHostKey.bmc_sut_id == sut_id)
    )


def endpoint_context(db, sut, transport, settings):
    row = mapping_row(db, sut.id, transport)
    if not row:
        fail(409, "not_configured")
    client, credential = None, None
    if transport == "uart":
        client = db.get(ConsoleClient, row.client_id) if row.client_id else None
        if not client or not client.enabled or client.lab_id != sut.lab_id:
            fail(409, "client_disabled_or_not_configured")
        credential = (
            db.get(ConsoleCredential, client.active_credential_id) if client.active_credential_id else None
        )
        key = current_key(db, client_id=client.id)
        validate_ipv4(client.ipv4, sensitive=settings.console_sensitive_ipv4)
        if (
            not credential
            or credential.client_security_id != client.security_id
            or credential.replaced_at
            or credential.method != client.auth_method
            or not key
            or key.ipv4 != client.ipv4
            or key.port != client.ssh_port
        ):
            fail(409, "client_validation_required")
    else:
        if not row.ipv4:
            fail(409, "not_configured")
        validate_ipv4(row.ipv4, bmc=True, sensitive=settings.console_sensitive_ipv4)
        key = current_key(db, sut_id=sut.id)
        if not key or key.ipv4 != row.ipv4 or key.port != 22 or key.endpoint_epoch != row.endpoint_epoch:
            fail(409, "host_key_unverified")
    return row, client, credential, key


def cleanup(db, now, *, settings=None):
    from types import SimpleNamespace

    settle_grants(db, now)
    for row in db.scalars(select(ConsoleSession).where(ConsoleSession.state != "closed")):
        login, user, sut = (
            db.get(LoginSession, row.login_session_digest),
            db.get(User, row.user_id),
            db.get(SUT, row.sut_id),
        )
        if (
            row.lease_until <= now
            or not login
            or login.expires_at <= now
            or not user.is_active
            or user.must_change_password
            or sut.is_archived
        ):
            close_session(db, row, "authorization_expired")
        else:
            policy = settings or SimpleNamespace(console_enabled=True, console_access_policy=row.policy)
            auth = authorization(db, user, row.login_session_digest, sut, policy, now=now)
            if auth["mode"] == "deny":
                close_session(db, row, "authorization_revoked")
            else:
                row.mode = auth["mode"]
    db.flush()


def reserve_session(db, actor, login_digest, sut_id, transport, instance_id, origin, settings):
    if transport not in ("uart", "bmc"):
        fail(422, "transport_invalid")
    normalize_origin(origin, settings)
    cleanup(db, clock_now(db), settings=settings)
    sut = get_or_404(db, SUT, sut_id)
    auth = authorization(db, actor, login_digest, sut, settings)
    if auth["mode"] == "deny":
        fail(403, "console_access_denied")
    mapping, client, credential, key = endpoint_context(db, sut, transport, settings)
    occupied = set(
        db.scalars(
            select(ConsoleSession.slot).where(
                ConsoleSession.user_id == actor.id, ConsoleSession.state != "closed"
            )
        )
    )
    slot = next((n for n in range(1, 11) if n not in occupied), None)
    if slot is None:
        fail(429, "quota_exceeded")
    login = db.get(LoginSession, login_digest)
    expiry = min(clock_now(db) + timedelta(seconds=30), login.expires_at)
    if auth["grant_id"]:
        expiry = min(expiry, db.get(ConsoleGrant, auth["grant_id"]).expires_at)
    row = ConsoleSession(
        user_id=actor.id,
        sut_id=sut_id,
        transport=transport,
        mode=auth["mode"],
        policy=settings.console_access_policy,
        login_session_digest=login_digest,
        slot=slot,
        instance_id=instance_id,
        lease_until=expiry,
        endpoint_epoch=mapping.endpoint_epoch,
        client_id=client.id if client else None,
        client_epoch=client.connection_epoch if client else 0,
        credential_generation=credential.generation if credential else 0,
        trust_revision=key.trust_revision,
        grant_id=auth["grant_id"],
        usage_key=auth["usage_key"],
        created_at=clock_now(db),
    )
    db.add(row)
    db.flush()
    token = issue_ticket(db, row, origin)
    return row, token


def normalize_origin(origin, settings):
    try:
        parsed = urlsplit(origin)
        valid = parsed.scheme in ("http", "https") and parsed.hostname and parsed.port != 0
        valid = valid and not (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path
        )
        if not valid or parsed.scheme + "://" + parsed.netloc != origin:
            raise ValueError()
        if parsed.scheme == "http" and not settings.console_allow_insecure_http:
            fail(403, "console_http_not_opted_in")
    except ValueError:
        fail(403, "console_origin_invalid")
    return origin


def issue_ticket(db, session, origin):
    token = secrets.token_urlsafe(32)
    db.add(
        ConsoleTicket(
            token_digest=digest(token),
            session_id=session.id,
            user_id=session.user_id,
            login_session_digest=session.login_session_digest,
            origin=origin,
            attachment_generation=session.attachment_generation,
            endpoint_epoch=session.endpoint_epoch,
            expires_at=session.lease_until,
            created_at=clock_now(db),
        )
    )
    return token


def consume_ticket(db, actor, login_digest, session_id, token, origin, generation, settings):
    normalize_origin(origin, settings)
    row, ticket = (
        db.get(ConsoleSession, session_id),
        db.scalar(select(ConsoleTicket).where(ConsoleTicket.token_digest == digest(token))),
    )
    if (
        not row
        or not ticket
        or row.state == "closed"
        or ticket.session_id != row.id
        or row.user_id != actor.id
        or row.login_session_digest != login_digest
        or ticket.login_session_digest != login_digest
        or ticket.used_at is not None
        or ticket.expires_at <= clock_now(db)
        or row.lease_until <= clock_now(db)
        or ticket.origin != origin
        or ticket.attachment_generation != generation
        or row.attachment_generation != generation
        or ticket.endpoint_epoch != row.endpoint_epoch
    ):
        fail(403, "console_ticket_invalid")
    sut = db.get(SUT, row.sut_id)
    auth = authorization(db, actor, login_digest, sut, settings)
    mapping, client, credential, key = endpoint_context(db, sut, row.transport, settings)
    if (
        auth["mode"] == "deny"
        or mapping.endpoint_epoch != row.endpoint_epoch
        or key.trust_revision != row.trust_revision
        or (
            client
            and (
                client.connection_epoch != row.client_epoch
                or credential.generation != row.credential_generation
            )
        )
    ):
        fail(403, "console_ticket_stale")
    ticket.used_at = clock_now(db)
    # Foundation only; redemption is NOT a successful SSH connection.
    return row


def reconnect_reservation(db, actor, login_digest, session_id, generation, origin, settings):
    """Same quota slot, fresh ticket/generation; still no network or input buffering."""
    normalize_origin(origin, settings)
    row = get_or_404(db, ConsoleSession, session_id)
    if (
        row.user_id != actor.id
        or row.login_session_digest != login_digest
        or row.state == "closed"
        or row.attachment_generation != generation
        or row.lease_until <= clock_now(db)
    ):
        fail(409, "console_attachment_stale")
    sut = db.get(SUT, row.sut_id)
    auth = authorization(db, actor, login_digest, sut, settings)
    mapping, client, credential, key = endpoint_context(db, sut, row.transport, settings)
    if (
        auth["mode"] == "deny"
        or mapping.endpoint_epoch != row.endpoint_epoch
        or key.trust_revision != row.trust_revision
        or client
        and (
            client.connection_epoch != row.client_epoch or credential.generation != row.credential_generation
        )
    ):
        fail(403, "console_attachment_revoked")
    row.attachment_generation += 1
    row.state, row.mode = "reserved", auth["mode"]
    row.lease_until = min(
        clock_now(db) + timedelta(seconds=30), db.get(LoginSession, login_digest).expires_at
    )
    if auth["grant_id"]:
        row.lease_until = min(row.lease_until, db.get(ConsoleGrant, auth["grant_id"]).expires_at)
    row.grant_id = auth["grant_id"]
    return row, issue_ticket(db, row, origin)


def close_generation(db, actor, login_digest, session_id, generation):
    row = get_or_404(db, ConsoleSession, session_id)
    if (
        row.user_id != actor.id
        or row.login_session_digest != login_digest
        or row.attachment_generation != generation
    ):
        fail(409, "console_attachment_stale")
    close_session(db, row, "explicit_disconnect")
