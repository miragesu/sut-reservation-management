from sqlalchemy import select

from app.core.database import unit_of_work
from app.models.domain import Notification
from conftest import identity, mutate


def test_notification_history_is_recipient_scoped_paginated_and_read_only(arena, application):
    users, sut, _, clock = arena
    recipient = identity(application, "rd")
    with unit_of_work(application.state.engine, write=True) as db:
        for i in range(123):
            db.add(
                Notification(
                    user_id=recipient,
                    sut_id=sut,
                    message=f"Notice {i}",
                    event_key=f"day3-{i}",
                    created_at=clock.now,
                )
            )
        db.add(
            Notification(
                user_id=identity(application, "lab"),
                message="Private other recipient",
                event_key="other",
                created_at=clock.now,
            )
        )
    response = users["rd"].get("/api/v1/notifications?page_size=100").json()
    assert response["total"] == response["unread_count"] == 123
    assert len(response["items"]) == 100
    second = users["rd"].get("/api/v1/notifications?page=2&page_size=100").json()
    assert len(second["items"]) == 23
    assert not ({n["id"] for n in response["items"]} & {n["id"] for n in second["items"]})
    cutoff = second["items"][0]["id"]
    changes = users["rd"].get(f"/api/v1/notifications?after_id={cutoff}&page_size=100").json()
    assert all(n["id"] > cutoff for n in changes["items"])
    notice = second["items"][-1]["id"]
    assert users["rd"].get("/notifications?page=3").status_code == 200
    assert users["rd"].post(f"/api/v1/notifications/{notice}/read").status_code == 403
    assert mutate(users["lab"], "POST", f"/api/v1/notifications/{notice}/read").status_code == 403
    first = mutate(users["rd"], "POST", f"/api/v1/notifications/{notice}/read").json()
    clock.advance(minutes=1)
    assert mutate(users["rd"], "POST", f"/api/v1/notifications/{notice}/read").json() == first
    assert users["rd"].get("/api/v1/notifications").json()["unread_count"] == 122
    with unit_of_work(application.state.engine) as db:
        assert len(db.scalars(select(Notification)).all()) == 124
    assert users["rd"].get("/api/v1/notifications?page=0").status_code == 422


def test_dashboard_modal_outside_refresh_fragment_and_safe_names(arena):
    users, sut, _, _ = arena
    result = mutate(
        users["root"],
        "PUT",
        f"/api/v1/suts/{sut}",
        {"name": "<script>alert(1)</script>", "platform": "Demo", "owner_team": "Demo"},
    )
    assert result.status_code == 200
    page = users["rd"].get("/").text
    fragment = users["rd"].get("/dashboard/fragment").text
    assert 'id="quick-modal"' in page and 'id="quick-modal"' not in fragment
    for action in ["claim", "queue", "reserve", "detail"]:
        assert fragment.count(f'data-quick-action="{action}"') == 4
    assert "<script>alert(1)</script>" not in fragment
    assert "bootstrap.bundle.min.js" in page
    assert "data-user-id=" in page


def test_profile_refreshes_live_coordination_without_changing_references(arena, application):
    from coordination_helpers import claim, join, reserve
    from app.models.domain import AuditEvent, CurrentUsage, QueueEntry, Reservation
    from sqlalchemy import func

    users, sut, sut2, clock = arena
    held = claim(users["rd"], sut)
    claim(users["root"], sut2)
    join(users["rd"], sut2)
    booking = reserve(users["rd"], sut, clock, start=120, length=60)
    uid = identity(application, "rd")
    assert (
        mutate(
            users["rd"],
            "PATCH",
            "/api/v1/users/me",
            {"display_name": "Updated RD", "team": "Updated Team", "email": "updated@example.com"},
        ).status_code
        == 200
    )
    usage = users["root"].get(f"/api/v1/suts/{sut}/coordination").json()["usage"]
    queued = users["root"].get(f"/api/v1/suts/{sut2}/coordination").json()["queue"][0]
    booked = users["root"].get(f"/api/v1/reservations/{booking['id']}").json()
    for row in [usage, queued, booked]:
        assert row["user"] == {
            "id": uid,
            "display_name": "Updated RD",
            "team": "Updated Team",
            "email": "updated@example.com",
        }
    with unit_of_work(application.state.engine) as db:
        assert (
            db.scalar(select(CurrentUsage.user_id).where(CurrentUsage.usage_key == held["usage_key"])) == uid
        )
        assert db.scalar(select(QueueEntry.user_id)) == uid
        assert db.get(Reservation, booking["id"]).user_id == uid
        assert (
            db.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.event_type == "profile_updated")
            )
            == 1
        )


