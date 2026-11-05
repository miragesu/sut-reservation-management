"""Offline custodian-only credential verification/atomic KEK rewrap; no secret output.

Stop Web and Broker first. Run --network none, never as a runtime service.
"""

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3

from app.services.console.crypto import Envelope, EnvelopeCipher

FIELDS = tuple(Envelope.__dataclass_fields__)


def maintain(database, keyring, *, backup=None):
    path = Path(database)
    if not path.is_file() or path.is_symlink():
        raise ValueError("Existing database required")
    cipher = EnvelopeCipher.from_file(keyring, login_secret=b"")
    db = sqlite3.connect(f"file:{path}?mode=rw", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("pragma foreign_keys=on")
        if db.execute("select version_num from alembic_version").fetchone()[0] != "console001_b01":
            raise ValueError("Matching schema required")
        if db.execute("select count(*) from console_sessions where state != 'closed'").fetchone()[0]:
            raise ValueError("Stop Web/Broker and fence active Console sessions first")
        if backup:
            fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            with sqlite3.connect(backup) as target:
                db.backup(target)
        db.execute("BEGIN IMMEDIATE")
        count = 0
        for row in db.execute("select * from console_credentials").fetchall():
            aad = cipher.aad(row["client_security_id"], row["security_id"], row["method"], row["generation"])
            envelope = Envelope(**{k: row[k] for k in FIELDS})
            cipher.decrypt(envelope, aad)  # Verify payload as well as wrap; never print it.
            if backup and row["key_id"] != cipher.active_id:
                value = asdict(cipher.rewrap(envelope, aad))
                assert value["ciphertext"] == row["ciphertext"]
                db.execute(
                    "update console_credentials set key_id=?, wrapped_data_key=?, wrap_nonce=?, crypto_revision=? where id=? and crypto_revision=?",
                    (
                        value["key_id"],
                        value["wrapped_data_key"],
                        value["wrap_nonce"],
                        value["crypto_revision"],
                        row["id"],
                        row["crypto_revision"],
                    ),
                )
                count += 1
        if backup:
            db.execute(
                "insert into console_audits (event_type,details,created_at) values (?,?,?)",
                (
                    "offline_kek_rewrap",
                    json.dumps({"key_id": cipher.active_id, "count": count}),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        if (
            db.execute("pragma integrity_check").fetchone()[0] != "ok"
            or db.execute("pragma foreign_key_check").fetchall()
        ):
            raise ValueError("Database integrity failed")
        db.commit()
        return count
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("verify", "rewrap"))
    parser.add_argument("--database", required=True)
    parser.add_argument("--keyring", required=True)
    parser.add_argument("--backup")
    args = parser.parse_args()
    if args.operation == "rewrap" and not args.backup or args.operation == "verify" and args.backup:
        parser.error("rewrap requires a new backup path; verify does not write a backup")
    try:
        count = maintain(args.database, args.keyring, backup=args.backup)
        print(f"Credential integrity verified; envelopes rewrapped: {count}")
    except Exception:
        raise SystemExit(
            "Offline key maintenance failed closed; preserve matching database/key backups"
        ) from None


if __name__ == "__main__":
    main()
