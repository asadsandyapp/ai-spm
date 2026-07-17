from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.config import get_settings
from ai_spm.domain.enums import (
    OrganizationStatus,
    SubscriptionPlan,
    SubscriptionStatus,
)
from ai_spm.domain.models import Agent, Organization, Subscription, UsageDaily

logger = structlog.get_logger(__name__)
settings = get_settings()

PLAN_LIMITS = {
    SubscriptionPlan.FREE: (
        settings.default_free_max_agents,
        settings.default_free_max_prompts_per_day,
        90,
    ),
    SubscriptionPlan.PRO: (
        settings.default_pro_max_agents,
        settings.default_pro_max_prompts_per_day,
        365,
    ),
    SubscriptionPlan.ENTERPRISE: (
        settings.default_enterprise_max_agents,
        settings.default_enterprise_max_prompts_per_day,
        2555,
    ),
}


class SubscriptionService:
    async def get_or_create(self, session: AsyncSession, org_id: UUID) -> Subscription:
        result = await session.execute(select(Subscription).where(Subscription.org_id == org_id))
        sub = result.scalar_one_or_none()
        if sub:
            return sub
        limits = PLAN_LIMITS[SubscriptionPlan.FREE]
        sub = Subscription(
            org_id=org_id,
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.TRIALING,
            max_agents=limits[0],
            max_prompts_per_day=limits[1],
            audit_retention_days=limits[2],
        )
        session.add(sub)
        await session.commit()
        await session.refresh(sub)
        return sub

    async def update_plan(
        self, session: AsyncSession, org_id: UUID, plan: SubscriptionPlan
    ) -> Subscription:
        sub = await self.get_or_create(session, org_id)
        limits = PLAN_LIMITS[plan]
        sub.plan = plan
        sub.max_agents = limits[0]
        sub.max_prompts_per_day = limits[1]
        sub.audit_retention_days = limits[2]
        sub.status = SubscriptionStatus.ACTIVE
        await session.commit()
        await session.refresh(sub)
        return sub

    async def suspend_for_billing(self, session: AsyncSession, org_id: UUID) -> None:
        result = await session.execute(select(Organization).where(Organization.id == org_id))
        org = result.scalar_one_or_none()
        if org:
            org.status = OrganizationStatus.SUSPENDED
        sub_result = await session.execute(select(Subscription).where(Subscription.org_id == org_id))
        sub = sub_result.scalar_one_or_none()
        if sub:
            sub.status = SubscriptionStatus.SUSPENDED
        await session.commit()
        logger.info("tenant_suspended_billing", org_id=str(org_id))


class UsageService:
    async def get_tenant_usage(
        self, session: AsyncSession, org_id: UUID
    ) -> dict[str, int | str]:
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        agent_count = await session.scalar(
            select(func.count()).select_from(Agent).where(Agent.org_id == org_id)
        )
        usage_result = await session.execute(
            select(UsageDaily.prompts_count).where(
                UsageDaily.org_id == org_id, UsageDaily.usage_date == today
            )
        )
        prompts_today = usage_result.scalar_one_or_none() or 0

        sub_result = await session.execute(
            select(Subscription).where(Subscription.org_id == org_id)
        )
        sub = sub_result.scalar_one_or_none()

        return {
            "agent_count": agent_count or 0,
            "prompts_today": prompts_today,
            "max_agents": sub.max_agents if sub else settings.default_free_max_agents,
            "max_prompts_per_day": sub.max_prompts_per_day
            if sub
            else settings.default_free_max_prompts_per_day,
            "plan": sub.plan.value if sub else "free",
        }