def test_all_status_sort_ranks_natural_ties_lab_groups_and_archive(arena, application):
    from datetime import timedelta
    from app.models.domain import SUT, CurrentUsage, Reservation

    users, first, second, clock = arena
    uid = identity(application, "rd")
    with unit_of_work(application.state.engine, write=True) as db:
        lab = db.get(SUT, first).lab_id
        ids = []
        for name, state in [
            ("SUT-10", "normal"),
            ("sut-02", "normal"),
            ("SUT-2", "normal"),
            ("reserved", "normal"),
            ("used", "normal"),
            ("repair", "maintenance"),
            ("broken", "out_of_service"),
            ("archive", "normal"),
        ]:
            row = SUT(
                lab_id=lab,
                name=name,
                normalized_name=name.casefold(),
                platform="Day3",
                owner_team="Demo",
                operational_state=state,
                operational_reason="Synthetic service" if state != "normal" else None,
                is_archived=name == "archive",
            )
            db.add(row)
            db.flush()
            ids.append(row.id)
        db.add(
            Reservation(
                sut_id=ids[3],
                user_id=uid,
                start_time=clock.now - timedelta(minutes=1),
                end_time=clock.now + timedelta(hours=1),
                purpose="Live",
            )
        )
        db.add(
            CurrentUsage(
                sut_id=ids[4],
                user_id=uid,
                start_time=clock.now - timedelta(hours=2),
                expected_end_time=clock.now - timedelta(hours=1),
            )
        )
    names = users["rd"].get("/api/v1/dashboard?platform=Day3").json()["items"]
    ties = [r["id"] for r in names if r["name"].casefold() in ("sut-02", "sut-2", "sut-10")]
    assert ties == ids[1:3] + ids[:1]
    ranked = users["rd"].get("/api/v1/dashboard?platform=Day3&sort=status").json()["items"]
    assert [r["status"] for r in ranked] == ["Available"] * 3 + [
        "Reserved",
        "In Use",
        "Maintenance",
        "Out of Service",
    ]
    assert next(r for r in ranked if r["status"] == "In Use")["overdue"]
    assert len(users["root"].get("/api/v1/suts?platform=Day3&include_archived=true").json()["items"]) == 8
    filtered = users["rd"].get("/dashboard/fragment?platform=Day3&status=Maintenance").text
    assert filtered.count("data-sut-id=") == 2
    assert "repair" in filtered and "SUT-10" not in filtered
    assert users["rd"].get("/suts?search=repair").text.count('href="/suts/') == 1
    assert "No matching SUTs." in users["rd"].get("/suts?lab_id=&search=missing-device").text
    assert users["rd"].get("/suts?lab_id=-1").status_code == 422
    assert users["rd"].get("/api/v1/dashboard?sort=status").json()["items"][-1]["id"] == second


def test_reservation_notices_are_persisted_once_per_schedule_and_start(arena, application):
    from coordination_helpers import reserve

    users, sut, _, clock = arena
    booking = reserve(users["rd"], sut, clock, start=60, length=60)
    before = users["rd"].get("/api/v1/notifications").json()
    assert any("upcoming reservation scheduled" in n["message"] for n in before["items"])
    clock.sweep()
    clock.sweep()
    assert users["rd"].get("/api/v1/notifications").json() == before
    clock.advance(minutes=60)
    clock.sweep()
    clock.sweep()
    notices = users["rd"].get("/api/v1/notifications").json()["items"]
    assert sum("has started" in n["message"] for n in notices) == 1
    assert users["rd"].get(f"/api/v1/reservations/{booking['id']}").json()["status"] == "confirmed"
