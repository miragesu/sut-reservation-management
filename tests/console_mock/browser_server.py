"""Disposable Phase D HTTP fixture; no production configuration or credentials."""

import json
import os
import sys
import time

from alembic import command
from alembic.config import Config
import uvicorn

from app.core.config import Settings
from app.core.database import unit_of_work
from app.main import create_app
from app.models.domain import Lab, SUT, User
from app.services.accounts import HASHER

fixture = json.load(sys.stdin)
os.environ["DATABASE_URL"] = "sqlite:////db/browser.db"
command.upgrade(Config("/app/alembic.ini"), "head")
settings = Settings(
    secret_key=fixture["login_secret"],
    database_url=os.environ["DATABASE_URL"],
    cookie_secure=False,
    app_env="test",
    console_enabled=True,
    console_allow_insecure_http=True,
    console_access_policy="shared_readonly",
    console_broker_socket="/ipc/broker.sock",
    console_broker_ipc_key_file="/ipc/auth",
    deadline_processor_enabled=True,
)
app = create_app(settings)
with unit_of_work(app.state.engine, write=True) as db:
    for name, role in (
        ("uiroot", "super_admin"),
        ("uilab", "lab_admin"),
        ("uird", "user"),
        ("uipeer", "user"),
    ):
        db.add(
            User(
                username=name,
                display_name="Synthetic " + name,
                team="Mock",
                email=name + "@example.test",
                role=role,
                password_hash=HASHER.hash(fixture["web_password"]),
                must_change_password=False,
            )
        )
    lab = Lab(name="Browser Mock Lab", location="Synthetic")
    other = Lab(name="Other Mock Lab", location="Synthetic")
    db.add_all([lab, other])
    db.flush()
    for name in ("UI UART", "UI Peer", "UI Maintenance"):
        db.add(
            SUT(
                lab_id=lab.id,
                name=name,
                normalized_name=name.casefold(),
                platform="Mock",
                owner_team="Mock",
                operational_state="maintenance" if name == "UI Maintenance" else "normal",
                operational_reason="Synthetic maintenance" if name == "UI Maintenance" else None,
            )
        )
# Disposable-only reproducer: keep the normal login write transaction open
# while its worker is slow. No terminal data or credential is recorded.
delay = min(1.2, max(0.0, float(fixture.get("r1_login_delay", 0))))
if delay:
    from app.services import accounts

    original_login = accounts.login

    def delayed_login(db, data, settings):
        if data.username == "uird":
            time.sleep(delay)
        return original_login(db, data, settings)

    accounts.login = delayed_login
fixture.clear()
uvicorn.run(app, host="0.0.0.0", port=8080, access_log=False, log_level="critical", proxy_headers=False)
