from app.analysis.openai_analyzer import analyze_with_ai
from app.analysis.rules import should_trigger
from app.market.mock_provider import get_snapshot
from app.notify.feishu import send_feishu_card


async def analyze_symbol(symbol: str, push: bool = False) -> dict:
    snapshot = get_snapshot(symbol)
    triggered, reasons = should_trigger(snapshot)
    analysis = analyze_with_ai(snapshot, reasons)
    result = None
    if push:
        result = await send_feishu_card(snapshot, analysis, reasons or ["手动分析"])
    return {
        "snapshot": snapshot.model_dump(),
        "triggered": triggered,
        "trigger_reasons": reasons,
        "analysis": analysis.model_dump(),
        "notify_result": result,
    }


async def scan_symbol(symbol: str) -> dict:
    snapshot = get_snapshot(symbol)
    triggered, reasons = should_trigger(snapshot)
    if not triggered:
        return {"symbol": symbol, "triggered": False, "trigger_reasons": []}
    analysis = analyze_with_ai(snapshot, reasons)
    result = await send_feishu_card(snapshot, analysis, reasons)
    return {
        "symbol": symbol,
        "triggered": True,
        "trigger_reasons": reasons,
        "analysis": analysis.model_dump(),
        "notify_result": result,
    }
