from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.core.csrf import check_csrf
from app.core.dependencies import current_user, database
from app.models.domain import CurrentUsage, Reservation, SUT, User
from app.routers.web.routes import redirect, render
from app.schemas.coordination import (
    ClaimInput,
    ExpectedEndInput,
    QueueInput,
    QueueLeaveInput,
    ReasonInput,
    ReleaseInput,
    ReservationInput,
    ReservationUpdate,
)
from app.services import coordination as c, coordination_queries as q
from app.services.common import get_or_404

router = APIRouter(dependencies=[Depends(check_csrf)], include_in_schema=False)
DB = Annotated[object, Depends(database, scope="function")]
Actor = Annotated[User, Depends(current_user)]
TAIPEI = ZoneInfo("Asia/Taipei")


def optional_id(value):
    if value in ("", None):
        return None
    try:
        result = int(value)
        if result <= 0:
            raise ValueError
        return result
    except (TypeError, ValueError):
        raise HTTPException(422, "Filter IDs must be positive integers") from None


def local_time(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=TAIPEI)
        return parsed.astimezone(UTC)
    except (ValueError, OverflowError):
        raise HTTPException(422, "Invalid time; enter a valid Asia/Taipei date and time") from None


async def form_payload(request, schema):
    values = dict(await request.form())
    values.pop("csrf_token", None)
    for field in ("start_time", "end_time", "expected_end_time"):
        if field in values:
            values[field] = local_time(values[field])
    try:
        return schema.model_validate(values)
    except ValidationError as exc:
        raise HTTPException(
            422,
            "Invalid input: "
            + "; ".join(".".join(str(x) for x in e["loc"]) + ": " + e["msg"] for e in exc.errors()),
        ) from None


async def perform(request, actor, operation, db, identity, data, *, path):
    try:
        await run_in_threadpool(operation, db, actor, identity, data, now=request.app.state.clock())
    except HTTPException as exc:
        if (
            exc.status_code != 409
            or not isinstance(exc.detail, dict)
            or exc.detail.get("code") != "reservation_conflict_confirmation_required"
        ):
            raise
        # A confirmation page must not commit any preliminary reconciliation from
        # the rejected action; the independent deadline worker will catch up.
        db.rollback()
        detail = dict(exc.detail)
        detail["suggested_expected_end_time"] = datetime.fromisoformat(detail["suggested_expected_end_time"])
        detail["conflicts"] = [
            {
                **r,
                "start_time": datetime.fromisoformat(r["start_time"]),
                "end_time": datetime.fromisoformat(r["end_time"]),
            }
            for r in detail["conflicts"]
        ]
        response = render(
            request,
            "confirm_conflict.html",
            actor,
            conflict=detail,
            fields=data.model_dump(
                mode="json", exclude={"acknowledge_reservation_conflict"}, exclude_none=True
            ),
            path=path,
        )
        response.status_code = 409
        return response
    return redirect(f"/suts/{identity}")


@router.post("/suts/{identity}/claim")
async def claim(identity: int, request: Request, db: DB, actor: Actor):
    return await perform(
        request,
        actor,
        c.claim,
        db,
        identity,
        await form_payload(request, ClaimInput),
        path=f"/suts/{identity}/claim",
    )


@router.post("/suts/{identity}/release")
async def release(identity: int, request: Request, db: DB, actor: Actor):
    await run_in_threadpool(
        c.release,
        db,
        actor,
        identity,
        await form_payload(request, ReleaseInput),
        now=request.app.state.clock(),
    )
    return redirect(f"/suts/{identity}")


@router.post("/suts/{identity}/force-release")
async def force_release(identity: int, request: Request, db: DB, actor: Actor):
    await run_in_threadpool(
        c.release,
        db,
        actor,
        identity,
        await form_payload(request, ReleaseInput),
        force=True,
        now=request.app.state.clock(),
    )
    return redirect(f"/suts/{identity}")


@router.post("/suts/{identity}/expected-end")
async def expected_end(identity: int, request: Request, db: DB, actor: Actor):
    return await perform(
        request,
        actor,
        c.extend,
        db,
        identity,
        await form_payload(request, ExpectedEndInput),
        path=f"/suts/{identity}/expected-end",
    )


@router.post("/suts/{identity}/queue")
async def join_queue(identity: int, request: Request, db: DB, actor: Actor):
    await run_in_threadpool(
        c.join_queue,
        db,
        actor,
        identity,
        await form_payload(request, QueueInput),
        now=request.app.state.clock(),
    )
    return redirect(f"/suts/{identity}")


@router.post("/suts/{identity}/queue/leave")
async def leave_queue(identity: int, request: Request, db: DB, actor: Actor):
    data = await form_payload(request, QueueLeaveInput)
    await run_in_threadpool(
        c.leave_queue, db, actor, identity, entry_key=data.entry_key, now=request.app.state.clock()
    )
    return redirect(f"/suts/{identity}")


@router.post("/suts/{identity}/queue/clear")
async def clear_queue(identity: int, request: Request, db: DB, actor: Actor):
    data = await form_payload(request, ReasonInput)
    await run_in_threadpool(
        c.leave_queue, db, actor, identity, clear=True, reason=data.reason, now=request.app.state.clock()
    )
    return redirect(f"/suts/{identity}")


@router.get("/suts/{identity}/activity")
def activity(identity: int, request: Request, db: DB, actor: Actor):
    return render(
        request,
        "sut_activity.html",
        actor,
        coordination=q.coordination_view(db, identity, request.app.state.clock()),
        sut=get_or_404(db, SUT, identity),
    )


