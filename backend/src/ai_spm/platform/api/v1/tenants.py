from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.billing.subscription_service import SubscriptionService, UsageService
from ai_spm.config import get_settings
from ai_spm.core.schemas import (
    AssignPlanRequest,
    ChangePasswordRequest,
    PlatformLoginRequest,
    PlatformUserResponse,
    SalesLeadResponse,
    SuspendTenantRequest,
    TenantDetailResponse,
    TenantListItem,
    TokenResponse,
    UpdateLeadRequest,
    UpdateProfileRequest,
    UsageResponse,
)
from ai_spm.domain.enums import OrganizationStatus, SubscriptionPlan, SubscriptionStatus
from ai_spm.domain.models import (
    Agent,
    BillingEvent,
    Organization,
    PlatformAuditLog,
    PlatformUser,
    SalesLead,
    Subscription,
    User,
)
from ai_spm.infrastructure.auth.password import (
    create_platform_access_token,
    hash_password,
    verify_password,
)
from ai_spm.infrastructure.db.session import get_platform_session

router = APIRouter(prefix="/platform/v1", tags=["platform"])
settings = get_settings()
usage_service = UsageService()
subscription_service = SubscriptionService()


def _subscription_list_fields(sub: Subscription | None) -> dict:
    if not sub:
        return {
            "plan": "starter",
            "subscription_status": "incomplete",
            "current_period_end": None,
            "trial_ends_at": None,
            "has_stripe_customer": False,
        }
    return {
        "plan": sub.plan.value,
        "subscription_status": sub.status.value,
        "current_period_end": getattr(sub, "current_period_end", None),
        "trial_ends_at": getattr(sub, "trial_ends_at", None),
        "has_stripe_customer": bool(getattr(sub, "stripe_customer_id", None)),
    }


def _tenant_detail_from(
    org: Organization,
    sub: Subscription | None,
    usage: dict,
) -> TenantDetailResponse:
    list_fields = _subscription_list_fields(sub)
    max_agents = usage.get("max_agents")
    if max_agents is None and sub is not None:
        max_agents = sub.max_agents
    return TenantDetailResponse(
        id=org.id,
        slug=org.slug,
        name=org.name,
        status=org.status.value,
        created_at=org.created_at,
        agent_count=int(usage.get("agent_count") or 0),
        prompts_today=int(usage.get("prompts_today") or 0),
        max_agents=max_agents if max_agents is not None else 0,
        max_prompts_per_day=int(
            usage.get("max_prompts_per_day")
            or (sub.max_prompts_per_day if sub else 0)
            or 0
        ),
        max_prompts_per_month=getattr(sub, "max_prompts_per_month", None)
        if sub
        else usage.get("max_prompts_per_month"),
        max_users=getattr(sub, "max_users", None) if sub else usage.get("max_users"),
        user_count=int(usage.get("user_count") or 0),
        audit_retention_days=getattr(sub, "audit_retention_days", None) if sub else None,
        billing_interval=getattr(sub, "billing_interval", None) or "month",
        cancel_at_period_end=bool(getattr(sub, "cancel_at_period_end", False)) if sub else False,
        stripe_customer_id=getattr(sub, "stripe_customer_id", None) if sub else None,
        stripe_subscription_id=getattr(sub, "stripe_subscription_id", None) if sub else None,
        expires_at=getattr(sub, "expires_at", None) if sub else None,
        past_due_since=getattr(sub, "past_due_since", None) if sub else None,
        onboarding_step=(
            sub.onboarding_step.value
            if sub is not None and hasattr(sub, "onboarding_step") and sub.onboarding_step
            else None
        ),
        **list_fields,
    )


