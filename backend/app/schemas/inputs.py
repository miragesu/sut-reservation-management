from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, IPvAnyAddress, SecretStr, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, hide_input_in_errors=True)


class ProfileInput(Input):
    display_name: str = Field(min_length=1, max_length=120)
    team: str = Field(min_length=1, max_length=80)
    email: EmailStr = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return str(value).casefold()


class UserInput(ProfileInput):
    username: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    role: Literal["user", "lab_admin", "super_admin"] = "user"
    temporary_password: SecretStr

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value):
        return value.casefold()


class LoginInput(Input):
    username: str = Field(min_length=1, max_length=80)
    password: SecretStr


class PasswordInput(Input):
    current_password: SecretStr
    new_password: SecretStr


class ResetInput(Input):
    temporary_password: SecretStr


class RoleInput(Input):
    role: Literal["user", "lab_admin", "super_admin"]


class StatusInput(Input):
    is_active: bool
    reason: str = Field(default="", max_length=1000)
    acknowledge_resources: bool = False


class LabInput(Input):
    name: str = Field(min_length=1, max_length=120)
    location: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)


class SUTUpdate(Input):
    name: str = Field(min_length=1, max_length=120)
    platform: str = Field(min_length=1, max_length=100)
    owner_team: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=4000)
    bmc_ip: IPvAnyAddress | None = None
    host_ip: IPvAnyAddress | None = None

    @field_validator("bmc_ip", "host_ip", mode="before")
    @classmethod
    def empty_ip(cls, value):
        return None if value == "" else value


class SUTInput(SUTUpdate):
    lab_id: int = Field(gt=0)


class OperationalInput(Input):
    state: Literal["normal", "maintenance", "out_of_service"]
    reason: str = Field(default="", max_length=1000)
    acknowledge_activity: bool = False
