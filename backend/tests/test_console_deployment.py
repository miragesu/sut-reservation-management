"""Synthetic deployment policy and offline key lifecycle; no target connections."""

import base64
import json
import os
from pathlib import Path
import secrets
import sqlite3

import pytest
from fastapi import HTTPException

from app.console_deployment import DeploymentError, denies_target, firewall, policy_file, provision
from app.console_keyring import maintain
from app.services.console.crypto import EnvelopeCipher, SecretUnavailable
from app.services.console.targets import validate_ipv4


def policy(tmp_path):
    p = tmp_path / "network.json"
    p.write_text(
        json.dumps(
            {"version": 1, "host_ipv4": ["10.4.0.1"], "deny_cidrs": ["10.5.0.0/24"], "ssh_ports": [22, 2222]}
        )
    )
    return p


@pytest.mark.parametrize(
    "invalid", [{}, {"version": 2}, {"host_ipv4": []}, {"ssh_ports": [True]}, {"deny_cidrs": ["10.5.0.1/24"]}]
)
def test_policy_fails_closed(tmp_path, invalid):
    p = policy(tmp_path)
    data = json.loads(p.read_text())
    data.update(invalid)
    p.write_text(json.dumps(data) if invalid else "{}")
    with pytest.raises(DeploymentError):
        policy_file(p)


def test_target_policy_is_not_lab_allowlist(tmp_path, monkeypatch):
    p = policy(tmp_path)
    monkeypatch.setenv("CONSOLE_NETWORK_POLICY_FILE", str(p))
    for address in ("10.4.0.1", "10.5.0.40", "127.0.0.1", "169.254.169.254", "8.8.8.8"):
        with pytest.raises(HTTPException):
            validate_ipv4(address, bmc=True, local=())
    for address in ("10.6.1.4", "172.20.2.4", "192.168.88.4"):
        assert validate_ipv4(address, bmc=True, local=()) == address
    assert denies_target(p, "10.6.1.4", 80)
    assert not denies_target(p, "10.6.1.4", 2222)
    p.unlink()
    with pytest.raises(HTTPException) as error:
        validate_ipv4("10.6.1.4", bmc=True, local=())
    assert error.value.status_code == 503


def test_firewall_drop_before_flush_and_allow(tmp_path, monkeypatch):
    monkeypatch.setattr("app.console_deployment.local_denials", lambda: {"172.20.0.1"})
    calls = []
    firewall(policy(tmp_path), run=lambda args, **_: calls.append(args))
    assert calls[0][-3:] == ["-P", "OUTPUT", "DROP"]
    assert calls[2][-2:] == ["-F", "OUTPUT"]
    rejects = [i for i, c in enumerate(calls) if "REJECT" in c]
    accepts = [i for i, c in enumerate(calls) if "--dport" in c]
    assert max(rejects) < min(accepts)
    assert any("169.254.0.0/16" in c for c in calls)
    assert not any("ACCEPT" in c and c[0] == "ip6tables" for c in calls)


def test_provision_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(os, "chown", lambda *_: None)
    tmp_path.chmod(0o700)
    provision(tmp_path)
    key = (tmp_path / "keys/keyring").read_bytes()
    assert (tmp_path / "ipc-auth").stat().st_mode & 0o777 == 0o640
    with pytest.raises(DeploymentError):
        provision(tmp_path)
    assert (tmp_path / "keys/keyring").read_bytes() == key


def keyring(path, keys, active):
    path.write_text(
        json.dumps(
            {"active_key_id": active, "keys": {k: base64.b64encode(v).decode() for k, v in keys.items()}}
        )
    )
    path.chmod(0o600)
    return path


