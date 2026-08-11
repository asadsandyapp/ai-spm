from uuid import UUID

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.billing.entitlements import STRIPE_LOOKUP_KEYS
from ai_spm.billing.subscription_service import SubscriptionService
from ai_spm.config import get_settings
from ai_spm.domain.enums import OrganizationStatus, SubscriptionPlan
from ai_spm.domain.models import BillingEvent, Organization, Subscription
from ai_spm.infrastructure.db.session import get_platform_session

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/billing", tags=["billing"])
settings = get_settings()
subscription_service = SubscriptionService()


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
) -> dict[str, str]:
    if not settings.stripe_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe disabled")

    import stripe

    stripe.api_key = settings.stripe_secret_key
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    async with get_platform_session() as session:
        existing = await session.execute(
            select(BillingEvent).where(BillingEvent.stripe_event_id == event["id"])
        )
        if existing.scalar_one_or_none():
            return {"status": "already_processed"}

        org_id = _extract_org_id(event)
        session.add(
            BillingEvent(
                org_id=org_id,
                stripe_event_id=event["id"],
                event_type=event["type"],
                payload=dict(event),
            )
        )
        await session.commit()
        await _handle_stripe_event(session, event, org_id)

    return {"status": "ok"}


def _extract_org_id(event: dict) -> UUID | None:
    data_object = event.get("data", {}).get("object", {})
    metadata = data_object.get("metadata") or {}
    if "org_id" in metadata:
        try:
            return UUID(metadata["org_id"])
        except ValueError:
            return None
    # checkout.session.completed may nest subscription metadata differently
    client_ref = data_object.get("client_reference_id")
    if client_ref:
        try:
            return UUID(client_ref)
        except ValueError:
            return None
    return None


def _plan_from_price(data: dict) -> SubscriptionPlan | None:
    items = data.get("items", {}).get("data") or []
    if not items:
        # checkout session
        lookup = (data.get("metadata") or {}).get("plan")
        if lookup:
            try:
                return SubscriptionPlan(lookup)
            except ValueError:
                pass
        return None
    price = items[0].get("price") or {}
    lookup_key = price.get("lookup_key")
    if lookup_key and lookup_key in STRIPE_LOOKUP_KEYS:
        return STRIPE_LOOKUP_KEYS[lookup_key]
    meta_plan = (data.get("metadata") or {}).get("plan")
    if meta_plan:
        try:
            return SubscriptionPlan(meta_plan)
        except ValueError:
            return None
    return None


async def _handle_stripe_event(
    session: AsyncSession, event: dict, org_id: UUID | None
) -> None:
    event_type = event["type"]
    data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        if not org_id and data.get("metadata", {}).get("org_id"):
            org_id = UUID(data["metadata"]["org_id"])
        if org_id:
            plan = _plan_from_price(data) or SubscriptionPlan(
                data.get("metadata", {}).get("plan", "starter")
            )
            await subscription_service.activate_subscription(
                session,
                org_id,
                plan,
                stripe_customer_id=data.get("customer"),
                stripe_subscription_id=data.get("subscription"),
            )

    elif event_type == "customer.subscription.updated" and org_id:
        stripe_status = data.get("status")
        plan = _plan_from_price(data)
        if stripe_status == "active":
            await subscription_service.activate_subscription(
                session,
                org_id,
                plan,
                stripe_customer_id=data.get("customer"),
                stripe_subscription_id=data.get("id"),
            )
        elif stripe_status == "past_due":
            await subscription_service.mark_past_due(session, org_id)
        elif stripe_status in ("canceled", "unpaid"):
            await subscription_service.cancel_subscription(session, org_id)
        elif plan:
            await subscription_service.update_plan(session, org_id, plan)

    elif event_type == "customer.subscription.deleted" and org_id:
        await subscription_service.cancel_subscription(session, org_id)
        await subscription_service.suspend_for_billing(session, org_id)

    elif event_type == "invoice.payment_failed" and org_id:
        await subscription_service.mark_past_due(session, org_id)
        # Auto-suspend after grace is enforced on access / scheduled job
        sub = (
            await session.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one_or_none()
        if sub:
            still_ok = await subscription_service.enforce_past_due_grace(session, org_id)
            if not still_ok:
                logger.info("past_due_grace_exhausted", org_id=str(org_id))

    elif event_type == "invoice.paid" and org_id:
        result = await session.execute(select(Organization).where(Organization.id == org_id))
        org = result.scalar_one_or_none()
        if org and org.status == OrganizationStatus.SUSPENDED:
            org.status = OrganizationStatus.ACTIVE
            await session.commit()
        plan = _plan_from_price(data)
        await subscription_service.activate_subscription(session, org_id, plan)

    elif event_type == "invoice.payment_succeeded" and org_id:
        result = await session.execute(select(Organization).where(Organization.id == org_id))
        org = result.scalar_one_or_none()
        if org and org.status == OrganizationStatus.SUSPENDED:
            org.status = OrganizationStatus.ACTIVE
            await session.commit()
        await subscription_service.activate_subscription(session, org_id, None)

    logger.info("stripe_event_processed", event_type=event_type, org_id=str(org_id) if org_id else None)
