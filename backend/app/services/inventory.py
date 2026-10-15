import re
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.core.database import utcnow
from app.models.domain import CurrentUsage, Lab, Notification, QueueEntry, Reservation, SUT, User
from app.services.common import audit, get_or_404, require_role

ADMIN = ("lab_admin", "super_admin")
ACTIVE_RESERVATIONS = ("confirmed", "waiting_for_release", "claimed")
STATES = {"normal": None, "maintenance": "Maintenance", "out_of_service": "Out of Service"}
RANK = {s: n for n, s in enumerate(["Available", "Reserved", "In Use", "Maintenance", "Out of Service"])}


def lab_save(db, actor, data, identity=None):
    require_role(actor, *ADMIN)
    lab = get_or_404(db, Lab, identity) if identity else Lab()
    for key, value in data.model_dump().items():
        setattr(lab, key, value)
    db.add(lab)
    db.flush()
    audit(db, actor, "lab_updated" if identity else "lab_created", lab_id=lab.id)
    return lab_dict(lab)


def lab_delete(db, actor, identity):
    require_role(actor, *ADMIN)
    lab = get_or_404(db, Lab, identity)
    if db.scalar(select(SUT.id).where(SUT.lab_id == identity).limit(1)):
        raise HTTPException(409, "Lab contains SUTs (including archived); preserve their history")
    db.delete(lab)
    audit(db, actor, "lab_deleted", lab_id=identity, name=lab.name)


def lab_dict(lab):
    return {k: getattr(lab, k) for k in ("id", "name", "location", "description")}


def sut_save(db, actor, data, identity=None):
    require_role(actor, *ADMIN)
    if identity:
        sut = get_or_404(db, SUT, identity)
    else:
        get_or_404(db, Lab, data.lab_id)
        sut = SUT(lab_id=data.lab_id)
    values = data.model_dump(exclude={"lab_id"})
    for key, value in values.items():
        setattr(sut, key, str(value) if key in ("bmc_ip", "host_ip") and value is not None else value)
    sut.normalized_name = data.name.casefold()
    db.add(sut)
    db.flush()
    audit(db, actor, "sut_updated" if identity else "sut_created", sut_id=sut.id)
    return sut.id


def activity(db, sut_id, now=None):
    now = now or utcnow()
    return {
        "usages": db.scalar(
            select(func.count()).select_from(CurrentUsage).where(CurrentUsage.sut_id == sut_id)
        ),
        "queues": db.scalar(select(func.count()).select_from(QueueEntry).where(QueueEntry.sut_id == sut_id)),
        "reservations": db.scalar(
            select(func.count())
            .select_from(Reservation)
            .where(
                Reservation.sut_id == sut_id,
                Reservation.status.in_(ACTIVE_RESERVATIONS),
                Reservation.end_time > now,
            )
        ),
    }


def archive(db, actor, identity, *, restore=False):
    require_role(actor, *ADMIN)
    sut = get_or_404(db, SUT, identity)
    if restore:
        if not sut.is_archived:
            raise HTTPException(409, "SUT is already active")
        sut.is_archived = False
        sut.archived_at = sut.archived_by_user_id = None
    else:
        if sut.is_archived:
            raise HTTPException(409, "SUT is already archived")
        if any(activity(db, identity).values()):
            raise HTTPException(
                409, "Resolve active usage, queue and current/future reservations before archiving"
            )
        sut.is_archived = True
        sut.archived_at = utcnow()
        sut.archived_by_user_id = actor.id
    audit(db, actor, "sut_restored" if restore else "sut_archived", sut_id=identity)


def operational(db, actor, identity, data):
    require_role(actor, *ADMIN)
    sut = get_or_404(db, SUT, identity)
    if sut.is_archived:
        raise HTTPException(409, "Restore the SUT before changing its operational state")
    if data.state != "normal" and not data.reason:
        raise HTTPException(422, "A reason is required for an unavailable SUT")
    if data.state != "normal" and any(activity(db, identity).values()) and not data.acknowledge_activity:
        raise HTTPException(409, "Review outstanding activity and acknowledge before changing state")
    before = {"state": sut.operational_state, "reason": sut.operational_reason}
    sut.operational_state = data.state
    sut.operational_reason = data.reason if data.state != "normal" else None
    sut.operational_updated_at = utcnow()
    sut.operational_updated_by_user_id = actor.id
    audit(
        db,
        actor,
        "operational_state_changed",
        sut_id=identity,
        before=before,
        state=data.state,
        reason=sut.operational_reason,
    )
    db.flush()
    # Persist safe in-app notices; coordination worker integration is Day 2.
    users = set(db.scalars(select(CurrentUsage.user_id).where(CurrentUsage.sut_id == identity)))
    users.update(db.scalars(select(QueueEntry.user_id).where(QueueEntry.sut_id == identity)))
    users.update(
        db.scalars(
            select(Reservation.user_id).where(
                Reservation.sut_id == identity,
                Reservation.status.in_(ACTIVE_RESERVATIONS),
                Reservation.end_time > utcnow(),
            )
        )
    )
    event = f"operational:{identity}:{sut.operational_updated_at.isoformat()}"
    for user_id in users:
        db.add(
            Notification(
                user_id=user_id,
                sut_id=identity,
                event_key=event,
                message=f"{sut.name}: operational state changed to {data.state}. Existing activity is retained.",
            )
        )


