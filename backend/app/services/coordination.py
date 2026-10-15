"""Coordination transitions. Call only inside a BEGIN IMMEDIATE write unit of work.

The clock is sampled by each caller AFTER acquiring the write reservation. GETs use
projections in coordination_queries and never reconcile or expire records.
"""

from datetime import UTC, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select

from app.core.database import utcnow
from app.models.domain import (
    AuditEvent,
    CurrentUsage,
    Notification,
    QueueEntry,
    Reservation,
    SUT,
    UsageHistory,
    User,
)
from app.services.common import get_or_404, require_role
from app.services.inventory import ACTIVE_RESERVATIONS, ADMIN

GRACE = timedelta(minutes=15)


def event(db, actor, kind, now, sut_id, **details):
    db.add(
        AuditEvent(
            actor_user_id=actor.id if actor else None,
            sut_id=sut_id,
            event_type=kind,
            details_json=details,
            created_at=now,
        )
    )


def notice(db, user_id, sut_id, key, message, now):
    if not db.scalar(
        select(Notification.id).where(Notification.user_id == user_id, Notification.event_key == key)
    ):
        db.add(Notification(user_id=user_id, sut_id=sut_id, event_key=key, message=message, created_at=now))
        db.flush()


def active_actor(actor):
    if not actor.is_active:
        raise HTTPException(401, "Account is inactive")
    if actor.must_change_password:
        raise HTTPException(403, "password_change_required")


def registerable(sut):
    if sut.is_archived:
        raise HTTPException(409, "SUT is archived; an administrator must restore it")
    if sut.operational_state != "normal":
        raise HTTPException(409, "SUT is unavailable: " + (sut.operational_reason or sut.operational_state))


def expected_end(now, minutes):
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or minutes <= 0:
        raise HTTPException(422, "Duration must be a positive finite number of minutes")
    try:
        end = now + timedelta(minutes=minutes)
    except (OverflowError, ValueError):
        raise HTTPException(422, "Duration cannot be represented as a timestamp") from None
    if end <= now:
        raise HTTPException(422, "Duration is below timestamp precision")
    return end


def current_usage(db, sut_id):
    return db.scalar(select(CurrentUsage).where(CurrentUsage.sut_id == sut_id))


def reservations(db, sut_id):
    return list(
        db.scalars(
            select(Reservation)
            .where(Reservation.sut_id == sut_id, Reservation.status.in_(ACTIVE_RESERVATIONS))
            .order_by(Reservation.start_time, Reservation.id)
        )
    )


def protected(db, sut_id, now):
    # Disabled accounts retain their records for admin review, but cannot deadlock allocation.
    return next(
        (
            r
            for r in reservations(db, sut_id)
            if r.start_time <= now < r.end_time
            and db.get(User, r.user_id).is_active
            and (r.checked_in_at is not None or r.status == "claimed" or now < r.start_time + GRACE)
        ),
        None,
    )


def queue_entries(db, sut_id):
    return list(
        db.scalars(
            select(QueueEntry)
            .where(QueueEntry.sut_id == sut_id)
            .order_by(QueueEntry.created_at, QueueEntry.id)
        )
    )


def pause_offer(db, entry, now, reason):
    if entry.offer_status == "notified" and entry.paused_at is None:
        entry.remaining_microseconds = max(0, int((entry.offer_expires_at - now) / timedelta(microseconds=1)))
        entry.paused_at = now
        event(db, None, "queue_offer_paused", now, entry.sut_id, entry_key=entry.entry_key, reason=reason)


def expire_offer(db, entry, now):
    event(
        db,
        None,
        "offer_timeout",
        now,
        entry.sut_id,
        entry_key=entry.entry_key,
        entry_id=entry.id,
        user_id=entry.user_id,
        notified_at=entry.notified_at.isoformat(),
        offer_expires_at=entry.offer_expires_at.isoformat(),
    )
    notice(
        db,
        entry.user_id,
        entry.sut_id,
        f"offer-timeout:{entry.entry_key}:{entry.offer_generation}",
        "Your queue offer expired without a Claim. You may join the back of the queue again.",
        now,
    )
    db.delete(entry)


