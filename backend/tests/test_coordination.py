from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.database import unit_of_work
from app.models.domain import (
    AuditEvent,
    CurrentUsage,
    Notification,
    QueueEntry,
    Reservation,
    UsageHistory,
)
from conftest import identity, mutate


from coordination_helpers import claim, release, join, reserve, count


def test_multisut_uncapped_claim_release_history_actual_duration_and_stale_retry(arena, application):
    users, sut, sut2, clock = arena
    first = claim(users["rd"], sut, 72 * 60)
    second = claim(users["rd"], sut2, 48 * 60)
    assert first["usage_key"] != second["usage_key"]
    assert len(users["rd"].get("/api/v1/usages/me").json()["items"]) == 2
    clock.advance(minutes=17, seconds=49)
    response = release(users["rd"], sut, first)
    assert response.status_code == 200
    row = response.json()["history"]
    assert row["duration_minutes"] == 17
    assert row["purpose"] == "Synthetic coordination"
    assert row["end_time"] == clock.now.isoformat().replace("+00:00", "Z")
    assert release(users["rd"], sut, first).status_code == 409
    assert count(application, UsageHistory) == 1
    assert count(application, CurrentUsage) == 1
    assert users["rd"].get("/api/v1/usages/me").json()["items"][0]["sut_id"] == sut2
    third = claim(users["rd"], sut, 1)
    assert third["usage_key"] != first["usage_key"]
    assert release(users["rd"], sut, first).status_code == 409
    assert (
        users["rd"].get(f"/api/v1/suts/{sut}/coordination").json()["usage"]["usage_key"] == third["usage_key"]
    )
    assert release(users["rd"], sut, third).status_code == 200
    assert count(application, UsageHistory) == 2


@pytest.mark.parametrize("duration", [0, -1, True, "NaN", "1e200", 10**30])
def test_invalid_and_overflow_duration(arena, duration):
    users, sut, _, _ = arena
    assert (
        mutate(users["rd"], "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": duration}).status_code
        == 422
    )
    assert (
        mutate(
            users["rd"], "POST", f"/api/v1/suts/{sut}/queue", {"requested_duration_minutes": duration}
        ).status_code
        == 422
    )


def test_owner_admin_permissions_no_direct_handover_and_force_reason(arena, application):
    users, sut, sut2, clock = arena
    for sid in (sut, sut2):
        usage = claim(users["rd"], sid)
        assert release(users["root"], sid, usage).status_code == 403
        assert release(users["rd"], sid, usage, force=True, reason="No permission").status_code == 403
        assert release(users["lab"], sid, usage, force=True).status_code == 422
        response = release(users["lab"], sid, usage, force=True, reason="Synthetic admin intervention")
        assert response.status_code == 200, response.text
        assert response.json()["history"]["release_reason"] == "admin"
        assert response.json()["history"]["release_note"] == "Synthetic admin intervention"
        assert response.json()["history"]["released_by_user_id"] == identity(application, "lab")
        assert count(application, CurrentUsage) == 0
        assert (
            mutate(
                users["root"],
                "POST",
                f"/api/v1/suts/{sid}/handover",
                {"user_id": identity(application, "lab")},
            ).status_code
            == 404
        )
    assert count(application, UsageHistory) == 2


def test_overdue_reminder_idempotency_and_no_auto_release(arena, application):
    users, sut, _, clock = arena
    usage = claim(users["rd"], sut, 1)
    clock.advance(days=10)
    clock.sweep()
    clock.sweep()
    assert count(application, CurrentUsage) == 1 and count(application, UsageHistory) == 0
    assert count(application, Notification, Notification.event_key.like("overdue:%")) == 1
    assert users["rd"].get("/api/v1/usages/me").json()["items"][0]["overdue"]
    assert "Overdue" in users["rd"].get("/my-usage").text
    assert release(users["rd"], sut, usage).json()["history"]["duration_minutes"] == 10 * 24 * 60


