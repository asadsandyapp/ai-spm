import re
from uuid import UUID

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ai_spm.config import get_settings
from ai_spm.domain.enums import OrganizationStatus
from ai_spm.infrastructure.db.session import get_platform_session
from ai_spm.tenant.context import TenantContext, clear_tenant_context, set_tenant_context
from sqlalchemy import select

from ai_spm.domain.models import Organization

logger = structlog.get_logger(__name__)

SPIFFE_ORG_PATTERN = re.compile(
    r"spiffe://aispm\.io/org/([0-9a-fA-F-]{36})/agent/([0-9a-fA-F-]{36})"
)
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

PUBLIC_PATHS = {
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
}
PUBLIC_PREFIXES = ("/public/v1/",)


def _is_public_path(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def _extract_org_from_mtls_headers(request: Request) -> tuple[UUID, UUID | None] | None:
    org_header = request.headers.get("X-Org-ID")
    agent_header = request.headers.get("X-Agent-ID")
    spiffe_uri = request.headers.get("X-Client-Cert-SAN") or request.headers.get(
        "X-Forwarded-Client-Cert-SAN"
    )

    if spiffe_uri:
        match = SPIFFE_ORG_PATTERN.search(spiffe_uri)
        if match:
            return UUID(match.group(1)), UUID(match.group(2))

    if org_header and UUID_PATTERN.match(org_header):
        agent_id = UUID(agent_header) if agent_header and UUID_PATTERN.match(agent_header) else None
        return UUID(org_header), agent_id

    return None


def _extract_org_from_jwt(request: Request) -> tuple[UUID, UUID, frozenset[str]] | None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        org_id = payload.get("org_id")
        user_id = payload.get("sub")
        permissions = payload.get("permissions", [])
        if org_id and user_id:
            return UUID(org_id), UUID(user_id), frozenset(permissions)
    except (JWTError, ValueError):
        return None
    return None


async def _check_org_active(org_id: UUID) -> OrganizationStatus | None:
    async with get_platform_session() as session:
        result = await session.execute(select(Organization.status).where(Organization.id == org_id))
        row = result.scalar_one_or_none()
        return row


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Extract tenant context from JWT (admin) or mTLS headers (agent) on every request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # CORS preflight requests never carry auth credentials and must reach the
        # CORSMiddleware (which runs after this one) to receive the Access-Control-*
        # headers. Rejecting them here with 401 makes the browser report a generic
        # "network error" on every authenticated call.
        if request.method == "OPTIONS":
            return await call_next(request)

        if _is_public_path(path) or path.startswith("/platform/v1/"):
            return await call_next(request)

        clear_tenant_context()
        ctx: TenantContext | None = None

        if path.startswith("/agent/v1/"):
            mtls_data = _extract_org_from_mtls_headers(request)
            if not mtls_data:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Missing or invalid mTLS tenant context"},
                )
            org_id, agent_id = mtls_data
            ctx = TenantContext(org_id=org_id, auth_source="mtls", agent_id=agent_id)

        elif path.startswith("/admin/v1/"):
            jwt_data = _extract_org_from_jwt(request)
            if not jwt_data:
                if path.endswith("/auth/login") or path.endswith("/auth/refresh"):
                    return await call_next(request)
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Missing or invalid admin JWT"},
                )
            org_id, user_id, permissions = jwt_data
            ctx = TenantContext(
                org_id=org_id,
                auth_source="jwt",
                user_id=user_id,
                permissions=permissions,
            )

        if ctx is not None:
            org_status = await _check_org_active(ctx.org_id)
            if org_status is None:
                return JSONResponse(
                    status_code=status.HTTP_404_NOT_FOUND,
                    content={"detail": "Organization not found"},
                )
            if org_status == OrganizationStatus.SUSPENDED:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Tenant suspended"},
                )
            if org_status in (OrganizationStatus.DELETED, OrganizationStatus.PENDING):
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": f"Organization is {org_status.value}"},
                )

            set_tenant_context(ctx)
            request.state.tenant_context = ctx

        response = await call_next(request)
        clear_tenant_context()
        return response


class OrgIdBodyValidationMiddleware(BaseHTTPMiddleware):
    """Reject requests where body org_id != tenant context (IDOR prevention)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        path = request.url.path
        if not path.startswith(("/admin/v1/", "/agent/v1/")):
            return await call_next(request)

        from ai_spm.tenant.context import get_tenant_context

        ctx = get_tenant_context()
        if ctx is None:
            return await call_next(request)

        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type:
            return await call_next(request)

        body = await request.body()
        if not body:
            return await call_next(request)

        import json

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return await call_next(request)

        if isinstance(data, dict) and "org_id" in data:
            try:
                body_org_id = UUID(str(data["org_id"]))
            except ValueError:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Invalid org_id format"},
                )
            if body_org_id != ctx.org_id:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "org_id mismatch with tenant context"},
                )

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive  # noqa: SLF001
        return await call_next(request)
