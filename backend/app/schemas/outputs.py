from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LabView(Output):
    id: int
    name: str
    location: str
    description: str


class ProfileView(Output):
    id: int
    username: str
    display_name: str
    team: str
    email: str


class UserView(ProfileView):
    role: str
    is_active: bool
    must_change_password: bool


class ContactView(Output):
    id: int
    display_name: str
    team: str
    email: str


class BookingView(Output):
    id: int
    user: ContactView
    start_time: datetime
    end_time: datetime
    purpose: str


class SUTView(Output):
    id: int
    lab_id: int
    lab_name: str
    name: str
    platform: str
    owner_team: str
    description: str
    bmc_ip: str | None
    host_ip: str | None
    is_archived: bool
    operational_state: str
    operational_reason: str | None
    status: str
    holder: ContactView | None
    expected_end_time: datetime | None
    usage_purpose: str | None
    in_use: bool
    overdue: bool
    next_reservation: BookingView | None
    reservations_24h: list[BookingView]


class DashboardView(Output):
    items: list[SUTView]
    total: int
    as_of: datetime
    metrics: dict[str, int]


T = TypeVar("T")


class Collection(Output, Generic[T]):
    items: list[T]


class LoginView(Output):
    must_change_password: bool


class CSRFView(Output):
    csrf_token: str


class ResourceView(Output):
    id: int
    sut_id: int
    sut_name: str
    lab_name: str


class ImpactView(Output):
    usages: list[ResourceView]
    queues: list[ResourceView]
    reservations: list[ResourceView]
