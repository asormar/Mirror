"""APScheduler bootstrap.

We use AsyncIOScheduler because the FastAPI event loop is asyncio.
BlockingScheduler would freeze the whole process on every job tick.

Jobs are registered in `register_jobs` and started in the FastAPI
lifespan context (see app.main).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def build_scheduler() -> AsyncIOScheduler:
    return AsyncIOScheduler(timezone="UTC")


def register_jobs(scheduler: AsyncIOScheduler) -> None:
    from app.pipeline.jobs.detect_publications import detect_publications

    scheduler.add_job(
        _wrap(detect_publications),
        CronTrigger.from_crontab("*/15 * * * *"),
        id="detect_publications",
        name="Detect new SEC 13F-HR publications",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


def _wrap(coro_fn: Callable[..., Awaitable[Any]]) -> Callable[[], Any]:
    async def _runner() -> None:
        try:
            await coro_fn()
        except Exception:
            logger.exception("scheduled job %s failed", coro_fn.__name__)

    return _runner
