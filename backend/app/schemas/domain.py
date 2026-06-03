from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StockIn(BaseModel):
    code: str
    name: str
    industry: str | None = None
    concepts: list[str] | None = None


class StockOut(StockIn):
    exchange: str

    class Config:
        from_attributes = True


class WatchlistIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class WatchlistItemIn(BaseModel):
    code: str
    name: str | None = None
    focus_level: str = "normal"
    cost_price: float | None = None
    stop_profit_price: float | None = None
    stop_loss_price: float | None = None
    note: str | None = None


class QuoteOut(BaseModel):
    stock_code: str
    name: str
    latest_price: float
    change_percent: float | None
    volume: float | None
    turnover: float | None
    source_name: str
    delay_status: str
    confidence: str
    quote_time: datetime

    class Config:
        from_attributes = True


class CapitalFlowOut(BaseModel):
    stock_code: str
    name: str
    main_net_inflow: float | None
    main_net_ratio: float | None
    super_large_net_inflow: float | None
    super_large_net_ratio: float | None
    large_net_inflow: float | None
    large_net_ratio: float | None
    medium_net_inflow: float | None
    medium_net_ratio: float | None
    small_net_inflow: float | None
    small_net_ratio: float | None
    five_day_main_net_inflow: float | None
    five_day_main_net_ratio: float | None
    source_name: str
    confidence: str
    flow_time: datetime

    class Config:
        from_attributes = True


class AlertRuleIn(BaseModel):
    name: str
    stock_code: str | None = None
    rule_type: str
    params: dict[str, Any]
    severity: str = "normal"
    cooldown_seconds: int = 300
    enabled: bool = True


class AlertRuleOut(AlertRuleIn):
    id: int

    class Config:
        from_attributes = True


class CollectorSourceIn(BaseModel):
    name: str
    source_type: str
    entry_url: str
    frequency_seconds: int = 30
    parser_config: dict[str, Any] | None = None
    trust_level: str = "medium"
    enabled: bool = True


class NotificationChannelIn(BaseModel):
    name: str
    provider: str
    webhook_url: str
    enabled: bool = True
    min_severity: str = "normal"


class NotificationChannelOut(BaseModel):
    id: int
    name: str
    provider: str
    webhook_url_masked: str
    enabled: bool
    min_severity: str

    class Config:
        from_attributes = True


class InfoItemOut(BaseModel):
    id: int
    title: str
    source_name: str
    source_url: str
    published_at: datetime
    summary: str | None
    event_type: str | None
    confidence: str
    importance_score: int
    tags: list[str] | None
    related_stocks: list[str] | None
    is_read: bool
    is_favorite: bool

    class Config:
        from_attributes = True


class AiChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    provider: str | None = None
    model: str | None = Field(default=None, max_length=120)


class AiChatOut(BaseModel):
    answer: str
    provider: str
    model: str
    generated_at: datetime
