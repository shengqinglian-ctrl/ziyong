from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import AlertEvent, AlertRule, CapitalFlowSnapshot, CollectorSource, InfoItem, NotificationChannel, QuoteSnapshot, Watchlist, WatchlistItem
from app.notifications.providers import mask_webhook
from app.notifications.service import send_event_notifications
from app.schemas.domain import AiChatIn, AiChatOut, AlertRuleIn, AlertRuleOut, CapitalFlowOut, CollectorSourceIn, InfoItemOut, NotificationChannelIn, NotificationChannelOut, QuoteOut, WatchlistIn, WatchlistItemIn
from app.services.llm import LLMError, generate_analysis_summary_cached, generate_chat_answer, model_status
from app.services.quotes import QuoteRefreshError, active_watchlist_codes, capital_flow_status, latest_capital_flow_map, latest_quote_map, refresh_capital_flow_for_codes, refresh_quotes_for_watchlist
from app.services.scheduler import scheduler_status
from app.services.stocks import add_stock_to_watchlist, normalize_stock_code

router = APIRouter(prefix="/api")


@router.get("/system/health")
def health():
    return {"status": "ok", "service": "A-Stock Watcher", "time": datetime.utcnow()}


@router.get("/watchlists")
def list_watchlists(db: Session = Depends(get_db)):
    return db.query(Watchlist).order_by(Watchlist.id).all()


@router.post("/watchlists")
def create_watchlist(payload: WatchlistIn, db: Session = Depends(get_db)):
    watchlist = Watchlist(name=payload.name)
    db.add(watchlist)
    db.commit()
    db.refresh(watchlist)
    return watchlist


@router.post("/watchlists/{watchlist_id}/stocks")
async def add_watchlist_stock(watchlist_id: int, payload: WatchlistItemIn, db: Session = Depends(get_db)):
    try:
        item = await add_stock_to_watchlist(db, watchlist_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(item)
    return item


@router.delete("/watchlists/{watchlist_id}/stocks/{code}")
def delete_watchlist_stock(watchlist_id: int, code: str, db: Session = Depends(get_db)):
    from app.services.stocks import normalize_stock_code
    from app.models.domain import WatchlistItem

    normalized, _ = normalize_stock_code(code)
    item = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.watchlist_id == watchlist_id, WatchlistItem.stock_code == normalized)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="自选股不存在")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.get("/quotes/latest", response_model=list[QuoteOut])
def latest_quotes(db: Session = Depends(get_db)):
    watchlist_codes = _active_watchlist_codes(db)
    if not watchlist_codes:
        return []
    rows = (
        db.query(QuoteSnapshot)
        .filter(QuoteSnapshot.stock_code.in_(watchlist_codes))
        .order_by(QuoteSnapshot.stock_code, desc(QuoteSnapshot.quote_time))
        .all()
    )
    latest = {}
    history = {}
    for row in rows:
        latest.setdefault(row.stock_code, row)
        history.setdefault(row.stock_code, []).append(row)
    return list(latest.values())


@router.get("/capital-flow/latest", response_model=list[CapitalFlowOut])
def latest_capital_flow(db: Session = Depends(get_db)):
    watchlist_codes = _active_watchlist_codes(db)
    if not watchlist_codes:
        return []
    latest = latest_capital_flow_map(db, watchlist_codes)
    return [latest[code] for code in watchlist_codes if code in latest]


@router.post("/capital-flow/refresh", response_model=list[CapitalFlowOut])
async def refresh_capital_flow(db: Session = Depends(get_db)):
    watchlist_codes = _active_watchlist_codes(db)
    snapshots = await refresh_capital_flow_for_codes(db, watchlist_codes)
    db.commit()
    return snapshots


