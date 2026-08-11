"""Admin billing, plan selection, Stripe Checkout / Customer Portal."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.billing.entitlements import STRIPE_LOOKUP_KEYS, get_plan, public_plan_catalog
from ai_spm.billing.subscription_service import SubscriptionService, UsageService
from ai_spm.config import get_settings
from ai_spm.domain.enums import SubscriptionPlan
from ai_spm.domain.models import Organization, Subscription, User
from ai_spm.infrastructure.db.session import get_session
from ai_spm.tenant.context import require_tenant_context

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["admin-billing"])
settings = get_settings()
subscription_service = SubscriptionService()
usage_service = UsageService()


def _configured_price_id(plan: SubscriptionPlan) -> str | None:
    """Price ID from STRIPE_PRICE_* env (e.g. price_abc…) — local/dev friendly."""
    raw = {
        SubscriptionPlan.STARTER: settings.stripe_price_starter,
        SubscriptionPlan.PROFESSIONAL: settings.stripe_price_professional,
        SubscriptionPlan.ENTERPRISE: settings.stripe_price_enterprise,
    }.get(plan, "")
    if raw and raw.startswith("price_"):
        return raw
    return None


def _stripe_meta_value(meta: object | None, key: str) -> str | None:
    """Read metadata from Stripe Session (StripeObject or plain dict)."""
    if meta is None:
        return None
    if isinstance(meta, dict):
        val = meta.get(key)
    else:
        val = getattr(meta, key, None)
        if val is None:
            try:
                val = meta[key]  # type: ignore[index]
            except (KeyError, TypeError):
                val = None
    return str(val) if val is not None else None


def _resolve_stripe_price_id(plan: SubscriptionPlan) -> str:
    """Resolve Stripe Price id via lookup_key (prod catalog) or STRIPE_PRICE_* env."""
    import stripe

    defn = get_plan(plan)
    prices = stripe.Price.list(lookup_keys=[defn.stripe_lookup_key], active=True, limit=1)
    if prices.data:
        return prices.data[0].id

    env_price = _configured_price_id(plan)
    if env_price:
        logger.info(
            "stripe_price_env_fallback",
            plan=plan.value,
            price_id=env_price,
            lookup_key=defn.stripe_lookup_key,
        )
        return env_price

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            f"Stripe price not configured for lookup_key={defn.stripe_lookup_key}. "
            f"Set lookup key on the Price in Stripe Dashboard, or set "
            f"STRIPE_PRICE_{plan.value.upper()}=price_… in deploy/.env"
        ),
    )


class SelectPlanRequest(BaseModel):
    plan: str = Field(..., pattern="^(starter|professional)$")


class CheckoutRequest(BaseModel):
    plan: str = Field(..., pattern="^(starter|professional)$")
    success_url: str | None = None
    cancel_url: str | None = None


class PortalRequest(BaseModel):
    return_url: str | None = None


class ConfirmCheckoutRequest(BaseModel):
    session_id: str = Field(..., min_length=8)


class BillingStatusResponse(BaseModel):
    org_id: UUID
    plan: str
    status: str
    onboarding_step: str
    console_access: bool
    entitlements: dict
    usage: dict


@router.get("/billing/plans")
async def list_plans() -> dict:
    """Public-shaped catalog (auth required but gated allowlist)."""
    return {"plans": public_plan_catalog()}


@router.get("/billing/status", response_model=BillingStatusResponse)
async def billing_status(session: AsyncSession = Depends(get_session)) -> BillingStatusResponse:
    ctx = require_tenant_context()
    sub = await subscription_service.get_or_create(session, ctx.org_id)
    usage = await usage_service.get_tenant_usage(session, ctx.org_id)
    entitlements = subscription_service.entitlements_payload(sub)
    return BillingStatusResponse(
        org_id=ctx.org_id,
        plan=sub.plan.value,
        status=sub.status.value,
        onboarding_step=sub.onboarding_step.value,
        console_access=entitlements["console_access"],
        entitlements=entitlements,
        usage=usage,
    )


@router.get("/billing/usage")
async def billing_usage(session: AsyncSession = Depends(get_session)) -> dict:
    ctx = require_tenant_context()
    return await usage_service.get_tenant_usage(session, ctx.org_id)


@router.get("/onboarding/status")
async def onboarding_status(session: AsyncSession = Depends(get_session)) -> dict:
    ctx = require_tenant_context()
    sub = await subscription_service.get_or_create(session, ctx.org_id)
    return subscription_service.entitlements_payload(sub)


@router.post("/billing/select-plan")
async def select_plan(
    body: SelectPlanRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    ctx = require_tenant_context()
    plan = SubscriptionPlan(body.plan)
    try:
        sub = await subscription_service.select_plan(session, ctx.org_id, plan)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return subscription_service.entitlements_payload(sub)


@router.post("/billing/checkout")
async def create_checkout(
    body: CheckoutRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    ctx = require_tenant_context()
    plan = SubscriptionPlan(body.plan)
    await subscription_service.select_plan(session, ctx.org_id, plan)

    success_url = body.success_url or f"{settings.app_base_url}/billing/success"
    cancel_url = body.cancel_url or f"{settings.app_base_url}/pricing?checkout=canceled"

    if not settings.stripe_enabled:
        # Non-production / Stripe-off: mark checkout pending; client uses dev-activate.
        await subscription_service.mark_checkout_pending(session, ctx.org_id)
        return {
            "mode": "dev",
            "checkout_url": f"{settings.app_base_url}/billing/success?dev=1&plan={plan.value}",
            "session_id": None,
            "message": "Stripe disabled — use /billing/dev-activate in non-production",
        }

    import stripe

    stripe.api_key = settings.stripe_secret_key

    org = (
        await session.execute(select(Organization).where(Organization.id == ctx.org_id))
    ).scalar_one()
    user = (
        await session.execute(select(User).where(User.id == ctx.user_id))
    ).scalar_one()
    sub = await subscription_service.get_or_create(session, ctx.org_id)

    customer_id = sub.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            name=org.name,
            metadata={"org_id": str(org.id)},
        )
        customer_id = customer["id"]
        sub.stripe_customer_id = customer_id
        await session.commit()

    price_id = _resolve_stripe_price_id(plan)

    checkout = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url + ("&" if "?" in success_url else "?") + "session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url,
        metadata={"org_id": str(org.id), "plan": plan.value},
        subscription_data={"metadata": {"org_id": str(org.id), "plan": plan.value}},
    )
    await subscription_service.mark_checkout_pending(session, ctx.org_id, checkout["id"])
    return {"mode": "stripe", "checkout_url": checkout["url"], "session_id": checkout["id"]}


@router.post("/billing/dev-activate")
async def dev_activate(
    body: SelectPlanRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Activate subscription without Stripe when STRIPE_ENABLED=false (non-production)."""
    if settings.stripe_enabled and settings.app_env == "production":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not available")
    if settings.app_env == "production" and settings.stripe_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not available")

    ctx = require_tenant_context()
    plan = SubscriptionPlan(body.plan)
    sub = await subscription_service.activate_subscription(
        session,
        ctx.org_id,
        plan,
        current_period_end=datetime.now(UTC) + timedelta(days=30),
    )
    return subscription_service.entitlements_payload(sub)


