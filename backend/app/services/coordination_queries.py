"""Authenticated read projections: no deadlines, writes or GET side effects."""

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.database import utcnow
from app.models.domain import (
    Notification,
    Reservation,
    SUT,
    UsageHistory,
    User,
)
from app.services.common import get_or_404
from app.services.coordination import current_usage, queue_entries, protected
from app.services.inventory import contact, effective_status, ACTIVE_RESERVATIONS


def usage_view(db, usage, now=None):
    now = now or utcnow()
    sut = db.get(SUT, usage.sut_id)
    return {
        **{
            k: getattr(usage, k)
            for k in (
                "id",
                "usage_key",
                "sut_id",
                "start_time",
                "expected_end_time",
                "purpose",
                "reservation_id",
            )
        },
        "sut_name": sut.name,
        "lab_name": sut.lab.name,
        "user": contact(db.get(User, usage.user_id)),
        "overdue": usage.expected_end_time <= now,
    }


def queue_view(db, sut_id):
    sut = get_or_404(db, SUT, sut_id)
    return [
        {
            **{
                k: getattr(entry, k)
                for k in (
                    "id",
                    "entry_key",
                    "requested_duration_minutes",
                    "created_at",
                    "notified_at",
                    "offer_expires_at",
                    "paused_at",
                    "offer_status",
                )
            },
            "user": contact(db.get(User, entry.user_id)),
            "position": position,
            "eligible": db.get(User, entry.user_id).is_active
            and not sut.is_archived
            and sut.operational_state == "normal",
        }
        for position, entry in enumerate(queue_entries(db, sut_id), 1)
    ]


def reservation_view(db, booking, now=None):
    now = now or utcnow()
    sut = db.get(SUT, booking.sut_id)
    usage = current_usage(db, sut.id)
    booked_now = db.scalar(
        select(Reservation.id)
        .where(
            Reservation.sut_id == sut.id,
            Reservation.status.in_(ACTIVE_RESERVATIONS),
            Reservation.start_time <= now,
            Reservation.end_time > now,
        )
        .limit(1)
    )
    return {
        **{
            k: getattr(booking, k)
            for k in (
                "id",
                "sut_id",
                "start_time",
                "end_time",
                "purpose",
                "status",
                "checked_in_at",
                "claimed_at",
                "cancelled_at",
                "no_show_at",
            )
        },
        "sut_name": sut.name,
        "lab_name": sut.lab.name,
        "user": contact(db.get(User, booking.user_id)),
        "at_risk": bool(
            usage
            and booking.status in ACTIVE_RESERVATIONS
            and booking.end_time > now
            and usage.reservation_id != booking.id
            and (
                usage.expected_end_time > booking.start_time
                or usage.expected_end_time <= now
                and booking.start_time <= now
            )
        ),
        "operational_state": sut.operational_state,
        "operational_reason": sut.operational_reason,
        "effective_status": effective_status(sut, usage, booked_now is not None),
        "in_use": usage is not None,
    }


def reservation_page(db, *, sut_id=None, user_id=None, start=None, end=None, page=1, page_size=25, now=None):
    if start is not None and end is not None and end <= start:
        raise HTTPException(422, "End filter must be after start filter")
    conditions = []
    if sut_id is not None:
        conditions.append(Reservation.sut_id == sut_id)
    if user_id is not None:
        conditions.append(Reservation.user_id == user_id)
    if start is not None:
        conditions.append(Reservation.end_time > start)
    if end is not None:
        conditions.append(Reservation.start_time < end)
    total = db.scalar(select(func.count()).select_from(Reservation).where(*conditions))
    items = db.scalars(
        select(Reservation)
        .where(*conditions)
        .order_by(Reservation.start_time, Reservation.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {"items": [reservation_view(db, r, now) for r in items], "total": total}


def history_view(db, history):
    sut = db.get(SUT, history.sut_id)
    return {
        **{
            k: getattr(history, k)
            for k in (
                "id",
                "usage_key",
                "sut_id",
                "start_time",
                "end_time",
                "duration_minutes",
                "release_reason",
                "release_note",
                "released_by_user_id",
                "purpose",
                "reservation_id",
            )
        },
        "sut_name": sut.name,
        "lab_name": sut.lab.name,
        "user": contact(db.get(User, history.user_id)),
    }


def history_page(db, *, sut_id=None, user_id=None, start=None, end=None, page=1, page_size=25):
    if start is not None and end is not None and end <= start:
        raise HTTPException(422, "End filter must be after start filter")
    conditions = []
    if sut_id is not None:
        conditions.append(UsageHistory.sut_id == sut_id)
    if user_id is not None:
        conditions.append(UsageHistory.user_id == user_id)
    if start is not None:
        conditions.append(UsageHistory.end_time >= start)
    if end is not None:
        conditions.append(UsageHistory.start_time < end)
    total = db.scalar(select(func.count()).select_from(UsageHistory).where(*conditions))
    rows = db.scalars(
        select(UsageHistory)
        .where(*conditions)
        .order_by(UsageHistory.end_time.desc(), UsageHistory.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {"items": [history_view(db, r) for r in rows], "total": total}


def coordination_view(db, sut_id, now):
    sut = get_or_404(db, SUT, sut_id)
    usage = current_usage(db, sut_id)
    priority = protected(db, sut_id, now)
    booked = db.scalar(
        select(Reservation.id)
        .where(
            Reservation.sut_id == sut_id,
            Reservation.status.in_(ACTIVE_RESERVATIONS),
            Reservation.start_time <= now,
            Reservation.end_time > now,
        )
        .limit(1)
    )
    return {
        "status": effective_status(sut, usage, booked is not None),
        "priority_reservation_id": priority.id if priority else None,
        "usage": usage_view(db, usage, now) if usage else None,
        "queue": queue_view(db, sut_id),
        "reservations": reservation_page(db, sut_id=sut_id, start=now, page_size=100, now=now)["items"],
    }


def notification_list(db, actor, *, limit=50):
    return [
        {k: getattr(n, k) for k in ("id", "sut_id", "message", "created_at", "read_at")}
        for n in db.scalars(
            select(Notification)
            .where(Notification.user_id == actor.id)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
        )
    ]


def mark_read(db, actor, identity, now):
    row = get_or_404(db, Notification, identity)
    if row.user_id != actor.id:
        raise HTTPException(403, "Notification belongs to another user")
    if row.read_at is None:
        row.read_at = now
    return {k: getattr(row, k) for k in ("id", "sut_id", "message", "created_at", "read_at")}