def test_offline_rewrap_recovery_and_wrong_keys(tmp_path):
    # Minimal real migrated schema, populated with one encrypted credential via SQL.
    from alembic import command
    from alembic.config import Config

    dbpath = tmp_path / "test.db"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    config.set_main_option("sqlalchemy.url", "sqlite:///" + str(dbpath))
    # Alembic env honors DATABASE_URL; scope it rather than inheriting a real target.
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = "sqlite:///" + str(dbpath)
    try:
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL")
        else:
            os.environ["DATABASE_URL"] = previous
    old, new = secrets.token_bytes(32), secrets.token_bytes(32)
    oldfile = keyring(tmp_path / "old", {"old": old}, "old")
    both = keyring(tmp_path / "both", {"old": old, "new": new}, "new")
    newfile = keyring(tmp_path / "new", {"new": new}, "new")
    aad = EnvelopeCipher.aad("client", "credential", "password", 1)
    envelope = EnvelopeCipher.from_file(oldfile, login_secret=b"").encrypt(b"synthetic-secret", aad)
    with sqlite3.connect(dbpath) as db:
        # FK inserts are deliberately minimal fixture-only (the crypto maintenance never bypasses FK checks).
        db.execute(
            "insert into users (id,username,display_name,team,email,password_hash,role,is_active,must_change_password,created_at) values (1,'mock','Mock','Mock','mock@example.test','synthetic-hash','super_admin',1,0,datetime('now'))"
        )
        db.execute(
            "insert into labs (id,name,location,description,created_at) values (1,'Mock','Mock','',datetime('now'))"
        )
        db.execute(
            "insert into console_clients (id,security_id,lab_id,name,normalized_name,ipv4,ssh_port,ssh_username,auth_method,enabled,notes,metadata_version,connection_epoch,updated_at,updated_by,created_at) values (1,'client',1,'Mock','mock','10.8.0.4',22,'mock','password',1,'',1,1,datetime('now'),1,datetime('now'))"
        )
        db.execute(
            "insert into console_credentials (security_id,client_security_id,method,ciphertext,nonce,wrapped_data_key,wrap_nonce,key_id,algorithm,generation,crypto_revision,created_by,created_at) values (?,?,?,?,?,?,?,?,?,1,1,1,datetime('now'))",
            (
                "credential",
                "client",
                "password",
                envelope.ciphertext,
                envelope.nonce,
                envelope.wrapped_data_key,
                envelope.wrap_nonce,
                envelope.key_id,
                envelope.algorithm,
            ),
        )
    with pytest.raises(SecretUnavailable):
        maintain(dbpath, newfile)
    backup = tmp_path / "before.db"
    assert maintain(dbpath, both, backup=backup) == 1
    assert maintain(dbpath, newfile) == 0
    assert maintain(backup, oldfile) == 0
    with pytest.raises(SecretUnavailable):
        maintain(dbpath, oldfile)
    with pytest.raises(FileExistsError):
        maintain(dbpath, both, backup=backup)
    with sqlite3.connect(dbpath) as db:
        assert db.execute("select crypto_revision from console_credentials").fetchone()[0] == 2
        assert db.execute("select ciphertext from console_credentials").fetchone()[0] == envelope.ciphertext

    # A later corrupt envelope fails after an earlier row was rewrapped: all SQL
    # changes must roll back, while the exclusive pre-change backup is retained.
    with sqlite3.connect(dbpath) as db:
        db.execute(
            "insert into console_credentials (security_id,client_security_id,method,ciphertext,nonce,wrapped_data_key,wrap_nonce,key_id,algorithm,generation,crypto_revision,created_by,created_at) select 'corrupt',client_security_id,method,ciphertext,nonce,wrapped_data_key,wrap_nonce,key_id,algorithm,2,1,created_by,created_at from console_credentials limit 1"
        )
    staged = keyring(tmp_path / "third", {"new": new, "third": secrets.token_bytes(32)}, "third")
    with pytest.raises(SecretUnavailable):
        maintain(dbpath, staged, backup=tmp_path / "failed-before.db")
    with sqlite3.connect(dbpath) as db:
        assert db.execute(
            "select key_id,crypto_revision from console_credentials where security_id='credential'"
        ).fetchone() == ("new", 2)
        assert (
            db.execute(
                "select count(*) from console_audits where event_type='offline_kek_rewrap'"
            ).fetchone()[0]
            == 1
        )


def test_broker_verification_never_returns_secret():
    import asyncio
    from dataclasses import asdict
    from app.console_broker.executor import Executor
    from app.console_broker.ipc import BrokerError

    async def scenario():
        cipher = EnvelopeCipher({"test": secrets.token_bytes(32)}, "test")
        aad = ["client", "credential", "password", 1]
        value = asdict(cipher.encrypt(b"synthetic-canary", cipher.aad(*aad)))
        for field in ("ciphertext", "nonce", "wrapped_data_key", "wrap_nonce"):
            value[field] = base64.b64encode(value[field]).decode()
        executor = Executor(cipher)
        assert await executor.dispatch("verify_credential", {"envelope": value, "aad": aad}) == {
            "verified": True
        }
        with pytest.raises(BrokerError):
            await executor.dispatch("verify_credential", {"envelope": value, "aad": ["other", *aad[1:]]})

    asyncio.run(scenario())
