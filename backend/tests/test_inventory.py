from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.database import unit_of_work, utcnow
from app.models.domain import (
    AuditEvent,
    CurrentUsage,
    Notification,
    QueueEntry,
    Reservation,
    SUT,
    UsageHistory,
)
from app.services import inventory
from conftest import create_inventory, identity, mutate, sign_in


def test_all_lab_crud_and_delete_guards(client):
    sign_in(client, "lab")
    lab1, sut1 = create_inventory(client)
    lab2, sut2 = create_inventory(client, lab_name="Demo Lab 2")
    assert (
        mutate(client, "PUT", f"/api/v1/labs/{lab2}", {"name": "Updated Lab", "location": "Demo"}).status_code
        == 200
    )
    assert mutate(client, "DELETE", f"/api/v1/labs/{lab1}").status_code == 409
    for sid in (sut1, sut2):
        response = mutate(
            client,
            "PUT",
            f"/api/v1/suts/{sid}",
            {
                "name": "Updated",
                "platform": "P2",
                "owner_team": "T2",
                "bmc_ip": "192.0.2.1",
                "host_ip": "2001:db8::1",
            },
        )
        assert response.status_code == 200, response.text
    for sid in (sut1, sut2):
        assert mutate(client, "DELETE", f"/api/v1/suts/{sid}").status_code == 204
        assert mutate(client, "POST", f"/api/v1/suts/{sid}/restore").status_code == 204
    assert mutate(client, "POST", "/api/v1/labs", {"name": "Empty", "location": "Demo"}).status_code == 201
    empty = client.get("/api/v1/labs").json()["items"][-1]["id"]
    # Find by name rather than depending on list ordering.
    empty = next(x["id"] for x in client.get("/api/v1/labs").json()["items"] if x["name"] == "Empty")
    assert mutate(client, "DELETE", f"/api/v1/labs/{empty}").status_code == 204
    assert mutate(client, "DELETE", "/api/v1/labs/99999").status_code == 404


def test_user_cannot_mutate_inventory(root):
    lab, sut = create_inventory(root)
    sign_in(root, "rd")
    for method, path, data in [
        ("POST", "/api/v1/labs", {"name": "X", "location": "Y"}),
        ("PUT", f"/api/v1/labs/{lab}", {"name": "X", "location": "Y"}),
        ("DELETE", f"/api/v1/labs/{lab}", None),
        ("POST", "/api/v1/suts", {"lab_id": lab, "name": "X", "platform": "P", "owner_team": "T"}),
        ("PUT", f"/api/v1/suts/{sut}", {"name": "X", "platform": "P", "owner_team": "T"}),
        ("DELETE", f"/api/v1/suts/{sut}", None),
        ("POST", f"/api/v1/suts/{sut}/restore", None),
        ("PATCH", f"/api/v1/suts/{sut}/operational-state", {"state": "maintenance", "reason": "Demo"}),
    ]:
        assert mutate(root, method, path, data).status_code == 403
    assert root.get("/api/v1/suts?include_archived=true").status_code == 403
    assert root.get("/suts/new").status_code == 403
    assert root.get("/api/v1/suts/999").status_code == 404


def test_names_archives_lab_immutability_and_invalid_ips(root, application):
    lab, sut = create_inventory(root, name=" SUT-1 ")
    body = {"lab_id": lab, "name": "sut-1", "platform": "P", "owner_team": "T"}
    assert mutate(root, "POST", "/api/v1/suts", body).status_code == 409
    assert mutate(root, "DELETE", f"/api/v1/suts/{sut}").status_code == 204
    assert root.get("/api/v1/dashboard").json()["metrics"]["suts"] == 0
    assert root.get("/api/v1/suts").json()["items"] == []
    assert len(root.get("/api/v1/suts?include_archived=true").json()["items"]) == 1
    assert mutate(root, "POST", "/api/v1/suts", body).status_code == 409
    assert mutate(root, "DELETE", f"/api/v1/labs/{lab}").status_code == 409
    assert mutate(root, "DELETE", f"/api/v1/suts/{sut}").status_code == 409
    assert mutate(root, "POST", f"/api/v1/suts/{sut}/restore").status_code == 204
    assert mutate(root, "POST", f"/api/v1/suts/{sut}/restore").status_code == 409
    lab2, sut2 = create_inventory(root, name="sut-1", lab_name="Other Lab")
    assert mutate(root, "PUT", f"/api/v1/suts/{sut}", {**body, "lab_id": lab2}).status_code == 422
    assert mutate(root, "POST", "/api/v1/suts", {**body, "name": "  "}).status_code == 422
    assert (
        mutate(root, "POST", "/api/v1/suts", {**body, "name": "Invalid", "bmc_ip": "not-an-ip"}).status_code
        == 422
    )
    assert mutate(root, "POST", "/api/v1/suts", {**body, "name": "Orphan", "lab_id": 999}).status_code == 404
    response = mutate(root, "POST", "/api/v1/suts", {**body, "name": "Second"})
    assert response.status_code == 201
    assert (
        mutate(
            root,
            "PUT",
            f"/api/v1/suts/{response.json()['id']}",
            {"name": "sut-1", "platform": "P", "owner_team": "T"},
        ).status_code
        == 409
    )
    sign_in(root, "rd")
    # Private lifecycle history remains admin inventory only.
    assert root.get("/api/v1/suts").status_code == 200


