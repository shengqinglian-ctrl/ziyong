from fastapi import FastAPI
from app.analysis.local_fallback import local_analysis
from app.config import settings
from app.market.mock_provider import get_snapshot
from app.notify.feishu import send_feishu_card
from app.scheduler import start_scheduler
from app.services import analyze_symbol, scan_symbol


app = FastAPI(
    title="Stock AI Feishu MVP",
    description="股票异动归因、近期状态分析、飞书机器人推送 MVP",
    version="0.1.0",
)


@app.on_event("startup")
async def on_startup():
    start_scheduler()


@app.get("/")
async def root():
    return {
        "name": "Stock AI Feishu MVP",
        "watchlist": settings.symbols,
        "openai_enabled": settings.enable_openai_analysis,
        "feishu_enabled": settings.enable_feishu_push,
    }


@app.get("/snapshot/{symbol}")
async def snapshot(symbol: str):
    return get_snapshot(symbol).model_dump()


@app.post("/analyze/{symbol}")
async def analyze(symbol: str, push: bool = False):
    return await analyze_symbol(symbol, push=push)


@app.post("/scan/{symbol}")
async def scan(symbol: str):
    return await scan_symbol(symbol)


@app.post("/scan")
async def scan_all():
    results = []
    for symbol in settings.symbols:
        results.append(await scan_symbol(symbol))
    return {"results": results}


@app.post("/notify/test")
async def notify_test():
    snapshot = get_snapshot("NVDA")
    analysis = local_analysis(snapshot, ["测试飞书机器人推送"])
    result = await send_feishu_card(snapshot, analysis, ["测试飞书机器人推送"])
    return {"notify_result": result}
