"""Checkout access gate + entitlements + max_agents enforcement."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from ai_spm.billing.entitlements import FEATURE_THREAT_DETECTION, get_plan, has_feature
from ai_spm.domain.enums import (
    OnboardingStep,
    OrganizationStatus,
    SubscriptionPlan,
    SubscriptionStatus,
    UserRole,
)
from ai_spm.domain.models import Organization, Subscription, User
from ai_spm.infrastructure.auth.password import create_admin_access_token, hash_password, hash_token
from ai_spm.infrastructure.db.session import get_platform_session
from ai_spm.main import create_app


@pytest.mark.asyncio
async def test_plan_catalog_agents_and_threat_feature():
    starter = get_plan(SubscriptionPlan.STARTER)
    pro = get_plan(SubscriptionPlan.PROFESSIONAL)
    ent = get_plan(SubscriptionPlan.ENTERPRISE)
    assert starter.max_agents == 25
    assert pro.max_agents == 150
    assert ent.max_agents == 0
    assert not has_feature(SubscriptionPlan.STARTER, FEATURE_THREAT_DETECTION)
    assert has_feature(SubscriptionPlan.PROFESSIONAL, FEATURE_THREAT_DETECTION)
    assert has_feature(SubscriptionPlan.ENTERPRISE, FEATURE_THREAT_DETECTION)
    assert starter.audit_retention_days == 7
    assert pro.audit_retention_days == 30
    assert ent.audit_retention_days == 365


@pytest.mark.asyncio
async def test_unpaid_org_blocked_from_dashboard_even_after_relogin(engine):
    """Hard gate: incomplete subscription cannot open console APIs; me still works."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    async with get_platform_session() as session:
        org = Organization(
            id=org_id,
            slug="gated-corp",
            name="Gated Corp",
            org_token_hash=hash_token("gated-org-token-secret-key-32chars-xx"),
            status=OrganizationStatus.ACTIVE,
        )
        user = User(
            id=user_id,
            org_id=org_id,
            email="admin@gated.com",
            password_hash=hash_password("GatedAdmin123!"),
            full_name="Gated Admin",
            role=UserRole.SUPER_ADMIN,
            email_verified=True,
        )
        sub = Subscription(
            org_id=org_id,
            plan=SubscriptionPlan.STARTER,
            status=SubscriptionStatus.INCOMPLETE,
            onboarding_step=OnboardingStep.EMAIL_VERIFIED,
            max_agents=25,
            max_prompts_per_day=1667,
            max_prompts_per_month=50_000,
            audit_retention_days=7,
        )
        session.add_all([org, user, sub])
        await session.commit()

    token = create_admin_access_token(str(user_id), str(org_id), UserRole.SUPER_ADMIN.value)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        me = await client.get(
            "/admin/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me.status_code == 200
        body = me.json()
        assert body["console_access"] is False
        assert body["subscription_status"] == "incomplete"

        dash = await client.get(
            "/admin/v1/dashboard/metrics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert dash.status_code == 402
        assert dash.json()["code"] == "checkout_required"

        # Relogin still gated
        login = await client.post(
            "/admin/v1/auth/login",
            json={"email": "admin@gated.com", "password": "GatedAdmin123!"},
        )
        assert login.status_code == 200
        token2 = login.json()["access_token"]
        dash2 = await client.get(
            "/admin/v1/dashboard/metrics",
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert dash2.status_code == 402


@pytest.mark.asyncio
async def test_dev_activate_unlocks_console(engine):
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    async with get_platform_session() as session:
        session.add_all(
            [
                Organization(
                    id=org_id,
                    slug="pay-corp",
                    name="Pay Corp",
                    org_token_hash=hash_token("pay-org-token-secret-key-32chars-xxx"),
                    status=OrganizationStatus.ACTIVE,
                ),
                User(
                    id=user_id,
                    org_id=org_id,
                    email="admin@pay.com",
                    password_hash=hash_password("PayAdmin12345!"),
                    full_name="Pay Admin",
                    role=UserRole.SUPER_ADMIN,
                    email_verified=True,
                ),
                Subscription(
                    org_id=org_id,
                    plan=SubscriptionPlan.STARTER,
                    status=SubscriptionStatus.INCOMPLETE,
                    onboarding_step=OnboardingStep.PLAN_SELECTED,
                    max_agents=25,
                    max_prompts_per_day=1667,
                    max_prompts_per_month=50_000,
                    audit_retention_days=7,
                ),
            ]
        )
        await session.commit()

    token = create_admin_access_token(str(user_id), str(org_id), UserRole.SUPER_ADMIN.value)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        act = await client.post(
            "/admin/v1/billing/dev-activate",
            headers={"Authorization": f"Bearer {token}"},
            json={"plan": "professional"},
        )
        assert act.status_code == 200
        assert act.json()["console_access"] is True
        assert act.json()["features"]["threat_detection"] is True

        dash = await client.get(
            "/admin/v1/dashboard/metrics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert dash.status_code == 200


@pytest.mark.asyncio
async def test_agent_register_blocked_without_subscription(engine, tenant_a):
    """Unpaid org: mutate tenant_a sub to incomplete and block register."""
    async with get_platform_session() as session:
        from sqlalchemy import select

        sub = (
            await session.execute(
                select(Subscription).where(Subscription.org_id == tenant_a["org"].id)
            )
        ).scalar_one()
        sub.status = SubscriptionStatus.INCOMPLETE
        sub.onboarding_step = OnboardingStep.EMAIL_VERIFIED
        await session.commit()

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/agent/v1/register",
            headers={
                "X-Org-ID": str(tenant_a["org"].id),
                "X-Agent-ID": str(uuid.uuid4()),
            },
            json={
                "hostname": "new-host-01",
                "org_token": tenant_a["org_token"],
                "os_version": "linux",
                "agent_version": "0.1.0",
            },
        )
        assert res.status_code == 402
