from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.billing.subscription_service import UsageService
from ai_spm.config import get_settings
from ai_spm.core.schemas import (
    PlatformLoginRequest,
    SuspendTenantRequest,
    TenantDetailResponse,
    TenantListItem,
    TokenResponse,
    UsageResponse,
)
from ai_spm.domain.enums import OrganizationStatus
from ai_spm.domain.models import Agent, Organization, PlatformAuditLog, PlatformUser, Subscription
from ai_spm.infrastructure.auth.password import create_platform_access_token, verify_password
from ai_spm.infrastructure.db.session import get_platform_session

router = APIRouter(prefix="/platform/v1", tags=["platform"])
settings = get_settings()
usage_service = UsageService()


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
                    plan=sub.plan.value if sub else "free",
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

        usage = await usage_service.get_tenant_usage(session, org_id)
        return TenantDetailResponse(
            id=org.id,
            slug=org.slug,
            name=org.name,
            status=org.status.value,
            created_at=org.created_at,
            agent_count=usage["agent_count"],
            plan=usage["plan"],
            prompts_today=usage["prompts_today"],
            max_agents=usage["max_agents"],
            max_prompts_per_day=usage["max_prompts_per_day"],
        )


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
        await log_platform_action(
            session,
            UUID(payload["sub"]),
            "tenant.activate",
            org_id,
        )
        return {"status": "active", "org_id": str(org_id)}


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
