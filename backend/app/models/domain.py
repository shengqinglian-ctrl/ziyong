from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Stock(Base):
    __tablename__ = "stocks"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    exchange: Mapped[str] = mapped_column(String(8))
    industry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    concepts: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    items: Mapped[list["WatchlistItem"]] = relationship(cascade="all, delete-orphan")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "stock_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"))
    stock_code: Mapped[str] = mapped_column(ForeignKey("stocks.code"))
    focus_level: Mapped[str] = mapped_column(String(16), default="normal")
    cost_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_profit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    stock: Mapped[Stock] = relationship()


class QuoteSnapshot(Base):
    __tablename__ = "quote_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(ForeignKey("stocks.code"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    latest_price: Mapped[float] = mapped_column(Float)
    change_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    open_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    turnover: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_name: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[str] = mapped_column(String(16), default="medium")
    delay_status: Mapped[str] = mapped_column(String(16), default="normal")
    quote_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CapitalFlowSnapshot(Base):
    __tablename__ = "capital_flow_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_code: Mapped[str] = mapped_column(ForeignKey("stocks.code"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    main_net_inflow: Mapped[float | None] = mapped_column(Float, nullable=True)
    main_net_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    super_large_net_inflow: Mapped[float | None] = mapped_column(Float, nullable=True)
    super_large_net_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    large_net_inflow: Mapped[float | None] = mapped_column(Float, nullable=True)
    large_net_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    medium_net_inflow: Mapped[float | None] = mapped_column(Float, nullable=True)
    medium_net_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    small_net_inflow: Mapped[float | None] = mapped_column(Float, nullable=True)
    small_net_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    five_day_main_net_inflow: Mapped[float | None] = mapped_column(Float, nullable=True)
    five_day_main_net_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_name: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[str] = mapped_column(String(16), default="medium")
    flow_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    stock_code: Mapped[str | None] = mapped_column(ForeignKey("stocks.code"), nullable=True)
    rule_type: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict] = mapped_column(JSON)
    severity: Mapped[str] = mapped_column(String(16), default="normal")
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("alert_rules.id"), nullable=True)
    stock_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    send_status: Mapped[str] = mapped_column(String(16), default="pending")


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(32))
    webhook_url_masked: Mapped[str] = mapped_column(String(256))
    webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_severity: Mapped[str] = mapped_column(String(16), default="normal")


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("notification_channels.id"), index=True)
    alert_event_id: Mapped[int | None] = mapped_column(ForeignKey("alert_events.id"), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(256), index=True)
    status: Mapped[str] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class AnalysisCache(Base):
    __tablename__ = "analysis_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    stock_code: Mapped[str] = mapped_column(String(16), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class CollectorSource(Base):
    __tablename__ = "collector_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    source_type: Mapped[str] = mapped_column(String(32))
    entry_url: Mapped[str] = mapped_column(String(512))
    frequency_seconds: Mapped[int] = mapped_column(Integer, default=30)
    parser_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trust_level: Mapped[str] = mapped_column(String(16), default="medium")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class InfoItem(Base):
    __tablename__ = "info_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(256), index=True)
    source_name: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str] = mapped_column(String(512))
    published_at: Mapped[datetime]
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[str] = mapped_column(String(16), default="medium")
    importance_score: Mapped[int] = mapped_column(Integer, default=50)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    related_stocks: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
