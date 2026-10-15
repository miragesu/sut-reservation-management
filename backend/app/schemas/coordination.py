from datetime import UTC, datetime
from typing import Annotated

from pydantic import AwareDatetime, Field, field_validator

from app.schemas.inputs import Input
from app.schemas.outputs import ContactView, Output


# No business cap: representability is validated relative to the server clock.
PositiveMinutes = Annotated[int, Field(gt=0)]


class ClaimInput(Input):
    duration_minutes: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    purpose: str = Field(default="", max_length=4000)
    acknowledge_reservation_conflict: bool = False
    reservation_id: int | None = Field(default=None, gt=0)

    @field_validator("duration_minutes", mode="before")
    @classmethod
    def valid_duration(cls, value):
        if isinstance(value, bool):
            raise ValueError("Duration must be a positive finite number of minutes")
        return value


class QueueInput(Input):
    requested_duration_minutes: PositiveMinutes

    @field_validator("requested_duration_minutes", mode="before")
    @classmethod
    def integer_minutes(cls, value):
        if isinstance(value, (bool, float)):
            raise ValueError("Queue duration must be a positive integer number of minutes")
        return value


class ReleaseInput(Input):
    usage_key: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="", max_length=1000)


def to_utc(value):
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError):
        raise ValueError("Time cannot be represented in UTC") from None


class ExpectedEndInput(Input):
    usage_key: str = Field(min_length=1, max_length=64)
    expected_end_time: AwareDatetime
    acknowledge_reservation_conflict: bool = False

    @field_validator("expected_end_time")
    @classmethod
    def utc(cls, value):
        return to_utc(value)


class ReservationUpdate(Input):
    start_time: AwareDatetime
    end_time: AwareDatetime
    purpose: str = Field(min_length=1, max_length=4000)

    @field_validator("start_time", "end_time")
    @classmethod
    def utc(cls, value):
        return to_utc(value)


class ReservationInput(ReservationUpdate):
    sut_id: int = Field(gt=0)


class ReasonInput(Input):
    reason: str = Field(min_length=1, max_length=1000)


class UsageView(Output):
    id: int
    usage_key: str
    sut_id: int
    sut_name: str
    lab_name: str
    user: ContactView
    start_time: datetime
    expected_end_time: datetime
    purpose: str | None
    reservation_id: int | None
    overdue: bool


class QueueView(Output):
    id: int
    entry_key: str
    user: ContactView
    position: int
    eligible: bool
    requested_duration_minutes: int
    created_at: datetime
    notified_at: datetime | None
    offer_expires_at: datetime | None
    paused_at: datetime | None
    offer_status: str


class ReservationView(Output):
    id: int
    sut_id: int
    sut_name: str
    lab_name: str
    user: ContactView
    start_time: datetime
    end_time: datetime
    purpose: str
    status: str
    checked_in_at: datetime | None
    claimed_at: datetime | None
    cancelled_at: datetime | None
    no_show_at: datetime | None
    at_risk: bool
    operational_state: str
    operational_reason: str | None
    effective_status: str
    in_use: bool


class HistoryView(Output):
    id: int
    usage_key: str
    sut_id: int
    sut_name: str
    lab_name: str
    user: ContactView
    start_time: datetime
    end_time: datetime
    duration_minutes: int
    release_reason: str
    release_note: str | None
    released_by_user_id: int | None
    purpose: str | None
    reservation_id: int | None


class HistoryPage(Output):
    items: list[HistoryView]
    total: int


class ReservationPage(Output):
    items: list[ReservationView]
    total: int


class NotificationView(Output):
    id: int
    sut_id: int | None
    message: str
    created_at: datetime
    read_at: datetime | None


class QueueLeaveInput(Input):
    entry_key: str = Field(min_length=1, max_length=64)


class CoordinationView(Output):
    status: str
    priority_reservation_id: int | None
    usage: UsageView | None
    queue: list[QueueView]
    reservations: list[ReservationView]


class ReleaseView(Output):
    history: HistoryView
    queue: list[QueueView]
    priority_reservation_id: int | None
