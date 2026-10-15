from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.core.database import unit_of_work
from app.models.domain import AuditEvent, QueueEntry, UsageHistory
from conftest import csrf, identity, mutate
from coordination_helpers import claim, count, join, release, reserve


def test_exact_microsecond_reservation_limits_and_overflow_datetime(arena):
    users, sut, _, clock = arena
    start = clock.now + timedelta(days=30)
    data = {
        "sut_id": sut,
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(hours=24)).isoformat(),
        "purpose": "Limit",
    }
    assert mutate(users["rd"], "POST", "/api/v1/reservations", data).status_code == 201
    assert (
        mutate(
            users["rd"],
            "POST",
            "/api/v1/reservations",
            {**data, "start_time": (start + timedelta(microseconds=1)).isoformat()},
        ).status_code
        == 422
    )
    assert (
        mutate(
            users["rd"],
            "POST",
            "/api/v1/reservations",
            {**data, "end_time": (start + timedelta(hours=24, microseconds=1)).isoformat()},
        ).status_code
        == 422
    )
    assert (
        mutate(
            users["rd"], "POST", "/api/v1/reservations", {**data, "start_time": "0001-01-01T00:00:00+14:00"}
        ).status_code
        == 422
    )


def test_estimate_extension_role_wrong_identity_and_clocks(arena, application):
    users, sut, _, clock = arena
    usage = claim(users["rd"], sut, 1)
    payload = {
        "usage_key": usage["usage_key"],
        "expected_end_time": (clock.now + timedelta(days=3)).isoformat(),
    }
    # A second ordinary account has no administrative adjustment rights.
    with unit_of_work(application.state.engine, write=True) as db:
        from app.models.domain import User

        db.get(User, identity(application, "lab")).role = "user"
    assert mutate(users["lab"], "PATCH", f"/api/v1/suts/{sut}/usage/expected-end", payload).status_code == 403
    assert (
        mutate(users["root"], "PATCH", f"/api/v1/suts/{sut}/usage/expected-end", payload).status_code == 200
    )
    assert (
        mutate(
            users["rd"], "PATCH", f"/api/v1/suts/{sut}/usage/expected-end", {**payload, "usage_key": "stale"}
        ).status_code
        == 409
    )
    assert (
        mutate(
            users["rd"],
            "PATCH",
            f"/api/v1/suts/{sut}/usage/expected-end",
            {**payload, "expected_end_time": "0001-01-01T00:00:00+14:00"},
        ).status_code
        == 422
    )
    clock.advance(minutes=2)
    assert mutate(users["rd"], "PATCH", f"/api/v1/suts/{sut}/usage/expected-end", payload).status_code == 200
    assert count(application, UsageHistory) == 0


def test_current_owner_reservation_claim_removes_own_queue(arena, application):
    users, sut, _, clock = arena
    holder = claim(users["root"], sut)
    join(users["rd"], sut)
    booking = reserve(users["rd"], sut, clock, start=1, length=60)
    clock.advance(minutes=1)
    assert release(users["root"], sut, holder).status_code == 200
    reserved = claim(users["rd"], sut, 1, reservation_id=booking["id"])
    assert reserved["reservation_id"] == booking["id"]
    assert count(application, QueueEntry) == 0
    assert users["rd"].get(f"/api/v1/reservations/{booking['id']}").json()["status"] == "claimed"


def test_reservation_deadline_shorter_than_grace_completes_without_no_show(arena, application):
    users, sut, _, clock = arena
    booking = reserve(users["rd"], sut, clock, start=1, length=5)
    clock.advance(minutes=6)
    clock.sweep()
    assert users["rd"].get(f"/api/v1/reservations/{booking['id']}").json()["status"] == "completed"
    assert count(application, AuditEvent, AuditEvent.event_type == "reservation_no_show") == 0


