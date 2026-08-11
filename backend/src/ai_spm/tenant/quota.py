from datetime import UTC, datetime
from uuid import UUID

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ai_spm.billing.entitlements import is_unlimited
from ai_spm.domain.models import Agent, Subscription, UsageDaily
from ai_spm.infrastructure.db.session import get_db_session
from ai_spm.tenant.context import get_tenant_context

logger = structlog.get_logger(__name__)


class QuotaExceededError(Exception):
    def __init__(self, resource: str, limit: int, current: int):
        self.resource = resource
        self.limit = limit
        self.current = current
        super().__init__(f"Quota exceeded for {resource}: {current}/{limit}")


async def get_subscription_limits(org_id: UUID) -> tuple[int, int]:
    async with get_db_session(org_id) as session:
        result = await session.execute(
            select(Subscription.max_agents, Subscription.max_prompts_per_day).where(
                Subscription.org_id == org_id
            )
        )
        row = result.one_or_none()
        if row is None:
            from ai_spm.billing.entitlements import get_plan
            from ai_spm.domain.enums import SubscriptionPlan

            defn = get_plan(SubscriptionPlan.STARTER)
            return defn.max_agents, defn.max_prompts_per_day
        return row[0], row[1]


async def check_agent_quota(org_id: UUID) -> None:
    max_agents, _ = await get_subscription_limits(org_id)
    if is_unlimited(max_agents):
        return
    async with get_db_session(org_id) as session:
        result = await session.execute(
            select(func.count()).select_from(Agent).where(Agent.org_id == org_id)
        )
        current = result.scalar_one()
        if current >= max_agents:
            raise QuotaExceededError("agents", max_agents, current)


async def check_prompt_quota(org_id: UUID) -> None:
    _, max_prompts = await get_subscription_limits(org_id)
    if is_unlimited(max_prompts):
        return
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    async with get_db_session(org_id) as session:
        result = await session.execute(
            select(UsageDaily.prompts_count).where(
                UsageDaily.org_id == org_id, UsageDaily.usage_date == today
            )
        )
        current = result.scalar_one_or_none() or 0
        if current >= max_prompts:
            raise QuotaExceededError("prompts_per_day", max_prompts, current)


async def increment_prompt_usage(org_id: UUID) -> None:
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    async with get_db_session(org_id) as session:
        result = await session.execute(
            select(UsageDaily).where(
                UsageDaily.org_id == org_id, UsageDaily.usage_date == today
            )
        )
        usage = result.scalar_one_or_none()
        if usage:
            usage.prompts_count += 1
        else:
            session.add(
                UsageDaily(org_id=org_id, usage_date=today, prompts_count=1, active_agents=0)
            )
        await session.commit()


class QuotaMiddleware(BaseHTTPMiddleware):
    """Enforce per-tenant plan limits on prompt submissions."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path == "/agent/v1/prompt" and request.method == "POST":
            ctx = get_tenant_context()
            if ctx:
                try:
                    await check_prompt_quota(ctx.org_id)
                except QuotaExceededError as exc:
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content={
                            "detail": str(exc),
                            "resource": exc.resource,
                            "limit": exc.limit,
                            "current": exc.current,
                        },
                    )
        return await call_next(request)
