from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai_spm.config import get_settings
from ai_spm.tenant.context import TenantContext, get_tenant_context, set_tenant_context
from ai_spm.tenant.rls import set_rls_context

settings = get_settings()

TENANT_DB_ROLE = "aispm_app"

engine = create_async_engine(
    str(settings.database_url),
    echo=settings.debug,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def _activate_tenant_role(session: AsyncSession) -> None:
    """Use non-owner DB role so PostgreSQL RLS policies apply."""
    await session.execute(text(f"SET ROLE {TENANT_DB_ROLE}"))


async def _reset_db_role(session: AsyncSession) -> None:
    await session.execute(text("RESET ROLE"))


@asynccontextmanager
async def get_db_session(org_id: UUID | None = None) -> AsyncGenerator[AsyncSession, None]:
    """Database session with tenant role + RLS context.

    Connections are pooled, so a prior user of this connection may have left
    ``row_security`` or ``ROLE`` in an unexpected state (especially if their
    transaction aborted before cleanup). We therefore establish the full
    required state deterministically at the START of the session rather than
    relying on best-effort ``finally`` cleanup: reset to owner, force
    ``row_security = on`` (so the non-owner tenant role cannot accidentally run
    with RLS disabled), then switch to the tenant role and bind the org id.
    """
    async with async_session_factory() as session:
        try:
            await _reset_db_role(session)
            await session.execute(text("SET row_security = on"))
            await _activate_tenant_role(session)
            await set_rls_context(session, org_id)
            yield session
        finally:
            await _safe_reset(session)


@asynccontextmanager
async def get_platform_session() -> AsyncGenerator[AsyncSession, None]:
    """Session for cross-tenant operations (auth, platform admin) — bypasses RLS."""
    async with async_session_factory() as session:
        try:
            await _reset_db_role(session)
            await session.execute(text("SET row_security = off"))
            yield session
        finally:
            await _safe_reset(session)


async def _safe_reset(session: AsyncSession) -> None:
    """Best-effort connection cleanup that never raises.

    If the transaction aborted, DDL/SET statements would fail with
    ``InFailedSQLTransactionError``; rolling back first restores a usable
    connection. The next user of this pooled connection re-establishes its own
    state at session start, so this cleanup is defensive, not load-bearing.
    """
    try:
        await session.rollback()
    except Exception:  # noqa: BLE001 - cleanup must not mask the real error
        pass
    try:
        await session.execute(text("RESET app.current_org_id"))
        await session.execute(text("RESET ROLE"))
        await session.execute(text("SET row_security = on"))
    except Exception:  # noqa: BLE001 - state is re-established on next checkout
        pass


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — uses request tenant context for RLS.

    Reads the tenant context from ``request.state`` (set by TenantContextMiddleware
    and carried reliably on the request scope). The ContextVar is only used as a
    fallback because it does not reliably propagate through Starlette's
    BaseHTTPMiddleware into dependency resolution, which previously left
    ``app.current_org_id`` unset and caused RLS to reject tenant-scoped writes.
    """
    ctx: TenantContext | None = getattr(request.state, "tenant_context", None)
    if ctx is None:
        ctx = get_tenant_context()
    elif get_tenant_context() is None:
        # Re-bind the ContextVar in this execution context so downstream calls to
        # require_tenant_context()/get_tenant_context() stay consistent.
        set_tenant_context(ctx)

    org_id = ctx.org_id if ctx else None
    async with get_db_session(org_id) as session:
        yield session
