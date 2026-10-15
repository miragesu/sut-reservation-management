from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    secret_key: SecretStr
    database_url: str = "sqlite:///./data/sut.db"
    app_env: Literal["development", "test", "production"] = "production"
    cookie_secure: bool = True
    session_hours: int = Field(default=12, ge=1, le=168)
    minimum_password_length: int = Field(default=12, ge=12, le=128)

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
