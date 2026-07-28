"""Seed a ready-to-use development tenant with a known org token.

Creates (idempotently) an ACTIVE organization, a verified super-admin user,
a FREE subscription, a default department, and a default security policy.
Prints the org_id and org_token needed to run the endpoint agent.

Usage:
    python scripts/seed_dev_tenant.py
"""

import asyncio
import uuid

from sqlalchemy import select

from ai_spm.domain.enums import (
    OrganizationStatus,
    SubscriptionPlan,
    SubscriptionStatus,
    UserRole,
)
from ai_spm.domain.models import Department, Organization, Policy, Subscription, User
from ai_spm.infrastructure.auth.password import hash_password, hash_token
from ai_spm.infrastructure.db.session import get_platform_session

# Fixed dev values (NOT for production).
DEV_SLUG = "dev-corp"
DEV_ADMIN_EMAIL = "admin@devcorp.io"
DEV_ADMIN_PASSWORD = "DevAdminPass123!"
from ai_spm.services.pii_catalog import default_policy_rules

DEV_ORG_TOKEN = "dev-org-token-please-change-32chars-minimum"

# Model governance is opt-in: empty allow list permits all models so ordinary
# web-UI traffic (e.g. ChatGPT's "auto" model) is not blocked before scanning.
DEFAULT_POLICY_RULES = default_policy_rules()


async def seed() -> None:
    async with get_platform_session() as session:
        existing = await session.execute(
            select(Organization).where(Organization.slug == DEV_SLUG)
        )
        org = existing.scalar_one_or_none()

        if org is None:
            org = Organization(
                id=uuid.uuid4(),
                slug=DEV_SLUG,
                name="Dev Corp",
                org_token_hash=hash_token(DEV_ORG_TOKEN),
                status=OrganizationStatus.ACTIVE,
                settings={"onboarding_completed": True},
            )
            session.add(org)
            await session.flush()

            session.add(
                User(
                    org_id=org.id,
                    email=DEV_ADMIN_EMAIL,
                    password_hash=hash_password(DEV_ADMIN_PASSWORD),
                    full_name="Dev Administrator",
                    role=UserRole.SUPER_ADMIN,
                    is_active=True,
                    email_verified=True,
                )
            )
            session.add(
                Subscription(
                    org_id=org.id,
                    plan=SubscriptionPlan.FREE,
                    status=SubscriptionStatus.ACTIVE,
                    max_agents=10,
                    max_prompts_per_day=1000,
                    audit_retention_days=90,
                )
            )
            session.add(
                Department(org_id=org.id, name="Default", description="Default department")
            )
            session.add(
                Policy(
                    org_id=org.id,
                    name="Default Security Policy",
                    description="Auto-seeded dev policy",
                    rules=DEFAULT_POLICY_RULES,
                    is_default=True,
                    is_active=True,
                )
            )
            await session.commit()
            await session.refresh(org)
        else:
            # Ensure the org is active and token is the known dev token.
            org.status = OrganizationStatus.ACTIVE
            org.org_token_hash = hash_token(DEV_ORG_TOKEN)
            await session.commit()
            await session.refresh(org)

        # Capture before session closes (avoids DetachedInstanceError on print).
        org_id = org.id

    print("=" * 68)
    print("  AI-SPM dev tenant ready")
    print("=" * 68)
    print(f"  Admin login : {DEV_ADMIN_EMAIL} / {DEV_ADMIN_PASSWORD}")
    print(f"  AISPM_ORG_ID    = {org_id}")
    print(f"  AISPM_ORG_TOKEN = {DEV_ORG_TOKEN}")
    print("=" * 68)


if __name__ == "__main__":
    asyncio.run(seed())
