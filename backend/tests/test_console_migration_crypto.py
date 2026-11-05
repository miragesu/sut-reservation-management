"""Disposable migration/backup and key-custody checks. Never open production data."""

import base64
from datetime import timedelta
import json
import os
import secrets
import sqlite3

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import inspect, text

from app.core.database import make_engine, unit_of_work, utcnow
from app.models.domain import (
    AuditEvent,
    CurrentUsage,
    Lab,
    LoginSession,
    Notification,
    QueueEntry,
    Reservation,
    SUT,
    UsageHistory,
    User,
)
from app.services.console.crypto import EnvelopeCipher, SecretUnavailable
from conftest import HASH, ROOT


def config(url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", url)
    return Config(str(ROOT / "backend/alembic.ini"))


def snapshot(path):
    with sqlite3.connect(path) as connection:
        names = [
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not row[0].startswith("console_") and row[0] not in ("alembic_version", "sqlite_sequence")
        ]
        return {
            name: connection.execute('SELECT * FROM "' + name + '" ORDER BY 1').fetchall() for name in names
        }


def test_populated_migration_and_compatible_backup_recovery(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.db"
    url = "sqlite:///" + str(path)
    cfg = config(url, monkeypatch)
    command.upgrade(cfg, "c2026101601")
    engine = make_engine(url)
    now = utcnow()
    with unit_of_work(engine, write=True) as db:
        user = User(
            username="synthetic",
            display_name="Synthetic",
            team="Mock",
            email="synthetic@example.com",
            password_hash=HASH,
            role="super_admin",
            must_change_password=False,
        )
        lab = Lab(name="Mock Lab", location="Synthetic")
        db.add_all([user, lab])
        db.flush()
        suts = [
            SUT(
                lab_id=lab.id,
                name="Mock" + str(n),
                normalized_name="mock" + str(n),
                platform="mock",
                owner_team="mock",
                bmc_ip="192.0.2.30",
            )
            for n in range(3)
        ]
        db.add_all(suts)
        db.flush()
        booking = Reservation(
            sut_id=suts[0].id,
            user_id=user.id,
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
            purpose="mock",
        )
        db.add(booking)
        db.flush()
        db.add_all(
            [
                LoginSession(id=secrets.token_hex(32), user_id=user.id, expires_at=now + timedelta(hours=1)),
                CurrentUsage(
                    sut_id=suts[1].id,
                    user_id=user.id,
                    start_time=now,
                    expected_end_time=now + timedelta(hours=1),
                ),
                QueueEntry(sut_id=suts[1].id, user_id=user.id, requested_duration_minutes=60),
                UsageHistory(
                    usage_key=secrets.token_hex(32),
                    sut_id=suts[2].id,
                    user_id=user.id,
                    start_time=now - timedelta(hours=1),
                    end_time=now,
                    duration_minutes=60,
                    release_reason="user",
                ),
                Notification(user_id=user.id, sut_id=suts[1].id, event_key="synthetic", message="mock"),
                AuditEvent(actor_user_id=user.id, sut_id=suts[1].id, event_type="synthetic", details_json={}),
            ]
        )
    engine.dispose()
    before = snapshot(path)
    backup = tmp_path / "pre-upgrade-backup.db"
    with sqlite3.connect(path) as source, sqlite3.connect(backup) as destination:
        source.backup(destination)
    command.upgrade(cfg, "head")
    assert snapshot(path) == before
    engine = make_engine(url)
    with engine.connect() as connection:
        names = [name for name in inspect(connection).get_table_names() if name.startswith("console_")]
        assert len(names) == 13
        assert all(connection.execute(text("SELECT count(*) FROM " + name)).scalar() == 0 for name in names)
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
        assert (
            connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "console001_b01"
        )
    command.check(cfg)
    engine.dispose()
    # Compatible PRE-upgrade backup restored into a separate empty location, no downgrade of live data.
    restored = tmp_path / "restored"
    restored.mkdir()
    restored_db = restored / "synthetic.db"
    with sqlite3.connect(backup) as source, sqlite3.connect(restored_db) as destination:
        source.backup(destination)
    assert snapshot(restored_db) == before
    with sqlite3.connect(restored_db) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "c2026101601"
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_empty_additive_migration_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "empty.db"
    cfg = config("sqlite:///" + str(path), monkeypatch)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "c2026101601")
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'console_%'"
            ).fetchall()
            == []
        )
    command.upgrade(cfg, "head")
    command.check(cfg)


