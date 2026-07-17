from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.core.schemas import (
    AgentRegisterRequest,
    AgentRegisterWithCertResponse,
    AgentResponse,
    AgentUpdateCheckResponse,
    PromptRequest,
    PromptResponse,
)
from ai_spm.domain.enums import AgentStatus, AuditEventType
from ai_spm.domain.models import Agent, Organization
from ai_spm.infrastructure.db.session import get_session
from ai_spm.services.cert_service import CertService
from ai_spm.services.prompt_pipeline import AgentService, PromptPipelineError, PromptPipelineService
from ai_spm.tenant.context import require_tenant_context
from ai_spm.tenant.quota import QuotaExceededError

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/agent/v1", tags=["agent"])
agent_service = AgentService()
prompt_service = PromptPipelineService()
cert_service = CertService()

AGENT_VERSION = "0.2.0"


@router.post("/register", response_model=AgentRegisterWithCertResponse, status_code=status.HTTP_201_CREATED)
async def register_agent(
    body: AgentRegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> AgentRegisterWithCertResponse:
    ctx = require_tenant_context()

    org_result = await session.execute(select(Organization).where(Organization.id == ctx.org_id))
    org = org_result.scalar_one_or_none()
    if not org or not org.org_token_hash:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid organization")

    try:
        agent = await agent_service.register(
            session,
            org_id=ctx.org_id,
            hostname=body.hostname,
            os_version=body.os_version,
            agent_version=body.agent_version or AGENT_VERSION,
            org_token=body.org_token,
            org_token_hash=org.org_token_hash,
        )
    except QuotaExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc

    if not agent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid org token")

    try:
        cert_info = cert_service.issue_agent_cert(ctx.org_id, agent.id, csr_pem=body.csr_pem)
        agent.cert_fingerprint = cert_info["cert_fingerprint"]
        await session.commit()
        cert_response_fields = {
            "certificate_pem": cert_info["certificate_pem"],
            "private_key_pem": cert_info["private_key_pem"],
            "ca_certificate_pem": cert_info["ca_certificate_pem"],
            "cert_expires_at": cert_info["expires_at"],
        }
    except Exception as exc:
        logger.exception(
            "agent_cert_issuance_failed",
            org_id=str(ctx.org_id),
            agent_id=str(agent.id),
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to issue agent mTLS certificate",
        ) from exc

    return AgentRegisterWithCertResponse(
        id=agent.id,
        org_id=agent.org_id,
        hostname=agent.hostname,
        status=agent.status.value,
        os_version=agent.os_version,
        agent_version=agent.agent_version,
        last_heartbeat_at=agent.last_heartbeat_at,
        **cert_response_fields,
    )


@router.post("/heartbeat")
async def heartbeat(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    ctx = require_tenant_context()
    if not ctx.agent_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent ID required")

    result = await agent_service.heartbeat(session, ctx.org_id, ctx.agent_id)
    if result == "revoked":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent revoked")
    if result == "missing":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return {"status": "ok"}


@router.post("/unregister", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_agent(session: AsyncSession = Depends(get_session)) -> None:
    """Endpoint self-removal after local uninstall — deletes the agent fleet row."""
    ctx = require_tenant_context()
    if not ctx.agent_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent ID required")
    ok = await agent_service.delete(session, ctx.org_id, ctx.agent_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")


@router.post("/prompt", response_model=PromptResponse)
async def submit_prompt(
    body: PromptRequest,
    session: AsyncSession = Depends(get_session),
) -> PromptResponse:
    ctx = require_tenant_context()
    try:
        result = await prompt_service.process_prompt(
            session,
            org_id=ctx.org_id,
            agent_id=ctx.agent_id,
            provider=body.provider,
            model=body.model,
            messages=body.messages,
            inspect_only=body.inspect_only,
        )
    except PromptPipelineError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return PromptResponse(**result)


@router.get("/updates/check", response_model=AgentUpdateCheckResponse)
async def check_updates(session: AsyncSession = Depends(get_session)) -> AgentUpdateCheckResponse:
    ctx = require_tenant_context()
    if not ctx.agent_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent ID required")

    result = await session.execute(
        select(Agent).where(Agent.id == ctx.agent_id, Agent.org_id == ctx.org_id)
    )
    agent = result.scalar_one_or_none()
    current = agent.agent_version if agent else "0.0.0"
    update_available = _version_lt(current or "0.0.0", AGENT_VERSION)

    return AgentUpdateCheckResponse(
        current_version=current or "0.0.0",
        latest_version=AGENT_VERSION,
        update_available=update_available,
        download_url=f"/agent/v1/updates/{AGENT_VERSION}/download" if update_available else None,
    )


@router.get("/updates/{version}/download")
async def download_update(version: str) -> dict[str, str]:
    require_tenant_context()
    return {
        "version": version,
        "message": "MSI packages served from MinIO in production",
        "minio_path": f"/{version}/aispm-agent.msi",
    }


def _version_lt(current: str, latest: str) -> bool:
    def parse(v: str) -> list[int]:
        return [int(x) for x in v.split(".")]

    try:
        return parse(current) < parse(latest)
    except ValueError:
        return True