def test_queue_admission_fifo_manual_claim_leave_and_tail_rejoin(arena, application):
    users, sut, _, clock = arena
    assert (
        mutate(
            users["rd"], "POST", f"/api/v1/suts/{sut}/queue", {"requested_duration_minutes": 60}
        ).status_code
        == 409
    )
    holder = claim(users["root"], sut)
    assert (
        mutate(
            users["root"], "POST", f"/api/v1/suts/{sut}/queue", {"requested_duration_minutes": 60}
        ).status_code
        == 409
    )
    first = join(users["rd"], sut)
    assert first["position"] == 1 and first["offer_status"] == "waiting"
    assert (
        mutate(
            users["rd"], "POST", f"/api/v1/suts/{sut}/queue", {"requested_duration_minutes": 60}
        ).status_code
        == 409
    )
    clock.advance(seconds=1)
    second = join(users["lab"], sut)
    assert second["position"] == 2
    result = release(users["root"], sut, holder).json()
    assert result["queue"][0]["offer_status"] == "notified"
    assert count(application, CurrentUsage) == 0
    assert users["rd"].get("/api/v1/dashboard").json()["items"][0]["status"] == "Available"
    assert (
        mutate(users["lab"], "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 60}).status_code == 409
    )
    assert (
        mutate(
            users["rd"], "DELETE", f"/api/v1/suts/{sut}/queue", {"entry_key": first["entry_key"]}
        ).status_code
        == 204
    )
    assert users["lab"].get(f"/api/v1/suts/{sut}/queue").json()["items"][0]["offer_status"] == "notified"
    rejoined = join(users["rd"], sut)
    assert rejoined["entry_key"] != first["entry_key"] and rejoined["position"] == 2
    assert (
        mutate(
            users["rd"], "DELETE", f"/api/v1/suts/{sut}/queue", {"entry_key": first["entry_key"]}
        ).status_code
        == 409
    )
    manual = claim(users["lab"], sut)
    assert manual["user"]["id"] == identity(application, "lab")
    assert len(users["root"].get(f"/api/v1/suts/{sut}/queue").json()["items"]) == 1


def test_exact_offer_expiry_next_head_and_rejoin(arena, application):
    users, sut, _, clock = arena
    holder = claim(users["root"], sut)
    first = join(users["rd"], sut)
    second = join(users["lab"], sut)
    assert release(users["root"], sut, holder).status_code == 200
    clock.advance(minutes=15, microseconds=-1)
    clock.sweep()
    assert count(application, QueueEntry) == 2
    clock.advance(microseconds=1)
    assert (
        mutate(users["rd"], "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 60}).status_code == 409
    )
    clock.sweep()
    clock.sweep()
    rows = users["root"].get(f"/api/v1/suts/{sut}/queue").json()["items"]
    assert len(rows) == 1 and rows[0]["id"] == second["id"] and rows[0]["offer_status"] == "notified"
    assert count(application, AuditEvent, AuditEvent.event_type == "offer_timeout") == 1
    assert count(application, Notification, Notification.event_key.like("offer-timeout:%")) == 1
    rejoin = join(users["rd"], sut)
    assert rejoin["entry_key"] != first["entry_key"] and rejoin["position"] == 2
    assert claim(users["lab"], sut)["user"]["id"] == identity(application, "lab")


@pytest.mark.parametrize(
    "start,length,expected",
    [
        (30 * 24 * 60, 24 * 60, 201),
        (30 * 24 * 60 + 1, 60, 422),
        (0, 60, 422),
        (-1, 60, 422),
        (1, 0, 422),
        (1, -1, 422),
        (1, 24 * 60 + 1, 422),
    ],
)
def test_reservation_horizon_and_elapsed_limits(arena, start, length, expected):
    users, sut, _, clock = arena
    data = {
        "sut_id": sut,
        "start_time": (clock.now + timedelta(minutes=start)).isoformat(),
        "end_time": (clock.now + timedelta(minutes=start + length)).isoformat(),
        "purpose": "Synthetic",
    }
    assert mutate(users["rd"], "POST", "/api/v1/reservations", data).status_code == expected


def test_reservation_offsets_half_open_overlap_conflicts_and_edit_permissions(arena, application):
    users, sut, _, clock = arena
    booked = reserve(users["rd"], sut, clock, start=60, length=60)
    adjacent = reserve(users["lab"], sut, clock, start=120, length=60)
    body = {
        "sut_id": sut,
        "start_time": (clock.now + timedelta(minutes=90)).isoformat(),
        "end_time": (clock.now + timedelta(minutes=150)).isoformat(),
        "purpose": "Overlap",
    }
    assert mutate(users["root"], "POST", "/api/v1/reservations", body).status_code == 409
    body.pop("sut_id")
    assert mutate(users["lab"], "PUT", f"/api/v1/reservations/{booked['id']}", body).status_code == 409
    # Regular unrelated user may neither edit nor cancel another reservation.
    assert mutate(users["rd"], "PUT", f"/api/v1/reservations/{adjacent['id']}", body).status_code == 403
    assert mutate(users["rd"], "DELETE", f"/api/v1/reservations/{adjacent['id']}").status_code == 403
    taipei = (clock.now + timedelta(minutes=30)).astimezone(__import__("zoneinfo").ZoneInfo("Asia/Taipei"))
    updated = {
        **body,
        "start_time": taipei.isoformat(),
        "end_time": (taipei + timedelta(minutes=20)).isoformat(),
    }
    response = mutate(users["lab"], "PUT", f"/api/v1/reservations/{booked['id']}", updated)
    assert response.status_code == 200
    assert response.json()["start_time"].endswith("Z")
    assert (
        mutate(users["root"], "DELETE", f"/api/v1/reservations/{booked['id']}").json()["status"]
        == "cancelled"
    )
    assert mutate(users["root"], "DELETE", f"/api/v1/reservations/{booked['id']}").status_code == 409
    assert count(application, Reservation) == 2
    assert users["rd"].get("/api/v1/reservations?start=2026-10-15T12:00:00").status_code == 422
    assert (
        mutate(
            users["rd"],
            "POST",
            "/api/v1/reservations",
            {**body, "sut_id": sut, "start_time": "2026-10-15T15:00:00"},
        ).status_code
        == 422
    )


def test_claim_and_extension_overlap_requires_ack_never_shortens_or_reassigns(arena, application):
    users, sut, _, clock = arena
    booking = reserve(users["lab"], sut, clock, start=60, length=60)
    response = mutate(users["rd"], "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 180})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "reservation_conflict_confirmation_required"
    assert response.json()["detail"]["conflicts"][0]["reservation_id"] == booking["id"]
    assert count(application, CurrentUsage) == 0
    usage = claim(users["rd"], sut, 180, acknowledge_reservation_conflict=True)
    assert usage["expected_end_time"] == (clock.now + timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    data = {"usage_key": usage["usage_key"], "expected_end_time": (clock.now + timedelta(days=3)).isoformat()}
    assert mutate(users["lab"], "PATCH", f"/api/v1/suts/{sut}/usage/expected-end", data).status_code == 409
    assert (
        mutate(
            users["rd"],
            "PATCH",
            f"/api/v1/suts/{sut}/usage/expected-end",
            {**data, "acknowledge_reservation_conflict": True},
        ).status_code
        == 200
    )
    assert (
        mutate(
            users["rd"],
            "PATCH",
            f"/api/v1/suts/{sut}/usage/expected-end",
            {**data, "expected_end_time": clock.now.isoformat()},
        ).status_code
        == 422
    )
    assert count(application, UsageHistory) == 0
    with unit_of_work(application.state.engine) as db:
        row = db.scalar(select(CurrentUsage))
        assert row.usage_key == usage["usage_key"] and row.start_time == clock.now
        assert db.get(Reservation, booking["id"]).status == "confirmed"


def test_waiting_does_not_expire_or_release_current_holder(arena, application):
    users, sut, _, clock = arena
    holder = claim(users["root"], sut, 72 * 60)
    booking = reserve(users["rd"], sut, clock, start=1, length=60)
    clock.advance(minutes=16)
    clock.sweep()
    row = users["rd"].get(f"/api/v1/reservations/{booking['id']}").json()
    assert row["status"] == "waiting_for_release" and row["start_deadline"] is None
    assert count(application, CurrentUsage) == 1 and count(application, UsageHistory) == 0
    assert count(application, AuditEvent, AuditEvent.event_type == "reservation_no_show") == 0
    assert release(users["root"], sut, holder).status_code == 200
    clock.advance(minutes=15)
    clock.sweep()
    assert users["rd"].get(f"/api/v1/reservations/{booking['id']}").json()["status"] == "no_show"
    assert count(application, AuditEvent, AuditEvent.event_type == "reservation_no_show") == 1


def test_automatic_wait_preserves_priority_and_handoff_over_fifo(arena, application):
    users, sut, _, clock = arena
    holder = claim(users["root"], sut, 60)
    join(users["lab"], sut)
    booking = reserve(users["rd"], sut, clock, start=1, length=60)
    assert mutate(users["rd"], "POST", f"/api/v1/reservations/{booking['id']}/check-in").status_code == 410
    clock.advance(minutes=17)
    clock.sweep()
    assert users["rd"].get(f"/api/v1/reservations/{booking['id']}").json()["status"] == "waiting_for_release"
    assert mutate(users["root"], "DELETE", f"/api/v1/reservations/{booking['id']}").status_code == 409
    result = release(users["root"], sut, holder).json()
    assert result["priority_reservation_id"] == booking["id"]
    assert result["queue"][0]["offer_status"] == "waiting"
    assert count(application, CurrentUsage) == 0
    assert (
        mutate(users["lab"], "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 1}).status_code == 409
    )
    assert (
        mutate(users["rd"], "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 60}).status_code == 422
    )
    reserved = claim(users["rd"], sut, 1, reservation_id=booking["id"])
    assert release(users["rd"], sut, reserved).status_code == 200
    assert users["lab"].get(f"/api/v1/suts/{sut}/queue").json()["items"][0]["offer_status"] == "notified"
    assert count(application, Notification, Notification.event_key.like(f"auto-ready:{booking['id']}:%")) == 1


def test_available_reservation_requires_explicit_start_before_deadline(arena, application):
    users, sut, _, clock = arena
    booking = reserve(users["rd"], sut, clock, start=1, length=30)
    clock.advance(minutes=1)
    clock.sweep()
    for name in ("lab", "rd"):
        assert (
            mutate(users[name], "POST", f"/api/v1/reservations/{booking['id']}/check-in").status_code == 410
        )
    assert count(application, CurrentUsage) == 0
    assert (
        users["rd"].get(f"/api/v1/reservations/{booking['id']}").json()["display_status"] == "Ready to start"
    )
    clock.advance(minutes=15)
    clock.sweep()
    assert users["rd"].get(f"/api/v1/reservations/{booking['id']}").json()["status"] == "no_show"


def test_no_show_releases_priority_and_notifies_fifo(arena, application):
    users, sut, _, clock = arena
    reserve(users["root"], sut, clock, start=1, length=60)
    clock.advance(minutes=1)
    first = join(users["rd"], sut)
    assert first["offer_status"] == "waiting"
    clock.advance(minutes=15)
    clock.sweep()
    clock.sweep()
    rows = users["rd"].get(f"/api/v1/suts/{sut}/queue").json()["items"]
    assert rows[0]["offer_status"] == "notified"
    assert count(application, Notification, Notification.event_key.like("offer:%")) == 1
    assert count(application, CurrentUsage) == 0
    assert claim(users["rd"], sut)["reservation_id"] is None


@pytest.mark.parametrize("state", ["maintenance", "out_of_service"])
def test_unavailable_and_archived_gate_new_actions_but_preserve_release(arena, application, state):
    users, sut, sut2, clock = arena
    usage = claim(users["rd"], sut)
    join(users["lab"], sut)
    booking = reserve(users["root"], sut, clock, start=60)
    data = {"state": state, "reason": "Synthetic repair", "acknowledge_activity": True}
    assert mutate(users["root"], "PATCH", f"/api/v1/suts/{sut}/operational-state", data).status_code == 200
    booked_state = users["root"].get(f"/api/v1/reservations/{booking['id']}").json()
    assert booked_state["operational_reason"] == "Synthetic repair"
    assert booked_state["in_use"] is True
    calendar = users["root"].get("/calendar?day=2026-10-15&view=day").text
    assert "Synthetic repair" in calendar and "In Use" in calendar
    assert (
        mutate(users["root"], "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 60}).status_code
        == 409
    )
    assert (
        mutate(
            users["root"], "POST", f"/api/v1/suts/{sut}/queue", {"requested_duration_minutes": 60}
        ).status_code
        == 409
    )
    assert (
        mutate(
            users["root"],
            "POST",
            "/api/v1/reservations",
            {
                "sut_id": sut,
                "start_time": (clock.now + timedelta(days=2)).isoformat(),
                "end_time": (clock.now + timedelta(days=2, hours=1)).isoformat(),
                "purpose": "New",
            },
        ).status_code
        == 409
    )
    assert (
        count(application, CurrentUsage) == 1
        and count(application, QueueEntry) == 1
        and count(application, Reservation) == 1
    )
    assert release(users["rd"], sut, usage).status_code == 200
    waiting = users["lab"].get(f"/api/v1/suts/{sut}/queue").json()["items"][0]
    assert waiting["offer_status"] == "waiting"
    assert (
        mutate(
            users["lab"], "DELETE", f"/api/v1/suts/{sut}/queue", {"entry_key": waiting["entry_key"]}
        ).status_code
        == 204
    )
    assert mutate(users["root"], "DELETE", f"/api/v1/suts/{sut2}").status_code == 204
    for path, payload in [
        (f"/suts/{sut2}/claim", {"duration_minutes": 60}),
        (f"/suts/{sut2}/queue", {"requested_duration_minutes": 60}),
        (
            "/reservations",
            {
                "sut_id": sut2,
                "start_time": (clock.now + timedelta(hours=1)).isoformat(),
                "end_time": (clock.now + timedelta(hours=2)).isoformat(),
                "purpose": "Archived",
            },
        ),
    ]:
        assert mutate(users["rd"], "POST", "/api/v1" + path, payload).status_code == 409


def test_maintenance_pauses_remaining_offer_time_and_does_not_resurrect_expired(arena, application):
    users, sut, _, clock = arena
    usage = claim(users["root"], sut)
    join(users["rd"], sut)
    join(users["lab"], sut)
    assert release(users["root"], sut, usage).status_code == 200
    clock.advance(minutes=5)
    assert (
        mutate(
            users["root"],
            "PATCH",
            f"/api/v1/suts/{sut}/operational-state",
            {"state": "maintenance", "reason": "Repair", "acknowledge_activity": True},
        ).status_code
        == 200
    )
    clock.advance(days=1)
    clock.sweep()
    assert count(application, QueueEntry) == 2
    assert (
        mutate(
            users["root"], "PATCH", f"/api/v1/suts/{sut}/operational-state", {"state": "normal"}
        ).status_code
        == 200
    )
    head = users["rd"].get(f"/api/v1/suts/{sut}/queue").json()["items"][0]
    assert head["paused_at"] is None
    assert datetime.fromisoformat(head["offer_expires_at"]) == clock.now + timedelta(minutes=10)
    clock.advance(minutes=10)
    clock.sweep()
    assert users["lab"].get(f"/api/v1/suts/{sut}/queue").json()["items"][0]["user"]["id"] == identity(
        application, "lab"
    )
    assert count(application, AuditEvent, AuditEvent.event_type == "offer_timeout") == 1


def test_disabled_queue_member_retained_but_skipped_and_history_preserved(arena, application):
    users, sut, _, clock = arena
    holder = claim(users["root"], sut)
    join(users["rd"], sut)
    join(users["lab"], sut)
    uid = identity(application, "rd")
    assert (
        mutate(
            users["root"],
            "PATCH",
            f"/api/v1/users/{uid}/status",
            {"is_active": False, "reason": "Synthetic", "acknowledge_resources": True},
        ).status_code
        == 200
    )
    assert count(application, QueueEntry) == 2
    assert release(users["root"], sut, holder).status_code == 200
    rows = users["root"].get(f"/api/v1/suts/{sut}/queue").json()["items"]
    assert not rows[0]["eligible"] and rows[1]["offer_status"] == "notified"
    assert (
        mutate(users["root"], "PATCH", f"/api/v1/users/{uid}/status", {"is_active": True}).status_code == 200
    )
    assert (
        mutate(
            users["rd"],
            "POST",
            "/api/v1/auth/login",
            {"username": "rd", "password": "Synthetic-password-123!"},
        ).status_code
        == 200
    )
    # Reactivation cannot bypass an already-issued live offer.
    assert (
        mutate(users["rd"], "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 60}).status_code == 409
    )
    usage = claim(users["lab"], sut)
    assert release(users["lab"], sut, usage).status_code == 200
    assert users["rd"].get(f"/api/v1/suts/{sut}/queue").json()["items"][0]["offer_status"] == "notified"


def test_history_survives_profile_archive_disable_and_read_filters(arena, application):
    users, sut, _, clock = arena
    usage = claim(users["rd"], sut)
    clock.advance(minutes=11)
    assert release(users["rd"], sut, usage).status_code == 200
    uid = identity(application, "rd")
    assert (
        mutate(
            users["rd"],
            "PATCH",
            "/api/v1/users/me",
            {"display_name": "Renamed RD", "team": "New Demo", "email": "renamed@example.com"},
        ).status_code
        == 200
    )
    assert mutate(users["root"], "DELETE", f"/api/v1/suts/{sut}").status_code == 204
    assert (
        mutate(
            users["root"], "PATCH", f"/api/v1/users/{uid}/status", {"is_active": False, "reason": "Synthetic"}
        ).status_code
        == 200
    )
    before = count(application, UsageHistory)
    data = users["root"].get(f"/api/v1/history?sut_id={sut}&user_id={uid}&page_size=1").json()
    assert data["total"] == 1 and data["items"][0]["user"]["display_name"] == "Renamed RD"
    assert data["items"][0]["sut_name"] == "Coordination-1"
    assert users["root"].get(f"/history?sut_id={sut}").status_code == 200
    clock.advance(days=365)
    clock.sweep()
    assert count(application, UsageHistory) == before == 1
    assert users["root"].get("/api/v1/history?page=2&page_size=1").json()["items"] == []


def test_notifications_recipient_isolation_explicit_read_and_gets_never_mutate(arena, application):
    users, sut, _, clock = arena
    claim(users["root"], sut, 1)
    clock.advance(minutes=2)
    before = count(application, Notification)
    for path in [
        "/api/v1/history",
        "/api/v1/reservations",
        "/api/v1/notifications",
        f"/api/v1/suts/{sut}/coordination",
        f"/suts/{sut}/activity",
    ]:
        assert users["root"].get(path).status_code == 200
    assert count(application, Notification) == before
    clock.sweep()
    notice = users["root"].get("/api/v1/notifications").json()["items"][0]
    assert notice["read_at"] is None
    assert users["rd"].get("/api/v1/notifications").json()["items"] == []
    assert mutate(users["rd"], "POST", f"/api/v1/notifications/{notice['id']}/read").status_code == 403
    assert mutate(users["root"], "POST", f"/api/v1/notifications/{notice['id']}/read").status_code == 200
    assert count(application, CurrentUsage) == 1
    for path in ["/history", "/calendar", "/reservations", "/my-usage", "/notifications"]:
        assert users["root"].get(path).status_code == 200