async def get_platform_payload(authorization: Annotated[str | None, Header()] = None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = authorization[7:]
    try:
        payload = jwt.decode(
            token,
            settings.platform_jwt_secret_key,
            algorithms=[settings.platform_jwt_algorithm],
        )
        if payload.get("type") != "platform":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token type")
        return payload
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def require_permission(payload: dict, permission: str) -> None:
    permissions = payload.get("permissions", [])
    resource = permission.split(":")[0]
    if f"{resource}:*" in permissions or permission in permissions:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


async def log_platform_action(
    session: AsyncSession,
    user_id: UUID,
    action: str,
    target_org_id: UUID | None = None,
    metadata: dict | None = None,
) -> None:
    session.add(
        PlatformAuditLog(
            platform_user_id=user_id,
            action=action,
            target_org_id=target_org_id,
            metadata_=metadata or {},
        )
    )
    await session.commit()


@router.post("/auth/login", response_model=TokenResponse)
async def platform_login(body: PlatformLoginRequest) -> TokenResponse:
    async with get_platform_session() as session:
        result = await session.execute(
            select(PlatformUser).where(PlatformUser.email == body.email.lower())
        )
        user = result.scalar_one_or_none()
        if not user or not verify_password(body.password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

        user.last_login_at = datetime.now(UTC)
        await session.commit()

        token = create_platform_access_token(str(user.id), user.role.value)
        return TokenResponse(
            access_token=token,
            expires_in=settings.platform_jwt_expire_minutes * 60,
        )


@router.get("/auth/me", response_model=PlatformUserResponse)
async def platform_me(payload: Annotated[dict, Depends(get_platform_payload)]) -> PlatformUserResponse:
    async with get_platform_session() as session:
        user = (
            await session.execute(select(PlatformUser).where(PlatformUser.id == UUID(payload["sub"])))
        ).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return PlatformUserResponse.model_validate(user)


@router.patch("/auth/me", response_model=PlatformUserResponse)
async def update_platform_profile(
    body: UpdateProfileRequest,
    payload: Annotated[dict, Depends(get_platform_payload)],
) -> PlatformUserResponse:
    async with get_platform_session() as session:
        user = (
            await session.execute(select(PlatformUser).where(PlatformUser.id == UUID(payload["sub"])))
        ).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        user.full_name = body.full_name.strip()
        if body.email is not None:
            new_email = str(body.email).lower()
            if new_email != user.email:
                clash = (
                    await session.execute(
                        select(PlatformUser).where(
                            PlatformUser.email == new_email,
                            PlatformUser.id != user.id,
                        )
                    )
                ).scalar_one_or_none()
                if clash:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Email already in use",
                    )
                user.email = new_email
        await session.commit()
        await session.refresh(user)
        return PlatformUserResponse.model_validate(user)


@router.post("/auth/change-password")
async def change_platform_password(
    body: ChangePasswordRequest,
    payload: Annotated[dict, Depends(get_platform_payload)],
) -> dict[str, str]:
    async with get_platform_session() as session:
        user = (
            await session.execute(select(PlatformUser).where(PlatformUser.id == UUID(payload["sub"])))
        ).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        if not verify_password(body.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )
        if body.current_password == body.new_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="New password must be different from the current password",
            )
        user.password_hash = hash_password(body.new_password)
        await session.commit()
        return {"status": "ok", "message": "Password updated"}


@router.get("/tenants", response_model=list[TenantListItem])
async def list_tenants(payload: Annotated[dict, Depends(get_platform_payload)]) -> list[TenantListItem]:
    require_permission(payload, "tenants:read")

    async with get_platform_session() as session:
        orgs_result = await session.execute(
            select(Organization).order_by(Organization.created_at.desc())
        )
        orgs = orgs_result.scalars().all()
        items: list[TenantListItem] = []
        for org in orgs:
            agent_count = await session.scalar(
                select(func.count()).select_from(Agent).where(Agent.org_id == org.id)
            )
            sub_result = await session.execute(
                select(Subscription).where(Subscription.org_id == org.id)
            )
            sub = sub_result.scalar_one_or_none()
            items.append(
                TenantListItem(
                    id=org.id,
                    slug=org.slug,
                    name=org.name,
                    status=org.status.value,
                    created_at=org.created_at,
                    agent_count=agent_count or 0,
                    **_subscription_list_fields(sub),
                )
            )
        return items


