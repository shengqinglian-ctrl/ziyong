import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import settings
from app.services import scan_symbol


scheduler = AsyncIOScheduler()


async def scan_watchlist() -> None:
    for symbol in settings.symbols:
        try:
            await scan_symbol(symbol)
        except Exception as exc:
            print(f"[scanner] {symbol} failed: {exc}")


def start_scheduler() -> None:
    scheduler.add_job(
        lambda: asyncio.create_task(scan_watchlist()),
        "interval",
        seconds=settings.scan_interval_seconds,
        id="watchlist_scanner",
        replace_existing=True,
    )
    scheduler.start()
