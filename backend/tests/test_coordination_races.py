from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import make_engine, unit_of_work
from app.core.deadlines import process_deadlines
from app.models.domain import AuditEvent, CurrentUsage, Notification, QueueEntry, Reservation, UsageHistory
from conftest import sign_in
from coordination_helpers import claim, count, join, release, reserve


def race(application, jobs):
    barrier = Barrier(len(jobs))

    def work(job):
        name, method, path, payload = job
        with TestClient(application) as client:
            sign_in(client, name)
            # Pre-fetch CSRF so the barrier sits immediately before mutation.
            token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
            barrier.wait(timeout=10)
            return client.request(method, path, json=payload, headers={"X-CSRF-Token": token}).status_code

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return list(pool.map(work, jobs))


def test_two_simultaneous_claims_one_winner(arena, application):
    users, sut, _, clock = arena
    results = race(
        application,
        [(name, "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 60}) for name in ("rd", "lab")],
    )
    assert sorted(results) == [201, 409]
    assert count(application, CurrentUsage) == 1
    assert count(application, AuditEvent, AuditEvent.event_type == "usage_claimed") == 1


def test_simultaneous_release_and_retry_exactly_one_history(arena, application):
    users, sut, _, clock = arena
    usage = claim(users["rd"], sut)
    results = race(
        application, [("rd", "POST", f"/api/v1/suts/{sut}/release", {"usage_key": usage["usage_key"]})] * 2
    )
    assert sorted(results) == [200, 409]
    assert count(application, CurrentUsage) == 0 and count(application, UsageHistory) == 1


def test_duplicate_queue_join_and_manual_claim_races(arena, application):
    users, sut, _, clock = arena
    holder = claim(users["root"], sut)
    results = race(
        application, [("rd", "POST", f"/api/v1/suts/{sut}/queue", {"requested_duration_minutes": 60})] * 2
    )
    assert sorted(results) == [201, 409]
    assert count(application, QueueEntry) == 1
    assert release(users["root"], sut, holder).status_code == 200
    results = race(application, [("rd", "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 60})] * 2)
    assert sorted(results) == [201, 409]
    assert count(application, CurrentUsage) == 1 and count(application, QueueEntry) == 0


def test_overlapping_reservations_race_and_nonoverlapping_adjacency(arena, application):
    from datetime import timedelta

    users, sut, _, clock = arena
    body = {
        "sut_id": sut,
        "start_time": (clock.now + timedelta(hours=1)).isoformat(),
        "end_time": (clock.now + timedelta(hours=2)).isoformat(),
        "purpose": "Concurrent",
    }
    results = race(application, [(name, "POST", "/api/v1/reservations", body) for name in ("rd", "lab")])
    assert sorted(results) == [201, 409]
    assert count(application, Reservation) == 1


@pytest.mark.parametrize("offset_microseconds", [-1, 0])
def test_claim_vs_expiry_serializes_at_exact_boundary(arena, application, offset_microseconds):

    users, sut, _, clock = arena
    holder = claim(users["root"], sut)
    join(users["rd"], sut)
    join(users["lab"], sut)
    assert release(users["root"], sut, holder).status_code == 200
    clock.advance(minutes=15, microseconds=offset_microseconds)
    barrier = Barrier(2)

    def claimant():
        with TestClient(application) as client:
            sign_in(client, "rd")
            token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
            barrier.wait(timeout=10)
            return client.post(
                f"/api/v1/suts/{sut}/claim", json={"duration_minutes": 60}, headers={"X-CSRF-Token": token}
            ).status_code

    def sweep():
        barrier.wait(timeout=10)
        process_deadlines(application.state.engine, lambda: clock.now)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(claimant)
        second = pool.submit(sweep)
        result = first.result()
        second.result()
    assert result == (201 if offset_microseconds < 0 else 409)
    assert count(application, CurrentUsage) == (1 if offset_microseconds < 0 else 0)
    assert count(application, AuditEvent, AuditEvent.event_type == "offer_timeout") == (
        0 if offset_microseconds < 0 else 1
    )


@pytest.mark.parametrize("offset_microseconds", [-1, 0])
def test_removed_checkin_cannot_extend_start_deadline(arena, application, offset_microseconds):
    users, sut, _, clock = arena
    booking = reserve(users["rd"], sut, clock, start=1, length=60)
    clock.advance(minutes=1)
    clock.sweep()  # Availability and its notification establish the persisted deadline.
    clock.advance(minutes=15, microseconds=offset_microseconds)
    barrier = Barrier(2)

    def checkin():
        with TestClient(application) as client:
            sign_in(client, "rd")
            token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
            barrier.wait(timeout=10)
            return client.post(
                f"/api/v1/reservations/{booking['id']}/check-in", headers={"X-CSRF-Token": token}
            ).status_code

    def sweep():
        barrier.wait(timeout=10)
        clock.sweep()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(checkin)
        second = pool.submit(sweep)
        result = first.result()
        second.result()
    assert result == 410
    assert users["root"].get(f"/api/v1/reservations/{booking['id']}").json()["status"] == (
        "confirmed" if offset_microseconds < 0 else "no_show"
    )
    assert count(application, CurrentUsage) == 0


def test_multiple_independent_processors_and_restart_are_idempotent(arena, application):
    users, sut, _, clock = arena
    holder = claim(users["root"], sut)
    join(users["rd"], sut)
    join(users["lab"], sut)
    assert release(users["root"], sut, holder).status_code == 200
    clock.advance(minutes=15)

    def worker(_):
        engine = make_engine(application.state.settings.database_url)
        try:
            process_deadlines(engine, lambda: clock.now)
        finally:
            engine.dispose()

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(worker, range(3)))
    before = count(application, Notification)
    worker(None)
    assert count(application, Notification) == before
    assert count(application, AuditEvent, AuditEvent.event_type == "offer_timeout") == 1
    with unit_of_work(application.state.engine) as db:
        rows = list(db.scalars(select(QueueEntry)))
        assert len(rows) == 1 and rows[0].offer_status == "notified"


def test_reservation_edit_vs_create_and_cancel_vs_claim_preserve_states(arena, application):
    from datetime import timedelta

    users, sut, _, clock = arena
    booking = reserve(users["rd"], sut, clock, start=60, length=60)
    change = {
        "start_time": (clock.now + timedelta(hours=3)).isoformat(),
        "end_time": (clock.now + timedelta(hours=4)).isoformat(),
        "purpose": "Edited",
    }
    results = race(
        application,
        [
            ("rd", "PUT", f"/api/v1/reservations/{booking['id']}", change),
            ("lab", "POST", "/api/v1/reservations", {"sut_id": sut, **change}),
        ],
    )
    assert sorted(results) == [200, 409] or sorted(results) == [201, 409]
    # On or after start, cancelling is never a way to bypass a protected Claim.
    row = users["rd"].get(f"/api/v1/reservations/{booking['id']}").json()
    clock.now = __import__("datetime").datetime.fromisoformat(row["start_time"])
    results = race(
        application,
        [
            ("rd", "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 1}),
            ("root", "DELETE", f"/api/v1/reservations/{booking['id']}", None),
        ],
    )
    assert sorted(results) == [201, 409]
    assert count(application, CurrentUsage) == 1


def test_claim_vs_maintenance_has_one_consistent_outcome(arena, application):
    users, sut, _, clock = arena
    results = race(
        application,
        [
            ("rd", "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 60}),
            (
                "root",
                "PATCH",
                f"/api/v1/suts/{sut}/operational-state",
                {"state": "maintenance", "reason": "Concurrent repair", "acknowledge_activity": True},
            ),
        ],
    )
    assert sorted(results) in ([200, 201], [200, 409])
    assert users["root"].get(f"/api/v1/suts/{sut}").json()["operational_state"] == "maintenance"
    assert count(application, CurrentUsage) == (1 if 201 in results else 0)


@pytest.mark.parametrize("offset_microseconds", [-1, 0])
def test_reserved_claim_vs_no_show_boundary(arena, application, offset_microseconds):
    users, sut, _, clock = arena
    booking = reserve(users["rd"], sut, clock, start=1, length=60)
    clock.advance(minutes=1)
    clock.sweep()  # Start the window when available and notified, not on the first later visit.
    clock.advance(minutes=15, microseconds=offset_microseconds)
    barrier = Barrier(2)

    def claimant():
        with TestClient(application) as client:
            sign_in(client, "rd")
            token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
            barrier.wait(timeout=10)
            return client.post(
                f"/api/v1/suts/{sut}/claim",
                json={"duration_minutes": 1, "reservation_id": booking["id"]},
                headers={"X-CSRF-Token": token},
            ).status_code

    def sweep():
        barrier.wait(timeout=10)
        clock.sweep()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(claimant)
        second = pool.submit(sweep)
        result = first.result()
        second.result()
    assert result == (201 if offset_microseconds < 0 else 409)
    assert count(application, CurrentUsage) == (1 if offset_microseconds < 0 else 0)
    assert users["root"].get(f"/api/v1/reservations/{booking['id']}").json()["status"] == (
        "claimed" if offset_microseconds < 0 else "no_show"
    )
