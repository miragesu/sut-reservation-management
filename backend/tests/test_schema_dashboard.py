import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.exc import IntegrityError, StatementError

from app.core.database import unit_of_work, utcnow
from app.models.domain import CurrentUsage, Lab, Reservation, SUT, User
from app.services import inventory
from conftest import ROOT, PASSWORD, create_inventory, identity, mutate


def test_fresh_migration_roundtrip_and_schema(application):
    cfg = Config(str(ROOT / "backend/alembic.ini"))
    command.check(cfg)
    tables = set(inspect(application.state.engine).get_table_names())
    assert {
        "users",
        "labs",
        "suts",
        "current_usages",
        "queue_entries",
        "reservations",
        "usage_histories",
        "notifications",
        "audit_events",
        "login_sessions",
    } <= tables
    with unit_of_work(application.state.engine, write=True) as db:
        db.execute(delete(User))
    with pytest.raises(RuntimeError, match="compatible backup"):
        command.downgrade(cfg, "base")
    assert "ready_at" in {c["name"] for c in inspect(application.state.engine).get_columns("reservations")}
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")
    command.check(cfg)


def test_sqlite_constraints_timezone_and_multiple_suts(root, application):
    lab, sut = create_inventory(root)
    uid = identity(application, "rd")
    now = utcnow()
    with unit_of_work(application.state.engine) as db:
        assert db.scalar(text("PRAGMA foreign_keys")) == 1
    with pytest.raises(IntegrityError), unit_of_work(application.state.engine, write=True) as db:
        db.add(SUT(lab_id=lab, name="duplicate", normalized_name="sut-1", platform="P", owner_team="T"))
        db.flush()
    with pytest.raises(IntegrityError), unit_of_work(application.state.engine, write=True) as db:
        db.add(SUT(lab_id=999, name="orphan", normalized_name="orphan", platform="P", owner_team="T"))
        db.flush()
    with pytest.raises(StatementError), unit_of_work(application.state.engine, write=True) as db:
        db.add(
            Reservation(
                sut_id=sut, user_id=uid, start_time=datetime(2026, 1, 1), end_time=now, purpose="Naive"
            )
        )
        db.flush()
    with unit_of_work(application.state.engine, write=True) as db:
        sut2 = SUT(lab_id=lab, name="second", normalized_name="second", platform="P", owner_team="T")
        db.add(sut2)
        db.flush()
        for sid in (sut, sut2.id):
            db.add(
                CurrentUsage(
                    sut_id=sid, user_id=uid, start_time=now, expected_end_time=now + timedelta(days=3)
                )
            )
    with pytest.raises(IntegrityError), unit_of_work(application.state.engine, write=True) as db:
        db.add(
            CurrentUsage(sut_id=sut, user_id=uid, start_time=now, expected_end_time=now + timedelta(hours=1))
        )
        db.flush()
    with unit_of_work(application.state.engine) as db:
        usage = db.scalar(select(CurrentUsage))
        assert usage.start_time.tzinfo == UTC and usage.start_time == now
    with pytest.raises(IntegrityError), unit_of_work(application.state.engine, write=True) as db:
        db.delete(db.get(User, uid))
        db.flush()


def test_bootstrap_once_secure_and_seed_repeatability(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/bootstrap.db"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config(str(ROOT / "backend/alembic.ini")), "head")
    environment = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "backend"),
        "SECRET_KEY": "synthetic-test-key-not-for-production-123456",
        "BOOTSTRAP_USERNAME": "demo",
        "BOOTSTRAP_DISPLAY_NAME": "Demo Admin",
        "BOOTSTRAP_TEAM": "Demo",
        "BOOTSTRAP_EMAIL": "demo@example.com",
        "BOOTSTRAP_PASSWORD": PASSWORD,
        "APP_ENV": "development",
    }

    def run(module, **changes):
        return subprocess.run(
            [sys.executable, "-m", module],
            cwd=ROOT / "backend",
            env={**environment, **changes},
            capture_output=True,
            text=True,
        )

    first = run("app.scripts.bootstrap_admin")
    second = run("app.scripts.bootstrap_admin")
    assert first.returncode == 0, first.stderr
    assert second.returncode != 0 and "already bootstrapped" in second.stderr
    assert PASSWORD not in first.stdout + first.stderr + second.stdout + second.stderr
    assert run("app.scripts.seed").returncode == 0
    assert run("app.scripts.seed").returncode == 0
    assert run("app.scripts.seed", APP_ENV="production").returncode != 0
    from app.core.database import make_engine

    engine = make_engine(url)
    with unit_of_work(engine) as db:
        assert len(list(db.scalars(select(Lab)))) == 2
        assert len(list(db.scalars(select(SUT)))) == 20
        assert len(list(db.scalars(select(User)))) == 1
        assert db.scalar(select(User)).must_change_password
    engine.dispose()