@router.get("/info/analysis")
def info_analysis(db: Session = Depends(get_db)):
    watchlist_codes = _active_watchlist_codes(db)
    if not watchlist_codes:
        return {"generated_at": datetime.utcnow(), "items": []}

    rows = (
        db.query(QuoteSnapshot)
        .filter(QuoteSnapshot.stock_code.in_(watchlist_codes))
        .order_by(QuoteSnapshot.stock_code, desc(QuoteSnapshot.quote_time))
        .all()
    )
    latest = {}
    history = {}
    for row in rows:
        latest.setdefault(row.stock_code, row)
        history.setdefault(row.stock_code, []).append(row)

    info_rows = db.query(InfoItem).order_by(desc(InfoItem.published_at)).limit(100).all()
    event_rows = db.query(AlertEvent).order_by(desc(AlertEvent.triggered_at)).limit(100).all()
    flow_map = latest_capital_flow_map(db, watchlist_codes)
    items = []
    for code in watchlist_codes:
        quote = latest.get(code)
        capital_flow = flow_map.get(code)
        related_info = [
            item for item in info_rows
            if item.related_stocks and code in item.related_stocks
        ][:5]
        related_events = [event for event in event_rows if event.stock_code == code][:5]
        change_percent = quote.change_percent if quote else None
        event_pressure = sum(1 for event in related_events if event.severity in {"important", "urgent"})
        info_pressure = sum((item.importance_score or 0) for item in related_info)
        heat_score = min(100, round(abs(change_percent or 0) * 8 + event_pressure * 20 + info_pressure / 5))
        if change_percent is None:
            stance = "缺少行情"
        elif change_percent >= 3:
            stance = "强势异动"
        elif change_percent >= 0:
            stance = "偏强"
        elif change_percent <= -3:
            stance = "弱势承压"
        else:
            stance = "偏弱"
        quote_history = history.get(code, [])
        previous_quote = quote_history[1] if len(quote_history) > 1 else None
        rise_fall_analysis = _rise_fall_analysis(quote, previous_quote)
        detailed_analysis = _detailed_analysis_sections(
            quote,
            previous_quote,
            related_info,
            related_events,
            capital_flow,
            quote_history,
        )
        drivers = []
        if quote:
            drivers.append(f"最新涨跌幅 {change_percent:.2f}%")
            if quote.turnover:
                drivers.append(f"成交额 {quote.turnover / 100000000:.2f} 亿")
        if capital_flow and capital_flow.main_net_inflow is not None:
            drivers.append(f"主力净流入 {capital_flow.main_net_inflow / 100000000:.2f} 亿")
        drivers.extend(item.title for item in related_info[:2])
        risks = []
        if event_pressure:
            risks.append(f"{event_pressure} 条重要提醒待跟踪")
        if change_percent is not None and abs(change_percent) >= 5:
            risks.append("日内波动较大")
        if not related_info:
            risks.append("暂无关联公开信息")
        item = {
            "stock_code": code,
            "name": quote.name if quote else code,
            "stance": stance,
            "heat_score": heat_score,
            "change_percent": change_percent,
            "latest_price": quote.latest_price if quote else None,
            "quote_time": quote.quote_time if quote else None,
            "rise_fall_analysis": rise_fall_analysis,
            "detailed_analysis": detailed_analysis,
            "drivers": drivers,
            "risks": risks,
            "related_info_count": len(related_info),
            "recent_event_count": len(related_events),
            "capital_flow": _capital_flow_payload(capital_flow),
        }
        item["model_summary"] = generate_analysis_summary_cached(db, item)
        items.append(item)
    db.commit()
    return {"generated_at": datetime.utcnow(), "items": items}


@router.post("/quotes/refresh", response_model=list[QuoteOut])
async def refresh_quotes(db: Session = Depends(get_db)):
    try:
        return await refresh_quotes_for_watchlist(db)
    except QuoteRefreshError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/quotes/mock-refresh", response_model=list[QuoteOut])
async def mock_refresh_quotes():
    raise HTTPException(status_code=410, detail="模拟行情已停用，请使用 /api/quotes/refresh")


@router.get("/alert-rules", response_model=list[AlertRuleOut])
def list_alert_rules(db: Session = Depends(get_db)):
    return db.query(AlertRule).order_by(AlertRule.id).all()


