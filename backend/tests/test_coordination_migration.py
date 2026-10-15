from datetime import UTC, datetime

from alembic import command
from alembic.config import Config
from sqlalchemy import text, select

from app.core.database import make_engine, unit_of_work
from app.models.domain import CurrentUsage, QueueEntry, UsageHistory
from conftest import ROOT


def test_upgrade_backfills_day1_live_data_and_downgrade_preserves_it(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/upgrade.db"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(ROOT / "backend/alembic.ini"))
    command.upgrade(config, "fd0b3a205c15")
    engine = make_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id,username,display_name,team,email,password_hash,role,is_active,must_change_password,created_at) VALUES (1,'demo','Demo','Demo','demo@example.com','synthetic-hash','user',1,0,'2026-10-15 04:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO labs (id,name,location,description,created_at) VALUES (1,'Demo','Synthetic','','2026-10-15 04:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO suts (id,lab_id,name,normalized_name,platform,owner_team,description,updated_at,is_archived,operational_state,created_at) VALUES (1,1,'Demo','demo','Demo','Demo','','2026-10-15 04:00:00',0,'normal','2026-10-15 04:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO current_usages (id,sut_id,user_id,start_time,expected_end_time,created_at,purpose) VALUES (1,1,1,'2026-10-15 04:00:00','2026-10-15 05:00:00','2026-10-15 04:00:00','Synthetic existing purpose')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO queue_entries (id,sut_id,user_id,requested_duration_minutes,offer_status,created_at) VALUES (1,1,1,60,'waiting','2026-10-15 04:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO usage_histories (id,usage_key,sut_id,user_id,start_time,end_time,duration_minutes,release_reason,created_at) VALUES (1,'existing-release',1,1,'2026-10-14 04:00:00','2026-10-14 05:00:00',60,'user','2026-10-14 05:00:00')"
            )
        )
    command.upgrade(config, "head")
    command.check(config)
    with unit_of_work(engine) as db:
        usage = db.scalar(select(CurrentUsage))
        entry = db.scalar(select(QueueEntry))
        history = db.scalar(select(UsageHistory))
        assert len(usage.usage_key) == 32 and len(entry.entry_key) == 32
        assert usage.purpose == "Synthetic existing purpose"
        assert usage.start_time == datetime(2026, 10, 15, 4, tzinfo=UTC)
        assert entry.offer_generation == 0 and entry.paused_at is None
        assert history.usage_key == "existing-release" and history.duration_minutes == 60
    command.downgrade(config, "fd0b3a205c15")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT purpose FROM current_usages")) == "Synthetic existing purpose"
        assert connection.scalar(text("SELECT count(*) FROM usage_histories")) == 1
    command.upgrade(config, "head")
    command.check(config)
    engine.dispose()