def test_dashboard_derived_status_booking_boundaries_sort_filters_and_readonly(root, application):
    lab, sut = create_inventory(root, name="SUT-10")
    uid = identity(application, "rd")
    now = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    with unit_of_work(application.state.engine, write=True) as db:
        sut2 = SUT(lab_id=lab, name="SUT-2", normalized_name="sut-2", platform="P2", owner_team="T2")
        db.add(sut2)
        db.flush()
        values = [
            (-1, 1, "confirmed"),
            (2, 3, "confirmed"),
            (23, 25, "waiting_for_release"),
            (24, 25, "confirmed"),
            (4, 5, "cancelled"),
            (5, 6, "no_show"),
            (-2, 0, "confirmed"),
        ]
        for start, end, status in values:
            db.add(
                Reservation(
                    sut_id=sut,
                    user_id=uid,
                    start_time=now + timedelta(hours=start),
                    end_time=now + timedelta(hours=end),
                    status=status,
                    purpose="Demo",
                )
            )
        sut2_id = sut2.id
    with unit_of_work(application.state.engine) as db:
        actor = db.get(User, identity(application, "root"))
        snapshot = inventory.snapshot(db, actor, now=now)
        assert [s["name"] for s in snapshot["items"]] == ["SUT-2", "SUT-10"]
        data = next(s for s in snapshot["items"] if s["id"] == sut)
        assert data["status"] == "Reserved"
        assert data["next_reservation"]["start_time"] == now + timedelta(hours=2)
        assert len(data["reservations_24h"]) == 3
        assert inventory.snapshot(db, actor, sort="status", now=now)["items"][0]["id"] == sut2_id
        assert (
            inventory.snapshot(db, actor, platform="P2", owner_team="T2", search="sut-2", now=now)["total"]
            == 1
        )
        before = db.execute(text("SELECT count(*) FROM audit_events")).scalar()
    for path in ["/", "/dashboard/fragment", "/api/v1/dashboard", "/suts", "/labs", f"/suts/{sut}"]:
        assert root.get(path).status_code == 200
    with unit_of_work(application.state.engine) as db:
        assert db.execute(text("SELECT count(*) FROM audit_events")).scalar() == before
    assert root.get("/api/v1/suts?page_size=101").status_code == 422
    assert root.get("/api/v1/dashboard?sort=platform").status_code == 422
    assert root.get("/api/v1/suts?status=bad").status_code == 422


def test_html_crud_csrf_validation_and_escape(root):
    from conftest import csrf

    token = csrf(root)
    assert (
        root.post(
            "/labs",
            data={"csrf_token": token, "name": "<script>alert(1)</script>", "location": "Demo"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    page = root.get("/labs").text
    assert "&lt;script&gt;" in page and "<script>alert(1)" not in page
    lab = root.get("/api/v1/labs").json()["items"][0]["id"]
    response = root.post(
        "/suts",
        data={
            "csrf_token": csrf(root),
            "lab_id": lab,
            "name": "HTML-SUT",
            "platform": "P",
            "owner_team": "T",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    location = response.headers["location"]
    assert root.get(location + "/edit").status_code == 200
    assert (
        root.post(
            location + "/edit",
            data={"csrf_token": csrf(root), "name": "Edited", "platform": "P2", "owner_team": "T2"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert "Edited" in root.get(location).text
    assert (
        root.post(location + "/archive", data={"csrf_token": csrf(root)}, follow_redirects=False).status_code
        == 303
    )
    assert (
        root.post(location + "/restore", data={"csrf_token": csrf(root)}, follow_redirects=False).status_code
        == 303
    )
    assert root.post("/labs", data={"name": "No CSRF", "location": "Demo"}).status_code == 403
    assert (
        root.post("/labs", data={"csrf_token": csrf(root), "name": " ", "location": "Demo"}).status_code
        == 422
    )


def test_openapi_output_schemas_and_secure_cookie(root, application):
    from fastapi.testclient import TestClient
    from app.main import create_app

    schema = root.get("/openapi.json").json()
    assert "SUTView" in schema["components"]["schemas"]
    assert "password_hash" not in schema["components"]["schemas"]["UserView"]["properties"]
    secure_app = create_app(application.state.settings.model_copy(update={"cookie_secure": True}))
    try:
        with TestClient(secure_app, base_url="https://testserver") as client:
            response = client.get("/api/v1/auth/csrf")
            assert "secure" in response.headers["set-cookie"].lower()
    finally:
        secure_app.state.engine.dispose()


def test_contention_returns_retryable_error(root, application):
    # A separate SQLite writer holds the lock beyond our bounded busy timeout.
    with application.state.engine.connect() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            response = mutate(root, "POST", "/api/v1/labs", {"name": "Contended", "location": "Demo"})
            assert response.status_code == 503
            assert response.headers["retry-after"] == "1"
        finally:
            connection.rollback()
    assert mutate(root, "POST", "/api/v1/labs", {"name": "Contended", "location": "Demo"}).status_code == 201


def test_html_lab_edit_delete(root):
    from conftest import csrf

    response = root.post(
        "/labs",
        data={"csrf_token": csrf(root), "name": "Empty HTML", "location": "Demo"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    lab = root.get("/api/v1/labs").json()["items"][0]["id"]
    assert (
        root.post(
            f"/labs/{lab}/edit",
            data={"csrf_token": csrf(root), "name": "Renamed HTML", "location": "New demo"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert "Renamed HTML" in root.get("/labs").text
    assert (
        root.post(f"/labs/{lab}/delete", data={"csrf_token": csrf(root)}, follow_redirects=False).status_code
        == 303
    )
    assert root.get("/api/v1/labs").json()["items"] == []
