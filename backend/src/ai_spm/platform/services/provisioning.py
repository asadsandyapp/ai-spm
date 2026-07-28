import re
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.config import get_settings
from ai_spm.domain.enums import OrganizationStatus, SubscriptionPlan, SubscriptionStatus, UserRole
from ai_spm.domain.models import (
    Department,
    EmailVerificationToken,
    Organization,
    Policy,
    Subscription,
    User,
)
from ai_spm.infrastructure.auth.password import generate_token, hash_password, hash_token
from ai_spm.infrastructure.email.sender import send_verification_email, send_welcome_email

logger = structlog.get_logger(__name__)
settings = get_settings()

from ai_spm.services.pii_catalog import default_policy_rules

# Model governance is opt-in: an empty allow list permits every model so the
# gateway never blocks ordinary web-UI traffic (e.g. ChatGPT's "auto" model
# router) before PII/threat scanning runs. Admins can populate `models.allowed`
# later to restrict specific models. PII detections are per-entity toggles
# under rules.pii.detections (enterprise detection policies).
DEFAULT_POLICY_RULES = default_policy_rules()


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:80] or "org"


async def _unique_slug(session: AsyncSession, base_slug: str) -> str:
    slug = base_slug
    suffix = 0
    while True:
        result = await session.execute(select(Organization.id).where(Organization.slug == slug))
        if result.scalar_one_or_none() is None:
            return slug
        suffix += 1
        slug = f"{base_slug}-{suffix}"


class ProvisioningService:
    async def signup(
        self,
        session: AsyncSession,
        company_name: str,
        admin_email: str,
        admin_password: str,
        admin_full_name: str,
    ) -> tuple[Organization, str, str]:
        """Create organization, admin user, defaults. Returns (org, slug, verification_token)."""
        base_slug = slugify(company_name)
        slug = await _unique_slug(session, base_slug)
        org_token = generate_token(48)
        org_token_hash = hash_token(org_token)

        org = Organization(
            name=company_name,
            slug=slug,
            org_token_hash=org_token_hash,
            status=OrganizationStatus.PENDING,
            settings={"onboarding_completed": False},
        )
        session.add(org)
        await session.flush()

        admin = User(
            org_id=org.id,
            email=admin_email.lower(),
            password_hash=hash_password(admin_password),
            full_name=admin_full_name,
            role=UserRole.SUPER_ADMIN,
            is_active=True,
            email_verified=False,
        )
        session.add(admin)
        await session.flush()

        subscription = Subscription(
            org_id=org.id,
            plan=SubscriptionPlan.FREE,
            status=SubscriptionStatus.TRIALING,
            max_agents=settings.default_free_max_agents,
            max_prompts_per_day=settings.default_free_max_prompts_per_day,
            audit_retention_days=90,
            expires_at=datetime.now(UTC) + timedelta(days=14),
        )
        session.add(subscription)

        department = Department(
            org_id=org.id,
            name="Default",
            description="Default department for all agents",
        )
        session.add(department)
        await session.flush()

        policy = Policy(
            org_id=org.id,
            name="Default Security Policy",
            description="Auto-generated policy on signup",
            rules=DEFAULT_POLICY_RULES,
            is_default=True,
            is_active=True,
        )
        session.add(policy)

        verification_token = generate_token()
        token_record = EmailVerificationToken(
            org_id=org.id,
            user_id=admin.id,
            token_hash=hash_token(verification_token),
            expires_at=datetime.now(UTC)
            + timedelta(hours=settings.email_verification_expire_hours),
        )
        session.add(token_record)
        await session.commit()
        await session.refresh(org)

        await send_verification_email(admin_email, verification_token, company_name)

        logger.info("tenant_provisioned", org_id=str(org.id), slug=slug)
        # Org token is rotated on email verify; return verification_token for activation.
        return org, slug, verification_token

    async def verify_email(
        self, session: AsyncSession, token: str
    ) -> tuple[Organization, str] | None:
        """Activate org after email verify. Returns (org, plaintext org_token) once."""
        token_hash = hash_token(token)
        result = await session.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == token_hash,
                EmailVerificationToken.used_at.is_(None),
                EmailVerificationToken.expires_at > datetime.now(UTC),
            )
        )
        token_record = result.scalar_one_or_none()
        if not token_record:
            return None

        token_record.used_at = datetime.now(UTC)

        user_result = await session.execute(select(User).where(User.id == token_record.user_id))
        user = user_result.scalar_one()
        user.email_verified = True

        org_result = await session.execute(
            select(Organization).where(Organization.id == token_record.org_id)
        )
        org = org_result.scalar_one()
        org.status = OrganizationStatus.ACTIVE

        await session.commit()

        org_token = generate_token(48)
        org.org_token_hash = hash_token(org_token)
        await session.commit()

        await send_welcome_email(user.email, org.name, org_token)
        return org, org_token

    async def seed_roles_for_org(self, session: AsyncSession, org_id: uuid.UUID) -> None:
        """RBAC roles are enum-based; this seeds default policy if missing."""
        result = await session.execute(
            select(Policy).where(Policy.org_id == org_id, Policy.is_default.is_(True))
        )
        if result.scalar_one_or_none() is None:
            session.add(
                Policy(
                    org_id=org_id,
                    name="Default Security Policy",
                    rules=DEFAULT_POLICY_RULES,
                    is_default=True,
                    is_active=True,
                )
            )
            await session.commit()
