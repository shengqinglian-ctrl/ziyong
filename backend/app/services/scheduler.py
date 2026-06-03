import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.quotes import QuoteRefreshError, refresh_quotes_for_watchlist


logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
last_quote_refresh: dict[str, object] = {
    "status": "idle",
    "last_success_at": None,
    "last_failure_at": None,
    "last_error": None,
    "records": 0,
}


async def refresh_quotes_job() -> None:
    db = SessionLocal()
    try:
        snapshots = await refresh_quotes_for_watchlist(db)
        last_quote_refresh.update(
            {
                "status": "ok",
                "last_success_at": datetime.utcnow(),
                "last_error": None,
                "records": len(snapshots),
            }
        )
        if snapshots:
            logger.info("auto quote refresh stored %s snapshots", len(snapshots))
    except QuoteRefreshError as exc:
        db.rollback()
        last_quote_refresh.update({"status": "error", "last_failure_at": datetime.utcnow(), "last_error": str(exc)})
        logger.warning("auto quote refresh failed: %s", exc)
    except Exception:
        db.rollback()
        last_quote_refresh.update(
            {"status": "error", "last_failure_at": datetime.utcnow(), "last_error": "unexpected error"}
        )
        logger.exception("auto quote refresh failed unexpectedly")
    finally:
        db.close()


def start_scheduler() -> None:
    settings = get_settings()
    if not settings.auto_quote_refresh_enabled or scheduler.running:
        return
    scheduler.add_job(
        refresh_quotes_job,
        "interval",
        seconds=settings.auto_quote_refresh_seconds,
        id="quote-refresh",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.utcnow(),
    )
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def scheduler_status() -> dict[str, object]:
    settings = get_settings()
    job = scheduler.get_job("quote-refresh") if scheduler.running else None
    return {
        "enabled": settings.auto_quote_refresh_enabled,
        "running": scheduler.running,
        "interval_seconds": settings.auto_quote_refresh_seconds,
        "next_run_time": job.next_run_time if job else None,
        **last_quote_refresh,
    }
