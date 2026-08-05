import re
from uuid import UUID

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ai_spm.config import get_settings
from ai_spm.domain.enums import OrganizationStatus
from ai_spm.domain.models import Organization
from ai_spm.infrastructure.db.session import get_platform_session
from ai_spm.tenant.context import TenantContext, clear_tenant_context, set_tenant_context

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


def _extract_org_from_spiffe_san(request: Request) -> tuple[UUID, UUID] | None:
    """Real mTLS path: trusts X-Client-Cert-SAN only when it's actually been
    set by a gateway that verified the client certificate. Nothing in this
    repo's deployment does that yet (no Kong mTLS plugin is configured), so
    this is currently dead in practice - kept so a future real mTLS rollout
    is a config change, not a code change."""
    spiffe_uri = request.headers.get("X-Client-Cert-SAN") or request.headers.get(
        "X-Forwarded-Client-Cert-SAN"
    )
    if not spiffe_uri:
        return None
    match = SPIFFE_ORG_PATTERN.search(spiffe_uri)
    if not match:
        return None
    return UUID(match.group(1)), UUID(match.group(2))


def _extract_bare_org_header(request: Request) -> UUID | None:
    """/register only: there's no session token yet to check (this call is
    what issues one), so the org_id header is accepted at face value here -
    the real secret check is register_agent's org_token vs. org_token_hash
    comparison, deeper in the request. Every other /agent/v1/* endpoint must
    go through _verify_agent_session_token instead."""
    org_header = request.headers.get("X-Org-ID")
    if org_header and UUID_PATTERN.match(org_header):
        return UUID(org_header)
    return None


async def _verify_agent_session_token(request: Request) -> tuple[UUID, UUID] | None:
    """The actual authentication check for every /agent/v1/* endpoint other
    than /register: requires X-Org-ID + X-Agent-ID + a bearer token that
    hashes to the specific agent's stored session_token_hash (issued once at
    registration - see AgentService.register). Closes the previous gap
    where those two UUID headers alone, with no secret, were trusted.

    Looking the Agent row up here is also the natural place to reject a
    revoked agent on every authenticated call, not just heartbeat."""
    org_header = request.headers.get("X-Org-ID")
    agent_header = request.headers.get("X-Agent-ID")
    auth_header = request.headers.get("Authorization", "")

    if not (org_header and UUID_PATTERN.match(org_header)):
        return None
    if not (agent_header and UUID_PATTERN.match(agent_header)):
        return None
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    if not token:
        return None

    org_id, agent_id = UUID(org_header), UUID(agent_header)

    from ai_spm.domain.enums import AgentStatus
    from ai_spm.domain.models import Agent
    from ai_spm.infrastructure.auth.password import hash_token

    # All attribute access on `agent` must happen before the session context
    # exits - accessing it afterward on a detached instance raises
    # DetachedInstanceError (caught this via a real test run, not by
    # inspection: get_platform_session() expires instances on scope exit).
    async with get_platform_session() as session:
        result = await session.execute(
            select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id)
        )
        agent = result.scalar_one_or_none()
        if agent is None or agent.status == AgentStatus.REVOKED:
            return None
        if not agent.session_token_hash or hash_token(token) != agent.session_token_hash:
            return None

    return org_id, agent_id


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
            spiffe_data = _extract_org_from_spiffe_san(request)
            if spiffe_data:
                org_id, agent_id = spiffe_data
                ctx = TenantContext(org_id=org_id, auth_source="mtls", agent_id=agent_id)
            elif path == "/agent/v1/register":
                # No session token exists yet - org_token (checked deeper in
                # register_agent) is the real credential for this one call.
                bare_org_id = _extract_bare_org_header(request)
                if bare_org_id is None:
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"detail": "Missing or invalid X-Org-ID"},
                    )
                ctx = TenantContext(org_id=bare_org_id, auth_source="org_token", agent_id=None)
            else:
                session_data = await _verify_agent_session_token(request)
                if session_data is None:
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"detail": "Missing or invalid agent session token"},
                    )
                org_id, agent_id = session_data
                ctx = TenantContext(org_id=org_id, auth_source="session_token", agent_id=agent_id)

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


# PromptRequest.messages has no size constraint, and nothing else in this
# stack checks body size before buffering it - an unbounded body forwarded
# straight into the PII/threat scanners (and, for a real provider, the LLM
# call itself) is a memory/cost DoS. Mirrors the equivalent fix already
# applied to the Rust MITM agent's request handler
# (rust/crates/agent-proxy/src/handler.rs).
MAX_AGENT_BODY_BYTES = 256 * 1024


class MaxBodySizeMiddleware(BaseHTTPMiddleware):
    """Caps request body size for /agent/v1/* POST endpoints. Must be
    registered (via app.add_middleware in main.py) so it runs *before*
    TenantContextMiddleware/OrgIdBodyValidationMiddleware - Starlette runs
    middleware in the reverse of registration order, so this needs to be
    added last, closest to the app - so the body is capped before anything
    downstream ever buffers it."""

    def __init__(self, app, max_bytes: int = MAX_AGENT_BODY_BYTES) -> None:
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method != "POST" or not request.url.path.startswith("/agent/v1/"):
            return await call_next(request)

        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > self.max_bytes:
            return JSONResponse(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                content={"detail": f"request body exceeds {self.max_bytes} byte limit"},
            )

        # Cap while streaming regardless of what Content-Length claims (or
        # if it's absent - chunked transfer-encoding): bounds memory even
        # for an understated/missing header, not just the honest case above.
        chunks: list[bytes] = []
        total = 0
        while True:
            message = await request.receive()
            if message["type"] != "http.request":
                break
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self.max_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content={"detail": f"request body exceeds {self.max_bytes} byte limit"},
                )
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request._receive = receive  # noqa: SLF001
        return await call_next(request)
