from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.config import get_settings
from ai_spm.core.schemas import (
    AgentResponse,
    AuditEventResponse,
    AuditExportResponse,
    ChangePasswordRequest,
    CreatePolicyRequest,
    CreateUserRequest,
    DashboardMetricsResponse,
    EnrollmentInfoResponse,
    LLMConfigRequest,
    LLMConfigResponse,
    LoginRequest,
    OrgTokenRotateResponse,
    PiiDetectionPolicyResponse,
    PolicyResponse,
    ReportSummaryResponse,
    ThreatEventResponse,
    TokenResponse,
    UpdatePiiDetectionRequest,
    UpdatePolicyRequest,
    UpdateProfileRequest,
    UserResponse,
)
from ai_spm.domain.enums import OrganizationStatus, UserRole
from ai_spm.domain.models import LLMProviderConfig, Organization, Policy, User
from ai_spm.infrastructure.auth.password import (
    create_admin_access_token,
    hash_password,
    verify_password,
)
from ai_spm.infrastructure.db.session import get_platform_session, get_session
from ai_spm.services.audit_service import AuditService, GDPRService, hostname_map_for_agents
from ai_spm.services.web_audit_text import humanize_prompt_text
from ai_spm.services.dashboard_service import DashboardService
from ai_spm.services.enrollment_service import enrollment_service, resolve_public_gateway_url
from ai_spm.services.policy_engine import PolicyEngine
from ai_spm.services.prompt_pipeline import AgentService
from ai_spm.tenant.context import require_tenant_context

router = APIRouter(prefix="/admin/v1", tags=["admin"])
settings = get_settings()
agent_service = AgentService()
dashboard_service = DashboardService()
audit_service = AuditService()
gdpr_service = GDPRService()
policy_engine = PolicyEngine()


def _gateway_url_for_request(request: Request) -> str:
    cfg = get_settings()
    if cfg.aispm_public_gateway_url.strip():
        return resolve_public_gateway_url(cfg)
    # Dev fallback: derive Kong/API origin from the incoming request host.
    return resolve_public_gateway_url(
        cfg,
        request_base=str(request.base_url).rstrip("/"),
    )


def _require_permission(permission: str) -> None:
    ctx = require_tenant_context()
    perms = ctx.permissions or frozenset()
    resource = permission.split(":")[0]
    if f"{resource}:*" not in perms and permission not in perms:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    async with get_platform_session() as session:
        result = await session.execute(select(User).where(User.email == body.email.lower()))
        users = result.scalars().all()

        user = None
        org = None
        for candidate in users:
            org_result = await session.execute(
                select(Organization).where(Organization.id == candidate.org_id)
            )
            candidate_org = org_result.scalar_one_or_none()
            if candidate_org and candidate_org.status == OrganizationStatus.ACTIVE:
                if verify_password(body.password, candidate.password_hash):
                    user = candidate
                    org = candidate_org
                    break

        if not user or not org:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        if not user.email_verified:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified")

        user.last_login_at = datetime.now(UTC)
        await session.commit()

        token = create_admin_access_token(
            user_id=str(user.id),
            org_id=str(user.org_id),
            role=user.role.value,
        )
        return TokenResponse(
            access_token=token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )


@router.get("/auth/me", response_model=UserResponse)
async def me(session: AsyncSession = Depends(get_session)) -> UserResponse:
    from ai_spm.billing.subscription_service import SubscriptionService

    ctx = require_tenant_context()
    result = await session.execute(
        select(User).where(User.id == ctx.user_id, User.org_id == ctx.org_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    sub_svc = SubscriptionService()
    sub = await sub_svc.get_or_create(session, ctx.org_id)
    entitlements = sub_svc.entitlements_payload(sub)
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        org_id=user.org_id,
        subscription_status=sub.status.value,
        onboarding_step=sub.onboarding_step.value,
        plan=sub.plan.value,
        console_access=entitlements["console_access"],
        entitlements=entitlements,
    )


@router.patch("/auth/me", response_model=UserResponse)
async def update_profile(
    body: UpdateProfileRequest,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    ctx = require_tenant_context()
    result = await session.execute(
        select(User).where(User.id == ctx.user_id, User.org_id == ctx.org_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.full_name = body.full_name.strip()
    if body.email is not None:
        new_email = str(body.email).lower()
        if new_email != user.email:
            clash = (
                await session.execute(
                    select(User).where(
                        User.org_id == ctx.org_id,
                        User.email == new_email,
                        User.id != user.id,
                    )
                )
            ).scalar_one_or_none()
            if clash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already in use in this organization",
                )
            user.email = new_email
    await session.commit()
    await session.refresh(user)
    return await me(session)


@router.post("/auth/change-password")
async def change_password(
    body: ChangePasswordRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    ctx = require_tenant_context()
    result = await session.execute(
        select(User).where(User.id == ctx.user_id, User.org_id == ctx.org_id)
    )
    user = result.scalar_one_or_none()
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


@router.get("/dashboard/metrics", response_model=DashboardMetricsResponse)
async def dashboard_metrics(session: AsyncSession = Depends(get_session)) -> DashboardMetricsResponse:
    _require_permission("dashboard:read")
    ctx = require_tenant_context()
    data = await dashboard_service.get_metrics(session, ctx.org_id)
    return DashboardMetricsResponse(**data)


@router.get("/dashboard/threats", response_model=list[ThreatEventResponse])
async def dashboard_threats(
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
) -> list[ThreatEventResponse]:
    _require_permission("threats:read")
    ctx = require_tenant_context()
    threats = await dashboard_service.get_threats(session, ctx.org_id, limit=limit)
    return [ThreatEventResponse(**t) for t in threats]


@router.get("/reports/summary", response_model=ReportSummaryResponse)
async def reports_summary(
    session: AsyncSession = Depends(get_session),
    days: int = Query(30, ge=1, le=365),
    event_type: str | None = Query(None),
    provider: str | None = Query(None),
    device: str | None = Query(None),
    entity: str | None = Query(None),
) -> ReportSummaryResponse:
    _require_permission("dashboard:read")
    ctx = require_tenant_context()
    try:
        data = await dashboard_service.get_report(
            session,
            ctx.org_id,
            days=days,
            event_type=event_type or None,
            provider=provider or None,
            device=device or None,
            entity=entity or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ReportSummaryResponse(**data)


@router.get("/agents", response_model=list[AgentResponse])
async def list_agents(session: AsyncSession = Depends(get_session)) -> list[AgentResponse]:
    _require_permission("agents:read")
    ctx = require_tenant_context()
    agents = await agent_service.list_agents(session, ctx.org_id)
    return [AgentResponse.model_validate(a) for a in agents]


@router.get("/agents/enrollment", response_model=EnrollmentInfoResponse)
async def get_agent_enrollment(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> EnrollmentInfoResponse:
    """Tenant enrollment metadata for Download Agent (never returns raw org_token)."""
    _require_permission("agents:read")
    ctx = require_tenant_context()
    try:
        info = await enrollment_service.enrollment_info(
            session,
            ctx.org_id,
            gateway_url=_gateway_url_for_request(request),
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return EnrollmentInfoResponse(**info)


@router.post("/org-token/rotate", response_model=OrgTokenRotateResponse)
async def rotate_org_token(
    session: AsyncSession = Depends(get_session),
) -> OrgTokenRotateResponse:
    """Rotate org enrollment token and return plaintext once."""
    _require_permission("agents:write")
    ctx = require_tenant_context()
    try:
        org, plaintext = await enrollment_service.rotate_org_token(session, ctx.org_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return OrgTokenRotateResponse(org_id=org.id, org_token=plaintext)


@router.get("/agents/installer/linux")
async def download_linux_installer(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Stream a sealed self-extracting Linux installer (rotates org_token, embeds enrollment)."""
    _require_permission("agents:write")
    ctx = require_tenant_context()
    try:
        org, plaintext = await enrollment_service.rotate_org_token(session, ctx.org_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    gateway = _gateway_url_for_request(request)
    try:
        payload = enrollment_service.build_linux_installer(
            gateway_url=gateway,
            org_id=org.id,
            org_token=plaintext,
            org_name=org.name,
            org_slug=org.slug,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    filename = f"aispm-agent-linux-{org.slug}.run"
    return StreamingResponse(
        iter([payload]),
        media_type="application/x-makeself",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-AISPM-Org-Token": plaintext,
            "X-AISPM-Gateway-URL": gateway,
            "Access-Control-Expose-Headers": "X-AISPM-Org-Token, X-AISPM-Gateway-URL, Content-Disposition",
        },
    )


@router.post("/agents/{agent_id}/revoke")
async def revoke_agent(
    agent_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    _require_permission("agents:write")
    ctx = require_tenant_context()
    ok = await agent_service.revoke(session, ctx.org_id, agent_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return {"status": "revoked", "agent_id": str(agent_id)}


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: UUID,
    session: AsyncSession = Depends(get_session),
    purge_data: bool = Query(
        False,
        description="When true, also delete audit events attributed to this agent.",
    ),
) -> None:
    _require_permission("agents:write")
    ctx = require_tenant_context()
    ok = await agent_service.delete(session, ctx.org_id, agent_id, purge_data=purge_data)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")


@router.get("/audit", response_model=list[AuditEventResponse])
async def list_audit(
    session: AsyncSession = Depends(get_session),
    limit: int = 50,
    cursor: UUID | None = None,
    event_type: str | None = None,
    keyword: str | None = None,
    agent_id: UUID | None = None,
) -> list[AuditEventResponse]:
    _require_permission("audit:read")
    ctx = require_tenant_context()
    events, _ = await audit_service.search(
        session,
        ctx.org_id,
        event_type=event_type,
        keyword=keyword,
        agent_id=agent_id,
        cursor=cursor,
        limit=limit,
    )
    hostnames = await hostname_map_for_agents(
        session, ctx.org_id, {e.agent_id for e in events if e.agent_id}
    )
    return [
        AuditEventResponse(
            id=e.id,
            event_type=e.event_type.value,
            agent_id=e.agent_id,
            hostname=hostnames.get(e.agent_id) if e.agent_id else None,
            provider=(e.metadata_ or {}).get("provider"),
            masked_content=humanize_prompt_text(e.masked_content) or e.masked_content,
            original_content=humanize_prompt_text(
                (e.metadata_ or {}).get("original_content")
            )
            or (e.metadata_ or {}).get("original_content"),
            pii_entities=list((e.metadata_ or {}).get("pii_entities") or []),
            pii_hit_count=int((e.metadata_ or {}).get("pii_hit_count") or 0),
            source=(e.metadata_ or {}).get("source"),
            created_at=e.created_at,
        )
        for e in events
    ]


@router.post("/audit/export", response_model=AuditExportResponse)
async def export_audit(
    session: AsyncSession = Depends(get_session),
    days: int = Query(default=90, ge=1, le=365),
) -> AuditExportResponse:
    _require_permission("audit:export")
    ctx = require_tenant_context()
    csv_data = await audit_service.export_csv(session, ctx.org_id, days=days)
    return AuditExportResponse(
        format="csv",
        row_count=csv_data.count("\n") - 1,
        download_url=f"/admin/v1/audit/export/download?days={days}",
    )


@router.get("/audit/export/download")
async def download_audit_export(
    session: AsyncSession = Depends(get_session),
    days: int = Query(default=90, ge=1, le=365),
) -> PlainTextResponse:
    _require_permission("audit:export")
    ctx = require_tenant_context()
    csv_data = await audit_service.export_csv(session, ctx.org_id, days=days)
    return PlainTextResponse(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_export.csv"},
    )


@router.get("/policies", response_model=list[PolicyResponse])
async def list_policies(session: AsyncSession = Depends(get_session)) -> list[PolicyResponse]:
    _require_permission("policies:read")
    ctx = require_tenant_context()
    result = await session.execute(
        select(Policy).where(Policy.org_id == ctx.org_id).order_by(Policy.created_at.desc())
    )
    return [PolicyResponse.model_validate(p) for p in result.scalars().all()]


@router.get("/pii-detections", response_model=list[PiiDetectionPolicyResponse])
async def list_pii_detections(
    session: AsyncSession = Depends(get_session),
) -> list[PiiDetectionPolicyResponse]:
    """Enterprise PII detection policies — one toggleable card per entity."""
    _require_permission("policies:read")
    ctx = require_tenant_context()
    rows = await policy_engine.list_pii_detection_policies(session, ctx.org_id)
    return [PiiDetectionPolicyResponse.model_validate(r) for r in rows]


@router.put("/pii-detections/{entity_id}", response_model=PiiDetectionPolicyResponse)
async def update_pii_detection(
    entity_id: str,
    body: UpdatePiiDetectionRequest,
    session: AsyncSession = Depends(get_session),
) -> PiiDetectionPolicyResponse:
    _require_permission("policies:write")
    ctx = require_tenant_context()
    try:
        row = await policy_engine.set_pii_detection_enabled(
            session, ctx.org_id, entity_id.upper(), body.enabled
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown PII detection '{entity_id}'",
        ) from None
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    await session.commit()
    return PiiDetectionPolicyResponse.model_validate(row)


@router.post("/policies", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    body: CreatePolicyRequest,
    session: AsyncSession = Depends(get_session),
) -> PolicyResponse:
    _require_permission("policies:write")
    ctx = require_tenant_context()
    policy = Policy(
        org_id=ctx.org_id,
        name=body.name,
        description=body.description,
        rules=body.rules,
        is_default=body.is_default,
        is_active=True,
    )
    session.add(policy)
    await session.commit()
    await session.refresh(policy)
    await policy_engine.invalidate_cache(ctx.org_id)
    return PolicyResponse.model_validate(policy)


@router.put("/policies/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: UUID,
    body: UpdatePolicyRequest,
    session: AsyncSession = Depends(get_session),
) -> PolicyResponse:
    _require_permission("policies:write")
    ctx = require_tenant_context()
    result = await session.execute(
        select(Policy).where(Policy.id == policy_id, Policy.org_id == ctx.org_id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")

    if body.name is not None:
        policy.name = body.name
    if body.description is not None:
        policy.description = body.description
    if body.rules is not None:
        policy.rules = body.rules
    if body.is_active is not None:
        policy.is_active = body.is_active

    await session.commit()
    await session.refresh(policy)
    await policy_engine.invalidate_cache(ctx.org_id)
    return PolicyResponse.model_validate(policy)


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    _require_permission("policies:write")
    ctx = require_tenant_context()
    result = await session.execute(
        select(Policy).where(Policy.id == policy_id, Policy.org_id == ctx.org_id)
    )
    policy = result.scalar_one_or_none()
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    if policy.is_default:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete default policy")
    await session.delete(policy)
    await session.commit()
    await policy_engine.invalidate_cache(ctx.org_id)


@router.get("/users", response_model=list[UserResponse])
async def list_users(session: AsyncSession = Depends(get_session)) -> list[UserResponse]:
    _require_permission("users:read")
    ctx = require_tenant_context()
    result = await session.execute(select(User).where(User.org_id == ctx.org_id))
    return [UserResponse.model_validate(u) for u in result.scalars().all()]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    session: AsyncSession = Depends(get_session),
) -> UserResponse:
    _require_permission("users:write")
    ctx = require_tenant_context()
    existing = await session.execute(
        select(User).where(User.org_id == ctx.org_id, User.email == body.email.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    user = User(
        org_id=ctx.org_id,
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=UserRole(body.role),
        is_active=True,
        email_verified=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return UserResponse.model_validate(user)


@router.get("/llm-configs", response_model=list[LLMConfigResponse])
async def list_llm_configs(session: AsyncSession = Depends(get_session)) -> list[LLMConfigResponse]:
    _require_permission("llm:read")
    ctx = require_tenant_context()
    result = await session.execute(
        select(LLMProviderConfig).where(LLMProviderConfig.org_id == ctx.org_id)
    )
    return [
        LLMConfigResponse(id=c.id, provider=c.provider, is_active=c.is_active)
        for c in result.scalars().all()
    ]


@router.post("/llm-configs", response_model=LLMConfigResponse, status_code=status.HTTP_201_CREATED)
async def upsert_llm_config(
    body: LLMConfigRequest,
    session: AsyncSession = Depends(get_session),
) -> LLMConfigResponse:
    _require_permission("llm:write")
    ctx = require_tenant_context()
    result = await session.execute(
        select(LLMProviderConfig).where(
            LLMProviderConfig.org_id == ctx.org_id,
            LLMProviderConfig.provider == body.provider,
        )
    )
    config = result.scalar_one_or_none()
    if config:
        config.api_key_encrypted = body.api_key
        config.is_active = body.is_active
    else:
        config = LLMProviderConfig(
            org_id=ctx.org_id,
            provider=body.provider,
            api_key_encrypted=body.api_key,
            is_active=body.is_active,
        )
        session.add(config)
    await session.commit()
    await session.refresh(config)
    return LLMConfigResponse(id=config.id, provider=config.provider, is_active=config.is_active)


@router.post("/gdpr/export")
async def gdpr_export(session: AsyncSession = Depends(get_session)) -> dict:
    _require_permission("settings:write")
    ctx = require_tenant_context()
    return await gdpr_service.export_tenant_data(session, ctx.org_id)


@router.post("/gdpr/delete")
async def gdpr_delete(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    _require_permission("settings:write")
    ctx = require_tenant_context()
    await gdpr_service.delete_tenant_data(session, ctx.org_id)
    return {"status": "deleted", "org_id": str(ctx.org_id)}