def natural(value):
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part.casefold()) for part in re.split(r"(\d+)", value)
    )


def contact(user):
    return {"id": user.id, "display_name": user.display_name, "team": user.team, "email": user.email}


def snapshot(
    db,
    actor,
    *,
    include_archived=False,
    search="",
    lab_id=None,
    platform="",
    owner_team="",
    status="",
    sort="name",
    now=None,
):
    if include_archived:
        require_role(actor, *ADMIN)
    if sort not in ("name", "status"):
        raise HTTPException(422, "Sort must be name or status")
    if status and status not in RANK:
        raise HTTPException(422, "Invalid status filter")
    now = now or utcnow()
    suts = list(
        db.scalars(
            select(SUT)
            .options(joinedload(SUT.lab))
            .where(*([] if include_archived else [SUT.is_archived.is_(False)]))
        )
    )
    usages = {u.sut_id: u for u in db.scalars(select(CurrentUsage))}
    users = {u.id: u for u in db.scalars(select(User))}
    reservations = list(
        db.scalars(
            select(Reservation)
            .where(Reservation.status.in_(ACTIVE_RESERVATIONS), Reservation.end_time > now)
            .order_by(Reservation.start_time, Reservation.id)
        )
    )
    bookings = {}
    for reservation in reservations:
        bookings.setdefault(reservation.sut_id, []).append(reservation)
    result = []
    for sut in suts:
        usage = usages.get(sut.id)
        scheduled = bookings.get(sut.id, [])
        effective = STATES[sut.operational_state] or (
            "In Use"
            if usage
            else "Reserved"
            if any(r.start_time <= now < r.end_time for r in scheduled)
            else "Available"
        )
        if (
            search.casefold() not in sut.name.casefold()
            or lab_id
            and sut.lab_id != lab_id
            or platform
            and sut.platform != platform
            or owner_team
            and sut.owner_team != owner_team
            or status
            and effective != status
        ):
            continue

        def booking(r):
            return {
                "id": r.id,
                "user": contact(users[r.user_id]),
                "start_time": r.start_time,
                "end_time": r.end_time,
                "purpose": r.purpose,
            }

        upcoming = next((r for r in scheduled if r.start_time > now), None)
        result.append(
            {
                **{
                    k: getattr(sut, k)
                    for k in (
                        "id",
                        "lab_id",
                        "name",
                        "platform",
                        "owner_team",
                        "description",
                        "bmc_ip",
                        "host_ip",
                        "is_archived",
                        "operational_state",
                        "operational_reason",
                    )
                },
                "lab_name": sut.lab.name,
                "status": effective,
                "holder": contact(users[usage.user_id]) if usage else None,
                "expected_end_time": usage.expected_end_time if usage else None,
                "usage_purpose": usage.purpose if usage else None,
                "in_use": usage is not None,
                "overdue": bool(usage and usage.expected_end_time <= now),
                "next_reservation": booking(upcoming) if upcoming else None,
                "reservations_24h": [
                    booking(r) for r in scheduled if r.start_time < now + timedelta(hours=24)
                ],
            }
        )
    result.sort(
        key=lambda s: (
            natural(s["lab_name"]),
            s["lab_id"],
            RANK[s["status"]] if sort == "status" else 0,
            natural(s["name"]),
            s["id"],
        )
    )
    return {
        "items": result,
        "total": len(result),
        "as_of": now,
        "metrics": {
            "labs": db.scalar(select(func.count()).select_from(Lab)),
            "suts": len(result),
            **{k: sum(s["status"] == k for s in result) for k in RANK},
        },
    }


def detail(db, actor, identity):
    sut = get_or_404(db, SUT, identity)
    if sut.is_archived and actor.role not in ADMIN:
        raise HTTPException(404, "SUT not found")
    return next(
        s for s in snapshot(db, actor, include_archived=sut.is_archived)["items"] if s["id"] == identity
    )
