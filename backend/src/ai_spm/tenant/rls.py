from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.tenant.context import get_tenant_context


async def set_rls_context(session: AsyncSession, org_id: UUID | None = None) -> None:
    """Set PostgreSQL session variable for Row-Level Security policies."""
    ctx = get_tenant_context()
    effective_org_id = org_id or (ctx.org_id if ctx else None)
    if effective_org_id is None:
        await session.execute(text("RESET app.current_org_id"))
        return
    # Session-scoped (is_local=false) so the setting survives commits within the
    # same request; get_db_session's finally block RESETs it before the pooled
    # connection is reused, preventing cross-tenant leakage.
    await session.execute(
        text("SELECT set_config('app.current_org_id', :org_id, false)"),
        {"org_id": str(effective_org_id)},
    )


async def clear_rls_context(session: AsyncSession) -> None:
    await session.execute(text("RESET app.current_org_id"))
