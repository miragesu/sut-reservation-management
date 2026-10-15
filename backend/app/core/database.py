from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.types import DateTime, TypeDecorator


NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def utcnow():
    return datetime.now(UTC)


def clock_now(db):
    return db.info.get("clock", utcnow)()


class UTCDateTime(TypeDecorator):
    """SQLite stores naive UTC; all Python boundaries require/return aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone-aware datetime required")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


def make_engine(url):
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 5})

    @event.listens_for(engine, "connect")
    def configure(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA journal_mode=WAL")

    return engine


@contextmanager
def unit_of_work(engine, *, write=False):
    with Session(engine, expire_on_commit=False) as db:
        try:
            if write:
                # Acquire the SQLite write reservation BEFORE reads/checks.
                db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            yield db
            db.commit() if write else db.rollback()
        except Exception:
            db.rollback()
            raise