@router.post("/billing/confirm-checkout")
async def confirm_checkout(
    body: ConfirmCheckoutRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Activate after Stripe Checkout when webhooks are not configured locally."""
    if not settings.stripe_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stripe is not enabled — use /billing/dev-activate",
        )

    import stripe

    stripe.api_key = settings.stripe_secret_key
    ctx = require_tenant_context()
    try:
        checkout = stripe.checkout.Session.retrieve(body.session_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid checkout session: {exc}",
        ) from exc

    # Stripe SDK returns StripeObject — use attrs/brackets, not dict .get().
    meta_obj = getattr(checkout, "metadata", None)

    org_meta = _stripe_meta_value(meta_obj, "org_id") or getattr(
        checkout, "client_reference_id", None
    )
    if not org_meta or str(org_meta) != str(ctx.org_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Checkout session does not belong to this organization",
        )

    checkout_status = getattr(checkout, "status", None)
    payment_status = getattr(checkout, "payment_status", None)
    if checkout_status != "complete" and payment_status not in (
        "paid",
        "no_payment_required",
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Checkout not complete "
                f"(status={checkout_status}, payment={payment_status})"
            ),
        )

    plan_raw = _stripe_meta_value(meta_obj, "plan") or "starter"
    try:
        plan = SubscriptionPlan(plan_raw)
    except ValueError:
        plan = SubscriptionPlan.STARTER

    customer = getattr(checkout, "customer", None)
    subscription = getattr(checkout, "subscription", None)
    sub = await subscription_service.activate_subscription(
        session,
        ctx.org_id,
        plan,
        stripe_customer_id=str(customer) if customer else None,
        stripe_subscription_id=str(subscription) if subscription else None,
        current_period_end=datetime.now(UTC) + timedelta(days=30),
    )
    return subscription_service.entitlements_payload(sub)


@router.post("/billing/portal")
async def create_portal(
    body: PortalRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    ctx = require_tenant_context()
    sub = await subscription_service.get_or_create(session, ctx.org_id)
    if not settings.stripe_enabled:
        return {
            "mode": "dev",
            "portal_url": f"{settings.app_base_url}/billing",
            "message": "Stripe disabled — manage plan in-app",
        }
    if not sub.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Stripe customer on file",
        )
    import stripe

    stripe.api_key = settings.stripe_secret_key
    portal = stripe.billing_portal.Session.create(
        customer=sub.stripe_customer_id,
        return_url=body.return_url or f"{settings.app_base_url}/billing",
    )
    return {"mode": "stripe", "portal_url": portal["url"]}
