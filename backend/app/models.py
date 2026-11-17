from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    sequence: Mapped[int] = mapped_column(default=0)
    aging_minutes: Mapped[int] = mapped_column(default=15)
    priority_weight: Mapped[int] = mapped_column(default=30)
    grace_minutes: Mapped[int] = mapped_column(default=15)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(default=0)
    window: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Service(Base):
    __tablename__ = "services"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    minutes: Mapped[int] = mapped_column(default=10)
    capacity: Mapped[int] = mapped_column(default=2)
    active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (CheckConstraint("minutes > 0 AND capacity > 0"),)


class Counter(Base):
    __tablename__ = "counters"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"))
    staff_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, unique=True)
    active: Mapped[bool] = mapped_column(default=True)


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"), index=True)
    token: Mapped[str] = mapped_column(String(30))
    secret: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: uuid4().hex + uuid4().hex)
    name: Mapped[str] = mapped_column(String(100))
    contact: Mapped[str] = mapped_column(String(254), default="")
    channel: Mapped[str] = mapped_column(String(20), default="email")
    source: Mapped[str] = mapped_column(String(20))
    priority: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), index=True)
    slot: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    checked_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    counter_id: Mapped[str | None] = mapped_column(ForeignKey("counters.id"), nullable=True)
    __table_args__ = (
        UniqueConstraint("org_id", "token"),
        CheckConstraint("priority >= 0 AND priority <= 2"),
        CheckConstraint("status IN ('booked','waiting','serving','completed','cancelled','no_show')"),
        Index(
            "uq_serving_counter",
            "counter_id",
            unique=True,
            postgresql_where=text("status = 'serving'"),
            sqlite_where=text("status = 'serving'"),
        ),
    )


class Inbox(Base):
    __tablename__ = "inbox"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Outbox(Base):
    __tablename__ = "outbox"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    available: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    attempts: Mapped[int] = mapped_column(default=0)
    state: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(60))
    target: Mapped[str] = mapped_column(String(100))
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
