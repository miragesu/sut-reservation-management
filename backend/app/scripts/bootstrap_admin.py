"""One-time administrator provisioning. Never puts passwords in argv or output."""

import getpass
import os

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.database import make_engine, unit_of_work
from app.schemas.inputs import UserInput
from app.services.accounts import provision


def main():
    settings = Settings()
    fields = {
        key: os.environ.get("BOOTSTRAP_" + key.upper()) or input(label + ": ")
        for key, label in [
            ("username", "Username"),
            ("display_name", "Display name"),
            ("team", "Team"),
            ("email", "Work email"),
        ]
    }
    raw = os.environ.get("BOOTSTRAP_PASSWORD")
    if raw is None:
        raw = getpass.getpass(f"Temporary password ({settings.password_minimum}–128 characters): ")
        if raw != getpass.getpass("Confirm temporary password: "):
            raise SystemExit("Passwords do not match")
    data = UserInput(**fields, role="super_admin", temporary_password=raw)
    engine = make_engine(settings.database_url)
    try:
        with unit_of_work(engine, write=True) as db:
            provision(db, None, data, settings, bootstrap=True)
    except HTTPException as exc:
        raise SystemExit(exc.detail) from None
    except IntegrityError:
        raise SystemExit("Username or email already exists; no administrator was created") from None
    finally:
        engine.dispose()
    print("Super Admin created. First login requires a password change.")


if __name__ == "__main__":
    main()
