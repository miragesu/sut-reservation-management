from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.database import unit_of_work, utcnow
from app.models.domain import CurrentUsage, QueueEntry, Reservation, User
from conftest import create_inventory, identity, mutate, sign_in


def test_deactivation_impact_ack_session_reactivation_and_preservation(root, application):
    lab, sut = create_inventory(root)
    uid = identity(application, "rd")
    now = utcnow()
    with unit_of_work(application.state.engine, write=True) as db:
        db.add(
            CurrentUsage(sut_id=sut, user_id=uid, start_time=now, expected_end_time=now + timedelta(days=2))
        )
        db.add(QueueEntry(sut_id=sut, user_id=uid, requested_duration_minutes=60))
        db.add(
            Reservation(
                sut_id=sut,
                user_id=uid,
                start_time=now + timedelta(hours=1),
                end_time=now + timedelta(hours=2),
                purpose="Demo",
            )
        )
    impact = root.get(f"/api/v1/users/{uid}/impact").json()
    assert all(len(items) == 1 for items in impact.values())
    assert impact["usages"][0]["lab_name"] == "Demo Lab 1"
    with TestClient(application) as other:
        sign_in(other, "rd")
        path = f"/api/v1/users/{uid}/status"
        assert mutate(root, "PATCH", path, {"is_active": False, "reason": "Demo"}).status_code == 409
        assert (
            mutate(
                root, "PATCH", path, {"is_active": False, "reason": "Demo", "acknowledge_resources": True}
            ).status_code
            == 200
        )
        assert other.get("/api/v1/labs").status_code == 401
        assert (
            mutate(
                other, "POST", "/api/v1/auth/login", {"username": "rd", "password": "Synthetic-password-123!"}
            ).status_code
            == 401
        )
        assert "Demo Lab 1" in root.get("/admin/users").text
        assert "Demo Lab 1" in root.get(f"/admin/users/{uid}").text
        with unit_of_work(application.state.engine) as db:
            for model in (CurrentUsage, QueueEntry, Reservation):
                assert db.scalar(select(func.count()).select_from(model)) == 1
            user = db.get(User, uid)
            assert user.deactivation_reason == "Demo" and user.deactivated_at.tzinfo is not None
        assert mutate(root, "PATCH", path, {"is_active": True}).status_code == 200
        assert other.get("/api/v1/labs").status_code == 401
        sign_in(other, "rd")
        assert other.get("/api/v1/labs").status_code == 200


def test_role_and_last_admin_guards(root, application):
    rid = identity(application, "root")
    uid = identity(application, "rd")
    assert (
        mutate(
            root, "PATCH", f"/api/v1/users/{rid}/status", {"is_active": False, "reason": "Demo"}
        ).status_code
        == 409
    )
    assert mutate(root, "PATCH", f"/api/v1/users/{rid}", {"role": "user"}).status_code == 409
    sign_in(root, "lab")
    assert (
        mutate(
            root, "PATCH", f"/api/v1/users/{uid}/status", {"is_active": False, "reason": "Demo"}
        ).status_code
        == 403
    )
    assert root.get(f"/api/v1/users/{uid}/impact").status_code == 403
    sign_in(root, "rd")
    assert root.get("/api/v1/users").status_code == 403


def test_concurrent_last_admin_guard(root, application):
    second = identity(application, "lab")
    first = identity(application, "root")
    assert mutate(root, "PATCH", f"/api/v1/users/{second}", {"role": "super_admin"}).status_code == 200

    def disable(pair):
        name, uid = pair
        with TestClient(application) as client:
            sign_in(client, name)
            return mutate(
                client, "PATCH", f"/api/v1/users/{uid}/status", {"is_active": False, "reason": "Demo"}
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(disable, [("root", first), ("lab", second)]))
    assert sorted(statuses) == [200, 409]
    with unit_of_work(application.state.engine) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.role == "super_admin", User.is_active.is_(True))
            )
            == 1
        )