def test_nonempty_console_downgrade_refuses(application, monkeypatch):
    cfg = config(application.state.settings.database_url, monkeypatch)
    with unit_of_work(application.state.engine, write=True) as db:
        db.execute(
            text(
                "INSERT INTO console_audits (actor_id,sut_id,event_type,details,created_at) VALUES (NULL,NULL,'mock','{}',:now)"
            ),
            {"now": utcnow().isoformat()},
        )
    with pytest.raises(RuntimeError, match="compatible pre-upgrade backup"):
        command.downgrade(cfg, "c2026101601")
    with unit_of_work(application.state.engine) as db:
        assert db.execute(text("SELECT count(*) FROM console_audits")).scalar() == 1
        assert db.execute(text("SELECT version_num FROM alembic_version")).scalar() == "console001_b01"


def test_keyring_missing_wrong_permissions_symlink_and_independence(tmp_path):
    path = tmp_path / "keyring.json"
    independent = os.urandom(32)
    data = {"active_key_id": "one", "keys": {"one": base64.b64encode(independent).decode()}}
    with pytest.raises(SecretUnavailable):
        EnvelopeCipher.from_file(path, login_secret=b"different")
    path.write_text(json.dumps(data))
    path.chmod(0o644)
    with pytest.raises(SecretUnavailable):
        EnvelopeCipher.from_file(path, login_secret=b"different")
    path.chmod(0o600)
    cipher = EnvelopeCipher.from_file(path, login_secret=b"different")
    secret = os.urandom(42)
    aad = cipher.aad("client", "credential", "private_key", 1)
    encrypted = cipher.encrypt(secret, aad)
    assert cipher.decrypt(encrypted, aad) == secret
    with pytest.raises(SecretUnavailable):
        EnvelopeCipher.from_file(path, login_secret=independent)
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(SecretUnavailable):
        EnvelopeCipher.from_file(link, login_secret=b"different")
    path.write_text("{invalid canary")
    with pytest.raises(SecretUnavailable) as error:
        EnvelopeCipher.from_file(path, login_secret=b"different")
    assert "canary" not in str(error.value)
    assert not list(tmp_path.glob("*.db"))


def test_enabled_startup_requires_independent_keyring(tmp_path):
    from app.core.config import Settings
    from app.main import create_app

    secret = secrets.token_urlsafe(48)
    with pytest.raises(SecretUnavailable):
        create_app(Settings(secret_key=secret, console_enabled=True))
    path = tmp_path / "independent-keyring.json"
    path.write_text(
        json.dumps({"active_key_id": "one", "keys": {"one": base64.b64encode(os.urandom(32)).decode()}})
    )
    path.chmod(0o600)
    settings = Settings(
        secret_key=secret,
        console_enabled=True,
        console_keyring_file=str(path),
        database_url="sqlite:///" + str(tmp_path / "database" / "unused.db"),
    )
    app = create_app(settings)
    assert not (
        tmp_path / "database" / "unused.db"
    ).exists()  # no startup create_all/migrations/SSH side effect
    app.state.engine.dispose()


def test_keyring_rejected_inside_sqlite_backup_directory(tmp_path):
    from app.core.config import Settings
    from app.main import create_app

    path = tmp_path / "console-keyring.json"
    path.write_text(
        json.dumps({"active_key_id": "one", "keys": {"one": base64.b64encode(os.urandom(32)).decode()}})
    )
    path.chmod(0o600)
    with pytest.raises(SecretUnavailable):
        create_app(
            Settings(
                secret_key=secrets.token_urlsafe(48),
                console_enabled=True,
                console_keyring_file=str(path),
                database_url="sqlite:///" + str(tmp_path / "synthetic.db"),
            )
        )
