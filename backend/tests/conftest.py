from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from app.core.deadlines import process_deadlines
import secrets
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.database import unit_of_work
from app.main import create_app
from app.models.domain import User
from app.services.accounts import HASHER

PASSWORD = "Synthetic-password-123!"
NEW_PASSWORD = "Changed-password-456!"
HASH = HASHER.hash(PASSWORD)
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def application(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("DATABASE_URL", url)
    cfg = Config(str(ROOT / "backend/alembic.ini"))
    command.upgrade(cfg, "head")
    settings = Settings(
        secret_key=secrets.token_urlsafe(48),
        database_url=url,
        app_env="test",
        deadline_processor_enabled=False,
        cookie_secure=False,
    )
    app = create_app(settings)
    with unit_of_work(app.state.engine, write=True) as db:
        for name, role, forced in [
            ("root", "super_admin", False),
            ("lab", "lab_admin", False),
            ("rd", "user", False),
            ("temp", "user", True),
        ]:
            db.add(
                User(
                    username=name,
                    display_name=f"Synthetic {name}",
                    team="Demo",
                    email=f"{name}@example.com",
                    role=role,
                    password_hash=HASH,
                    must_change_password=forced,
                )
            )
    yield app
    app.state.engine.dispose()


@pytest.fixture
def client(application):
    with TestClient(application) as client:
        yield client


def csrf(client):
    return client.get("/api/v1/auth/csrf").json()["csrf_token"]


def mutate(client, method, path, data=None):
    return client.request(method, path, json=data, headers={"X-CSRF-Token": csrf(client)})


def sign_in(client, username="root", password=PASSWORD):
    response = mutate(client, "POST", "/api/v1/auth/login", {"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response


@pytest.fixture
def root(client):
    sign_in(client)
    return client


def identity(application, name):
    with unit_of_work(application.state.engine) as db:
        return db.scalar(select(User.id).where(User.username == name))


def create_inventory(client, name="SUT-1", lab_name="Demo Lab 1"):
    response = mutate(client, "POST", "/api/v1/labs", {"name": lab_name, "location": "Synthetic Taiwan"})
    assert response.status_code == 201, response.text
    lab_id = response.json()["id"]
    response = mutate(
        client,
        "POST",
        "/api/v1/suts",
        {"name": name, "lab_id": lab_id, "platform": "Demo", "owner_team": "Demo"},
    )
    assert response.status_code == 201, response.text
    return lab_id, response.json()["id"]


@pytest.fixture
def arena(root, application):
    lab, sut = create_inventory(root, name="Coordination-1")
    lab2, sut2 = create_inventory(root, name="Coordination-2", lab_name="Demo Lab 2")

    class Clock:
        now = datetime(2026, 10, 15, 4, 0, tzinfo=UTC)

        def advance(self, **delta):
            self.now += timedelta(**delta)

        def sweep(self):
            process_deadlines(application.state.engine, lambda: self.now)

    clock = Clock()
    application.state.clock = lambda: clock.now
    with ExitStack() as stack:
        clients = {"root": root}
        for name in ("rd", "lab"):
            clients[name] = stack.enter_context(TestClient(application))
            sign_in(clients[name], name)
        yield clients, sut, sut2, clock
