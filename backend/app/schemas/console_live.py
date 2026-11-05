"""Version1 terminal/control contracts; extra fields never become SSH arguments."""

from typing import Literal

from pydantic import Field, SecretStr, StrictBool, StrictInt, field_validator

from app.schemas.console import Input, ClientPatch


class SessionCreate(Input):
    sut_id: StrictInt = Field(gt=0)
    transport: Literal["uart", "bmc"]
    expected_revision: StrictInt = Field(ge=1)
    tab_id: str = Field(min_length=1, max_length=64)


class Attach(Input):
    attachment_generation: StrictInt = Field(ge=1)
    tab_id: str = Field(min_length=1, max_length=64)
    confirm_connected: StrictBool = False


class Challenge(Input):
    client_id: StrictInt | None = Field(default=None, gt=0)
    sut_id: StrictInt | None = Field(default=None, gt=0)


class TrustAccept(Input):
    challenge_id: str = Field(min_length=1, max_length=128)
    expected_trust_revision: StrictInt = Field(ge=0)
    fingerprint: str = Field(min_length=1, max_length=100)
    out_of_band_verified: Literal[True]
    confirmation_id: SecretStr | None = Field(default=None, max_length=128)


class ClientValidation(Input):
    client_id: StrictInt | None = Field(default=None, gt=0)
    expected_version: StrictInt | None = Field(default=None, ge=1)
    lab_id: StrictInt | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    ipv4: str | None = Field(default=None, min_length=1, max_length=15)
    ssh_port: StrictInt | None = Field(default=None, ge=1, le=65535)
    ssh_username: str | None = Field(default=None, min_length=1, max_length=256)
    auth_method: Literal["password", "private_key"] | None = None
    secret: SecretStr | None = Field(default=None, min_length=1, max_length=65536)
    passphrase: SecretStr | None = Field(default=None, max_length=1024)
    notes: str | None = Field(default=None, max_length=2000)
    trust_challenge_id: str | None = Field(default=None, max_length=128)


class ClientCommit(Input):
    validation_id: str = Field(min_length=1, max_length=128)


class VerifiedPatch(ClientPatch):
    validation_id: str | None = Field(default=None, min_length=1, max_length=128)


class Hello(Input):
    v: Literal[1]
    type: Literal["hello"]
    ticket: SecretStr = Field(min_length=1, max_length=128)
    tab_id: str = Field(min_length=1, max_length=64)
    attachment_generation: StrictInt = Field(ge=1)
    cols: StrictInt = Field(ge=2, le=500)
    rows: StrictInt = Field(ge=1, le=200)


class InputFrame(Input):
    type: Literal["input"]
    attachment_generation: StrictInt = Field(ge=1)
    seq: StrictInt = Field(ge=1)
    data: str = Field(min_length=1, max_length=10924)


class KeyFrame(Input):
    type: Literal["send_key"]
    attachment_generation: StrictInt = Field(ge=1)
    seq: StrictInt = Field(ge=1)
    key: Literal["esc", "tab", "ctrl_c", "ctrl_d", "ctrl_z"]


class ResizeFrame(Input):
    type: Literal["resize"]
    cols: StrictInt = Field(ge=2, le=500)
    rows: StrictInt = Field(ge=1, le=200)


class AuthFrame(Input):
    type: Literal["authenticate"]
    flow_id: str = Field(min_length=1, max_length=64)
    username: SecretStr = Field(min_length=1, max_length=256)
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("username", "password")
    @classmethod
    def byte_limit(cls, value, info):
        if len(value.get_secret_value().encode()) > (256 if info.field_name == "username" else 1024):
            raise ValueError("Credential exceeds byte limit")
        return value


class DisconnectFrame(Input):
    type: Literal["disconnect"]


class PasteBegin(Input):
    type: Literal["paste_begin"]
    attachment_generation: StrictInt = Field(ge=1)
    paste_id: str = Field(min_length=1, max_length=64)
    byte_count: StrictInt = Field(ge=1, le=65536)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    multiline_approved: StrictBool = False


class PasteChunk(Input):
    type: Literal["paste_chunk"]
    attachment_generation: StrictInt = Field(ge=1)
    paste_id: str = Field(min_length=1, max_length=64)
    seq: StrictInt = Field(ge=1)
    data: str = Field(min_length=1, max_length=10924)
    final: StrictBool = False
