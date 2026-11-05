"""Additive, terminal-free CONSOLE-001 foundation. No network/session executor."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UTCDateTime, utcnow
from app.models.domain import Created


def fk(target):
    return ForeignKey(target, ondelete="RESTRICT")


def identity():
    return uuid4().hex


class ConsoleClient(Created, Base):
    __tablename__ = "console_clients"
    __table_args__ = (
        UniqueConstraint("lab_id", "normalized_name"),
        CheckConstraint("ssh_port BETWEEN 1 AND 65535", name="port"),
        CheckConstraint("auth_method IN ('password','private_key')", name="method"),
        CheckConstraint("length(trim(name)) > 0", name="name"),
        CheckConstraint("metadata_version > 0 AND connection_epoch > 0", name="versions"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[str] = mapped_column(String(32), unique=True, default=identity)
    lab_id: Mapped[int] = mapped_column(fk("labs.id"))
    name: Mapped[str] = mapped_column(String(120))
    normalized_name: Mapped[str] = mapped_column(String(240))
    ipv4: Mapped[str] = mapped_column(String(15), unique=True)
    ssh_port: Mapped[int] = mapped_column(default=22)
    ssh_username: Mapped[str] = mapped_column(String(256))
    auth_method: Mapped[str] = mapped_column(String(16))
    active_credential_id: Mapped[int | None] = mapped_column(
        ForeignKey("console_credentials.id", ondelete="RESTRICT", use_alter=True)
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    metadata_version: Mapped[int] = mapped_column(default=1)
    connection_epoch: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_by: Mapped[int] = mapped_column(fk("users.id"))


class ConsoleCredential(Created, Base):
    __tablename__ = "console_credentials"
    __table_args__ = (
        UniqueConstraint("client_security_id", "generation"),
        CheckConstraint("method IN ('password','private_key')", name="method"),
        CheckConstraint("generation > 0 AND crypto_revision > 0", name="versions"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[str] = mapped_column(String(32), unique=True, default=identity)
    client_security_id: Mapped[str] = mapped_column(fk("console_clients.security_id"))
    method: Mapped[str] = mapped_column(String(16))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    wrapped_data_key: Mapped[bytes] = mapped_column(LargeBinary)
    wrap_nonce: Mapped[bytes] = mapped_column(LargeBinary)
    key_id: Mapped[str] = mapped_column(String(64))
    algorithm: Mapped[str] = mapped_column(String(32), default="AES-256-GCM/v1")
    generation: Mapped[int] = mapped_column(default=1)
    crypto_revision: Mapped[int] = mapped_column(default=1)
    replaced_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_by: Mapped[int] = mapped_column(fk("users.id"))


class ConsoleUartMapping(Base):
    __tablename__ = "console_uart_mappings"
    __table_args__ = (
        CheckConstraint(
            "(client_id IS NULL AND tmux_session IS NULL) OR (client_id IS NOT NULL AND tmux_session IS NOT NULL)",
            name="configured_pair",
        ),
        CheckConstraint("revision > 0 AND endpoint_epoch > 0", name="versions"),
        Index(
            "uq_console_uart_active_pair",
            "client_id",
            "tmux_session",
            unique=True,
            sqlite_where=text("active_slot = 1"),
        ),
    )
    sut_id: Mapped[int] = mapped_column(fk("suts.id"), primary_key=True)
    client_id: Mapped[int | None] = mapped_column(fk("console_clients.id"))
    tmux_session: Mapped[str | None] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(default=1)
    endpoint_epoch: Mapped[int] = mapped_column(default=1)
    active_slot: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_by: Mapped[int] = mapped_column(fk("users.id"))


class ConsoleBmcEndpoint(Base):
    __tablename__ = "console_bmc_endpoints"
    __table_args__ = (CheckConstraint("revision > 0 AND endpoint_epoch > 0", name="versions"),)
    sut_id: Mapped[int] = mapped_column(fk("suts.id"), primary_key=True)
    ipv4: Mapped[str | None] = mapped_column(String(15))
    revision: Mapped[int] = mapped_column(default=1)
    endpoint_epoch: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_by: Mapped[int] = mapped_column(fk("users.id"))


class ConsoleHostKey(Created, Base):
    __tablename__ = "console_host_keys"
    __table_args__ = (
        CheckConstraint(
            "(client_id IS NOT NULL AND bmc_sut_id IS NULL) OR (client_id IS NULL AND bmc_sut_id IS NOT NULL)",
            name="owner",
        ),
        Index("uq_console_host_key_client", "client_id", unique=True, sqlite_where=text("is_current = 1")),
        Index("uq_console_host_key_bmc", "bmc_sut_id", unique=True, sqlite_where=text("is_current = 1")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int | None] = mapped_column(fk("console_clients.id"))
    bmc_sut_id: Mapped[int | None] = mapped_column(fk("console_bmc_endpoints.sut_id"))
    ipv4: Mapped[str] = mapped_column(String(15))
    port: Mapped[int] = mapped_column()
    endpoint_epoch: Mapped[int] = mapped_column()
    algorithm: Mapped[str] = mapped_column(String(64))
    public_key: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(100))
    trust_revision: Mapped[int] = mapped_column(default=1)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    previous_id: Mapped[int | None] = mapped_column(fk("console_host_keys.id"))
    accepted_by: Mapped[int] = mapped_column(fk("users.id"))
    replaced_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ConsoleMappingEvent(Created, Base):
    __tablename__ = "console_mapping_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    sut_id: Mapped[int] = mapped_column(fk("suts.id"), index=True)
    transport: Mapped[str] = mapped_column(String(4))
    actor_id: Mapped[int] = mapped_column(fk("users.id"))
    old: Mapped[dict] = mapped_column(JSON)
    new: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(String(1000))


class ConsoleAudit(Created, Base):
    __tablename__ = "console_audits"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(fk("users.id"))
    sut_id: Mapped[int | None] = mapped_column(fk("suts.id"))
    event_type: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON)


class ConsoleGrant(Created, Base):
    __tablename__ = "console_grants"
    __table_args__ = (
        CheckConstraint(
            "expires_at > created_at AND julianday(expires_at) <= julianday(created_at) + 1", name="duration"
        ),
        CheckConstraint("state IN ('active','expired','revoked')", name="state"),
        Index(
            "uq_console_grant_active", "user_id", "sut_id", unique=True, sqlite_where=text("state = 'active'")
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(fk("users.id"))
    sut_id: Mapped[int] = mapped_column(fk("suts.id"))
    admin_id: Mapped[int] = mapped_column(fk("users.id"))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    reason: Mapped[str | None] = mapped_column(String(1000))
    state: Mapped[str] = mapped_column(String(8), default="active")
    revision: Mapped[int] = mapped_column(default=1)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    close_reason: Mapped[str | None] = mapped_column(String(40))


class ConsoleSession(Created, Base):
    __tablename__ = "console_sessions"
    __table_args__ = (
        UniqueConstraint("user_id", "slot"),
        CheckConstraint("transport IN ('uart','bmc')", name="transport"),
        CheckConstraint("mode IN ('read','write')", name="mode"),
        CheckConstraint(
            "state IN ('reserved','connecting','connected','reconnecting','closed')", name="state"
        ),
        CheckConstraint(
            "(state = 'closed' AND slot IS NULL) OR (state != 'closed' AND slot BETWEEN 1 AND 10 AND slot IS NOT NULL)",
            name="slot",
        ),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identity)
    user_id: Mapped[int] = mapped_column(fk("users.id"))
    sut_id: Mapped[int] = mapped_column(fk("suts.id"))
    client_id: Mapped[int | None] = mapped_column(fk("console_clients.id"))
    login_session_digest: Mapped[str] = mapped_column(String(64), index=True)
    transport: Mapped[str] = mapped_column(String(4))
    mode: Mapped[str] = mapped_column(String(5))
    policy: Mapped[str] = mapped_column(String(20))
    grant_id: Mapped[int | None] = mapped_column(fk("console_grants.id"))
    usage_key: Mapped[str | None] = mapped_column(String(64))
    slot: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(12), default="reserved")
    instance_id: Mapped[str] = mapped_column(String(64))
    attachment_generation: Mapped[int] = mapped_column(default=1)
    endpoint_epoch: Mapped[int] = mapped_column()
    client_epoch: Mapped[int] = mapped_column(default=0)
    credential_generation: Mapped[int] = mapped_column(default=0)
    trust_revision: Mapped[int] = mapped_column()
    lease_until: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    connected_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    close_reason: Mapped[str | None] = mapped_column(String(40))


class ConsoleTicket(Created, Base):
    __tablename__ = "console_tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    session_id: Mapped[str] = mapped_column(fk("console_sessions.id"))
    user_id: Mapped[int] = mapped_column(fk("users.id"))
    login_session_digest: Mapped[str] = mapped_column(String(64))
    origin: Mapped[str] = mapped_column(String(256))
    attachment_generation: Mapped[int] = mapped_column()
    endpoint_epoch: Mapped[int] = mapped_column()
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ConsoleConfirmation(Created, Base):
    __tablename__ = "console_confirmations"
    token_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[int] = mapped_column(fk("users.id"))
    login_session_digest: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str] = mapped_column(String(64))
    payload_hash: Mapped[str] = mapped_column(String(64))
    sessions_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ConsoleAuthFlow(Created, Base):
    __tablename__ = "console_auth_flows"
    __table_args__ = (CheckConstraint("attempt_count BETWEEN 0 AND 3", name="attempts"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=identity)
    session_id: Mapped[str] = mapped_column(fk("console_sessions.id"))
    user_id: Mapped[int] = mapped_column(fk("users.id"))
    login_session_digest: Mapped[str] = mapped_column(String(64))
    attachment_generation: Mapped[int] = mapped_column()
    attempt_count: Mapped[int] = mapped_column(default=0)
    in_flight: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ConsoleRevocation(Created, Base):
    __tablename__ = "console_revocations"
    __table_args__ = (UniqueConstraint("session_id", "attachment_generation"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(fk("console_sessions.id"))
    attachment_generation: Mapped[int] = mapped_column()
    target_epoch: Mapped[int] = mapped_column()
    reason: Mapped[str] = mapped_column(String(40))
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
