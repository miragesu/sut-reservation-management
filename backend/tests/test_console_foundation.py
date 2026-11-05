"""Synthetic DB/crypto tests only: no SSH, BMC, UART or production credentials."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import json
import os
import secrets
from threading import Barrier

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import HTTPException
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.database import unit_of_work
from app.models.console import (
    ConsoleAudit,
    ConsoleClient,
    ConsoleCredential,
    ConsoleGrant,
    ConsoleHostKey,
    ConsoleRevocation,
    ConsoleSession,
    ConsoleTicket,
    ConsoleUartMapping,
)
from app.models.domain import CurrentUsage, LoginSession, SUT, User
from app.schemas.console import ClientInput, UartInput
from app.services.console import foundation as f
from app.services.console.credentials import (
    HostEvidence,
    create_verified_client,
    prepare,
    replace_verified_credential,
    UnavailableValidation,
)
from app.services.console.crypto import Envelope, EnvelopeCipher, SecretUnavailable
from app.services.console.targets import validate_ipv4
from conftest import csrf, identity, mutate, sign_in


class SyntheticVerifier:
    """Test-only implementation; never imported/installed by application code."""

    def __init__(self, now):
        self.now = now
        self.public = (
            Ed25519PrivateKey.generate()
            .public_key()
            .public_bytes(Encoding.OpenSSH, PublicFormat.OpenSSH)
            .decode()
        )

    def verify(self, candidate_hash, actor_id, ipv4, port):
        return HostEvidence(
            actor_id, candidate_hash, ipv4, port, "ssh-ed25519", self.public, self.now + timedelta(minutes=2)
        )


def cmutate(client, method, path, data=None):
    return client.request(
        method,
        "/api/v1/console" + path,
        json=data,
        headers={"X-CSRF-Token": csrf(client), "Origin": "http://testserver"},
    )


@pytest.fixture
def console_arena(arena, application):
    clients, sut, sut2, clock = arena
    settings = application.state.settings
    settings.console_enabled = True
    settings.console_allow_insecure_http = True
    settings.console_access_policy = "all_authenticated"
    cipher = EnvelopeCipher({"test-key": os.urandom(32)}, "test-key")
    actor_id = identity(application, "root")
    with unit_of_work(application.state.engine) as db:
        lab_id = db.get(SUT, sut).lab_id
    data = ClientInput(
        lab_id=lab_id,
        name="Synthetic Client",
        ipv4="192.168.234.10",
        ssh_username="synthetic-console",
        auth_method="password",
        secret=secrets.token_urlsafe(24),
    )
    prepared = prepare(data, actor_id, cipher, verifier=SyntheticVerifier(clock.now))
    with unit_of_work(application.state.engine, write=True) as db:
        db.info["clock"] = lambda: clock.now
        client = create_verified_client(db, db.get(User, actor_id), data, prepared)
    response = cmutate(
        clients["rd"],
        "PUT",
        f"/suts/{sut}/uart",
        {"expected_revision": 0, "client_id": client["id"], "tmux_session": "existing_target"},
    )
    assert response.status_code == 200, response.text
    return clients, sut, sut2, clock, client["id"], cipher, data


def context(application, db, name="rd"):
    actor = db.get(User, identity(application, name))
    login = db.scalar(select(LoginSession).where(LoginSession.user_id == actor.id))
    return actor, login.id


def reserve(application, db, sut, clock, *, name="rd", instance="test-tab"):
    db.info["clock"] = lambda: clock.now
    actor, login = context(application, db, name)
    return f.reserve_session(
        db, actor, login, sut, "uart", instance, "http://testserver", application.state.settings
    )


@pytest.mark.parametrize("field", ["console_enabled", "console_allow_insecure_http"])
@pytest.mark.parametrize("bad", ["yes", "1", "enabled", "", 1, None])
def test_strict_flags(field, bad):
    with pytest.raises(ValueError):
        Settings(secret_key=secrets.token_urlsafe(48), **{field: bad})


def test_defaults_policy_and_deny_config():
    settings = Settings(secret_key=secrets.token_urlsafe(48))
    assert not settings.console_enabled and not settings.console_allow_insecure_http
    assert settings.console_access_policy == "claim_only"
    for extra in ({"console_access_policy": "allow_all"}, {"console_sensitive_ipv4": ["0177.0.0.1"]}):
        with pytest.raises(ValueError):
            Settings(secret_key=secrets.token_urlsafe(48), **extra)


def test_disabled_console_no_mutation(root, application):
    assert root.get("/api/v1/console/clients").status_code == 404
    assert cmutate(root, "POST", "/clients", {}).status_code == 404
    with unit_of_work(application.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(ConsoleClient)) == 0
    application.state.settings.console_enabled = True
    assert root.get("/api/v1/console/clients").status_code == 403


@pytest.mark.parametrize(
    "address",
    [
        "8.8.8.8",
        "203.0.113.5",
        "127.0.0.1",
        "169.254.169.254",
        "224.0.0.1",
        "0.0.0.0",
        "255.255.255.255",
        "10.0.0.0",
        "10.255.255.255",
        "10.001.2.3",
        "0x0a000001",
        "::ffff:10.1.2.3",
        "example.invalid",
    ],
)
def test_bmc_unsafe_targets(address):
    with pytest.raises(HTTPException):
        validate_ipv4(address, bmc=True, local=set())


@pytest.mark.parametrize("address", ["10.123.45.67", "172.16.40.20", "172.31.8.20", "192.168.234.10"])
def test_bmc_private_without_lab_allowlist(address):
    assert validate_ipv4(address, bmc=True, local=set()) == address
    with pytest.raises(HTTPException):
        validate_ipv4(address, bmc=True, sensitive=[address], local=set())
    with pytest.raises(HTTPException):
        validate_ipv4(address, bmc=True, local={address})


def test_validation_boundary_and_secret_projection(console_arena, application, caplog):
    clients, sut, _, clock, client_id, cipher, data = console_arena
    secret = data.secret.get_secret_value()
    payload = data.model_dump(mode="json")
    payload["secret"] = secret
    for path in ("/clients", "/client-validations"):
        response = cmutate(clients["root"], "POST", path, payload)
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "client_validation_unavailable"
        assert secret not in response.text
    assert cmutate(clients["rd"], "POST", "/clients", payload).status_code == 403
    assert (
        cmutate(
            clients["root"], "PATCH", f"/clients/{client_id}", {"expected_version": 1, "secret": secret}
        ).status_code
        == 503
    )
    assert cmutate(clients["rd"], "POST", "/trust/accept", {}).status_code == 503
    payload["verified"] = True
    assert cmutate(clients["root"], "POST", "/clients", payload).status_code == 422
    with pytest.raises(HTTPException) as error:
        prepare(data, identity(application, "root"), cipher, verifier=UnavailableValidation())
    assert secret not in str(error.value)
    rd_rows = clients["rd"].get("/api/v1/console/clients").json()
    assert "ssh_username" not in rd_rows["items"][0]
    with unit_of_work(application.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(ConsoleClient)) == 1
        credential = db.scalar(select(ConsoleCredential))
        assert secret.encode() not in credential.ciphertext
        assert secret not in str(db.scalar(select(ConsoleAudit)).details)
    assert secret not in caplog.text
    assert secret not in clients["root"].get("/api/v1/console/clients").text
    # No real terminal, generic exec or WS routes are added.
    paths = {getattr(route, "path", "") for route in application.routes}
    assert not any(path.startswith("/ws/") for path in paths)
    assert "/api/v1/console/exec" not in paths and "/api/v1/console/sessions" not in paths


def test_console_csrf_origin_and_password_gate(console_arena):
    clients, sut, *_ = console_arena
    data = {"expected_revision": 0, "ipv4": "192.168.234.20"}
    path = f"/api/v1/console/suts/{sut}/bmc"
    assert clients["rd"].put(path, json=data).status_code == 403
    assert (
        clients["rd"]
        .put(path, json=data, headers={"X-CSRF-Token": csrf(clients["rd"]), "Origin": "http://evil.invalid"})
        .status_code
        == 403
    )
    sign_in(clients["rd"], "temp")
    assert clients["rd"].get("/api/v1/console/clients").status_code == 403


def test_mapping_separate_versions_clear_history(console_arena, application):
    clients, sut, _, _, _, _, _ = console_arena
    assert (
        cmutate(
            clients["rd"],
            "PUT",
            f"/suts/{sut}/bmc",
            {"expected_revision": 0, "ipv4": "192.168.234.20", "reason": ""},
        ).status_code
        == 200
    )
    state = clients["rd"].get(f"/api/v1/console/suts/{sut}/connections").json()
    assert state["uart"]["revision"] == state["bmc"]["revision"] == 1
    assert state["bmc"]["port"] == 22 and not state["terminal_available"]
    assert (
        cmutate(clients["rd"], "PUT", f"/suts/{sut}/bmc", {"expected_revision": 0, "clear": True}).status_code
        == 409
    )
    assert (
        cmutate(
            clients["rd"],
            "PUT",
            f"/suts/{sut}/bmc",
            {"expected_revision": 1, "ipv4": "192.168.234.20", "port": 23},
        ).status_code
        == 422
    )
    assert (
        cmutate(
            clients["rd"], "PUT", f"/suts/{sut}/uart", {"expected_revision": 1, "clear": True}
        ).status_code
        == 200
    )
    state = clients["rd"].get(f"/api/v1/console/suts/{sut}/connections").json()
    assert (
        state["uart"]["revision"] == 2
        and state["uart"]["client_id"] is None
        and state["bmc"]["revision"] == 1
    )
    history = clients["lab"].get(f"/api/v1/console/suts/{sut}/history").json()["items"]
    assert len(history) == 3 and history[0]["transport"] == "uart"
    with pytest.raises(IntegrityError), unit_of_work(application.state.engine, write=True) as db:
        db.execute(text("DELETE FROM console_mapping_events"))


def test_same_lab_and_active_pair_uniqueness(console_arena, application):
    clients, sut, sut2, _, client_id, _, _ = console_arena
    assert (
        cmutate(
            clients["rd"],
            "PUT",
            f"/suts/{sut2}/uart",
            {"expected_revision": 0, "client_id": client_id, "tmux_session": "existing_target"},
        ).status_code
        == 422
    )
    with unit_of_work(application.state.engine, write=True) as db:
        source = db.get(SUT, sut)
        another = SUT(
            lab_id=source.lab_id,
            name="Synthetic extra",
            normalized_name="synthetic extra",
            platform="mock",
            owner_team="mock",
        )
        db.add(another)
        db.flush()
        other_id = another.id
    assert (
        cmutate(
            clients["rd"],
            "PUT",
            f"/suts/{other_id}/uart",
            {"expected_revision": 0, "client_id": client_id, "tmux_session": "existing_target"},
        ).status_code
        == 409
    )
    with pytest.raises(IntegrityError), unit_of_work(application.state.engine, write=True) as db:
        db.add(
            ConsoleUartMapping(
                sut_id=sut2,
                client_id=client_id,
                tmux_session="other",
                active_slot=True,
                updated_by=identity(application, "root"),
            )
        )
    with pytest.raises(IntegrityError), unit_of_work(application.state.engine, write=True) as db:
        db.execute(
            text(
                "UPDATE console_clients SET lab_id=(SELECT lab_id FROM suts WHERE id=:sut) WHERE id=:client"
            ),
            {"sut": sut2, "client": client_id},
        )


def test_client_metadata_roles_versions_and_disable(console_arena, application):
    clients, sut, _, clock, client_id, *_ = console_arena
    assert (
        cmutate(
            clients["rd"], "PATCH", f"/clients/{client_id}", {"expected_version": 1, "notes": "mock"}
        ).status_code
        == 403
    )
    response = cmutate(
        clients["lab"],
        "PATCH",
        f"/clients/{client_id}",
        {"expected_version": 1, "name": "  Changed mock  ", "notes": "mock"},
    )
    assert response.status_code == 200 and response.json()["connection_epoch"] == 1
    assert (
        cmutate(
            clients["root"], "PATCH", f"/clients/{client_id}", {"expected_version": 1, "enabled": False}
        ).status_code
        == 409
    )
    assert (
        cmutate(
            clients["root"], "PATCH", f"/clients/{client_id}", {"expected_version": 2, "enabled": False}
        ).status_code
        == 200
    )
    with unit_of_work(application.state.engine) as db:
        assert not db.get(ConsoleUartMapping, sut).active_slot
    assert (
        cmutate(
            clients["rd"],
            "PUT",
            f"/suts/{sut}/uart",
            {"expected_revision": 1, "client_id": client_id, "tmux_session": "other"},
        ).status_code
        == 409
    )
    assert clients["rd"].get("/api/v1/console/clients").json()["items"] == []
    assert (
        clients["rd"].get(f"/api/v1/console/suts/{sut}/connections").json()["uart"]["client"]["enabled"]
        is False
    )
    assert (
        cmutate(
            clients["root"], "PATCH", f"/clients/{client_id}", {"expected_version": 3, "enabled": True}
        ).status_code
        == 200
    )
    with unit_of_work(application.state.engine, write=True) as db:
        reserve(application, db, sut, clock)


def test_impact_confirmation_binds_exact_generations(console_arena, application):
    clients, sut, _, clock, *_ = console_arena
    with unit_of_work(application.state.engine, write=True) as db:
        session, _ = reserve(application, db, sut, clock)
        session_id = session.id
    update = {"expected_revision": 1, "clear": True}
    assert cmutate(clients["rd"], "PUT", f"/suts/{sut}/uart", update).status_code == 409
    preview = cmutate(clients["rd"], "POST", f"/suts/{sut}/uart/preview", update).json()
    assert preview["affected"] == {"sut_count": 1, "rd_count": 1, "session_count": 1}
    with unit_of_work(application.state.engine, write=True) as db:
        db.get(ConsoleSession, session_id).attachment_generation += 1
    update["confirmation_id"] = preview["confirmation_id"]
    assert cmutate(clients["rd"], "PUT", f"/suts/{sut}/uart", update).status_code == 409
    preview = cmutate(clients["rd"], "POST", f"/suts/{sut}/uart/preview", update).json()
    update["confirmation_id"] = preview["confirmation_id"]
    response = cmutate(clients["rd"], "PUT", f"/suts/{sut}/uart", update)
    assert response.status_code == 200 and response.json()["revocation_delivery"] == "pending"
    with unit_of_work(application.state.engine) as db:
        session = db.get(ConsoleSession, session_id)
        assert session.state == "closed" and session.slot is None
        outbox = db.scalar(select(ConsoleRevocation))
        assert outbox.attachment_generation == 2 and outbox.delivered_at is None


@pytest.mark.parametrize(
    "policy,holder,role,expected",
    [
        ("claim_only", False, "user", "deny"),
        ("claim_only", True, "user", "write"),
        ("shared_readonly", False, "user", "read"),
        ("shared_readonly", True, "user", "write"),
        ("all_authenticated", False, "user", "write"),
        ("all_authenticated", True, "user", "write"),
        *[
            (p, False, r, "write")
            for p in ("claim_only", "shared_readonly", "all_authenticated")
            for r in ("lab_admin", "super_admin")
        ],
    ],
)
def test_policy_matrix(console_arena, application, policy, holder, role, expected):
    _, sut, _, clock, *_ = console_arena
    settings = application.state.settings
    settings.console_access_policy = policy
    with unit_of_work(application.state.engine, write=True) as db:
        db.info["clock"] = lambda: clock.now
        user, login = context(application, db)
        user.role = role
        if holder:
            db.add(
                CurrentUsage(
                    sut_id=sut,
                    user_id=user.id,
                    start_time=clock.now,
                    expected_end_time=clock.now + timedelta(hours=1),
                )
            )
            db.flush()
        assert f.authorization(db, user, login, db.get(SUT, sut), settings)["mode"] == expected
        user.is_active = False
        assert f.authorization(db, user, login, db.get(SUT, sut), settings)["mode"] == "deny"
        user.is_active, user.must_change_password = True, True
        assert f.authorization(db, user, login, db.get(SUT, sut), settings)["mode"] == "deny"
        user.must_change_password = False
        db.get(LoginSession, login).expires_at = clock.now
        assert f.authorization(db, user, login, db.get(SUT, sut), settings)["mode"] == "deny"


@pytest.mark.parametrize("hours", [1, 2, 4, 8, 12, 24])
def test_grant_presets_no_coordination_side_effects(console_arena, application, hours):
    clients, sut, _, clock, *_ = console_arena
    response = mutate(
        clients["root"],
        "PATCH",
        f"/api/v1/suts/{sut}/operational-state",
        {"state": "maintenance", "reason": "synthetic"},
    )
    assert response.status_code == 200
    with unit_of_work(application.state.engine) as db:
        before = {
            table: db.scalar(text("SELECT count(*) FROM " + table))
            for table in (
                "notifications",
                "current_usages",
                "reservations",
                "queue_entries",
                "usage_histories",
            )
        }
    response = cmutate(
        clients["lab"],
        "POST",
        f"/suts/{sut}/grants",
        {"user_id": identity(application, "rd"), "duration_hours": hours},
    )
    assert response.status_code == 201, response.text
    application.state.settings.console_access_policy = "claim_only"
    with unit_of_work(application.state.engine) as db:
        db.info["clock"] = lambda: clock.now
        user, login = context(application, db)
        row = db.scalar(select(ConsoleGrant))
        assert row.expires_at == clock.now + timedelta(hours=hours)
        assert (
            f.authorization(db, user, login, db.get(SUT, sut), application.state.settings)["mode"] == "write"
        )
        assert before == {table: db.scalar(text("SELECT count(*) FROM " + table)) for table in before}


def test_grant_extend_expire_new_grant_and_independent_peers(console_arena, application):
    clients, sut, _, clock, *_ = console_arena
    assert (
        mutate(
            clients["root"],
            "PATCH",
            f"/api/v1/suts/{sut}/operational-state",
            {"state": "maintenance", "reason": "synthetic"},
        ).status_code
        == 200
    )
    rd = identity(application, "rd")
    first = cmutate(
        clients["root"], "POST", f"/suts/{sut}/grants", {"user_id": rd, "duration_hours": 1}
    ).json()
    second = cmutate(
        clients["root"],
        "POST",
        f"/suts/{sut}/grants",
        {"user_id": identity(application, "lab"), "duration_hours": 2},
    ).json()
    assert (
        cmutate(
            clients["root"], "POST", f"/suts/{sut}/grants", {"user_id": rd, "duration_hours": 1}
        ).status_code
        == 409
    )
    payload = {
        "expected_revision": 1,
        "new_expires_at": (clock.now + timedelta(hours=24, microseconds=1)).isoformat(),
    }
    assert cmutate(clients["root"], "PATCH", f"/grants/{first['id']}", payload).status_code == 422
    payload["new_expires_at"] = (clock.now + timedelta(hours=24)).isoformat()
    assert cmutate(clients["root"], "PATCH", f"/grants/{first['id']}", payload).status_code == 200
    application.state.settings.console_access_policy = "claim_only"
    with unit_of_work(application.state.engine, write=True) as db:
        row, _ = reserve(application, db, sut, clock)
        session_id = row.id
        row.lease_until = clock.now + timedelta(hours=24)
    clock.advance(hours=24)
    fresh = cmutate(clients["root"], "POST", f"/suts/{sut}/grants", {"user_id": rd, "duration_hours": 1})
    assert fresh.status_code == 201 and fresh.json()["id"] != first["id"]
    with unit_of_work(application.state.engine) as db:
        assert db.get(ConsoleGrant, first["id"]).state == "expired"
        assert db.get(ConsoleGrant, second["id"]).state == "expired"
        assert db.get(ConsoleSession, session_id).state == "closed"
    assert (
        cmutate(
            clients["root"],
            "PATCH",
            f"/grants/{first['id']}",
            {"expected_revision": 2, "new_expires_at": (clock.now + timedelta(hours=1)).isoformat()},
        ).status_code
        == 409
    )


def test_grant_revoke_preserves_alternate_right_and_normal_permanent(console_arena, application):
    clients, sut, _, clock, *_ = console_arena
    mutate(
        clients["root"],
        "PATCH",
        f"/api/v1/suts/{sut}/operational-state",
        {"state": "maintenance", "reason": "synthetic"},
    )
    row = cmutate(
        clients["root"],
        "POST",
        f"/suts/{sut}/grants",
        {"user_id": identity(application, "rd"), "duration_hours": 2},
    ).json()
    application.state.settings.console_access_policy = "claim_only"
    with unit_of_work(application.state.engine, write=True) as db:
        session, _ = reserve(application, db, sut, clock)
        session_id = session.id
        db.add(
            CurrentUsage(
                sut_id=sut,
                user_id=identity(application, "rd"),
                start_time=clock.now,
                expected_end_time=clock.now + timedelta(hours=1),
            )
        )
    response = cmutate(clients["root"], "POST", f"/grants/{row['id']}/revoke", {"expected_revision": 1})
    assert response.status_code == 200 and response.json()["expires_at"] == row["expires_at"]
    with unit_of_work(application.state.engine) as db:
        assert db.get(ConsoleSession, session_id).state != "closed"
    other = cmutate(
        clients["root"],
        "POST",
        f"/suts/{sut}/grants",
        {"user_id": identity(application, "lab"), "duration_hours": 1},
    ).json()
    assert (
        mutate(
            clients["root"], "PATCH", f"/api/v1/suts/{sut}/operational-state", {"state": "normal"}
        ).status_code
        == 200
    )
    with unit_of_work(application.state.engine) as db:
        assert db.get(ConsoleGrant, other["id"]).state == "revoked"


def test_concurrent_quota_11th_and_recovery(console_arena, application):
    _, sut, _, clock, *_ = console_arena
    barrier = Barrier(11)

    def allocate(n):
        barrier.wait()
        try:
            with unit_of_work(application.state.engine, write=True) as db:
                row, _ = reserve(application, db, sut, clock, instance=str(n))
                return row.id
        except HTTPException as e:
            return e.status_code

    with ThreadPoolExecutor(max_workers=11) as pool:
        result = list(pool.map(allocate, range(11)))
    assert result.count(429) == 1 and len([x for x in result if isinstance(x, str)]) == 10
    with unit_of_work(application.state.engine) as db:
        assert len(set(db.scalars(select(ConsoleSession.slot)))) == 10
        assert db.scalar(select(func.count()).select_from(ConsoleTicket)) == 10
    clock.advance(seconds=30)
    with unit_of_work(application.state.engine, write=True) as db:
        reserve(application, db, sut, clock)
        assert (
            db.scalar(
                select(func.count()).select_from(ConsoleSession).where(ConsoleSession.state != "closed")
            )
            == 1
        )


def test_ticket_bindings_single_use_and_login_removal(console_arena, application):
    _, sut, _, clock, *_ = console_arena
    with unit_of_work(application.state.engine, write=True) as db:
        row, token = reserve(application, db, sut, clock)
        actor, login = context(application, db)
        with pytest.raises(HTTPException):
            f.consume_ticket(
                db, actor, login, row.id, token, "http://other.invalid", 1, application.state.settings
            )
        assert (
            f.consume_ticket(
                db, actor, login, row.id, token, "http://testserver", 1, application.state.settings
            ).id
            == row.id
        )
        with pytest.raises(HTTPException):
            f.consume_ticket(
                db, actor, login, row.id, token, "http://testserver", 1, application.state.settings
            )
        assert db.scalar(select(ConsoleTicket)).token_digest != token
        db.delete(db.get(LoginSession, login))
        db.flush()  # retained Console history has no FK to pruned LoginSession
        f.cleanup(db, clock.now)
        assert row.state == "closed" and row.slot is None


def test_envelope_binding_rotation_and_replacement(console_arena, application):
    _, _, _, clock, client_id, cipher, data = console_arena
    with unit_of_work(application.state.engine) as db:
        client = db.get(ConsoleClient, client_id)
        credential = db.get(ConsoleCredential, client.active_credential_id)
        encrypted = Envelope(**{k: getattr(credential, k) for k in Envelope.__dataclass_fields__})
        aad = cipher.aad(client.security_id, credential.security_id, credential.method, credential.generation)
        assert json.loads(cipher.decrypt(encrypted, aad))["secret"] == data.secret.get_secret_value()
        for changed in (aad + b"x", cipher.aad(client.security_id, credential.security_id, "private_key", 1)):
            with pytest.raises(SecretUnavailable):
                cipher.decrypt(encrypted, changed)
        with pytest.raises(SecretUnavailable):
            cipher.decrypt(
                replace(
                    encrypted, ciphertext=encrypted.ciphertext[:-1] + bytes([encrypted.ciphertext[-1] ^ 1])
                ),
                aad,
            )
        old_key = cipher._keys["test-key"]
        rotated = EnvelopeCipher({"test-key": old_key, "new-key": os.urandom(32)}, "new-key")
        rewrapped = rotated.rewrap(encrypted, aad)
        assert rewrapped.ciphertext == encrypted.ciphertext and rewrapped.crypto_revision == 2
        assert rotated.decrypt(rewrapped, aad) == cipher.decrypt(encrypted, aad)
        with pytest.raises(SecretUnavailable):
            cipher.decrypt(rewrapped, aad)
        security_id = client.security_id
    replacement = data.model_copy(
        update={"secret": __import__("pydantic").SecretStr(secrets.token_urlsafe(30))}
    )
    prepared = prepare(
        replacement,
        identity(application, "root"),
        cipher,
        verifier=SyntheticVerifier(clock.now),
        client_security_id=security_id,
        generation=2,
        expected_version=1,
    )
    with unit_of_work(application.state.engine, write=True) as db:
        db.info["clock"] = lambda: clock.now
        replace_verified_credential(
            db, db.get(User, identity(application, "root")), client_id, replacement, prepared
        )
        assert len(list(db.scalars(select(ConsoleCredential)))) == 2
        assert len(list(db.scalars(select(ConsoleHostKey)))) == 2
        assert (
            db.scalar(select(ConsoleCredential).where(ConsoleCredential.generation == 1)).replaced_at
            == clock.now
        )
        assert db.scalar(select(ConsoleHostKey).where(ConsoleHostKey.trust_revision == 1)).is_current is False


def test_reconnect_generation_keeps_slot_and_stale_close_denied(console_arena, application):
    _, sut, _, clock, *_ = console_arena
    with unit_of_work(application.state.engine, write=True) as db:
        row, old_token = reserve(application, db, sut, clock)
        actor, login = context(application, db)
        slot = row.slot
        row, new_token = f.reconnect_reservation(
            db, actor, login, row.id, 1, "http://testserver", application.state.settings
        )
        assert row.attachment_generation == 2 and row.slot == slot and new_token != old_token
        with pytest.raises(HTTPException):
            f.close_generation(db, actor, login, row.id, 1)
        with pytest.raises(HTTPException):
            f.consume_ticket(
                db, actor, login, row.id, old_token, "http://testserver", 1, application.state.settings
            )
        f.close_generation(db, actor, login, row.id, 2)
        assert row.slot is None and row.state == "closed"


def test_concurrent_mapping_pair_and_stale_edits(console_arena, application):
    _, sut, _, clock, client_id, *_ = console_arena
    actor_id = identity(application, "rd")
    with unit_of_work(application.state.engine, write=True) as db:
        source = db.get(SUT, sut)
        rows = [
            SUT(
                lab_id=source.lab_id,
                name="Concurrent mock" + str(n),
                normalized_name="concurrent mock" + str(n),
                platform="mock",
                owner_team="mock",
            )
            for n in range(2)
        ]
        db.add_all(rows)
        db.flush()
        ids = [row.id for row in rows]
    barrier = Barrier(2)

    def save(sut_id):
        barrier.wait()
        try:
            with unit_of_work(application.state.engine, write=True) as db:
                db.info["clock"] = lambda: clock.now
                actor = db.get(User, actor_id)
                data = UartInput(expected_revision=0, client_id=client_id, tmux_session="same_existing_mock")
                return f.save_mapping(
                    db, actor, "mock-login", sut_id, "uart", data, application.state.settings
                )["revision"]
        except HTTPException as e:
            return e.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, ids)) == [1, 409]
    with unit_of_work(application.state.engine, write=True) as db:
        db.info["clock"] = lambda: clock.now
        actor = db.get(User, actor_id)
        stale = UartInput(expected_revision=0, clear=True)
        winner = db.scalar(
            select(ConsoleUartMapping).where(ConsoleUartMapping.tmux_session == "same_existing_mock")
        )
        with pytest.raises(HTTPException):
            f.save_mapping(db, actor, "mock-login", winner.sut_id, "uart", stale, application.state.settings)


def test_client_unique_name_ip_and_foreign_keys(console_arena, application):
    _, _, sut2, clock, client_id, cipher, data = console_arena
    actor_id = identity(application, "root")

    def create(candidate):
        proof = prepare(candidate, actor_id, cipher, verifier=SyntheticVerifier(clock.now))
        with unit_of_work(application.state.engine, write=True) as db:
            db.info["clock"] = lambda: clock.now
            return create_verified_client(db, db.get(User, actor_id), candidate, proof)

    with pytest.raises(IntegrityError):
        create(data.model_copy(update={"name": " SYNTHETIC CLIENT ", "ipv4": "192.168.234.11"}))
    with unit_of_work(application.state.engine, write=True) as db:
        db.get(ConsoleClient, client_id).enabled = False
    with pytest.raises(IntegrityError):
        create(data.model_copy(update={"name": "Different mock"}))
    with unit_of_work(application.state.engine) as db:
        other_lab = db.get(SUT, sut2).lab_id
    assert create(data.model_copy(update={"lab_id": other_lab, "ipv4": "192.168.234.12"}))["id"] != client_id
    with pytest.raises(IntegrityError), unit_of_work(application.state.engine, write=True) as db:
        db.execute(text("DELETE FROM labs WHERE id=:id"), {"id": data.lab_id})


def test_active_slot_archival_restore_collision_and_disable_history(console_arena, application):
    clients, sut, _, clock, client_id, *_ = console_arena
    with unit_of_work(application.state.engine, write=True) as db:
        first = db.get(SUT, sut)
        first.is_archived = True
        other = SUT(
            lab_id=first.lab_id,
            name="Mock restore conflict",
            normalized_name="mock restore conflict",
            platform="mock",
            owner_team="mock",
        )
        db.add(other)
        db.flush()
        other_id = other.id
    assert (
        cmutate(
            clients["rd"],
            "PUT",
            f"/suts/{other_id}/uart",
            {"expected_revision": 0, "client_id": client_id, "tmux_session": "existing_target"},
        ).status_code
        == 200
    )
    with pytest.raises(IntegrityError), unit_of_work(application.state.engine, write=True) as db:
        db.get(SUT, sut).is_archived = False
    with unit_of_work(application.state.engine) as db:
        assert db.get(SUT, sut).is_archived
        assert db.get(ConsoleUartMapping, other_id).active_slot
    assert clients["rd"].get(f"/api/v1/console/suts/{sut}/history").status_code == 200
    assert (
        cmutate(
            clients["root"], "PATCH", f"/clients/{client_id}", {"expected_version": 1, "enabled": False}
        ).status_code
        == 200
    )
    # A14 frees inactive slots but reactivation cannot silently steal another mapping.
    with unit_of_work(application.state.engine, write=True) as db:
        db.get(SUT, sut).is_archived = False  # both retained mappings inactive while Client disabled
    assert (
        cmutate(
            clients["root"], "PATCH", f"/clients/{client_id}", {"expected_version": 2, "enabled": True}
        ).status_code
        == 409
    )
    with unit_of_work(application.state.engine) as db:
        assert not db.get(ConsoleClient, client_id).enabled


def test_client_disable_impact_and_bmc_mapping_independence(console_arena, application):
    clients, sut, _, clock, client_id, *_ = console_arena
    with unit_of_work(application.state.engine, write=True) as db:
        session, _ = reserve(application, db, sut, clock)
        session_id = session.id
    # A separate BMC edit must not revoke the UART attachment.
    assert (
        cmutate(
            clients["rd"], "PUT", f"/suts/{sut}/bmc", {"expected_revision": 0, "ipv4": "192.168.234.22"}
        ).status_code
        == 200
    )
    with unit_of_work(application.state.engine) as db:
        assert db.get(ConsoleSession, session_id).state != "closed"
    update = {"expected_version": 1, "enabled": False}
    assert cmutate(clients["root"], "PATCH", f"/clients/{client_id}", update).status_code == 409
    preview = cmutate(clients["root"], "POST", f"/clients/{client_id}/preview", update).json()
    update["confirmation_id"] = preview["confirmation_id"]
    assert cmutate(clients["root"], "PATCH", f"/clients/{client_id}", update).status_code == 200
    with unit_of_work(application.state.engine) as db:
        assert db.get(ConsoleSession, session_id).state == "closed"
        assert db.scalar(select(ConsoleRevocation)).delivered_at is None


def test_cleanup_feature_off_and_release_rights(console_arena, application):
    _, sut, _, clock, *_ = console_arena
    with unit_of_work(application.state.engine, write=True) as db:
        row, _ = reserve(application, db, sut, clock)
        application.state.settings.console_enabled = False
        f.cleanup(db, clock.now, settings=application.state.settings)
        assert row.state == "closed"


def test_stale_candidate_evidence_keeps_existing_credentials(console_arena, application):
    _, _, _, clock, client_id, cipher, data = console_arena
    actor_id = identity(application, "root")
    with unit_of_work(application.state.engine) as db:
        client = db.get(ConsoleClient, client_id)
        security_id, old_id = client.security_id, client.active_credential_id
    proof = prepare(
        data,
        actor_id,
        cipher,
        verifier=SyntheticVerifier(clock.now),
        client_security_id=security_id,
        generation=2,
        expected_version=1,
    )
    clock.advance(minutes=2)
    with pytest.raises(HTTPException), unit_of_work(application.state.engine, write=True) as db:
        db.info["clock"] = lambda: clock.now
        replace_verified_credential(db, db.get(User, actor_id), client_id, data, proof)
    with unit_of_work(application.state.engine) as db:
        assert db.get(ConsoleClient, client_id).active_credential_id == old_id
        assert db.get(ConsoleCredential, old_id).replaced_at is None


def test_mixed_transport_quota_and_bmc_trust_invalidation(console_arena, application):
    from app.models.console import ConsoleBmcEndpoint

    clients, sut, sut2, clock, _, _, _ = console_arena
    assert (
        cmutate(
            clients["rd"], "PUT", f"/suts/{sut2}/bmc", {"expected_revision": 0, "ipv4": "192.168.234.22"}
        ).status_code
        == 200
    )
    actor_id = identity(application, "rd")
    with unit_of_work(application.state.engine, write=True) as db:
        db.info["clock"] = lambda: clock.now
        public = SyntheticVerifier(clock.now).public
        from app.services.console.credentials import fingerprint

        db.add(
            ConsoleHostKey(
                bmc_sut_id=sut2,
                ipv4="192.168.234.22",
                port=22,
                endpoint_epoch=1,
                algorithm="ssh-ed25519",
                public_key=public,
                fingerprint=fingerprint(public, "ssh-ed25519"),
                accepted_by=actor_id,
                created_at=clock.now,
            )
        )
        db.flush()
        actor, login = context(application, db)
        for n in range(9):
            reserve(application, db, sut, clock, instance=str(n))
        bmc, _ = f.reserve_session(
            db, actor, login, sut2, "bmc", "bmc-tab", "http://testserver", application.state.settings
        )
        assert bmc.slot == 10
        with pytest.raises(HTTPException) as error:
            reserve(application, db, sut, clock)
        assert error.value.status_code == 429
    update = {"expected_revision": 1, "ipv4": "192.168.234.23"}
    preview = cmutate(clients["rd"], "POST", f"/suts/{sut2}/bmc/preview", update).json()
    update["confirmation_id"] = preview["confirmation_id"]
    assert cmutate(clients["rd"], "PUT", f"/suts/{sut2}/bmc", update).status_code == 200
    with unit_of_work(application.state.engine) as db:
        assert db.get(ConsoleBmcEndpoint, sut2).endpoint_epoch == 2
        assert db.scalar(select(ConsoleHostKey).where(ConsoleHostKey.bmc_sut_id == sut2)).is_current is False
        assert (
            db.scalar(
                select(func.count()).select_from(ConsoleSession).where(ConsoleSession.state != "closed")
            )
            == 9
        )


def test_no_target_probe_or_ssh_in_foundation(console_arena, monkeypatch):
    import socket

    clients, sut, *_ = console_arena

    def forbidden(*args, **kwargs):
        raise AssertionError("No network connection authorized in Phase B")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    response = cmutate(
        clients["rd"], "PUT", f"/suts/{sut}/bmc", {"expected_revision": 0, "ipv4": "192.168.234.22"}
    )
    assert response.status_code == 200
    assert clients["rd"].get(f"/api/v1/console/suts/{sut}/connections").json()["terminal_available"] is False


def test_private_key_credential_and_live_replacement_stays_closed(console_arena, application):
    from pydantic import SecretStr

    clients, sut, _, clock, client_id, cipher, data = console_arena
    with unit_of_work(application.state.engine, write=True) as db:
        row, _ = reserve(application, db, sut, clock)
        session_id = row.id
        client = db.get(ConsoleClient, client_id)
        security_id, old_credential_id = client.security_id, client.active_credential_id
    replacement = data.model_copy(
        update={"auth_method": "private_key", "secret": SecretStr(secrets.token_urlsafe(48))}
    )
    proof = prepare(
        replacement,
        identity(application, "root"),
        cipher,
        verifier=SyntheticVerifier(clock.now),
        client_security_id=security_id,
        generation=2,
        expected_version=1,
    )
    with pytest.raises(HTTPException) as error, unit_of_work(application.state.engine, write=True) as db:
        db.info["clock"] = lambda: clock.now
        replace_verified_credential(
            db, db.get(User, identity(application, "root")), client_id, replacement, proof
        )
    assert error.value.status_code == 503
    with unit_of_work(application.state.engine) as db:
        assert db.get(ConsoleClient, client_id).active_credential_id == old_credential_id
        assert db.get(ConsoleSession, session_id).state != "closed"
    with unit_of_work(application.state.engine, write=True) as db:
        db.info["clock"] = lambda: clock.now
        f.close_session(db, db.get(ConsoleSession, session_id), "explicit_disconnect")
    with unit_of_work(application.state.engine, write=True) as db:
        db.info["clock"] = lambda: clock.now
        replace_verified_credential(
            db, db.get(User, identity(application, "root")), client_id, replacement, proof
        )
        new = db.get(ConsoleCredential, db.get(ConsoleClient, client_id).active_credential_id)
        assert new.method == "private_key" and new.generation == 2


def test_readonly_fallback_and_expiry_audit_idempotent(console_arena, application):
    clients, sut, _, clock, *_ = console_arena
    mutate(
        clients["root"],
        "PATCH",
        f"/api/v1/suts/{sut}/operational-state",
        {"state": "maintenance", "reason": "synthetic"},
    )
    grant = cmutate(
        clients["root"],
        "POST",
        f"/suts/{sut}/grants",
        {"user_id": identity(application, "rd"), "duration_hours": 1},
    ).json()
    application.state.settings.console_access_policy = "shared_readonly"
    with unit_of_work(application.state.engine, write=True) as db:
        row, _ = reserve(application, db, sut, clock)
        session_id = row.id
        # Synthetic connected metadata emulates a future C attachment; no network is opened.
        row.state = "connected"
        row.lease_until = clock.now + timedelta(hours=2)
    clock.advance(hours=1)
    with unit_of_work(application.state.engine, write=True) as db:
        db.info["clock"] = lambda: clock.now
        f.cleanup(db, clock.now, settings=application.state.settings)
        f.cleanup(db, clock.now, settings=application.state.settings)
        session = db.get(ConsoleSession, session_id)
        assert session.state == "connected" and session.mode == "read" and session.grant_id is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(ConsoleAudit)
                .where(ConsoleAudit.event_type == "grant_expired")
            )
            == 1
        )
        assert db.get(ConsoleGrant, grant["id"]).state == "expired"


def test_host_key_history_and_grant_creation_immutable(console_arena, application):
    clients, sut, _, clock, *_ = console_arena
    with pytest.raises(IntegrityError), unit_of_work(application.state.engine, write=True) as db:
        db.execute(text("UPDATE console_host_keys SET fingerprint='unapproved'"))
    with pytest.raises(IntegrityError), unit_of_work(application.state.engine, write=True) as db:
        db.execute(text("DELETE FROM console_host_keys"))
    mutate(
        clients["root"],
        "PATCH",
        f"/api/v1/suts/{sut}/operational-state",
        {"state": "maintenance", "reason": "synthetic"},
    )
    cmutate(
        clients["root"],
        "POST",
        f"/suts/{sut}/grants",
        {"user_id": identity(application, "rd"), "duration_hours": 1},
    )
    with pytest.raises(IntegrityError), unit_of_work(application.state.engine, write=True) as db:
        db.execute(text("UPDATE console_grants SET created_at=datetime(created_at,'-1 hour')"))


@pytest.mark.parametrize(
    "origin",
    [
        "null",
        "http://@testserver",
        "http://user@testserver",
        "http://testserver/",
        "http://testserver?token=x",
        "http://testserver:0",
        "ftp://testserver",
    ],
)
def test_ticket_origin_syntax_rejected(origin, application):
    application.state.settings.console_allow_insecure_http = True
    with pytest.raises(HTTPException):
        f.normalize_origin(origin, application.state.settings)


def test_client_move_lists_retained_bindings(console_arena, application):
    clients, sut, sut2, _, client_id, *_ = console_arena
    with unit_of_work(application.state.engine) as db:
        destination = db.get(SUT, sut2).lab_id
    response = cmutate(
        clients["root"], "PATCH", f"/clients/{client_id}", {"expected_version": 1, "lab_id": destination}
    )
    assert response.status_code == 409
    assert response.json()["detail"]["sut_ids"] == [sut]


def test_local_safety_discovery_fails_closed_on_unsupported_host(monkeypatch):
    import sys
    from app.services.console.targets import local_denials

    monkeypatch.setitem(sys.modules, "fcntl", None)
    with pytest.raises(HTTPException) as error:
        local_denials()
    assert error.value.status_code == 503
