import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import select, func

from app.core.database import make_engine, unit_of_work
from app.models.domain import User, Lab, SUT, Reservation, CurrentUsage, Notification
from app.schemas.coordination import ClaimInput, ReleaseInput
from app.services import coordination as c, coordination_queries as q

T = datetime(2026, 10, 16, 8, tzinfo=UTC)


class StartWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])
        self.url = "sqlite:///" + (Path(self.temp.name) / "test.sqlite").as_posix()
        old = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = self.url
        try:
            command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
        finally:
            if old is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = old
        self.engine = make_engine(self.url)
        with unit_of_work(self.engine, write=True) as db:
            for i in (1, 2):
                db.add(
                    User(
                        id=i,
                        username=f"demo{i}",
                        display_name=f"Demo {i}",
                        team="Test",
                        email=f"demo{i}@example.com",
                        password_hash="unused",
                        must_change_password=False,
                    )
                )
            db.add(Lab(id=1, name="Demo Lab", location="Synthetic"))
            db.flush()
            db.add(
                SUT(
                    id=1,
                    lab_id=1,
                    name="Demo SUT",
                    normalized_name="demo sut",
                    platform="Demo",
                    owner_team="Test",
                )
            )
            db.flush()
            db.add(
                Reservation(
                    id=1, sut_id=1, user_id=1, start_time=T, end_time=T + timedelta(hours=1), purpose="Test"
                )
            )

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def test_free_start_timer_notice_and_idempotency(self):
        with unit_of_work(self.engine, write=True) as db:
            c.reconcile_sut(db, db.get(SUT, 1), T)
            r = db.get(Reservation, 1)
            self.assertEqual(r.start_deadline, T + timedelta(minutes=15))
            self.assertEqual(q.reservation_view(db, r, T)["display_status"], "Ready to start")
            count = db.scalar(select(func.count()).select_from(Notification))
            c.reconcile_sut(db, db.get(SUT, 1), T + timedelta(minutes=5))
            self.assertEqual(db.scalar(select(func.count()).select_from(Notification)), count)
            c.claim(
                db,
                db.get(User, 1),
                1,
                ClaimInput(duration_minutes=5, reservation_id=1),
                now=T + timedelta(minutes=14),
            )
            self.assertEqual(r.status, "claimed")
            self.assertIsNone(r.checked_in_at)

    def test_waiting_more_than_15_minutes_then_release(self):
        with unit_of_work(self.engine, write=True) as db:
            u = CurrentUsage(
                sut_id=1,
                user_id=2,
                start_time=T - timedelta(hours=1),
                expected_end_time=T + timedelta(hours=2),
            )
            db.add(u)
            db.flush()
            c.reconcile_sut(db, db.get(SUT, 1), T + timedelta(minutes=20))
            r = db.get(Reservation, 1)
            self.assertEqual(r.status, "waiting_for_release")
            self.assertIsNone(r.start_deadline)
            c.release(
                db, db.get(User, 2), 1, ReleaseInput(usage_key=u.usage_key), now=T + timedelta(minutes=25)
            )
            self.assertEqual(r.start_deadline, T + timedelta(minutes=40))
            self.assertIsNone(c.current_usage(db, 1))
            c.reconcile_sut(db, db.get(SUT, 1), T + timedelta(minutes=40))
            self.assertEqual(r.status, "no_show")
            self.assertIsNone(c.protected(db, 1, T + timedelta(minutes=40)))

    def test_deadline_capped_at_reservation_end(self):
        with unit_of_work(self.engine, write=True) as db:
            r = db.get(Reservation, 1)
            r.end_time = T + timedelta(minutes=10)
            c.reconcile_sut(db, db.get(SUT, 1), T + timedelta(minutes=8))
            self.assertEqual(r.start_deadline, r.end_time)
            c.reconcile_sut(db, db.get(SUT, 1), r.end_time)
            self.assertEqual(r.status, "no_show")

    def test_restart_keeps_deadline_and_legacy_attendance_does_not_exempt(self):
        with unit_of_work(self.engine, write=True) as db:
            db.get(Reservation, 1).checked_in_at = T
            c.reconcile_sut(db, db.get(SUT, 1), T)
        self.engine.dispose()
        self.engine = make_engine(self.url)
        with unit_of_work(self.engine, write=True) as db:
            self.assertEqual(db.get(Reservation, 1).start_deadline, T + timedelta(minutes=15))
            c.reconcile_sut(db, db.get(SUT, 1), T + timedelta(minutes=15))
            self.assertEqual(db.get(Reservation, 1).status, "no_show")

    def test_waiting_entire_period_is_not_no_show(self):
        with unit_of_work(self.engine, write=True) as db:
            db.add(
                CurrentUsage(
                    sut_id=1,
                    user_id=2,
                    start_time=T - timedelta(hours=1),
                    expected_end_time=T + timedelta(hours=2),
                )
            )
            db.flush()
            c.reconcile_sut(db, db.get(SUT, 1), T)
            c.reconcile_sut(db, db.get(SUT, 1), T + timedelta(hours=1))
            self.assertEqual(db.get(Reservation, 1).status, "completed")

    def test_unavailability_pauses_remaining_time(self):
        with unit_of_work(self.engine, write=True) as db:
            sut = db.get(SUT, 1)
            c.reconcile_sut(db, sut, T)
            sut.operational_state = "maintenance"
            sut.operational_reason = "Test"
            c.reconcile_sut(db, sut, T + timedelta(minutes=5))
            c.reconcile_sut(db, sut, T + timedelta(minutes=25))
            self.assertIsNone(db.get(Reservation, 1).start_deadline)
            sut.operational_state = "normal"
            c.reconcile_sut(db, sut, T + timedelta(minutes=30))
            self.assertEqual(db.get(Reservation, 1).start_deadline, T + timedelta(minutes=40))

    def test_projection_does_not_start_timer_and_manual_checkin_removed(self):
        with unit_of_work(self.engine, write=True) as db:
            r = db.get(Reservation, 1)
            q.reservation_view(db, r, T)
            self.assertIsNone(r.start_deadline)
            with self.assertRaises(HTTPException) as cm:
                c.check_in(db, db.get(User, 1), 1, now=T)
            self.assertEqual(cm.exception.status_code, 410)


if __name__ == "__main__":
    unittest.main()