@router.post("/alert-rules", response_model=AlertRuleOut)
def create_alert_rule(payload: AlertRuleIn, db: Session = Depends(get_db)):
    data = payload.model_dump()
    if data.get("stock_code"):
        try:
            data["stock_code"], _ = normalize_stock_code(data["stock_code"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        data["stock_code"] = None
    rule = AlertRule(**data)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/alert-rules/{rule_id}")
def delete_alert_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="规则不存在")
    db.delete(rule)
    db.commit()
    return {"ok": True}


@router.get("/alert-events")
def list_alert_events(db: Session = Depends(get_db)):
    watchlist_codes = _active_watchlist_codes(db)
    if not watchlist_codes:
        return []
    return (
        db.query(AlertEvent)
        .filter(AlertEvent.stock_code.in_(watchlist_codes))
        .order_by(desc(AlertEvent.triggered_at))
        .limit(200)
        .all()
    )


@router.get("/collectors")
def list_collectors(db: Session = Depends(get_db)):
    return db.query(CollectorSource).order_by(CollectorSource.id).all()


@router.post("/collectors")
def create_collector(payload: CollectorSourceIn, db: Session = Depends(get_db)):
    source = CollectorSource(**payload.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get("/collectors/status")
def collectors_status(db: Session = Depends(get_db)):
    return {
        "sources": db.query(CollectorSource).count(),
        "enabled": db.query(CollectorSource).filter(CollectorSource.enabled.is_(True)).count(),
        "quote_refresh": scheduler_status(),
        "capital_flow": capital_flow_status(),
    }


@router.get("/notification-channels", response_model=list[NotificationChannelOut])
def list_notification_channels(db: Session = Depends(get_db)):
    return db.query(NotificationChannel).order_by(NotificationChannel.id).all()


@router.post("/notification-channels", response_model=NotificationChannelOut)
def create_notification_channel(payload: NotificationChannelIn, db: Session = Depends(get_db)):
    provider = payload.provider.lower()
    if provider not in {"feishu", "wecom", "wechat"}:
        raise HTTPException(status_code=400, detail="provider 仅支持 feishu / wecom / wechat")
    channel = NotificationChannel(
        name=payload.name,
        provider=provider,
        webhook_url=payload.webhook_url,
        webhook_url_masked=mask_webhook(payload.webhook_url),
        enabled=payload.enabled,
        min_severity=payload.min_severity,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@router.delete("/notification-channels/{channel_id}")
def delete_notification_channel(channel_id: int, db: Session = Depends(get_db)):
    channel = db.get(NotificationChannel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="通知通道不存在")
    db.delete(channel)
    db.commit()
    return {"ok": True}


@router.post("/notification-channels/{channel_id}/test")
async def test_notification_channel(channel_id: int, db: Session = Depends(get_db)):
    channel = db.get(NotificationChannel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="通知通道不存在")
    event = AlertEvent(
        stock_code=None,
        title="A-Stock Watcher 测试提醒",
        message="如果你收到这条消息，说明通知通道已配置成功。",
        severity=channel.min_severity,
        payload={"category": f"notification_test:{datetime.utcnow().timestamp()}"},
    )
    db.add(event)
    db.flush()
    await send_event_notifications(db, [event])
    db.commit()
    if event.send_status != "sent":
        raise HTTPException(status_code=502, detail=(event.payload or {}).get("notification_errors") or event.send_status)
    return {"ok": True, "send_status": event.send_status}


@router.get("/ai/status")
def ai_status():
    return model_status()


@router.post("/ai/chat", response_model=AiChatOut)
def ai_chat(payload: AiChatIn, db: Session = Depends(get_db)):
    status = model_status()
    provider = (payload.provider or status["provider"]).lower()
    if provider not in {"local", "github"}:
        raise HTTPException(status_code=400, detail="provider 仅支持 local / github")
    if provider == "github" and not status["github_token_configured"]:
        raise HTTPException(status_code=503, detail="GitHub Models token 未配置")
    model = (payload.model or "").strip() or (status["github_model"] if provider == "github" else status["local_model"])
    context = _ai_chat_context(db) if _question_needs_market_context(payload.question) else {}
    try:
        answer = generate_chat_answer(payload.question, context, provider=provider, model=model)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not answer:
        raise HTTPException(status_code=502, detail="AI 模型暂不可用，请检查本地模型或 GitHub Models 配置")
    return {
        "answer": answer,
        "provider": provider,
        "model": model,
        "generated_at": datetime.utcnow(),
    }


@router.get("/info", response_model=list[InfoItemOut])
def list_info(db: Session = Depends(get_db), keyword: str | None = None):
    query = db.query(InfoItem)
    if keyword:
        query = query.filter(InfoItem.title.contains(keyword))
    return query.order_by(desc(InfoItem.published_at)).limit(100).all()


def _active_watchlist_codes(db: Session) -> list[str]:
    return active_watchlist_codes(db)


def _latest_quote_map(db: Session, codes: list[str]) -> dict[str, QuoteSnapshot]:
    return latest_quote_map(db, codes)


def _ai_chat_context(db: Session) -> dict:
    watchlist_codes = _active_watchlist_codes(db)
    quote_map = _latest_quote_map(db, watchlist_codes) if watchlist_codes else {}
    flow_map = latest_capital_flow_map(db, watchlist_codes) if watchlist_codes else {}
    info_rows = db.query(InfoItem).order_by(desc(InfoItem.published_at)).limit(10).all()
    event_rows = db.query(AlertEvent).order_by(desc(AlertEvent.triggered_at)).limit(10).all()
    return {
        "watchlist": watchlist_codes,
        "quotes": [_quote_context_payload(quote_map[code]) for code in watchlist_codes if code in quote_map],
        "capital_flows": [_flow_context_payload(flow_map[code]) for code in watchlist_codes if code in flow_map],
        "recent_events": [
            {
                "stock_code": event.stock_code,
                "title": _clip_text(event.title, 120),
                "message": _clip_text(event.message, 100),
                "severity": event.severity,
                "triggered_at": event.triggered_at,
            }
            for event in event_rows
            if event.stock_code is None or event.stock_code in watchlist_codes
        ][:2],
        "recent_info": [
            {
                "title": _clip_text(item.title, 120),
                "source_name": item.source_name,
                "published_at": item.published_at,
                "summary": _clip_text(item.summary, 120),
                "event_type": item.event_type,
                "importance_score": item.importance_score,
                "related_stocks": item.related_stocks,
            }
            for item in info_rows
            if not item.related_stocks or any(code in item.related_stocks for code in watchlist_codes)
        ][:2],
    }


def _quote_context_payload(quote: QuoteSnapshot) -> dict:
    return {
        "code": quote.stock_code,
        "name": quote.name,
        "price": quote.latest_price,
        "change_percent": quote.change_percent,
        "turnover_yi": round(quote.turnover / 100000000, 2) if quote.turnover else None,
        "time": quote.quote_time,
    }


def _flow_context_payload(flow: CapitalFlowSnapshot) -> dict:
    return {
        "code": flow.stock_code,
        "name": flow.name,
        "main_net_inflow_yi": round(flow.main_net_inflow / 100000000, 2) if flow.main_net_inflow is not None else None,
        "main_net_ratio": flow.main_net_ratio,
        "time": flow.flow_time,
    }


def _clip_text(value: str | None, max_length: int) -> str | None:
    if value is None or len(value) <= max_length:
        return value
    return value[:max_length] + "..."


def _question_needs_market_context(question: str) -> bool:
    keywords = {
        "股票", "自选", "行情", "涨", "跌", "资金", "流入", "流出", "提醒", "风险",
        "走势", "价格", "成交", "仓位", "600", "601", "000", "002", "300", "688",
    }
    return any(keyword in question for keyword in keywords)


def _rise_fall_analysis(quote: QuoteSnapshot | None, previous_quote: QuoteSnapshot | None = None) -> list[str]:
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
        if quote.name.startswith("ST"):
            analysis.append("涨幅接近 ST 股票常见日涨幅上限，短线情绪很热，追高风险同步升高。")
        else:
            analysis.append("涨幅达到强异动区间，短线资金推动明显，需关注是否能维持高位成交。")
    elif change >= 3:
        analysis.append("涨幅明显，买盘占优，但还要看收盘前是否回落以及成交额是否继续放大。")
    elif change > 0:
        analysis.append("小幅上涨，走势偏强但未形成明显异动，更像常规反弹或温和上行。")
    elif change <= -5:
        if quote.name.startswith("ST"):
            analysis.append("跌幅接近 ST 股票常见日跌幅下限，抛压集中，流动性和情绪风险都偏高。")
        else:
            analysis.append("跌幅达到强异动区间，抛压较集中，需观察是否有放量破位迹象。")
    elif change <= -3:
        analysis.append("跌幅明显，短线承压，除非后续放量修复，否则弱势可能延续。")
    elif change < 0:
        analysis.append("小幅下跌，走势偏弱但波动仍可控，暂未形成明显恐慌。")
    else:
        analysis.append("价格基本持平，方向信号不明显。")

    if quote.open_price is not None and quote.latest_price is not None:
        open_gap = (quote.latest_price - quote.open_price) / quote.open_price * 100
        if open_gap > 1:
            analysis.append(f"相对开盘价上涨 {open_gap:.2f}%，盘中承接较强。")
        elif open_gap < -1:
            analysis.append(f"相对开盘价回落 {abs(open_gap):.2f}%，盘中卖压占优。")
        else:
            analysis.append(f"相对开盘价变化 {open_gap:.2f}%，盘中方向变化不大。")

    if quote.high_price is not None and quote.low_price is not None and quote.latest_price:
        intraday_range = (quote.high_price - quote.low_price) / quote.latest_price * 100
        if quote.high_price > quote.low_price:
            close_position = (quote.latest_price - quote.low_price) / (quote.high_price - quote.low_price) * 100
            if close_position >= 80:
                analysis.append(f"现价处于日内高低区间的 {close_position:.0f}% 位置，接近高位，说明尾盘/当前价格保持强势。")
            elif close_position <= 20:
                analysis.append(f"现价处于日内高低区间的 {close_position:.0f}% 位置，接近低位，说明反弹力度不足。")
            else:
                analysis.append(f"现价处于日内高低区间的 {close_position:.0f}% 位置，处在中部区域，方向仍需确认。")
        if intraday_range >= 8:
            analysis.append(f"日内振幅约 {intraday_range:.2f}%，波动很高，适合重点盯防回撤。")
        elif intraday_range >= 4:
            analysis.append(f"日内振幅约 {intraday_range:.2f}%，波动偏高，价格分歧较明显。")
        else:
            analysis.append(f"日内振幅约 {intraday_range:.2f}%，波动相对温和。")

    if quote.turnover:
        turnover_yi = quote.turnover / 100000000
        if turnover_yi >= 10:
            analysis.append(f"成交额 {turnover_yi:.2f} 亿，资金参与度高，行情有效性较强。")
        elif turnover_yi >= 3:
            analysis.append(f"成交额 {turnover_yi:.2f} 亿，资金活跃度中等，仍需结合后续放量确认。")
        else:
            analysis.append(f"成交额 {turnover_yi:.2f} 亿，资金活跃度有限，价格信号可信度要打折。")

    if previous_quote and previous_quote.latest_price:
        refresh_move = (quote.latest_price - previous_quote.latest_price) / previous_quote.latest_price * 100
        if refresh_move > 0.5:
            analysis.append(f"相比上次刷新上涨 {refresh_move:.2f}%，短周期仍在走强。")
        elif refresh_move < -0.5:
            analysis.append(f"相比上次刷新回落 {abs(refresh_move):.2f}%，短周期有降温迹象。")
        else:
            analysis.append(f"相比上次刷新变化 {refresh_move:.2f}%，短周期价格基本稳定。")

    if quote.latest_price and quote.previous_close:
        if quote.latest_price >= quote.previous_close:
            analysis.append("现价位于昨收上方，日内偏多。")
        else:
            analysis.append("现价位于昨收下方，日内偏空。")

    if change >= 5:
        analysis.append("后续重点看能否维持高位成交；若成交萎缩且价格脱离高位，容易出现冲高回落。")
    elif change <= -5:
        analysis.append("后续重点看是否出现放量止跌；若继续放量下行，弱势风险仍未释放。")
    elif abs(change) >= 3:
        analysis.append("后续重点看涨跌幅是否继续扩大，以及价格能否站稳日内区间中上部。")
    else:
        analysis.append("后续重点看是否放量突破当前震荡区间，否则信号强度有限。")
    return analysis


def _detailed_analysis_sections(
    quote: QuoteSnapshot | None,
    previous_quote: QuoteSnapshot | None,
    related_info: list[InfoItem],
    related_events: list[AlertEvent],
    capital_flow: CapitalFlowSnapshot | None,
    quote_history: list[QuoteSnapshot] | None = None,
) -> list[dict[str, list[str] | str]]:
    if quote is None:
        return [
            {
                "title": "行情概况",
                "items": ["暂无最新行情。请先刷新真实行情。"],
            }
        ]

    change = quote.change_percent
    turnover_yi = quote.turnover / 100000000 if quote.turnover else None
    volume_wan = quote.volume / 10000 if quote.volume else None
    intraday_range = None
    close_position = None
    if quote.high_price is not None and quote.low_price is not None and quote.latest_price:
        intraday_range = (quote.high_price - quote.low_price) / quote.latest_price * 100
        if quote.high_price > quote.low_price:
            close_position = (quote.latest_price - quote.low_price) / (quote.high_price - quote.low_price) * 100

    refresh_change = None
    if previous_quote and previous_quote.latest_price:
        refresh_change = (quote.latest_price - previous_quote.latest_price) / previous_quote.latest_price * 100
    history_rows = quote_history or [quote]

    sections = [
        {
            "title": "行情概况",
            "items": [
                f"股价：{quote.latest_price:.2f} 元"
                + (f"（{quote.change_amount:+.2f} 元，{change:+.2f}%）。" if quote.change_amount is not None and change is not None else "。"),
                f"成交：{volume_wan:.1f} 万手，金额 {turnover_yi:.2f} 亿元。" if volume_wan is not None and turnover_yi is not None else "成交量或成交额数据暂缺。",
                f"走势：日内最高 {quote.high_price:.2f} 元、最低 {quote.low_price:.2f} 元，振幅约 {intraday_range:.2f}%。" if intraday_range is not None else "走势：日内高低价数据暂缺。",
                f"位置：现价处于日内高低区间约 {close_position:.0f}% 位置，{'接近高位，短线承接较强' if close_position is not None and close_position >= 80 else '接近低位，反弹力度偏弱' if close_position is not None and close_position <= 20 else '处于中部区域，方向仍需确认'}。" if close_position is not None else "位置：暂无法判断日内区间位置。",
            ],
        },
        {
            "title": "资金与量能",
            "items": [
                f"成交额 {turnover_yi:.2f} 亿元，{'资金参与度较高' if turnover_yi is not None and turnover_yi >= 10 else '资金活跃度中等' if turnover_yi is not None and turnover_yi >= 3 else '资金活跃度有限'}。" if turnover_yi is not None else "成交额数据暂缺，无法评估资金活跃度。",
                *_capital_flow_items(capital_flow),
                f"相比上次刷新价格变化 {refresh_change:+.2f}%，{'短周期仍在走强' if refresh_change is not None and refresh_change > 0.5 else '短周期有降温迹象' if refresh_change is not None and refresh_change < -0.5 else '短周期价格基本稳定'}。" if refresh_change is not None else "暂无上一条可比行情，短周期变化待下一次刷新确认。",
                *_volume_turnover_items(quote, history_rows),
            ],
        },
        {
            "title": "短线结构",
            "items": _short_term_structure_items(quote, history_rows, close_position),
        },
        {
            "title": "信息面",
            "items": (
                [
                    f"{item.published_at:%m-%d %H:%M} | 重要性 {item.importance_score} | {item.title}"
                    + (f"：{item.summary}" if item.summary else "")
                    for item in related_info[:5]
                ]
                if related_info
                else ["信息中心暂无该股关联公告/新闻；若需要公告驱动分析，需要接入公告或新闻采集源。"]
            ),
        },
        {
            "title": "提醒脉络",
            "items": _event_context_items(related_events),
        },
        {
            "title": "综合判断",
            "items": _judgement_items(quote, turnover_yi, close_position, related_events),
        },
        {
            "title": "风险与观察重点",
            "items": _watch_items(quote, turnover_yi, close_position, related_events),
        },
    ]
    return sections


def _capital_flow_items(capital_flow: CapitalFlowSnapshot | None) -> list[str]:
    if capital_flow is None:
        return ["资金流向数据暂缺；自动采集会在资金源可用时补充主力、超大单、大单等净流入。"]
    if capital_flow.main_net_inflow is None:
        return ["资金流向源暂未返回主力净流入，先以成交额和价格位置判断量价状态。"]

    main_yi = capital_flow.main_net_inflow / 100000000
    direction = "净流入" if capital_flow.main_net_inflow >= 0 else "净流出"
    items = [
        f"主力资金{direction} {abs(main_yi):.2f} 亿元"
        + (f"，净占比 {capital_flow.main_net_ratio:.2f}%。" if capital_flow.main_net_ratio is not None else "。")
    ]
    if capital_flow.super_large_net_inflow is not None or capital_flow.large_net_inflow is not None:
        super_yi = capital_flow.super_large_net_inflow / 100000000 if capital_flow.super_large_net_inflow is not None else None
        large_yi = capital_flow.large_net_inflow / 100000000 if capital_flow.large_net_inflow is not None else None
        items.append(
            "大单拆分："
            + (f"超大单 {super_yi:+.2f} 亿" if super_yi is not None else "超大单暂缺")
            + "，"
            + (f"大单 {large_yi:+.2f} 亿。" if large_yi is not None else "大单暂缺。")
        )
    if capital_flow.five_day_main_net_inflow is not None:
        items.append(
            f"近 5 日主力净流入 {capital_flow.five_day_main_net_inflow / 100000000:+.2f} 亿元"
            + (f"，净占比 {capital_flow.five_day_main_net_ratio:.2f}%。" if capital_flow.five_day_main_net_ratio is not None else "。")
        )
    return items


def _volume_turnover_items(quote: QuoteSnapshot, history_rows: list[QuoteSnapshot]) -> list[str]:
    previous_rows = [row for row in history_rows[1:6] if row.turnover]
    if not quote.turnover or not previous_rows:
        return ["量能对比：历史成交额样本不足，暂不能判断本次刷新是否明显放量。"]
    previous_avg = sum(row.turnover or 0 for row in previous_rows) / len(previous_rows)
    if previous_avg <= 0:
        return ["量能对比：历史成交额基数异常，暂不能判断放量/缩量。"]
    ratio = quote.turnover / previous_avg
    if ratio >= 1.5:
        verdict = "明显放量，价格信号可信度提高，但也要防范放量冲高后的分歧。"
    elif ratio >= 1.1:
        verdict = "温和放量，说明关注度有所提升。"
    elif ratio <= 0.7:
        verdict = "缩量，说明当前价格变化缺少持续资金确认。"
    else:
        verdict = "量能接近近期均值，暂未出现明显增量资金。"
    return [f"量能对比：当前成交额约为近 {len(previous_rows)} 次刷新均值的 {ratio:.2f} 倍，{verdict}"]


def _short_term_structure_items(
    quote: QuoteSnapshot,
    history_rows: list[QuoteSnapshot],
    close_position: float | None,
) -> list[str]:
    rows = [row for row in history_rows[:6] if row.latest_price is not None]
    items = []
    if len(rows) >= 2 and rows[-1].latest_price:
        first = rows[-1]
        latest = rows[0]
        window_change = (latest.latest_price - first.latest_price) / first.latest_price * 100
        up_steps = sum(1 for prev, curr in zip(rows[1:], rows[:-1]) if curr.latest_price > prev.latest_price)
        down_steps = sum(1 for prev, curr in zip(rows[1:], rows[:-1]) if curr.latest_price < prev.latest_price)
        items.append(
            f"近 {len(rows)} 次刷新累计变化 {window_change:+.2f}%，上涨刷新 {up_steps} 次、下跌刷新 {down_steps} 次。"
        )
        if up_steps >= len(rows) - 2 and window_change > 0:
            items.append("短周期呈连续抬升，强度优于单次脉冲。")
        elif down_steps >= len(rows) - 2 and window_change < 0:
            items.append("短周期连续走低，说明抛压尚未缓解。")
        elif abs(window_change) < 0.5:
            items.append("短周期横向震荡，方向信号还不够强。")
        else:
            items.append("短周期有来回拉扯，需结合下一次刷新确认方向。")
    else:
        items.append("短线结构：历史快照不足，至少需要两次刷新后才能判断连续性。")

    if quote.high_price is not None and quote.low_price is not None:
        items.append(
            f"日内参考区间 {quote.low_price:.2f}-{quote.high_price:.2f} 元；"
            + (
                "现价贴近上沿，若回落幅度小，说明高位承接较好。"
                if close_position is not None and close_position >= 80
                else "现价贴近下沿，若不能快速收回中位，弱势信号会延续。"
                if close_position is not None and close_position <= 20
                else "现价位于区间中部，上下沿都可能形成短线观察位。"
            )
        )
    return items


def _event_context_items(related_events: list[AlertEvent]) -> list[str]:
    if not related_events:
        return ["最近没有规则或突发提醒，当前分析主要依赖行情和资金数据。"]
    items = []
    for event in related_events[:5]:
        payload = event.payload or {}
        category = payload.get("category") or (f"规则 {event.rule_id}" if event.rule_id else "系统提醒")
        items.append(
            f"{event.triggered_at:%m-%d %H:%M} | {event.severity} | {category} | {event.title} | 发送状态：{event.send_status}"
        )
    return items


def _capital_flow_payload(capital_flow: CapitalFlowSnapshot | None) -> dict | None:
    if capital_flow is None:
        return None
    return {
        "stock_code": capital_flow.stock_code,
        "main_net_inflow": capital_flow.main_net_inflow,
        "main_net_ratio": capital_flow.main_net_ratio,
        "super_large_net_inflow": capital_flow.super_large_net_inflow,
        "large_net_inflow": capital_flow.large_net_inflow,
        "medium_net_inflow": capital_flow.medium_net_inflow,
        "small_net_inflow": capital_flow.small_net_inflow,
        "five_day_main_net_inflow": capital_flow.five_day_main_net_inflow,
        "flow_time": capital_flow.flow_time,
    }


def _judgement_items(
    quote: QuoteSnapshot,
    turnover_yi: float | None,
    close_position: float | None,
    related_events: list[AlertEvent],
) -> list[str]:
    change = quote.change_percent or 0
    items = []
    if change >= 5:
        items.append("短线属于强势异动：价格涨幅大、情绪热度高，但追高风险也同步上升。")
    elif change >= 3:
        items.append("短线明显偏强：买盘占优，但需要成交额和高位承接继续配合。")
    elif change > 0:
        items.append("走势温和偏强：尚未形成强异动，更多是常规反弹或震荡上行。")
    elif change <= -5:
        items.append("短线属于弱势异动：抛压较集中，优先观察是否放量止跌。")
    elif change < 0:
        items.append("走势偏弱：暂未出现明显修复信号。")
    else:
        items.append("价格基本持平，方向信号暂不明确。")

    if turnover_yi is not None and turnover_yi >= 3 and close_position is not None and close_position >= 80:
        items.append("成交活跃且价格维持日内高位，说明当前承接较强。")
    elif close_position is not None and close_position <= 20:
        items.append("价格接近日内低位，说明盘中反弹力度不足。")

    if related_events:
        items.append(f"近期开启了 {len(related_events)} 条相关提醒，说明该股已进入重点监控状态。")
    return items


def _watch_items(
    quote: QuoteSnapshot,
    turnover_yi: float | None,
    close_position: float | None,
    related_events: list[AlertEvent],
) -> list[str]:
    change = quote.change_percent or 0
    items = [
        "本系统只做行情和公开信息监控，不给出买卖指令。",
    ]
    if abs(change) >= 5:
        items.append("重点观察后续是否继续维持高位成交；若成交萎缩且价格脱离高位，容易冲高回落。")
    elif abs(change) >= 3:
        items.append("重点观察涨跌幅是否继续扩大，以及价格能否站稳日内区间中上部。")
    else:
        items.append("重点观察是否放量突破当前震荡区间，否则信号强度有限。")

    if quote.name.startswith("ST"):
        items.append("该股带 ST 标识，波动和退市/治理相关风险通常更高，需要更严格控制风险暴露。")
    if turnover_yi is not None and turnover_yi < 3:
        items.append("成交额不高时，单次价格波动的可靠性要打折。")
    if close_position is not None and close_position >= 80:
        items.append("若下一次刷新仍维持高位，可视为强势延续；若跌回区间中部，说明短线分歧加大。")
    if related_events:
        items.append("已有突发提醒时，应优先查看提醒详情中的触发原因和冷却阈值。")
    return items


@router.post("/info/{info_id}/mark-read")
def mark_info_read(info_id: int, db: Session = Depends(get_db)):
    item = db.get(InfoItem, info_id)
    if item is None:
        raise HTTPException(status_code=404, detail="信息不存在")
    item.is_read = True
    db.commit()
    return {"ok": True}


@router.post("/info/{info_id}/favorite")
def favorite_info(info_id: int, db: Session = Depends(get_db)):
    item = db.get(InfoItem, info_id)
    if item is None:
        raise HTTPException(status_code=404, detail="信息不存在")
    item.is_favorite = True
    db.commit()
    return {"ok": True}
