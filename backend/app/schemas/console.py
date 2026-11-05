from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ClientInput(Input):
    lab_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=120)
    ipv4: str = Field(max_length=15)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_username: str = Field(min_length=1, max_length=256)
    auth_method: Literal["password", "private_key"]
    secret: SecretStr = Field(min_length=1, max_length=65536)
    notes: str = Field(default="", max_length=2000)

    @field_validator("name", "ssh_username")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Required nonblank value")
        return value.strip()


class ClientPatch(Input):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    lab_id: int | None = Field(default=None, gt=0)
    ipv4: str | None = Field(default=None, max_length=15)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    ssh_username: str | None = Field(default=None, min_length=1, max_length=256)
    auth_method: Literal["password", "private_key"] | None = None
    secret: SecretStr | None = Field(default=None, min_length=1, max_length=65536)
    enabled: StrictBool | None = None
    confirmation_id: SecretStr | None = Field(default=None, max_length=128)


class MappingInput(Input):
    expected_revision: int = Field(ge=0)
    clear: StrictBool = False
    reason: str | None = Field(default=None, max_length=1000)
    confirmation_id: SecretStr | None = Field(default=None, max_length=128)


class UartInput(MappingInput):
    client_id: int | None = Field(default=None, gt=0)
    tmux_session: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,63}$")

    @model_validator(mode="after")
    def pair(self):
        if self.clear:
            if self.client_id is not None or self.tmux_session is not None:
                raise ValueError("Clear does not accept a mapping")
        elif self.client_id is None or self.tmux_session is None:
            raise ValueError("Client and existing tmux name are required")
        return self


class BmcInput(MappingInput):
    ipv4: str | None = Field(default=None, max_length=15)

    @model_validator(mode="after")
    def target(self):
        if self.clear == (self.ipv4 is not None):
            raise ValueError("Provide IPv4 or clear, exclusively")
        return self


class GrantInput(Input):
    user_id: int = Field(gt=0)
    duration_hours: Literal[1, 2, 4, 8, 12, 24]
    reason: str | None = Field(default=None, max_length=1000)


class GrantExtension(Input):
    expected_revision: int = Field(ge=1)
    new_expires_at: datetime

    @field_validator("new_expires_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timezone required")
        return value


class RevisionInput(Input):
    expected_revision: int = Field(ge=1)
