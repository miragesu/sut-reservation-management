import time

from fastapi.testclient import TestClient

from app.core.database import unit_of_work
from app.main import create_app
from app.models.domain import AuditEvent, Notification, QueueEntry, Reservation
from coordination_helpers import claim, count, join, release, reserve


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Background deadline processing did not complete")


def runtime_app(application, clock):
    app = create_app(
        application.state.settings.model_copy(
            update={"deadline_processor_enabled": True, "deadline_poll_seconds": 0.1}
        )
    )
    app.state.clock = lambda: clock.now
    return app


def test_lifespan_catches_up_and_periodic_worker_runs_without_requests(arena, application):
    users, sut, _, clock = arena
    holder = claim(users["root"], sut)
    join(users["rd"], sut)
    join(users["lab"], sut)
    assert release(users["root"], sut, holder).status_code == 200
    clock.advance(minutes=15)
    app = runtime_app(application, clock)
    try:
        with TestClient(app):
            # Startup catch-up finishes before accepting the first HTTP request.
            assert count(application, AuditEvent, AuditEvent.event_type == "offer_timeout") == 1
            clock.advance(minutes=15)
            wait_until(lambda: count(application, AuditEvent, AuditEvent.event_type == "offer_timeout") == 2)
            assert count(application, QueueEntry) == 0
        before = count(application, Notification)
        with TestClient(app):
            assert count(application, Notification) == before
    finally:
        app.state.engine.dispose()


def test_no_show_background_and_retry_after_failed_iteration(arena, application, monkeypatch, caplog):
    from app.core import deadlines

    users, sut, _, clock = arena
    booking = reserve(users["rd"], sut, clock, start=1, length=60)
    app = runtime_app(application, clock)
    real = deadlines.process_deadlines
    calls = []

    def transient(engine, clock):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("SYNTHETIC-PRIVATE-DETAIL")
        return real(engine, clock)

    monkeypatch.setattr(deadlines, "process_deadlines", transient)
    try:
        with TestClient(app):
            clock.advance(minutes=16)

            def is_no_show():
                with unit_of_work(application.state.engine) as db:
                    return db.get(Reservation, booking["id"]).status == "no_show"

            wait_until(is_no_show)
            assert len(calls) >= 2
            assert count(application, AuditEvent, AuditEvent.event_type == "reservation_no_show") == 1
            assert "SYNTHETIC-PRIVATE-DETAIL" not in caplog.text
        assert app.state.deadline_last_success is not None
    finally:
        app.state.engine.dispose()


def test_mid_transition_failure_rolls_back_notification_and_state_before_retry(
    arena, application, monkeypatch
):
    import pytest
    from app.core.deadlines import process_deadlines
    from app.services import coordination

    users, sut, _, clock = arena
    booking = reserve(users["rd"], sut, clock, start=1, length=60)
    baseline_notices = count(application, Notification)
    clock.advance(minutes=16)
    original = coordination.notice

    def interrupted(*args, **kwargs):
        original(*args, **kwargs)  # flush the state, audit and notification, but do not commit
        raise RuntimeError("Simulated process interruption before transaction commit")

    monkeypatch.setattr(coordination, "notice", interrupted)
    with pytest.raises(RuntimeError):
        process_deadlines(application.state.engine, lambda: clock.now)
    with unit_of_work(application.state.engine) as db:
        assert db.get(Reservation, booking["id"]).status == "confirmed"
    assert count(application, AuditEvent, AuditEvent.event_type == "reservation_no_show") == 0
    assert count(application, Notification) == baseline_notices
    monkeypatch.setattr(coordination, "notice", original)
    process_deadlines(application.state.engine, lambda: clock.now)
    process_deadlines(application.state.engine, lambda: clock.now)
    assert count(application, AuditEvent, AuditEvent.event_type == "reservation_no_show") == 1
    assert count(application, Notification) == baseline_notices + 1
