"""Subscription lifecycle, plan application, and usage snapshots."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.billing.entitlements import (
    PAST_DUE_GRACE_DAYS,
    PLAN_CATALOG,
    get_plan,
    is_unlimited,
)
from ai_spm.config import get_settings
from ai_spm.domain.enums import (
    OnboardingStep,
    OrganizationStatus,
    SubscriptionPlan,
    SubscriptionStatus,
)
from ai_spm.domain.models import Agent, Organization, Subscription, UsageDaily

logger = structlog.get_logger(__name__)
settings = get_settings()

# Statuses that unlock the full admin console (past_due has grace).
CONSOLE_ACCESS_STATUSES = frozenset(
    {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAST_DUE,
    }
)

# Agent enrollment / prompt processing require paid active (or past_due within grace).
AGENT_ACCESS_STATUSES = frozenset(
    {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.PAST_DUE,
    }
)


class SubscriptionService:
    async def get_or_create(self, session: AsyncSession, org_id: UUID) -> Subscription:
        result = await session.execute(select(Subscription).where(Subscription.org_id == org_id))
        sub = result.scalar_one_or_none()
        if sub:
            return sub
        defn = get_plan(SubscriptionPlan.STARTER)
        sub = Subscription(
            org_id=org_id,
            plan=SubscriptionPlan.STARTER,
            status=SubscriptionStatus.INCOMPLETE,
            onboarding_step=OnboardingStep.REGISTERED,
            max_agents=defn.max_agents,
            max_prompts_per_day=defn.max_prompts_per_day,
            max_prompts_per_month=defn.max_prompts_per_month,
            audit_retention_days=defn.audit_retention_days,
        )
        session.add(sub)
        await session.commit()
        # expire_on_commit=False — in-memory state is current. Avoid refresh():
        # post-commit SELECT under RLS can return 0 rows → 500 on checkout.
        return sub

    def apply_plan_limits(self, sub: Subscription, plan: SubscriptionPlan) -> None:
        defn = get_plan(plan)
        sub.plan = plan
        sub.max_agents = defn.max_agents
        sub.max_prompts_per_day = defn.max_prompts_per_day
        sub.max_prompts_per_month = defn.max_prompts_per_month
        sub.audit_retention_days = defn.audit_retention_days

    async def update_plan(
        self, session: AsyncSession, org_id: UUID, plan: SubscriptionPlan
    ) -> Subscription:
        sub = await self.get_or_create(session, org_id)
        self.apply_plan_limits(sub, plan)
        sub.status = SubscriptionStatus.ACTIVE
        sub.onboarding_step = OnboardingStep.COMPLETE
        sub.past_due_since = None
        await session.commit()
        return sub

    async def select_plan(
        self, session: AsyncSession, org_id: UUID, plan: SubscriptionPlan
    ) -> Subscription:
        """Record plan choice before checkout (Starter/Professional self-serve)."""
        if plan == SubscriptionPlan.ENTERPRISE:
            raise ValueError("Enterprise requires contact sales")
        sub = await self.get_or_create(session, org_id)
        self.apply_plan_limits(sub, plan)
        sub.onboarding_step = OnboardingStep.PLAN_SELECTED
        if sub.status not in CONSOLE_ACCESS_STATUSES:
            sub.status = SubscriptionStatus.INCOMPLETE
        await session.commit()
        return sub

    async def mark_checkout_pending(
        self, session: AsyncSession, org_id: UUID, checkout_session_id: str | None = None
    ) -> Subscription:
        sub = await self.get_or_create(session, org_id)
        sub.onboarding_step = OnboardingStep.CHECKOUT_PENDING
        if checkout_session_id:
            sub.stripe_checkout_session_id = checkout_session_id
        await session.commit()
        return sub

    async def activate_subscription(
        self,
        session: AsyncSession,
        org_id: UUID,
        plan: SubscriptionPlan | None = None,
        *,
        stripe_customer_id: str | None = None,
        stripe_subscription_id: str | None = None,
        current_period_end: datetime | None = None,
    ) -> Subscription:
        sub = await self.get_or_create(session, org_id)
        if plan:
            self.apply_plan_limits(sub, plan)
        sub.status = SubscriptionStatus.ACTIVE
        sub.onboarding_step = OnboardingStep.COMPLETE
        sub.past_due_since = None
        if stripe_customer_id:
            sub.stripe_customer_id = stripe_customer_id
        if stripe_subscription_id:
            sub.stripe_subscription_id = stripe_subscription_id
        if current_period_end:
            sub.current_period_end = current_period_end
        org_result = await session.execute(select(Organization).where(Organization.id == org_id))
        org = org_result.scalar_one_or_none()
        if org and org.status == OrganizationStatus.SUSPENDED:
            org.status = OrganizationStatus.ACTIVE
        await session.commit()
        logger.info("subscription_activated", org_id=str(org_id), plan=sub.plan.value)
        return sub

    async def mark_past_due(self, session: AsyncSession, org_id: UUID) -> Subscription:
        sub = await self.get_or_create(session, org_id)
        if sub.status != SubscriptionStatus.PAST_DUE:
            sub.status = SubscriptionStatus.PAST_DUE
            sub.past_due_since = datetime.now(UTC)
        await session.commit()
        return sub

    async def suspend_for_billing(self, session: AsyncSession, org_id: UUID) -> None:
        result = await session.execute(select(Organization).where(Organization.id == org_id))
        org = result.scalar_one_or_none()
        if org:
            org.status = OrganizationStatus.SUSPENDED
        sub = await self.get_or_create(session, org_id)
        sub.status = SubscriptionStatus.SUSPENDED
        await session.commit()
        logger.info("tenant_suspended_billing", org_id=str(org_id))

    async def cancel_subscription(self, session: AsyncSession, org_id: UUID) -> None:
        sub = await self.get_or_create(session, org_id)
        sub.status = SubscriptionStatus.CANCELED
        sub.onboarding_step = OnboardingStep.PLAN_SELECTED
        await session.commit()

    async def enforce_past_due_grace(self, session: AsyncSession, org_id: UUID) -> bool:
        """Suspend if past_due longer than grace. Returns True if still entitled."""
        sub = await self.get_or_create(session, org_id)
        if sub.status != SubscriptionStatus.PAST_DUE:
            return sub.status in CONSOLE_ACCESS_STATUSES
        since = sub.past_due_since or sub.updated_at
        if since.tzinfo is None:
            since = since.replace(tzinfo=UTC)
        if datetime.now(UTC) - since > timedelta(days=PAST_DUE_GRACE_DAYS):
            await self.suspend_for_billing(session, org_id)
            return False
        return True

    def console_access_allowed(self, sub: Subscription) -> bool:
        if sub.status == SubscriptionStatus.ACTIVE:
            return True
        if sub.status == SubscriptionStatus.PAST_DUE:
            since = sub.past_due_since or sub.updated_at
            if since and since.tzinfo is None:
                since = since.replace(tzinfo=UTC)
            if since and datetime.now(UTC) - since > timedelta(days=PAST_DUE_GRACE_DAYS):
                return False
            return True
        return False

    def agent_access_allowed(self, sub: Subscription) -> bool:
        return self.console_access_allowed(sub)

    def entitlements_payload(self, sub: Subscription) -> dict:
        defn = get_plan(sub.plan)
        return {
            "plan": sub.plan.value,
            "status": sub.status.value,
            "onboarding_step": sub.onboarding_step.value,
            "max_agents": sub.max_agents,
            "max_agents_unlimited": is_unlimited(sub.max_agents),
            "max_prompts_per_month": sub.max_prompts_per_month,
            "max_prompts_per_day": sub.max_prompts_per_day,
            "prompts_unlimited": is_unlimited(sub.max_prompts_per_month),
            "audit_retention_days": sub.audit_retention_days,
            "features": defn.feature_map(),
            "console_access": self.console_access_allowed(sub),
            "past_due_grace_days": PAST_DUE_GRACE_DAYS,
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "price_monthly_usd": defn.price_monthly_usd,
            "display_name": defn.display_name,
        }


class UsageService:
    async def get_tenant_usage(
        self, session: AsyncSession, org_id: UUID
    ) -> dict[str, int | str | bool | None]:
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = today.replace(day=1)

        agent_count = await session.scalar(
            select(func.count()).select_from(Agent).where(Agent.org_id == org_id)
        )
        usage_result = await session.execute(
            select(UsageDaily.prompts_count).where(
                UsageDaily.org_id == org_id, UsageDaily.usage_date == today
            )
        )
        prompts_today = usage_result.scalar_one_or_none() or 0

        month_prompts = await session.scalar(
            select(func.coalesce(func.sum(UsageDaily.prompts_count), 0)).where(
                UsageDaily.org_id == org_id,
                UsageDaily.usage_date >= month_start,
            )
        )

        sub_result = await session.execute(
            select(Subscription).where(Subscription.org_id == org_id)
        )
        sub = sub_result.scalar_one_or_none()
        defn = get_plan(sub.plan) if sub else get_plan(SubscriptionPlan.STARTER)

        return {
            "agent_count": agent_count or 0,
            "prompts_today": prompts_today,
            "prompts_this_month": int(month_prompts or 0),
            "max_agents": sub.max_agents if sub else defn.max_agents,
            "max_prompts_per_day": sub.max_prompts_per_day if sub else defn.max_prompts_per_day,
            "max_prompts_per_month": (
                sub.max_prompts_per_month if sub else defn.max_prompts_per_month
            ),
            "audit_retention_days": (
                sub.audit_retention_days if sub else defn.audit_retention_days
            ),
            "plan": sub.plan.value if sub else SubscriptionPlan.STARTER.value,
            "status": sub.status.value if sub else SubscriptionStatus.INCOMPLETE.value,
            "onboarding_step": (
                sub.onboarding_step.value if sub else OnboardingStep.REGISTERED.value
            ),
            "max_agents_unlimited": is_unlimited(sub.max_agents if sub else defn.max_agents),
            "prompts_unlimited": is_unlimited(
                sub.max_prompts_per_month if sub else defn.max_prompts_per_month
            ),
        }


# Re-export catalog for callers that imported PLAN_LIMITS from here
PLAN_LIMITS = {
    plan: (defn.max_agents, defn.max_prompts_per_day, defn.audit_retention_days)
    for plan, defn in PLAN_CATALOG.items()
}
