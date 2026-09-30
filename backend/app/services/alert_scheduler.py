"""Background automated scheduler executing periodic safety sweeps."""

import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database.session import get_session_factory
from app.services import alert_service

logger = logging.getLogger("childtrack.alert_scheduler")

_scheduler: AsyncIOScheduler | None = None
_is_running: bool = False


async def _scheduled_safety_sweep_task() -> None:
    """Async worker job executed periodically by the scheduler."""
    session_factory = get_session_factory()
    try:
        async with session_factory() as db:
            await alert_service.run_safety_checks_sweep(db)
    except Exception as exc:
        logger.error("Error during scheduled background safety sweep: %s", exc, exc_info=True)


def start_alert_scheduler(interval_seconds: int = 30) -> None:
    """Start the APScheduler background worker if not already active."""
    global _scheduler, _is_running
    if _is_running and _scheduler is not None:
        return

    try:
        _scheduler = AsyncIOScheduler()
        _scheduler.add_job(
            _scheduled_safety_sweep_task,
            "interval",
            seconds=interval_seconds,
            id="periodic_safety_sweep",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        _scheduler.start()
        _is_running = True
        logger.info("Safety alert background scheduler started (interval=%ds)", interval_seconds)
    except Exception as exc:
        logger.error("Failed to start safety alert scheduler: %s", exc, exc_info=True)


def stop_alert_scheduler() -> None:
    """Gracefully shutdown the background alert scheduler."""
    global _scheduler, _is_running
    if _scheduler is not None and _is_running:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("Safety alert background scheduler stopped.")
        except Exception as exc:
            logger.warning("Error stopping safety alert scheduler: %s", exc)
        finally:
            _scheduler = None
            _is_running = False


async def trigger_immediate_sweep() -> dict[str, Any]:
    """Manually trigger an immediate safety sweep on-demand."""
    session_factory = get_session_factory()
    async with session_factory() as db:
        return await alert_service.run_safety_checks_sweep(db)
