from datetime import datetime, timedelta

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.collectors.eastmoney_flow import EastmoneyCapitalFlowCollector
from app.collectors.tencent_quote import TencentQuoteCollector
from app.models.domain import AlertEvent, AlertRule, CapitalFlowSnapshot, QuoteSnapshot, WatchlistItem
from app.notifications.service import send_event_notifications
from app.rules.engine import RuleEngine


SUDDEN_DAY_MOVE_THRESHOLD = 5.0
SUDDEN_REFRESH_MOVE_THRESHOLD = 1.5
SUDDEN_ALERT_COOLDOWN_SECONDS = 300

rule_engine = RuleEngine()
last_capital_flow_refresh: dict[str, object] = {
    "status": "idle",
    "last_success_at": None,
    "last_failure_at": None,
    "last_error": None,
    "records": 0,
}


class QuoteRefreshError(RuntimeError):
    pass


async def refresh_quotes_for_watchlist(db: Session) -> list[QuoteSnapshot]:
    codes = active_watchlist_codes(db)
    previous_quotes = latest_quote_map(db, codes)
    collector = TencentQuoteCollector(codes)
    result = await collector.run()
    if not result.ok:
        raise QuoteRefreshError(result.error or "真实行情源刷新失败")
    if not result.records and codes:
        raise QuoteRefreshError("真实行情源未返回有效数据")

    snapshots = [QuoteSnapshot(**row) for row in result.records]
    db.add_all(snapshots)
    db.flush()
    await refresh_capital_flow_for_codes(db, codes)
    new_events = create_alerts_for_snapshots(db, snapshots, previous_quotes)
    db.flush()
    await send_event_notifications(db, new_events)
    db.commit()
    return snapshots


async def refresh_capital_flow_for_codes(db: Session, codes: list[str]) -> list[CapitalFlowSnapshot]:
    collector = EastmoneyCapitalFlowCollector(codes)
    result = await collector.run()
    if not result.ok:
        last_capital_flow_refresh.update(
            {
                "status": "error",
                "last_failure_at": datetime.utcnow(),
                "last_error": result.error or "资金流向源连接失败或未返回有效数据",
                "records": 0,
            }
        )
        return []
    snapshots = [CapitalFlowSnapshot(**row) for row in result.records]
    db.add_all(snapshots)
    db.flush()
    last_capital_flow_refresh.update(
        {
            "status": "ok",
            "last_success_at": datetime.utcnow(),
            "last_error": None,
            "records": len(snapshots),
        }
    )
    return snapshots


def capital_flow_status() -> dict[str, object]:
    return {
        "enabled": True,
        "source": EastmoneyCapitalFlowCollector.source_name,
        **last_capital_flow_refresh,
    }


def active_watchlist_codes(db: Session) -> list[str]:
    rows = (
        db.query(WatchlistItem.stock_code)
        .filter(WatchlistItem.enabled.is_(True))
        .order_by(WatchlistItem.id)
        .all()
    )
    return [row[0] for row in rows]


def latest_quote_map(db: Session, codes: list[str]) -> dict[str, QuoteSnapshot]:
    if not codes:
        return {}
    rows = (
        db.query(QuoteSnapshot)
        .filter(QuoteSnapshot.stock_code.in_(codes))
        .order_by(QuoteSnapshot.stock_code, desc(QuoteSnapshot.quote_time))
        .all()
    )
    latest = {}
    for row in rows:
        latest.setdefault(row.stock_code, row)
    return latest


def latest_capital_flow_map(db: Session, codes: list[str]) -> dict[str, CapitalFlowSnapshot]:
    if not codes:
        return {}
    rows = (
        db.query(CapitalFlowSnapshot)
        .filter(CapitalFlowSnapshot.stock_code.in_(codes))
        .order_by(CapitalFlowSnapshot.stock_code, desc(CapitalFlowSnapshot.flow_time))
        .all()
    )
    latest = {}
    for row in rows:
        latest.setdefault(row.stock_code, row)
    return latest


def create_alerts_for_snapshots(
    db: Session,
    snapshots: list[QuoteSnapshot],
    previous_quotes: dict[str, QuoteSnapshot],
) -> list[AlertEvent]:
    rules = db.query(AlertRule).filter(AlertRule.enabled.is_(True)).all()
    new_events = []
    for snapshot in snapshots:
        previous_quote = previous_quotes.get(snapshot.stock_code)
        sudden_alert = build_sudden_move_alert(snapshot, previous_quote)
        if sudden_alert and not recent_auto_alert_exists(db, snapshot.stock_code, sudden_alert["category"]):
            event = AlertEvent(
                rule_id=None,
                stock_code=snapshot.stock_code,
                title=sudden_alert["title"],
                message=sudden_alert["message"],
                severity=sudden_alert["severity"],
                payload=sudden_alert["payload"],
            )
            db.add(event)
            new_events.append(event)
        for rule in rules:
            if rule.stock_code and rule.stock_code != snapshot.stock_code:
                continue
            decision = rule_engine.evaluate_quote(rule, snapshot, previous_quote)
            if decision.triggered:
                event = AlertEvent(
                    rule_id=rule.id,
                    stock_code=snapshot.stock_code,
                    title=decision.title,
                    message=decision.message,
                    severity=rule.severity,
                    payload=decision.payload,
                )
                db.add(event)
                new_events.append(event)
    return new_events