def test_reservation_pause_and_resume_queue_offer_after_checked_in_priority(arena, application):
    users, sut, _, clock = arena
    holder = claim(users["root"], sut)
    join(users["lab"], sut)
    reserve(users["rd"], sut, clock, start=5, length=30)
    assert release(users["root"], sut, holder).status_code == 200
    clock.advance(minutes=5)
    clock.sweep()  # Reservation availability now automatically pauses FIFO offers.
    rows = users["root"].get(f"/api/v1/suts/{sut}/queue").json()["items"]
    assert rows[0]["paused_at"] is not None
    assert (
        mutate(
            users["root"],
            "PATCH",
            f"/api/v1/suts/{sut}/operational-state",
            {"state": "maintenance", "reason": "Repair", "acknowledge_activity": True},
        ).status_code
        == 200
    )
    clock.advance(minutes=20)
    clock.sweep()
    assert (
        mutate(
            users["root"], "PATCH", f"/api/v1/suts/{sut}/operational-state", {"state": "normal"}
        ).status_code
        == 200
    )
    assert users["root"].get(f"/api/v1/suts/{sut}/queue").json()["items"][0]["paused_at"] is not None
    assert (
        mutate(users["lab"], "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 1}).status_code == 409
    )
    clock.advance(minutes=10)
    clock.sweep()
    rows = users["root"].get(f"/api/v1/suts/{sut}/queue").json()["items"]
    assert rows[0]["paused_at"] is None
    assert datetime.fromisoformat(rows[0]["offer_expires_at"]) == clock.now + timedelta(minutes=10)
    assert claim(users["lab"], sut, 1)["user"]["id"] == identity(application, "lab")


def test_inactive_reservation_preserved_but_does_not_deadlock_queue(arena, application):
    users, sut, _, clock = arena
    booking = reserve(users["rd"], sut, clock, start=1, length=60)
    clock.advance(minutes=1)
    join(users["lab"], sut)
    uid = identity(application, "rd")
    assert (
        mutate(
            users["root"],
            "PATCH",
            f"/api/v1/users/{uid}/status",
            {"is_active": False, "reason": "Inactive", "acknowledge_resources": True},
        ).status_code
        == 200
    )
    stored = users["root"].get(f"/api/v1/reservations/{booking['id']}").json()
    assert stored["status"] == "waiting_for_release" and stored["cancelled_at"] is None
    assert users["root"].get(f"/api/v1/suts/{sut}/queue").json()["items"][0]["offer_status"] == "notified"
    assert claim(users["lab"], sut, 1, acknowledge_reservation_conflict=True)["sut_id"] == sut


def test_live_offer_disabled_and_reactivated_without_duplicate_or_priority_theft(arena, application):
    users, sut, _, clock = arena
    holder = claim(users["root"], sut)
    join(users["rd"], sut)
    join(users["lab"], sut)
    assert release(users["root"], sut, holder).status_code == 200
    clock.advance(minutes=2)
    uid = identity(application, "rd")
    assert (
        mutate(
            users["root"],
            "PATCH",
            f"/api/v1/users/{uid}/status",
            {"is_active": False, "reason": "Inactive", "acknowledge_resources": True},
        ).status_code
        == 200
    )
    rows = users["root"].get(f"/api/v1/suts/{sut}/queue").json()["items"]
    assert rows[0]["paused_at"] is not None and rows[1]["offer_status"] == "notified"
    clock.advance(minutes=1)
    assert (
        mutate(users["root"], "PATCH", f"/api/v1/users/{uid}/status", {"is_active": True}).status_code == 200
    )
    assert users["root"].get(f"/api/v1/suts/{sut}/queue").json()["items"][0]["paused_at"] is not None
    active = claim(users["lab"], sut, 1)
    assert release(users["lab"], sut, active).status_code == 200
    rows = users["root"].get(f"/api/v1/suts/{sut}/queue").json()["items"]
    assert rows[0]["paused_at"] is None
    assert datetime.fromisoformat(rows[0]["offer_expires_at"]) == clock.now + timedelta(minutes=13)


def test_maintenance_edit_cancel_existing_booking_and_clear_queue_authorization(arena, application):
    users, sut, sut2, clock = arena
    for sid in (sut, sut2):
        holder = claim(users["root"], sid)
        join(users["rd"], sid)
        booking = reserve(users["rd"], sid, clock, start=60)
        assert (
            mutate(
                users["rd"], "DELETE", f"/api/v1/suts/{sid}/queue/all", {"reason": "Unauthorized"}
            ).status_code
            == 403
        )
        assert (
            mutate(
                users["lab"], "DELETE", f"/api/v1/suts/{sid}/queue/all", {"reason": "Reviewed"}
            ).status_code
            == 204
        )
        assert (
            mutate(
                users["root"],
                "PATCH",
                f"/api/v1/suts/{sid}/operational-state",
                {"state": "maintenance", "reason": "Repair", "acknowledge_activity": True},
            ).status_code
            == 200
        )
        update = {
            "start_time": booking["start_time"],
            "end_time": booking["end_time"],
            "purpose": "Maintenance coordination",
        }
        assert mutate(users["rd"], "PUT", f"/api/v1/reservations/{booking['id']}", update).status_code == 200
        assert mutate(users["rd"], "DELETE", f"/api/v1/reservations/{booking['id']}").status_code == 200
        assert release(users["root"], sid, holder).status_code == 200
    assert count(application, QueueEntry) == 0


def test_web_forms_timezone_confirmation_history_and_blank_filters(arena, application):
    from zoneinfo import ZoneInfo

    users, sut, _, clock = arena
    reserve(users["lab"], sut, clock, start=60, length=60)
    response = users["rd"].post(
        f"/suts/{sut}/claim",
        data={"csrf_token": csrf(users["rd"]), "duration_minutes": 180, "purpose": "<script>test</script>"},
        follow_redirects=False,
    )
    assert response.status_code == 409 and "Taipei time (UTC+8)" in response.text
    assert "&lt;script&gt;" in response.text and "<script>test</script>" not in response.text
    response = users["rd"].post(
        f"/suts/{sut}/claim",
        data={
            "csrf_token": csrf(users["rd"]),
            "duration_minutes": 180,
            "purpose": "Synthetic",
            "acknowledge_reservation_conflict": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    usage = users["rd"].get(f"/api/v1/suts/{sut}/coordination").json()["usage"]
    local_end = (
        (clock.now + timedelta(days=2)).astimezone(ZoneInfo("Asia/Taipei")).replace(tzinfo=None).isoformat()
    )
    assert (
        users["rd"]
        .post(
            f"/suts/{sut}/expected-end",
            data={
                "csrf_token": csrf(users["rd"]),
                "usage_key": usage["usage_key"],
                "expected_end_time": local_end,
            },
            follow_redirects=False,
        )
        .status_code
        == 409
    )
    assert (
        users["rd"]
        .post(
            f"/suts/{sut}/expected-end",
            data={
                "csrf_token": csrf(users["rd"]),
                "usage_key": usage["usage_key"],
                "expected_end_time": local_end,
                "acknowledge_reservation_conflict": "true",
            },
            follow_redirects=False,
        )
        .status_code
        == 303
    )
    assert (
        users["rd"]
        .post(
            f"/suts/{sut}/release",
            data={"csrf_token": csrf(users["rd"]), "usage_key": usage["usage_key"]},
            follow_redirects=False,
        )
        .status_code
        == 303
    )
    assert "Synthetic" in users["root"].get("/history?sut_id=&user_id=&start=&end=").text
    assert users["root"].get("/reservations?sut_id=&user_id=").status_code == 200
    assert users["root"].get("/calendar?sut_id=&view=day&day=2026-10-15").status_code == 200
    assert users["root"].get("/calendar?day=9999-12-31").status_code == 422
    assert users["root"].get("/history?user_id=bad").status_code == 422


def test_csrf_auth_mass_assignment_on_all_new_mutations(arena, application):
    users, sut, _, clock = arena
    booking = reserve(users["root"], sut, clock)
    for path, body in [
        (f"/suts/{sut}/claim", {"duration_minutes": 60}),
        (f"/suts/{sut}/queue", {"requested_duration_minutes": 60}),
        (
            "/reservations",
            {
                "sut_id": sut,
                "start_time": booking["start_time"],
                "end_time": booking["end_time"],
                "purpose": "X",
            },
        ),
        (f"/reservations/{booking['id']}/check-in", None),
    ]:
        assert users["rd"].post("/api/v1" + path, json=body).status_code == 403
    assert (
        mutate(
            users["rd"],
            "POST",
            f"/api/v1/suts/{sut}/claim",
            {"duration_minutes": 60, "user_id": identity(application, "root")},
        ).status_code
        == 422
    )
    with TestClient(application) as anonymous:
        assert (
            mutate(anonymous, "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 60}).status_code
            == 401
        )
        assert anonymous.get("/api/v1/history").status_code == 401
        assert anonymous.get("/api/v1/reservations").status_code == 401
    with TestClient(application) as temporary:
        from conftest import sign_in

        sign_in(temporary, "temp")
        assert (
            mutate(temporary, "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 60}).status_code
            == 403
        )


def test_html_reservation_local_time_bounds_create_edit_cancel_and_invalid_input(arena):
    from zoneinfo import ZoneInfo

    users, sut, _, clock = arena
    local = (clock.now + timedelta(days=30)).astimezone(ZoneInfo("Asia/Taipei")).replace(tzinfo=None)
    data = {
        "csrf_token": csrf(users["rd"]),
        "sut_id": sut,
        "start_time": local.isoformat(),
        "end_time": (local + timedelta(hours=24)).isoformat(),
        "purpose": "HTML local boundary",
    }
    response = users["rd"].post("/reservations", data=data, follow_redirects=False)
    assert response.status_code == 303, response.text
    path = response.headers["location"]
    booking = users["rd"].get("/api/v1" + path).json()
    assert datetime.fromisoformat(booking["start_time"]) == clock.now + timedelta(days=30)
    assert (
        users["rd"]
        .post(
            "/reservations",
            data={**data, "end_time": (local + timedelta(hours=24, seconds=1)).isoformat()},
            follow_redirects=False,
        )
        .status_code
        == 422
    )
    assert (
        users["rd"]
        .post(
            "/reservations",
            data={**data, "start_time": (local + timedelta(seconds=1)).isoformat()},
            follow_redirects=False,
        )
        .status_code
        == 422
    )
    assert (
        users["rd"]
        .post("/reservations", data={**data, "start_time": "bad"}, follow_redirects=False)
        .status_code
        == 422
    )
    update = {k: v for k, v in data.items() if k != "sut_id"}
    update["purpose"] = "Edited HTML boundary"
    assert users["rd"].post(path + "/edit", data=update, follow_redirects=False).status_code == 303
    assert (
        users["rd"]
        .post(path + "/cancel", data={"csrf_token": csrf(users["rd"])}, follow_redirects=False)
        .status_code
        == 303
    )
    assert users["rd"].get("/api/v1" + path).json()["status"] == "cancelled"


def test_positive_fractional_claim_fits_subminute_booking_but_queue_remains_integer(arena, application):
    users, sut, _, clock = arena
    booking = reserve(users["rd"], sut, clock, start=1, length=0.5)
    clock.advance(minutes=1)
    usage = claim(users["rd"], sut, 0.1, reservation_id=booking["id"])
    assert datetime.fromisoformat(usage["expected_end_time"]) - datetime.fromisoformat(
        usage["start_time"]
    ) == timedelta(seconds=6)
    assert (
        mutate(
            users["lab"], "POST", f"/api/v1/suts/{sut}/queue", {"requested_duration_minutes": 1.5}
        ).status_code
        == 422
    )
    assert release(users["rd"], sut, usage).status_code == 200
    assert (
        mutate(users["rd"], "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 1e-30}).status_code
        == 422
    )
