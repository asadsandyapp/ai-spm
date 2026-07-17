"""Policy engine evaluation tests."""

import uuid

import pytest

from ai_spm.domain.enums import OrganizationStatus, SubscriptionPlan, SubscriptionStatus
from ai_spm.domain.models import Organization, Policy, Subscription
from ai_spm.infrastructure.db.session import get_platform_session
from ai_spm.services.policy_engine import PolicyEngine


@pytest.mark.asyncio
async def test_policy_blocks_disallowed_model():
    org_id = uuid.uuid4()
    async with get_platform_session() as session:
        org = Organization(
            id=org_id,
            slug="policy-test",
            name="Policy Test",
            status=OrganizationStatus.ACTIVE,
        )
        sub = Subscription(
            org_id=org_id,
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.ACTIVE,
            max_agents=10,
            max_prompts_per_day=1000,
            audit_retention_days=90,
        )
        policy = Policy(
            org_id=org_id,
            name="Restrict Models",
            rules={"models": {"allowed": ["gpt-4o-mini"]}},
            is_default=True,
            is_active=True,
        )
        session.add_all([org, sub, policy])
        await session.commit()

        engine = PolicyEngine()
        allowed, reason = await engine.evaluate(session, org_id, "openai", "gpt-4")
        assert allowed is False
        assert "gpt-4" in (reason or "")


@pytest.mark.asyncio
async def test_policy_allows_permitted_model():
    org_id = uuid.uuid4()
    async with get_platform_session() as session:
        org = Organization(
            id=org_id,
            slug="policy-allow",
            name="Policy Allow",
            status=OrganizationStatus.ACTIVE,
        )
        sub = Subscription(
            org_id=org_id,
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.ACTIVE,
            max_agents=10,
            max_prompts_per_day=1000,
            audit_retention_days=90,
        )
        policy = Policy(
            org_id=org_id,
            name="Allow Mini",
            rules={"models": {"allowed": ["gpt-4o-mini"]}},
            is_default=True,
            is_active=True,
        )
        session.add_all([org, sub, policy])
        await session.commit()

        engine = PolicyEngine()
        allowed, _ = await engine.evaluate(session, org_id, "openai", "gpt-4o-mini")
        assert allowed is True
