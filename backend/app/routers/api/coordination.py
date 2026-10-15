from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import AwareDatetime, AfterValidator
from sqlalchemy import select

from app.core.csrf import check_csrf
from app.core.dependencies import current_user, database
from app.models.domain import CurrentUsage, User
from app.schemas.coordination import (
    ClaimInput,
    CoordinationView,
    ExpectedEndInput,
    HistoryPage,
    NotificationView,
    QueueInput,
    QueueLeaveInput,
    QueueView,
    ReasonInput,
    ReleaseInput,
    ReleaseView,
    ReservationInput,
    ReservationPage,
    ReservationUpdate,
    ReservationView,
    UsageView,
)
from app.schemas.outputs import Collection
from app.services import coordination as c, coordination_queries as q
from app.services.common import get_or_404
from app.schemas.coordination import to_utc

UTCQuery = Annotated[AwareDatetime, AfterValidator(to_utc)]

router = APIRouter(prefix="/api/v1", dependencies=[Depends(check_csrf)])
DB = Annotated[object, Depends(database, scope="function")]
Actor = Annotated[User, Depends(current_user)]


@router.post("/suts/{identity}/claim", response_model=UsageView, status_code=201)
def claim(identity: int, data: ClaimInput, request: Request, db: DB, actor: Actor):
    now = request.app.state.clock()
    return q.usage_view(db, c.claim(db, actor, identity, data, now=now), now)


def release_result(db, history, now):
    priority = c.protected(db, history.sut_id, now)
    return {
        "history": q.history_view(db, history),
        "queue": q.queue_view(db, history.sut_id),
        "priority_reservation_id": priority.id if priority else None,
    }


@router.post("/suts/{identity}/release", response_model=ReleaseView)
def release(identity: int, data: ReleaseInput, request: Request, db: DB, actor: Actor):
    now = request.app.state.clock()
    return release_result(db, c.release(db, actor, identity, data, now=now), now)


@router.post("/suts/{identity}/force-release", response_model=ReleaseView)
def force_release(identity: int, data: ReleaseInput, request: Request, db: DB, actor: Actor):
    now = request.app.state.clock()
    return release_result(db, c.release(db, actor, identity, data, force=True, now=now), now)


@router.patch("/suts/{identity}/usage/expected-end", response_model=UsageView)
def expected_end(identity: int, data: ExpectedEndInput, request: Request, db: DB, actor: Actor):
    now = request.app.state.clock()
    return q.usage_view(db, c.extend(db, actor, identity, data, now=now), now)


@router.get("/suts/{identity}/coordination", response_model=CoordinationView)
def coordination(identity: int, request: Request, db: DB, actor: Actor):
    return q.coordination_view(db, identity, request.app.state.clock())


@router.get("/usages/me", response_model=Collection[UsageView])
def usages(request: Request, db: DB, actor: Actor):
    return {
        "items": [
            q.usage_view(db, row, request.app.state.clock())
            for row in db.scalars(
                select(CurrentUsage).where(CurrentUsage.user_id == actor.id).order_by(CurrentUsage.id)
            )
        ]
    }


@router.get("/suts/{identity}/queue", response_model=Collection[QueueView])
def queue(identity: int, db: DB, actor: Actor):
    return {"items": q.queue_view(db, identity)}


@router.post("/suts/{identity}/queue", response_model=QueueView, status_code=201)
def join_queue(identity: int, data: QueueInput, request: Request, db: DB, actor: Actor):
    entry = c.join_queue(db, actor, identity, data, now=request.app.state.clock())
    return next(row for row in q.queue_view(db, identity) if row["id"] == entry.id)


@router.delete("/suts/{identity}/queue", status_code=204)
def leave_queue(identity: int, data: QueueLeaveInput, request: Request, db: DB, actor: Actor):
    c.leave_queue(db, actor, identity, entry_key=data.entry_key, now=request.app.state.clock())
    return Response(status_code=204)


@router.delete("/suts/{identity}/queue/all", status_code=204)
def clear_queue(identity: int, data: ReasonInput, request: Request, db: DB, actor: Actor):
    c.leave_queue(db, actor, identity, clear=True, reason=data.reason, now=request.app.state.clock())
    return Response(status_code=204)


@router.get("/reservations", response_model=ReservationPage)
def reservations(
    request: Request,
    db: DB,
    actor: Actor,
    sut_id: int | None = None,
    user_id: int | None = None,
    start: UTCQuery | None = None,
    end: UTCQuery | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    return q.reservation_page(
        db,
        sut_id=sut_id,
        user_id=user_id,
        start=start,
        end=end,
        page=page,
        page_size=page_size,
        now=request.app.state.clock(),
    )


@router.post("/reservations", response_model=ReservationView, status_code=201)
def create_reservation(data: ReservationInput, request: Request, db: DB, actor: Actor):
    now = request.app.state.clock()
    return q.reservation_view(db, c.save_reservation(db, actor, data, now=now), now)


@router.get("/reservations/{identity}", response_model=ReservationView)
def reservation(identity: int, request: Request, db: DB, actor: Actor):
    from app.models.domain import Reservation

    return q.reservation_view(db, get_or_404(db, Reservation, identity), request.app.state.clock())


@router.put("/reservations/{identity}", response_model=ReservationView)
def edit_reservation(identity: int, data: ReservationUpdate, request: Request, db: DB, actor: Actor):
    now = request.app.state.clock()
    return q.reservation_view(db, c.save_reservation(db, actor, data, identity=identity, now=now), now)


@router.delete("/reservations/{identity}", response_model=ReservationView)
def cancel_reservation(identity: int, request: Request, db: DB, actor: Actor):
    now = request.app.state.clock()
    return q.reservation_view(db, c.cancel_reservation(db, actor, identity, now=now), now)


@router.post("/reservations/{identity}/check-in", response_model=ReservationView)
def check_in(identity: int, request: Request, db: DB, actor: Actor):
    now = request.app.state.clock()
    return q.reservation_view(db, c.check_in(db, actor, identity, now=now), now)


@router.get("/history", response_model=HistoryPage)
def history(
    db: DB,
    actor: Actor,
    sut_id: int | None = None,
    user_id: int | None = None,
    start: UTCQuery | None = None,
    end: UTCQuery | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    return q.history_page(
        db, sut_id=sut_id, user_id=user_id, start=start, end=end, page=page, page_size=page_size
    )


@router.get("/notifications", response_model=Collection[NotificationView])
def notifications(db: DB, actor: Actor):
    return {"items": q.notification_list(db, actor)}


@router.post("/notifications/{identity}/read", response_model=NotificationView)
def read_notification(identity: int, request: Request, db: DB, actor: Actor):
    return q.mark_read(db, actor, identity, request.app.state.clock())