@router.get("/tenants/{org_id}", response_model=TenantDetailResponse)
async def get_tenant(
    org_id: UUID,
    payload: Annotated[dict, Depends(get_platform_payload)],
) -> TenantDetailResponse:
    require_permission(payload, "tenants:read")

    async with get_platform_session() as session:
        result = await session.execute(select(Organization).where(Organization.id == org_id))
        org = result.scalar_one_or_none()
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        sub = (
            await session.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one_or_none()
        usage = await usage_service.get_tenant_usage(session, org_id)
        user_count = await session.scalar(
            select(func.count()).select_from(User).where(User.org_id == org_id)
        )
        usage = {**usage, "user_count": user_count or 0}
        return _tenant_detail_from(org, sub, usage)


@router.post("/tenants/{org_id}/suspend")
async def suspend_tenant(
    org_id: UUID,
    body: SuspendTenantRequest,
    payload: Annotated[dict, Depends(get_platform_payload)],
) -> dict[str, str]:
    require_permission(payload, "tenants:suspend")

    async with get_platform_session() as session:
        result = await session.execute(select(Organization).where(Organization.id == org_id))
        org = result.scalar_one_or_none()
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        org.status = OrganizationStatus.SUSPENDED
        sub = (
            await session.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one_or_none()
        if sub:
            sub.status = SubscriptionStatus.SUSPENDED
        await log_platform_action(
            session,
            UUID(payload["sub"]),
            "tenant.suspend",
            org_id,
            {"reason": body.reason},
        )
        return {"status": "suspended", "org_id": str(org_id)}


@router.post("/tenants/{org_id}/activate")
async def activate_tenant(
    org_id: UUID,
    payload: Annotated[dict, Depends(get_platform_payload)],
) -> dict[str, str]:
    require_permission(payload, "tenants:activate")

    async with get_platform_session() as session:
        result = await session.execute(select(Organization).where(Organization.id == org_id))
        org = result.scalar_one_or_none()
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        org.status = OrganizationStatus.ACTIVE
        sub = (
            await session.execute(select(Subscription).where(Subscription.org_id == org_id))
        ).scalar_one_or_none()
        if sub and sub.status == SubscriptionStatus.SUSPENDED:
            sub.status = SubscriptionStatus.ACTIVE
        await log_platform_action(
            session,
            UUID(payload["sub"]),
            "tenant.activate",
            org_id,
        )
        return {"status": "active", "org_id": str(org_id)}


@router.post("/tenants/{org_id}/assign-plan")
async def assign_plan(
    org_id: UUID,
    body: AssignPlanRequest,
    payload: Annotated[dict, Depends(get_platform_payload)],
) -> dict:
    """Super Admin: assign Enterprise / custom quotas and optionally activate."""
    require_permission(payload, "billing:write")

    async with get_platform_session() as session:
        org = (
            await session.execute(select(Organization).where(Organization.id == org_id))
        ).scalar_one_or_none()
        if not org:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        plan = SubscriptionPlan(body.plan)
        if body.activate:
            sub = await subscription_service.activate_subscription(session, org_id, plan)
        else:
            sub = await subscription_service.get_or_create(session, org_id)
            subscription_service.apply_plan_limits(sub, plan)
            await session.commit()
            await session.refresh(sub)

        if body.status:
            status_map = {s.value: s for s in SubscriptionStatus}
            if body.status in status_map:
                sub.status = status_map[body.status]
        if body.max_agents is not None:
            sub.max_agents = body.max_agents
        if body.max_users is not None and hasattr(sub, "max_users"):
            sub.max_users = body.max_users
        if body.max_prompts_per_day is not None:
            sub.max_prompts_per_day = body.max_prompts_per_day
        if body.max_prompts_per_month is not None and hasattr(sub, "max_prompts_per_month"):
            sub.max_prompts_per_month = body.max_prompts_per_month
            sub.max_prompts_per_day = (
                0
                if body.max_prompts_per_month <= 0
                else max(1, (body.max_prompts_per_month + 29) // 30)
            )
        if body.audit_retention_days is not None and hasattr(sub, "audit_retention_days"):
            sub.audit_retention_days = body.audit_retention_days
        await session.commit()
        await log_platform_action(
            session,
            UUID(payload["sub"]),
            "tenant.assign_plan",
            org_id,
            {"plan": plan.value, "max_agents": sub.max_agents},
        )
        return subscription_service.entitlements_payload(sub)


@router.get("/leads", response_model=list[SalesLeadResponse])
async def list_leads(
    payload: Annotated[dict, Depends(get_platform_payload)],
) -> list[SalesLeadResponse]:
    require_permission(payload, "tenants:read")
    async with get_platform_session() as session:
        result = await session.execute(
            select(SalesLead).order_by(SalesLead.created_at.desc()).limit(200)
        )
        return [SalesLeadResponse.model_validate(row) for row in result.scalars().all()]


@router.patch("/leads/{lead_id}", response_model=SalesLeadResponse)
async def update_lead(
    lead_id: UUID,
    body: UpdateLeadRequest,
    payload: Annotated[dict, Depends(get_platform_payload)],
) -> SalesLeadResponse:
    require_permission(payload, "tenants:activate")
    async with get_platform_session() as session:
        lead = (
            await session.execute(select(SalesLead).where(SalesLead.id == lead_id))
        ).scalar_one_or_none()
        if not lead:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
        lead.status = body.status
        if body.notes is not None:
            lead.notes = body.notes
        await log_platform_action(
            session,
            UUID(payload["sub"]),
            "lead.update",
            lead.org_id,
            {"lead_id": str(lead_id), "status": body.status},
        )
        await session.refresh(lead)
        return SalesLeadResponse.model_validate(lead)


@router.get("/billing/events")
async def list_billing_events(
    payload: Annotated[dict, Depends(get_platform_payload)],
) -> list[dict]:
    require_permission(payload, "billing:read")
    async with get_platform_session() as session:
        result = await session.execute(
            select(BillingEvent).order_by(BillingEvent.processed_at.desc()).limit(100)
        )
        return [
            {
                "id": str(ev.id),
                "org_id": str(ev.org_id) if ev.org_id else None,
                "stripe_event_id": ev.stripe_event_id,
                "event_type": ev.event_type,
                "processed_at": ev.processed_at.isoformat(),
            }
            for ev in result.scalars().all()
        ]


@router.get("/tenants/{org_id}/usage", response_model=UsageResponse)
async def tenant_usage(
    org_id: UUID,
    payload: Annotated[dict, Depends(get_platform_payload)],
) -> UsageResponse:
    require_permission(payload, "tenants:read")

    async with get_platform_session() as session:
        result = await session.execute(select(Organization.id).where(Organization.id == org_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

        usage = await usage_service.get_tenant_usage(session, org_id)
        return UsageResponse(**usage)