@pytest.mark.parametrize("blocker", ["usage", "queue", "confirmed", "waiting_for_release", "claimed"])
def test_archive_preserves_activity_and_blocks(root, application, blocker):
    lab, sut = create_inventory(root)
    uid = identity(application, "rd")
    now = utcnow()
    with unit_of_work(application.state.engine, write=True) as db:
        if blocker == "usage":
            db.add(
                CurrentUsage(
                    sut_id=sut, user_id=uid, start_time=now, expected_end_time=now + timedelta(days=2)
                )
            )
        elif blocker == "queue":
            db.add(QueueEntry(sut_id=sut, user_id=uid, requested_duration_minutes=60))
        else:
            db.add(
                Reservation(
                    sut_id=sut,
                    user_id=uid,
                    start_time=now - timedelta(minutes=2),
                    end_time=now + timedelta(hours=1),
                    purpose="Demo",
                    status=blocker,
                )
            )
    assert mutate(root, "DELETE", f"/api/v1/suts/{sut}").status_code == 409
    with unit_of_work(application.state.engine) as db:
        assert db.get(SUT, sut).is_archived is False
        assert any(inventory.activity(db, sut).values())


def test_history_retained_archive_and_operational_state(root, application):
    lab, sut = create_inventory(root)
    uid = identity(application, "rd")
    now = utcnow()
    with unit_of_work(application.state.engine, write=True) as db:
        db.add(
            UsageHistory(
                usage_key="demo-closed-usage",
                sut_id=sut,
                user_id=uid,
                start_time=now - timedelta(hours=1),
                end_time=now,
                duration_minutes=60,
                release_reason="user",
            )
        )
        db.add(
            Reservation(
                sut_id=sut,
                user_id=uid,
                start_time=now - timedelta(days=1),
                end_time=now - timedelta(hours=23),
                purpose="Old",
                status="completed",
            )
        )
    assert mutate(root, "DELETE", f"/api/v1/suts/{sut}").status_code == 204
    assert mutate(root, "POST", f"/api/v1/suts/{sut}/restore").status_code == 204
    with unit_of_work(application.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(UsageHistory)) == 1
        assert db.scalar(select(func.count()).select_from(Reservation)) == 1
        events = list(db.scalars(select(AuditEvent.event_type)))
        assert "sut_archived" in events and "sut_restored" in events


@pytest.mark.parametrize("state", ["maintenance", "out_of_service"])
def test_operational_reason_acknowledgement_and_preservation(root, application, state):
    lab, sut = create_inventory(root)
    uid = identity(application, "rd")
    now = utcnow()
    with unit_of_work(application.state.engine, write=True) as db:
        db.add(
            CurrentUsage(
                sut_id=sut,
                user_id=uid,
                start_time=now - timedelta(days=2),
                expected_end_time=now - timedelta(days=1),
            )
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
    path = f"/api/v1/suts/{sut}/operational-state"
    assert mutate(root, "PATCH", path, {"state": state}).status_code == 422
    assert mutate(root, "PATCH", path, {"state": state, "reason": "Demo repair"}).status_code == 409
    result = mutate(
        root, "PATCH", path, {"state": state, "reason": "Demo repair", "acknowledge_activity": True}
    )
    assert result.status_code == 200, result.text
    assert result.json()["status"] == inventory.STATES[state]
    assert result.json()["in_use"] and result.json()["overdue"]
    assert result.json()["holder"]["email"] == "rd@example.com"
    assert "password_hash" not in result.text
    assert "Demo repair" in root.get("/").text and "Demo repair" in root.get(f"/suts/{sut}").text
    listing = root.get("/suts").text
    assert f"<td>{inventory.STATES[state]} · In Use · Overdue</td>" in listing
    assert "rd@example.com" in listing and "Demo repair" in listing
    with unit_of_work(application.state.engine) as db:
        assert inventory.activity(db, sut) == {"usages": 1, "queues": 1, "reservations": 1}
        assert (
            db.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.event_key.like("operational:%"))
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count()).select_from(Notification).where(Notification.event_key.like("overdue:%"))
            )
            == 1
        )
    assert mutate(root, "PATCH", path, {"state": "normal"}).json()["operational_reason"] is None
    assert root.get(f"/api/v1/suts/{sut}").json()["status"] == "In Use"


def test_concurrent_duplicate_names_database_constraint(root, application):
    lab, sut = create_inventory(root)

    def insert(index):
        with TestClient(application) as client:
            sign_in(client, "lab")
            return mutate(
                client,
                "POST",
                "/api/v1/suts",
                {
                    "lab_id": lab,
                    "name": " duplicate " if index else "DUPLICATE",
                    "platform": "P",
                    "owner_team": "T",
                },
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(insert, [0, 1]))
    assert sorted(statuses) == [201, 409]