@router.get("/my-usage")
def my_usage(request: Request, db: DB, actor: Actor):
    rows = db.scalars(select(CurrentUsage).where(CurrentUsage.user_id == actor.id).order_by(CurrentUsage.id))
    return render(
        request, "my_usage.html", actor, usages=[q.usage_view(db, u, request.app.state.clock()) for u in rows]
    )


@router.get("/reservations")
def reservations(
    request: Request,
    db: DB,
    actor: Actor,
    sut_id: str = "",
    user_id: str = "",
    page: int = Query(1, ge=1),
):
    data = q.reservation_page(
        db, sut_id=optional_id(sut_id), user_id=optional_id(user_id), page=page, now=request.app.state.clock()
    )
    return render(
        request,
        "reservations.html",
        actor,
        data=data,
        page=page,
        filters={"sut_id": sut_id, "user_id": user_id},
        title="Reservations",
    )


@router.get("/reservations/new")
def new_reservation(request: Request, db: DB, actor: Actor, sut_id: int | None = None):
    return render(
        request,
        "reservation_form.html",
        actor,
        booking=None,
        selected_sut=sut_id,
        suts=list(db.scalars(select(SUT).where(SUT.is_archived.is_(False)).order_by(SUT.lab_id, SUT.name))),
    )


@router.post("/reservations")
async def create_reservation(request: Request, db: DB, actor: Actor):
    booking = await run_in_threadpool(
        c.save_reservation,
        db,
        actor,
        await form_payload(request, ReservationInput),
        now=request.app.state.clock(),
    )
    return redirect(f"/reservations/{booking.id}")


@router.get("/reservations/{identity}")
def reservation(identity: int, request: Request, db: DB, actor: Actor):
    return render(
        request,
        "reservation_detail.html",
        actor,
        booking=q.reservation_view(db, get_or_404(db, Reservation, identity), request.app.state.clock()),
        now=request.app.state.clock(),
    )


@router.get("/reservations/{identity}/edit")
def reservation_form(identity: int, request: Request, db: DB, actor: Actor):
    booking = get_or_404(db, Reservation, identity)
    if booking.user_id != actor.id and actor.role not in c.ADMIN:
        raise HTTPException(403, "Only the owner or an administrator may edit")
    if booking.status != "confirmed" or booking.start_time <= request.app.state.clock():
        raise HTTPException(409, "Only future confirmed reservations may be edited")
    return render(
        request,
        "reservation_form.html",
        actor,
        booking=q.reservation_view(db, booking, request.app.state.clock()),
        suts=[],
    )


@router.post("/reservations/{identity}/edit")
async def edit_reservation(identity: int, request: Request, db: DB, actor: Actor):
    await run_in_threadpool(
        c.save_reservation,
        db,
        actor,
        await form_payload(request, ReservationUpdate),
        identity=identity,
        now=request.app.state.clock(),
    )
    return redirect(f"/reservations/{identity}")


@router.post("/reservations/{identity}/cancel")
def cancel_reservation(identity: int, request: Request, db: DB, actor: Actor):
    c.cancel_reservation(db, actor, identity, now=request.app.state.clock())
    return redirect(f"/reservations/{identity}")


@router.post("/reservations/{identity}/check-in")
def check_in(identity: int, request: Request, db: DB, actor: Actor):
    c.check_in(db, actor, identity, now=request.app.state.clock())
    return redirect(f"/reservations/{identity}")


@router.get("/history")
def history(
    request: Request,
    db: DB,
    actor: Actor,
    sut_id: str = "",
    user_id: str = "",
    start: str = "",
    end: str = "",
    page: int = Query(1, ge=1),
):
    data = q.history_page(
        db,
        sut_id=optional_id(sut_id),
        user_id=optional_id(user_id),
        start=local_time(start) if start else None,
        end=local_time(end) if end else None,
        page=page,
    )
    return render(
        request,
        "history.html",
        actor,
        data=data,
        page=page,
        filters={"sut_id": sut_id, "user_id": user_id, "start": start, "end": end},
    )


@router.get("/calendar")
def calendar(
    request: Request,
    db: DB,
    actor: Actor,
    day: date | None = None,
    view: Literal["day", "week"] = "week",
    sut_id: str = "",
    page: int = Query(1, ge=1),
):
    day = day or request.app.state.clock().astimezone(TAIPEI).date()
    try:
        start = datetime.combine(day, time.min, tzinfo=TAIPEI)
        end = start + timedelta(days=7 if view == "week" else 1)
        start, end = start.astimezone(UTC), end.astimezone(UTC)
    except (ValueError, OverflowError):
        raise HTTPException(422, "Calendar date is outside the supported range") from None
    data = q.reservation_page(
        db,
        sut_id=optional_id(sut_id),
        start=start.astimezone(UTC),
        end=end.astimezone(UTC),
        page=page,
        now=request.app.state.clock(),
    )
    return render(
        request,
        "calendar.html",
        actor,
        data=data,
        day=day,
        view=view,
        page=page,
        filters={"day": day.isoformat(), "view": view, "sut_id": sut_id},
    )


@router.get("/notifications")
def notifications(request: Request, db: DB, actor: Actor):
    return render(request, "notifications.html", actor, notifications=q.notification_list(db, actor))


@router.get("/notifications/fragment")
def notification_fragment(request: Request, db: DB, actor: Actor):
    return render(request, "notification_list.html", actor, notifications=q.notification_list(db, actor))


@router.post("/notifications/{identity}/read")
def read_notification(identity: int, request: Request, db: DB, actor: Actor):
    q.mark_read(db, actor, identity, request.app.state.clock())
    return redirect("/notifications")
