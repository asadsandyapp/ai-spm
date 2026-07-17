"""Background jobs: agent offline detection, security score refresh."""

from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ai_spm.infrastructure.db.session import get_platform_session
from ai_spm.services.prompt_pipeline import AgentService

logger = structlog.get_logger(__name__)
scheduler = AsyncIOScheduler()
agent_service = AgentService()


async def agent_offline_detector() -> None:
    async with get_platform_session() as session:
        count = await agent_service.mark_offline_stale(session, threshold_seconds=120)
        if count:
            logger.info("agents_marked_offline", count=count)


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(
        agent_offline_detector,
        "interval",
        minutes=2,
        id="agent_offline_detector",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("background_scheduler_started")


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("background_scheduler_stopped")
