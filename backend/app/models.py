"""SQLAlchemy ORM models. Money and quantities use Numeric(24, 8) -> Python Decimal."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .core.db import Base

Money = Numeric(24, 8, asdecimal=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TZDateTime(TypeDecorator):
    """Timezone-aware UTC DateTime that also round-trips through SQLite (which drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        return aware(value)


def aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Stock(Base):
    __tablename__ = "stocks"
    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # provider symbol incl. suffix
    company: Mapped[str] = mapped_column(String(200), default="")
    kind: Mapped[str] = mapped_column(String(16), default="equity")  # equity | etf | index | fx
    exchange: Mapped[str] = mapped_column(String(64), default="")
    market: Mapped[str] = mapped_column(String(32), default="")  # US | DFM | ADX | NASDAQ_DUBAI | OTHER
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    sector: Mapped[str] = mapped_column(String(100), default="")
    industry: Mapped[str] = mapped_column(String(100), default="")
    country: Mapped[str] = mapped_column(String(64), default="")
    provider: Mapped[str] = mapped_column(String(32), default="yahoo")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_update: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    data_quality: Mapped[str] = mapped_column(String(16), default="unvalidated")  # ok|stale|unavailable|unvalidated
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)

    quote: Mapped["Quote | None"] = relationship(back_populates="stock", uselist=False, cascade="all, delete-orphan")


class Quote(Base):
    __tablename__ = "quotes"
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True)
    price: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    prev_close: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    change: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    change_pct: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="")
    market_state: Mapped[str] = mapped_column(String(16), default="UNKNOWN")  # OPEN|CLOSED|UNKNOWN
    delayed: Mapped[bool] = mapped_column(Boolean, default=True)
    quote_time: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    last_poll_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)

    stock: Mapped[Stock] = relationship(back_populates="quote")


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (UniqueConstraint("stock_id", "day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date)
    close: Mapped[Decimal] = mapped_column(Money)


class Broker(Base):
    __tablename__ = "brokers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    account_ref: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str] = mapped_column(Text, default="")


class Portfolio(Base):
    __tablename__ = "portfolios"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    base_currency: Mapped[str] = mapped_column(String(8), default="USD")
    broker_id: Mapped[int | None] = mapped_column(ForeignKey("brokers.id", ondelete="SET NULL"), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


TX_TYPES = ("BUY", "SELL", "DIVIDEND", "SPLIT", "FEE", "DEPOSIT", "WITHDRAWAL", "ADJUSTMENT")


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id", ondelete="RESTRICT"), nullable=True)
    broker_id: Mapped[int | None] = mapped_column(ForeignKey("brokers.id", ondelete="SET NULL"), nullable=True)
    type: Mapped[str] = mapped_column(String(16))
    trade_date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    price: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    fees: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))
    amount: Mapped[Decimal] = mapped_column(Money, default=Decimal(0))  # dividend/fee/cash amount or adjustment cost delta
    split_ratio: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class Benchmark(Base):
    __tablename__ = "benchmarks"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    stock: Mapped[Stock] = relationship()


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | list | int | str | bool | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_uid: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    portfolio_id: Mapped[int | None] = mapped_column(ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True)
    display_config: Mapped[dict] = mapped_column(JSON, default=dict)
    firmware: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    last_fetch_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uptime_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    data_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reported: Mapped[dict] = mapped_column(JSON, default=dict)  # last heartbeat diagnostics
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    prefix: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    key_hash: Mapped[str] = mapped_column(String(128))
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    last_used_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rotated_from_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow)


class ApiAccessLog(Base):
    __tablename__ = "api_access_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True, index=True)
    ts: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(200))
    status: Mapped[int] = mapped_column(Integer)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64), default="")
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class AIProvider(Base):
    __tablename__ = "ai_providers"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # openai | deepseek | ollama
    name: Mapped[str] = mapped_column(String(100))
    base_url: Mapped[str] = mapped_column(String(255))
    model: Mapped[str] = mapped_column(String(100))
    api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    timeout_s: Mapped[int] = mapped_column(Integer, default=60)
    last_test_at: Mapped[datetime | None] = mapped_column(TZDateTime(), nullable=True)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(String(500), nullable=True)


class SimulatorState(Base):
    __tablename__ = "simulator_state"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # profile name, 'default'
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    runtime: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, onupdate=utcnow)


class SimulatorEvent(Base):
    __tablename__ = "simulator_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(TZDateTime(), default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(String(500))
