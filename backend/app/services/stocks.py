import re

from sqlalchemy.orm import Session

from app.collectors.tencent_quote import TencentQuoteCollector
from app.models.domain import QuoteSnapshot
from app.models.domain import Stock, Watchlist, WatchlistItem
from app.schemas.domain import WatchlistItemIn


def normalize_stock_code(code: str) -> tuple[str, str]:
    raw = code.strip().upper()
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 6:
        raise ValueError("A 股代码必须包含 6 位数字")
    exchange = "SH" if digits.startswith(("5", "6", "9")) else "SZ"
    return f"{digits}.{exchange}", exchange


async def resolve_stock_name(code: str) -> tuple[str, dict | None]:
    result = await TencentQuoteCollector([code]).run()
    if result.ok and result.records:
        record = result.records[0]
        return record.get("name") or code, record
    return code, None


def upsert_stock(db: Session, item: WatchlistItemIn, resolved_name: str | None = None) -> Stock:
    normalized_code, exchange = normalize_stock_code(item.code)
    name = item.name or resolved_name or normalized_code
    stock = db.get(Stock, normalized_code)
    if stock is None:
        stock = Stock(code=normalized_code, name=name, exchange=exchange)
        db.add(stock)
    else:
        stock.name = name or stock.name
    return stock


async def add_stock_to_watchlist(db: Session, watchlist_id: int, item: WatchlistItemIn) -> WatchlistItem:
    watchlist = db.get(Watchlist, watchlist_id)
    if watchlist is None:
        raise ValueError("自选分组不存在")
    normalized_code, _ = normalize_stock_code(item.code)
    resolved_name, quote_record = await resolve_stock_name(normalized_code)
    stock = upsert_stock(db, item, resolved_name)
    if quote_record:
        db.add(QuoteSnapshot(**quote_record))
    existing = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.watchlist_id == watchlist_id, WatchlistItem.stock_code == stock.code)
        .one_or_none()
    )
    if existing:
        existing.focus_level = item.focus_level
        existing.cost_price = item.cost_price
        existing.stop_profit_price = item.stop_profit_price
        existing.stop_loss_price = item.stop_loss_price
        existing.note = item.note
        existing.enabled = True
        return existing
    watch_item = WatchlistItem(
        watchlist_id=watchlist_id,
        stock_code=stock.code,
        focus_level=item.focus_level,
        cost_price=item.cost_price,
        stop_profit_price=item.stop_profit_price,
        stop_loss_price=item.stop_loss_price,
        note=item.note,
    )
    db.add(watch_item)
    return watch_item