def recent_auto_alert_exists(db: Session, stock_code: str, category: str) -> bool:
    cutoff = datetime.utcnow() - timedelta(seconds=SUDDEN_ALERT_COOLDOWN_SECONDS)
    rows = (
        db.query(AlertEvent)
        .filter(AlertEvent.stock_code == stock_code, AlertEvent.triggered_at >= cutoff)
        .order_by(desc(AlertEvent.triggered_at))
        .limit(20)
        .all()
    )
    return any((row.payload or {}).get("category") == category for row in rows)


def build_sudden_move_alert(snapshot: QuoteSnapshot, previous_quote: QuoteSnapshot | None) -> dict | None:
    day_change = snapshot.change_percent
    refresh_change = None
    if previous_quote and previous_quote.latest_price:
        refresh_change = (snapshot.latest_price - previous_quote.latest_price) / previous_quote.latest_price * 100

    day_triggered = day_change is not None and abs(day_change) >= SUDDEN_DAY_MOVE_THRESHOLD
    refresh_triggered = refresh_change is not None and abs(refresh_change) >= SUDDEN_REFRESH_MOVE_THRESHOLD
    if day_triggered and not refresh_triggered and previous_quote and _same_sudden_day_move(snapshot, previous_quote):
        day_triggered = False
    if not day_triggered and not refresh_triggered:
        return None

    direction = "大涨" if (day_change or refresh_change or 0) > 0 else "大跌"
    category = "sudden_rise" if direction == "大涨" else "sudden_fall"
    severity = "urgent" if day_change is not None and abs(day_change) >= 5 else "important"
    analysis = rise_fall_analysis(snapshot, previous_quote)
    refresh_text = f"{refresh_change:.2f}%" if refresh_change is not None else "暂无"
    day_text = f"{day_change:.2f}%" if day_change is not None else "暂无"
    message = (
        f"股票：{snapshot.name} {snapshot.stock_code}\n"
        f"触发类型：突发{direction}\n"
        f"最新价：{snapshot.latest_price}\n"
        f"日内涨跌幅：{day_text}\n"
        f"相邻刷新变化：{refresh_text}\n"
    )
    if snapshot.turnover:
        message += f"成交额：{snapshot.turnover / 100000000:.2f} 亿\n"
    message += (
        f"更新时间：{snapshot.quote_time:%Y-%m-%d %H:%M:%S}\n"
        "\n涨跌分析：\n"
        + "\n".join(f"- {line}" for line in analysis)
        + "\n\n提示：本提醒仅基于公开行情和用户配置生成，不构成投资建议。"
    )
    return {
        "category": category,
        "title": f"突发{direction}提醒：{snapshot.name} {day_text}",
        "message": message,
        "severity": severity,
        "payload": {
            "category": category,
            "quote_id": snapshot.id,
            "day_change_percent": day_change,
            "refresh_change_percent": refresh_change,
            "thresholds": {
                "day_move": SUDDEN_DAY_MOVE_THRESHOLD,
                "refresh_move": SUDDEN_REFRESH_MOVE_THRESHOLD,
                "cooldown_seconds": SUDDEN_ALERT_COOLDOWN_SECONDS,
            },
            "analysis": analysis,
        },
    }


def _same_sudden_day_move(snapshot: QuoteSnapshot, previous_quote: QuoteSnapshot) -> bool:
    if snapshot.change_percent is None or previous_quote.change_percent is None:
        return False
    if abs(previous_quote.change_percent) < SUDDEN_DAY_MOVE_THRESHOLD:
        return False
    if (snapshot.change_percent > 0) != (previous_quote.change_percent > 0):
        return False
    return (
        abs(snapshot.latest_price - previous_quote.latest_price) <= 1e-9
        and abs(snapshot.change_percent - previous_quote.change_percent) <= 1e-9
    )


def rise_fall_analysis(quote: QuoteSnapshot | None, previous_quote: QuoteSnapshot | None = None) -> list[str]:
    if quote is None or quote.change_percent is None:
        return ["暂无最新行情，先刷新真实行情。"]

    analysis = []
    change = quote.change_percent
    direction = "上涨" if change > 0 else "下跌" if change < 0 else "持平"
    analysis.append(
        f"当前价格 {quote.latest_price:.2f}，较昨收{direction} {abs(change):.2f}%"
        + (f"（涨跌额 {quote.change_amount:.2f}）。" if quote.change_amount is not None else "。")
    )
    if change >= 5:
        analysis.append("涨幅达到强异动区间，短线资金推动明显，需关注是否能维持高位成交。")
    elif change >= 3:
        analysis.append("涨幅明显，买盘占优，但还要看收盘前是否回落以及成交额是否继续放大。")
    elif change > 0:
        analysis.append("小幅上涨，走势偏强但未形成明显异动。")
    elif change <= -5:
        analysis.append("跌幅达到强异动区间，抛压较集中，需观察是否有放量破位迹象。")
    elif change <= -3:
        analysis.append("跌幅明显，短线承压，除非后续放量修复，否则弱势可能延续。")
    elif change < 0:
        analysis.append("小幅下跌，走势偏弱但波动仍可控。")
    else:
        analysis.append("价格基本持平，方向信号不明显。")

    if quote.turnover:
        turnover_yi = quote.turnover / 100000000
        analysis.append(f"成交额 {turnover_yi:.2f} 亿。")
    if previous_quote and previous_quote.latest_price:
        refresh_move = (quote.latest_price - previous_quote.latest_price) / previous_quote.latest_price * 100
        analysis.append(f"相比上次刷新变化 {refresh_move:.2f}%。")
    return analysis
