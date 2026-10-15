"""Read-only timeline projection, including clipped cross-day and overlapping bookings."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models.domain import Reservation
from app.services.coordination_queries import reservation_view

TAIPEI = ZoneInfo("Asia/Taipei")


def day_events(bookings, day):
    start = datetime.combine(day, time.min, tzinfo=TAIPEI)
    end = start + timedelta(days=1)
    events = []
    for booking in bookings:
        begins = booking["start_time"].astimezone(TAIPEI)
        finishes = booking["end_time"].astimezone(TAIPEI)
        if begins >= end or finishes <= start:
            continue
        top = (max(begins, start) - start).total_seconds() / 60
        bottom = (min(finishes, end) - start).total_seconds() / 60
        events.append(
            {
                **booking,
                "top": top,
                "bottom": min(1440, max(bottom, top + 30)),
                "continues_before": begins < start,
                "continues_after": finishes > end,
                "time_label": f"{max(begins, start):%H:%M}–"
                + ("24:00" if finishes >= end else f"{finishes:%H:%M}"),
            }
        )
    events.sort(key=lambda e: (e["top"], e["bottom"], e["id"]))
    cluster, lanes = [], []

    def finish_cluster():
        for event in cluster:
            event["lanes"] = len(lanes)

    for event in events:
        if lanes and event["top"] >= max(lanes):
            finish_cluster()
            cluster, lanes = [], []
        lane = next((i for i, until in enumerate(lanes) if until <= event["top"]), len(lanes))
        if lane == len(lanes):
            lanes.append(event["bottom"])
        else:
            lanes[lane] = event["bottom"]
        event["lane"] = lane
        event["height"] = event["bottom"] - event["top"]
        cluster.append(event)
    finish_cluster()
    return events


def schedule(db, start, end, sut_id, now):
    conditions = [Reservation.end_time > start, Reservation.start_time < end]
    if sut_id is not None:
        conditions.append(Reservation.sut_id == sut_id)
    bookings = [
        reservation_view(db, row, now)
        for row in db.scalars(
            select(Reservation).where(*conditions).order_by(Reservation.start_time, Reservation.id)
        )
    ]
    first = start.astimezone(TAIPEI).date()
    days = [
        {"date": first + timedelta(days=i), "events": day_events(bookings, first + timedelta(days=i))}
        for i in range((end.astimezone(TAIPEI).date() - first).days)
    ]
    return {"days": days, "total": len(bookings)}
