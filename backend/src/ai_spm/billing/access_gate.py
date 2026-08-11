"""Server-authoritative checkout / subscription access gate for admin + agent APIs."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ai_spm.billing.entitlements import PAST_DUE_GRACE_DAYS
from ai_spm.domain.enums import OnboardingStep, SubscriptionStatus
from ai_spm.domain.models import Subscription
from ai_spm.infrastructure.db.session import get_platform_session
from ai_spm.tenant.context import get_tenant_context

logger = structlog.get_logger(__name__)

ADMIN_GATE_ALLOWLIST_SUFFIXES = (
    "/auth/login",
    "/auth/refresh",
    "/auth/me",
    "/auth/change-password",
    "/billing/status",
    "/billing/usage",
    "/billing/checkout",
    "/billing/portal",
    "/billing/select-plan",
    "/billing/dev-activate",
    "/billing/confirm-checkout",
    "/billing/plans",
    "/onboarding/status",
)

AGENT_BLOCK_PREFIXES = (
    "/agent/v1/prompt",
    "/agent/v1/register",
)


@dataclass(frozen=True)
class SubSnapshot:
    status: SubscriptionStatus
    onboarding_step: OnboardingStep
    past_due_since: datetime | None
    updated_at: datetime | None

    def console_access_allowed(self) -> bool:
        if self.status == SubscriptionStatus.ACTIVE:
            return True
        if self.status == SubscriptionStatus.PAST_DUE:
            since = self.past_due_since or self.updated_at
            if since and since.tzinfo is None:
                since = since.replace(tzinfo=UTC)
            if since and datetime.now(UTC) - since > timedelta(days=PAST_DUE_GRACE_DAYS):
                return False
            return True
        return False


def _admin_path_allowed(path: str) -> bool:
    if not path.startswith("/admin/v1/"):
        return True
    for suffix in ADMIN_GATE_ALLOWLIST_SUFFIXES:
        if path.endswith(suffix):
            return True
    if "/admin/v1/billing/" in path or path.endswith("/admin/v1/billing"):
        return True
    if "/admin/v1/onboarding/" in path:
        return True
    return False


async def _load_subscription_snapshot(org_id: UUID) -> SubSnapshot | None:
    async with get_platform_session() as session:
        result = await session.execute(select(Subscription).where(Subscription.org_id == org_id))
        sub = result.scalar_one_or_none()
        if sub is None:
            return None
        return SubSnapshot(
            status=sub.status,
            onboarding_step=sub.onboarding_step,
            past_due_since=sub.past_due_since,
            updated_at=sub.updated_at,
        )


class SubscriptionAccessMiddleware(BaseHTTPMiddleware):
    """Block unpaid orgs from console APIs and agent enrollment/prompts (402)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        ctx = get_tenant_context()

        if any(path.startswith(p) for p in AGENT_BLOCK_PREFIXES):
            if ctx is None:
                return await call_next(request)
            snap = await _load_subscription_snapshot(ctx.org_id)
            if snap is None or not snap.console_access_allowed():
                return JSONResponse(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    content={
                        "detail": "Active subscription required for agent enrollment and prompt inspection",
                        "subscription_status": snap.status.value if snap else "missing",
                        "code": "subscription_required",
                    },
                )
            return await call_next(request)

        if path.startswith("/admin/v1/") and not _admin_path_allowed(path):
            if ctx is None:
                return await call_next(request)
            snap = await _load_subscription_snapshot(ctx.org_id)
            if snap is None or not snap.console_access_allowed():
                return JSONResponse(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    content={
                        "detail": "Complete checkout to unlock your AI-SPM security console",
                        "subscription_status": snap.status.value if snap else "incomplete",
                        "onboarding_step": snap.onboarding_step.value if snap else "registered",
                        "code": "checkout_required",
                    },
                )

        return await call_next(request)