def reconcile_sut(db, sut, now):
    """Idempotent deadline/eligibility reconciliation, including restart catch-up."""
    for booking in reservations(db, sut.id):
        deadline = booking.start_time + GRACE
        if (
            booking.status == "confirmed"
            and booking.checked_in_at is None
            and deadline <= now
            and deadline <= booking.end_time
        ):
            booking.status = "no_show"
            booking.no_show_at = now
            event(
                db,
                None,
                "reservation_no_show",
                now,
                sut.id,
                reservation_id=booking.id,
                deadline=deadline.isoformat(),
            )
            notice(
                db,
                booking.user_id,
                sut.id,
                f"no-show:{booking.id}",
                "Your reservation became no-show after the 15-minute check-in deadline.",
                now,
            )
        elif booking.end_time <= now:
            booking.status = "completed"
            event(db, None, "reservation_completed", now, sut.id, reservation_id=booking.id)
    db.flush()
    usage = current_usage(db, sut.id)
    priority = protected(db, sut.id, now)
    if usage and usage.expected_end_time <= now:
        notice(
            db,
            usage.user_id,
            sut.id,
            f"overdue:{usage.usage_key}:{usage.expected_end_time.isoformat()}",
            f"{sut.name}: your usage estimate is overdue. Record Release when finished; no automatic release occurs.",
            now,
        )
    if usage and priority and priority.user_id != usage.user_id:
        notice(
            db,
            usage.user_id,
            sut.id,
            f"booking-start:{priority.id}:{usage.usage_key}",
            f"{sut.name}: a reservation has started while you remain recorded as using it. Coordinate a manual Release.",
            now,
        )
    if priority and not usage:
        notice(
            db,
            priority.user_id,
            sut.id,
            f"booking-ready:{priority.id}",
            f"{sut.name}: your reservation has priority. Manually Claim to start usage.",
            now,
        )
    entries = queue_entries(db, sut.id)
    for entry in entries:
        if not db.get(User, entry.user_id).is_active:
            pause_offer(db, entry, now, "inactive_account")
        elif entry.offer_status == "notified" and (
            entry.paused_at is None
            and entry.offer_expires_at <= now
            or entry.paused_at is not None
            and entry.remaining_microseconds == 0
        ):
            expire_offer(db, entry, now)
    db.flush()
    entries = queue_entries(db, sut.id)
    blocked = (
        sut.is_archived or sut.operational_state != "normal" or usage is not None or priority is not None
    )
    if blocked:
        for entry in entries:
            pause_offer(db, entry, now, "sut_unavailable_or_usage_or_reservation")
        db.flush()
        return
    eligible = [e for e in entries if db.get(User, e.user_id).is_active]
    # Honor an already-issued live offer if an earlier disabled member is reactivated.
    live = [e for e in eligible if e.offer_status == "notified" and e.paused_at is None]
    head = live[0] if live else next(iter(eligible), None)
    for entry in entries:
        if entry is not head:
            pause_offer(db, entry, now, "another_live_offer")
    if head is None:
        return
    if head.offer_status == "waiting":
        head.offer_status = "notified"
        head.offer_generation += 1
        head.notified_at = now
        head.offer_expires_at = now + GRACE
        event(
            db,
            None,
            "queue_offer_notified",
            now,
            sut.id,
            entry_key=head.entry_key,
            user_id=head.user_id,
            offer_expires_at=head.offer_expires_at.isoformat(),
        )
        upcoming = next(
            (r for r in reservations(db, sut.id) if r.start_time > now and db.get(User, r.user_id).is_active),
            None,
        )
        warning = (
            ""
            if upcoming is None
            else " Upcoming reservation: "
            + upcoming.start_time.astimezone(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M Asia/Taipei")
            + "; plan a manual handoff before it starts."
        )
        notice(
            db,
            head.user_id,
            sut.id,
            f"offer:{head.entry_key}:{head.offer_generation}",
            f"{sut.name}: it is your turn. Manually Claim within 15 minutes; notification is not usage."
            + warning,
            now,
        )
    elif head.paused_at is not None:
        paused = head.paused_at.isoformat()
        head.offer_expires_at = now + timedelta(microseconds=head.remaining_microseconds)
        head.paused_at = None
        head.remaining_microseconds = None
        event(
            db,
            None,
            "queue_offer_resumed",
            now,
            sut.id,
            entry_key=head.entry_key,
            offer_expires_at=head.offer_expires_at.isoformat(),
        )
        notice(
            db,
            head.user_id,
            sut.id,
            f"offer-resume:{head.entry_key}:{head.offer_generation}:{paused}",
            f"{sut.name}: your queue offer resumed with its remaining response time. Manually Claim before the displayed deadline.",
            now,
        )
    db.flush()


def reconcile_all(db, now):
    for sut in db.scalars(select(SUT).order_by(SUT.id)):
        reconcile_sut(db, sut, now)


def overlapping(db, sut_id, start, end, *, exclude_user=None, exclude_id=None):
    query = select(Reservation).where(
        Reservation.sut_id == sut_id,
        Reservation.status.in_(ACTIVE_RESERVATIONS),
        Reservation.start_time < end,
        Reservation.end_time > start,
    )
    if exclude_user is not None:
        query = query.where(Reservation.user_id != exclude_user)
    if exclude_id is not None:
        query = query.where(Reservation.id != exclude_id)
    return list(db.scalars(query.order_by(Reservation.start_time, Reservation.id)))


def warning_payload(db, conflicts):
    from app.services.inventory import contact

    return [
        {
            "reservation_id": r.id,
            "user": contact(db.get(User, r.user_id)),
            "start_time": r.start_time.isoformat(),
            "end_time": r.end_time.isoformat(),
        }
        for r in conflicts
    ]


def require_ack(db, conflicts, acknowledged):
    if conflicts and not acknowledged:
        raise HTTPException(
            409,
            {
                "code": "reservation_conflict_confirmation_required",
                "message": "Review the booking and explicitly acknowledge the overlap; your estimate will not be shortened.",
                "conflicts": warning_payload(db, conflicts),
                "suggested_expected_end_time": conflicts[0].start_time.isoformat(),
            },
        )


def claim(db, actor, sut_id, data, *, now=None):
    active_actor(actor)
    now = now or utcnow()
    sut = get_or_404(db, SUT, sut_id)
    registerable(sut)
    end = expected_end(now, data.duration_minutes)
    reconcile_sut(db, sut, now)
    if current_usage(db, sut.id):
        raise HTTPException(409, "SUT already has a recorded current holder")
    priority = protected(db, sut.id, now)
    if priority and priority.user_id != actor.id:
        raise HTTPException(
            409, "Another reservation holder has priority until release of reservation protection"
        )
    if data.reservation_id is not None and (priority is None or priority.id != data.reservation_id):
        raise HTTPException(409, "Reservation is not currently eligible for Claim")
    if priority:
        if end > priority.end_time:
            raise HTTPException(
                422, "Reservation-specific Claim estimate must end by " + priority.end_time.isoformat()
            )
    else:
        entries = queue_entries(db, sut.id)
        eligible = [e for e in entries if db.get(User, e.user_id).is_active]
        offered = next(
            (
                e
                for e in eligible
                if e.offer_status == "notified" and e.paused_at is None and e.offer_expires_at > now
            ),
            None,
        )
        if eligible and (offered is None or offered.user_id != actor.id):
            raise HTTPException(409, "Only the notified eligible FIFO head may Claim")
    conflicts = overlapping(db, sut.id, now, end, exclude_user=actor.id)
    require_ack(db, conflicts, data.acknowledge_reservation_conflict)
    usage = CurrentUsage(
        sut_id=sut.id,
        user_id=actor.id,
        start_time=now,
        expected_end_time=end,
        purpose=data.purpose or None,
        reservation_id=priority.id if priority else None,
        created_at=now,
    )
    db.add(usage)
    if priority:
        priority.status = "claimed"
        priority.claimed_at = now
        priority.checked_in_at = priority.checked_in_at or now
    own_entry = db.scalar(
        select(QueueEntry).where(QueueEntry.sut_id == sut.id, QueueEntry.user_id == actor.id)
    )
    if own_entry:
        event(db, actor, "queue_claimed", now, sut.id, entry_key=own_entry.entry_key)
        db.delete(own_entry)
    db.flush()
    event(
        db,
        actor,
        "usage_claimed",
        now,
        sut.id,
        usage_key=usage.usage_key,
        reservation_id=usage.reservation_id,
        expected_end_time=end.isoformat(),
        acknowledged_conflicts=warning_payload(db, conflicts),
    )
    reconcile_sut(db, sut, now)
    return usage


def release(db, actor, sut_id, data, *, force=False, now=None):
    active_actor(actor)
    now = now or utcnow()
    sut = get_or_404(db, SUT, sut_id)
    if force:
        require_role(actor, *ADMIN)
        if not data.reason:
            raise HTTPException(422, "Force-release requires a reason")
    usage = current_usage(db, sut.id)
    if not usage or usage.usage_key != data.usage_key:
        raise HTTPException(409, "Usage already released or changed; reload before retrying")
    if not force and usage.user_id != actor.id:
        raise HTTPException(403, "Only the holder may Release; administrators must use audited force-release")
    if now < usage.start_time:
        raise HTTPException(409, "Server time precedes usage start")
    history = UsageHistory(
        usage_key=usage.usage_key,
        sut_id=sut.id,
        user_id=usage.user_id,
        start_time=usage.start_time,
        end_time=now,
        duration_minutes=int((now - usage.start_time).total_seconds() // 60),
        release_reason="admin" if force else "user",
        released_by_user_id=actor.id,
        release_note=data.reason or None,
        purpose=usage.purpose,
        reservation_id=usage.reservation_id,
        created_at=now,
    )
    db.add(history)
    if usage.reservation_id:
        booking = db.get(Reservation, usage.reservation_id)
        booking.status = "completed"
    event(
        db,
        actor,
        "usage_force_released" if force else "usage_released",
        now,
        sut.id,
        usage_key=usage.usage_key,
        user_id=usage.user_id,
        reason=data.reason,
    )
    notice(
        db,
        usage.user_id,
        sut.id,
        f"release:{usage.usage_key}",
        f"{sut.name}: usage was recorded as released.",
        now,
    )
    db.delete(usage)
    db.flush()
    reconcile_sut(db, sut, now)
    return history


def extend(db, actor, sut_id, data, *, now=None):
    active_actor(actor)
    now = now or utcnow()
    get_or_404(db, SUT, sut_id)
    usage = current_usage(db, sut_id)
    if usage is None or usage.usage_key != data.usage_key:
        raise HTTPException(409, "Usage already released or changed; reload before retrying")
    if usage.user_id != actor.id and actor.role not in ADMIN:
        raise HTTPException(403, "Only the holder or an administrator may change the estimate")
    end = data.expected_end_time.astimezone(UTC)
    if end <= now or end <= usage.start_time:
        raise HTTPException(422, "Expected end must be after now and the original start")
    conflicts = overlapping(db, sut_id, now, end, exclude_user=usage.user_id)
    require_ack(db, conflicts, data.acknowledge_reservation_conflict)
    old = usage.expected_end_time
    usage.expected_end_time = end
    event(
        db,
        actor,
        "usage_estimate_changed",
        now,
        sut_id,
        usage_key=usage.usage_key,
        before=old.isoformat(),
        after=end.isoformat(),
        acknowledged_conflicts=warning_payload(db, conflicts),
    )
    db.flush()
    return usage


def join_queue(db, actor, sut_id, data, *, now=None):
    active_actor(actor)
    now = now or utcnow()
    sut = get_or_404(db, SUT, sut_id)
    registerable(sut)
    expected_end(now, data.requested_duration_minutes)
    reconcile_sut(db, sut, now)
    usage = current_usage(db, sut.id)
    if usage and usage.user_id == actor.id:
        raise HTTPException(409, "Current holder cannot join their own SUT queue")
    entries = queue_entries(db, sut.id)
    if any(e.user_id == actor.id for e in entries):
        raise HTTPException(409, "Already queued for this SUT")
    if usage is None and protected(db, sut.id, now) is None and not entries:
        raise HTTPException(409, "SUT is Available with no queue; Claim directly")
    entry = QueueEntry(
        sut_id=sut.id,
        user_id=actor.id,
        requested_duration_minutes=data.requested_duration_minutes,
        created_at=now,
    )
    db.add(entry)
    db.flush()
    event(db, actor, "queue_joined", now, sut.id, entry_key=entry.entry_key)
    reconcile_sut(db, sut, now)
    return entry


def leave_queue(db, actor, sut_id, *, clear=False, reason="", entry_key=None, now=None):
    active_actor(actor)
    now = now or utcnow()
    sut = get_or_404(db, SUT, sut_id)
    if clear:
        require_role(actor, *ADMIN)
        if not reason:
            raise HTTPException(422, "Queue clearing requires a reason")
    entries = queue_entries(db, sut.id)
    if clear:
        event(db, actor, "queue_clear_requested", now, sut.id, reason=reason, entry_count=len(entries))
    targets = entries if clear else [e for e in entries if e.user_id == actor.id]
    if not clear and not targets:
        raise HTTPException(404, "You have no queue entry for this SUT")
    if not clear and targets[0].entry_key != entry_key:
        raise HTTPException(409, "Queue entry changed; reload before leaving")
    for entry in targets:
        event(
            db,
            actor,
            "queue_cleared" if clear else "queue_left",
            now,
            sut.id,
            entry_key=entry.entry_key,
            user_id=entry.user_id,
            reason=reason,
        )
        notice(
            db,
            entry.user_id,
            sut.id,
            f"queue-remove:{entry.entry_key}",
            f"{sut.name}: your queue entry was removed by an explicit action.",
            now,
        )
        db.delete(entry)
    db.flush()
    reconcile_sut(db, sut, now)


def validate_booking(db, sut_id, data, now, *, exclude_id=None):
    start, end = data.start_time.astimezone(UTC), data.end_time.astimezone(UTC)
    if not timedelta(0) < end - start <= timedelta(hours=24):
        raise HTTPException(422, "Reservation must be longer than zero and at most 24 elapsed hours")
    if not now < start <= now + timedelta(days=30):
        raise HTTPException(422, "Reservation start must be future and within 30 × 24 hours")
    if overlapping(db, sut_id, start, end, exclude_id=exclude_id):
        raise HTTPException(
            409, "Reservation overlaps an active booking; adjacent half-open intervals are allowed"
        )
    return start, end


def save_reservation(db, actor, data, *, identity=None, now=None):
    active_actor(actor)
    now = now or utcnow()
    booking = get_or_404(db, Reservation, identity) if identity else None
    if booking and booking.user_id != actor.id and actor.role not in ADMIN:
        raise HTTPException(403, "Only the reservation owner or an administrator may edit")
    sut = get_or_404(db, SUT, booking.sut_id if booking else data.sut_id)
    if booking is None or sut.is_archived:
        registerable(sut)
    reconcile_sut(db, sut, now)
    if booking and (
        booking.status != "confirmed" or booking.checked_in_at is not None or booking.start_time <= now
    ):
        raise HTTPException(409, "Only future confirmed reservations can be edited")
    start, end = validate_booking(db, sut.id, data, now, exclude_id=identity)
    before = (
        None
        if not booking
        else {
            "start_time": booking.start_time.isoformat(),
            "end_time": booking.end_time.isoformat(),
            "purpose": booking.purpose,
        }
    )
    if booking is None:
        booking = Reservation(sut_id=sut.id, user_id=actor.id, created_at=now)
        db.add(booking)
    booking.start_time, booking.end_time, booking.purpose = start, end, data.purpose
    db.flush()
    event(
        db,
        actor,
        "reservation_edited" if identity else "reservation_created",
        now,
        sut.id,
        reservation_id=booking.id,
        before=before,
        after={"start_time": start.isoformat(), "end_time": end.isoformat(), "purpose": booking.purpose},
    )
    reconcile_sut(db, sut, now)
    return booking


def cancel_reservation(db, actor, identity, *, now=None):
    active_actor(actor)
    now = now or utcnow()
    booking = get_or_404(db, Reservation, identity)
    if booking.user_id != actor.id and actor.role not in ADMIN:
        raise HTTPException(403, "Only the owner or an administrator may cancel")
    if booking.status != "confirmed" or booking.checked_in_at is not None or booking.start_time <= now:
        raise HTTPException(409, "Only future confirmed reservations can be cancelled")
    booking.status = "cancelled"
    booking.cancelled_at = now
    event(db, actor, "reservation_cancelled", now, booking.sut_id, reservation_id=identity)
    db.flush()
    reconcile_sut(db, get_or_404(db, SUT, booking.sut_id), now)
    return booking


def check_in(db, actor, identity, *, now=None):
    active_actor(actor)
    now = now or utcnow()
    booking = get_or_404(db, Reservation, identity)
    if booking.user_id != actor.id:
        raise HTTPException(403, "Only the reservation owner may check in")
    sut = get_or_404(db, SUT, booking.sut_id)
    if (
        booking.checked_in_at is not None
        and booking.status == "waiting_for_release"
        and now < booking.end_time
    ):
        return booking
    if booking.status != "confirmed" or not booking.start_time <= now < min(
        booking.start_time + GRACE, booking.end_time
    ):
        raise HTTPException(409, "Check-in requires an active reservation before its 15-minute deadline")
    booking.status = "waiting_for_release"
    booking.checked_in_at = now
    event(db, actor, "reservation_checked_in", now, sut.id, reservation_id=identity)
    usage = current_usage(db, sut.id)
    if usage and usage.user_id != actor.id:
        recipients = {
            usage.user_id,
            *db.scalars(select(User.id).where(User.role.in_(ADMIN), User.is_active.is_(True))),
        }
        for user_id in recipients:
            notice(
                db,
                user_id,
                sut.id,
                f"check-in:{identity}",
                f"{sut.name}: reservation holder checked in and awaits a manual recorded Release.",
                now,
            )
    db.flush()
    reconcile_sut(db, sut, now)
    return booking
