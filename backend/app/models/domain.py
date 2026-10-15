from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, UTCDateTime, utcnow


class Created:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class User(Created, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('user','lab_admin','super_admin')", name="role"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    display_name: Mapped[str] = mapped_column(String(120))
    team: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    deactivated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    deactivated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    deactivation_reason: Mapped[str | None] = mapped_column(Text)


class LoginSession(Created, Base):
    __tablename__ = "login_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)


class Lab(Created, Base):
    __tablename__ = "labs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    location: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")


class SUT(Created, Base):
    __tablename__ = "suts"
    __table_args__ = (
        UniqueConstraint("lab_id", "normalized_name", name="uq_suts_lab_normalized_name"),
        CheckConstraint(
            "operational_state IN ('normal','maintenance','out_of_service')", name="operational_state"
        ),
        CheckConstraint(
            "operational_state = 'normal' OR length(trim(operational_reason)) > 0 AND operational_reason IS NOT NULL",
            name="operational_reason",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    lab_id: Mapped[int] = mapped_column(ForeignKey("labs.id"), index=True)
    lab: Mapped[Lab] = relationship()
    name: Mapped[str] = mapped_column(String(120))
    normalized_name: Mapped[str] = mapped_column(String(240))
    platform: Mapped[str] = mapped_column(String(100))
    owner_team: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    bmc_ip: Mapped[str | None] = mapped_column(String(45))
    host_ip: Mapped[str | None] = mapped_column(String(45))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    archived_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    operational_state: Mapped[str] = mapped_column(String(20), default="normal")
    operational_reason: Mapped[str | None] = mapped_column(Text)
    operational_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    operational_updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Reservation(Created, Base):
    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="positive_interval"),
        CheckConstraint(
            "status IN ('confirmed','waiting_for_release','claimed','cancelled','completed','no_show')",
            name="status",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    sut_id: Mapped[int] = mapped_column(ForeignKey("suts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    end_time: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    purpose: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(25), default="confirmed", index=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    checked_in_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    claimed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    no_show_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class CurrentUsage(Created, Base):
    __tablename__ = "current_usages"
    __table_args__ = (CheckConstraint("expected_end_time > start_time", name="positive_interval"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    usage_key: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: uuid4().hex)
    sut_id: Mapped[int] = mapped_column(ForeignKey("suts.id"), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(UTCDateTime())
    expected_end_time: Mapped[datetime] = mapped_column(UTCDateTime())
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("reservations.id"))
    purpose: Mapped[str | None] = mapped_column(Text)


class QueueEntry(Created, Base):
    __tablename__ = "queue_entries"
    __table_args__ = (
        UniqueConstraint("sut_id", "user_id"),
        CheckConstraint("requested_duration_minutes > 0", name="positive_duration"),
        CheckConstraint("offer_status IN ('waiting','notified')", name="offer_status"),
        CheckConstraint(
            "offer_status != 'notified' OR (notified_at IS NOT NULL AND offer_expires_at IS NOT NULL AND offer_expires_at > notified_at)",
            name="offer_deadline",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    sut_id: Mapped[int] = mapped_column(ForeignKey("suts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    entry_key: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: uuid4().hex)
    offer_generation: Mapped[int] = mapped_column(Integer, default=0)
    paused_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    remaining_microseconds: Mapped[int | None] = mapped_column(Integer)
    requested_duration_minutes: Mapped[int] = mapped_column(Integer)
    notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    offer_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    offer_status: Mapped[str] = mapped_column(String(20), default="waiting")


class UsageHistory(Created, Base):
    __tablename__ = "usage_histories"
    __table_args__ = (
        CheckConstraint("end_time >= start_time AND duration_minutes >= 0", name="nonnegative_duration"),
        CheckConstraint("release_reason IN ('user','admin')", name="release_reason"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    purpose: Mapped[str | None] = mapped_column(Text)
    released_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    release_note: Mapped[str | None] = mapped_column(Text)
    # Immutable release identity, independent of a deleted current_usages row.
    usage_key: Mapped[str] = mapped_column(String(64), unique=True)
    sut_id: Mapped[int] = mapped_column(ForeignKey("suts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    start_time: Mapped[datetime] = mapped_column(UTCDateTime())
    end_time: Mapped[datetime] = mapped_column(UTCDateTime())
    duration_minutes: Mapped[int] = mapped_column(Integer)
    release_reason: Mapped[str] = mapped_column(String(10))
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("reservations.id"))


class AuditEvent(Created, Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    sut_id: Mapped[int | None] = mapped_column(ForeignKey("suts.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)


class Notification(Created, Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "event_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    sut_id: Mapped[int | None] = mapped_column(ForeignKey("suts.id"))
    event_key: Mapped[str] = mapped_column(String(150))
    message: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
