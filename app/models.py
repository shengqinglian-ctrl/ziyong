from typing import Literal
from pydantic import BaseModel, Field


class TechnicalSnapshot(BaseModel):
    trend_5d: str
    trend_20d: str
    price_vs_ma20: str
    price_vs_ma50: str
    rsi_14: float
    macd: str
    vwap_position: str


class KeyLevels(BaseModel):
    support: list[float] = Field(default_factory=list)
    resistance: list[float] = Field(default_factory=list)


class NewsItem(BaseModel):
    title: str
    time: str | None = None
    sentiment: str | None = None


class PeerMove(BaseModel):
    symbol: str
    change_pct: float


class StockSnapshot(BaseModel):
    symbol: str
    company: str
    current_price: float
    today_change_pct: float
    five_day_change_pct: float
    twenty_day_change_pct: float
    volume_vs_20d_avg: float
    sector: str
    sector_change_pct: float
    spy_change_pct: float
    qqq_change_pct: float
    technical: TechnicalSnapshot
    key_levels: KeyLevels
    recent_news: list[NewsItem] = Field(default_factory=list)
    peer_moves: list[PeerMove] = Field(default_factory=list)


class MoveExplanation(BaseModel):
    main_reason: str
    supporting_factors: list[str]
    uncertain_factors: list[str]


class RecentStatus(BaseModel):
    trend: Literal["uptrend", "downtrend", "range", "rebound", "pullback", "unclear"]
    momentum: Literal["strong", "positive", "neutral", "weak", "very_weak"]
    risk_level: Literal["low", "medium", "high"]
    summary: str


class WatchNext(BaseModel):
    support: list[float]
    resistance: list[float]
    triggers: list[str]


class StockAnalysis(BaseModel):
    symbol: str
    bias: Literal["bullish", "neutral", "bearish"]
    confidence: float = Field(ge=0, le=1)
    move_explanation: MoveExplanation
    recent_status: RecentStatus
    watch_next: WatchNext
    disclaimer: str = "仅供信息整理和研究参考，不构成投资建议。"
