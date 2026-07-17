from uuid import UUID

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.billing.subscription_service import SubscriptionService
from ai_spm.config import get_settings
from ai_spm.domain.enums import OrganizationStatus, SubscriptionPlan
from ai_spm.domain.models import BillingEvent, Organization
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

        org_id = None
        data_object = event.get("data", {}).get("object", {})
        metadata = data_object.get("metadata", {})
        if "org_id" in metadata:
            from uuid import UUID

            org_id = UUID(metadata["org_id"])

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


async def _handle_stripe_event(
    session: AsyncSession, event: dict, org_id: UUID | None
) -> None:
    event_type = event["type"]
    data = event.get("data", {}).get("object", {})

    if event_type == "customer.subscription.deleted" and org_id:
        await subscription_service.suspend_for_billing(session, org_id)
    elif event_type == "invoice.payment_failed" and org_id:
        await subscription_service.suspend_for_billing(session, org_id)
    elif event_type == "customer.subscription.updated" and org_id:
        plan_id = data.get("items", {}).get("data", [{}])[0].get("price", {}).get("lookup_key")
        plan_map = {"free": SubscriptionPlan.FREE, "pro": SubscriptionPlan.PRO, "enterprise": SubscriptionPlan.ENTERPRISE}
        if plan_id in plan_map:
            await subscription_service.update_plan(session, org_id, plan_map[plan_id])
    elif event_type == "invoice.payment_succeeded" and org_id:
        result = await session.execute(select(Organization).where(Organization.id == org_id))
        org = result.scalar_one_or_none()
        if org and org.status == OrganizationStatus.SUSPENDED:
            org.status = OrganizationStatus.ACTIVE
            await session.commit()

    logger.info("stripe_event_processed", event_type=event_type, org_id=str(org_id))
