from fastapi import APIRouter, HTTPException, Query, Request, status

from ai_spm.billing.entitlements import public_plan_catalog
from ai_spm.config import get_settings
from ai_spm.core.schemas import (
    ContactSalesRequest,
    ContactSalesResponse,
    SignupRequest,
    SignupResponse,
    VerifyEmailResponse,
)
from ai_spm.domain.models import SalesLead
from ai_spm.infrastructure.cache.redis import rate_limit_check
from ai_spm.infrastructure.db.session import get_platform_session
from ai_spm.platform.services.provisioning import ProvisioningService

router = APIRouter(prefix="/public/v1", tags=["public"])
provisioning = ProvisioningService()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "ai-spm-public"}


@router.get("/plans")
async def list_plans() -> dict:
    return {"plans": public_plan_catalog()}


@router.post("/contact-sales", response_model=ContactSalesResponse, status_code=status.HTTP_201_CREATED)
async def contact_sales(request: Request, body: ContactSalesRequest) -> ContactSalesResponse:
    client_ip = request.client.host if request.client else "unknown"
    allowed = await rate_limit_check(f"contact-sales:{client_ip}", limit=10, window_seconds=3600)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many contact requests",
        )
    async with get_platform_session() as session:
        lead = SalesLead(
            company_name=body.company_name.strip(),
            contact_name=body.contact_name.strip(),
            email=body.email.lower(),
            phone=body.phone,
            estimated_agents=body.estimated_agents,
            message=body.message,
            status="new",
        )
        session.add(lead)
        await session.commit()
        await session.refresh(lead)
        return ContactSalesResponse(id=lead.id)


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
async def signup(request: Request, body: SignupRequest) -> SignupResponse:
    client_ip = request.client.host if request.client else "unknown"
    allowed = await rate_limit_check(f"signup:{client_ip}", limit=5, window_seconds=3600)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many signup attempts",
        )

    settings = get_settings()
    async with get_platform_session() as session:
        org, slug, verification_token = await provisioning.signup(
            session,
            company_name=body.company_name,
            admin_email=body.admin_email,
            admin_password=body.admin_password,
            admin_full_name=body.admin_full_name,
        )
        include_token = settings.app_env != "production" or settings.debug
        return SignupResponse(
            org_id=org.id,
            slug=slug,
            verification_token=verification_token if include_token else None,
            message=(
                "Verification email sent"
                if not include_token
                else "Verification email sent (verification_token included for non-production)"
            ),
        )


@router.get("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(token: str = Query(..., min_length=32)) -> VerifyEmailResponse:
    async with get_platform_session() as session:
        result = await provisioning.verify_email(session, token)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification token",
            )
        org, org_token = result
        return VerifyEmailResponse(
            org_id=org.id,
            slug=org.slug,
            status=org.status.value,
            org_token=org_token,
            message="Email verified. Choose a plan to unlock your security console.",
        )
