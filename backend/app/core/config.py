from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    secret_key: SecretStr
    database_url: str = "sqlite:///./data/sut.db"
    app_env: Literal["development", "test", "production"] = "production"
    cookie_secure: bool = True
    low_security_passwd: bool = False
    console_enabled: bool = False
    console_access_policy: Literal["claim_only", "shared_readonly", "all_authenticated"] = "claim_only"
    console_allow_insecure_http: bool = False
    console_keyring_file: str | None = None
    console_broker_socket: str | None = None
    console_broker_ipc_key_file: str | None = None
    console_broker_uid: int = Field(default=10002, ge=1)
    console_allowed_origins: list[str] = Field(default_factory=list)
    console_sensitive_ipv4: list[str] = Field(default_factory=list)
    deadline_processor_enabled: bool = True
    deadline_poll_seconds: float = Field(default=1.0, ge=0.1, le=60)
    session_hours: int = Field(default=12, ge=1, le=168)
    minimum_password_length: int = Field(default=12, ge=12, le=128)

    @field_validator("low_security_passwd", "console_enabled", "console_allow_insecure_http", mode="before")
    @classmethod
    def explicit_boolean(cls, value, info):
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        raise ValueError(f"{info.field_name.upper()} must be true or false")

    @field_validator("console_sensitive_ipv4")
    @classmethod
    def canonical_deny_addresses(cls, values):
        from ipaddress import IPv4Address

        try:
            if any(str(IPv4Address(value)) != value for value in values):
                raise ValueError()
        except ValueError:
            raise ValueError("Console deny entries must be canonical IPv4") from None
        return values

    @property
    def password_minimum(self):
        return 1 if self.low_security_passwd else self.minimum_password_length

    @field_validator("secret_key")
    @classmethod
    def strong_key(cls, value):
        if len(value.get_secret_value()) < 32 or "REPLACE" in value.get_secret_value():
            raise ValueError("SECRET_KEY must contain at least 32 random characters")
        return value

    @field_validator("database_url")
    @classmethod
    def sqlite_only(cls, value):
        if not value.startswith("sqlite:///"):
            raise ValueError("MVP supports SQLite only")
        return value
