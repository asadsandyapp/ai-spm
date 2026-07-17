"""PostgreSQL RLS isolation tests — defense-in-depth layer."""

import uuid

import pytest
from sqlalchemy import select, text

from ai_spm.domain.enums import AuditEventType
from ai_spm.domain.models import AuditEvent
from ai_spm.tenant.rls import set_rls_context


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_select(db_session, tenant_a, tenant_b):
    """Without correct org context, tenant-scoped queries return zero rows."""
    await set_rls_context(db_session, tenant_a["org"].id)
    result = await db_session.execute(
        select(AuditEvent).where(AuditEvent.org_id == tenant_b["org"].id)
    )
    rows = result.scalars().all()
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_rls_allows_same_tenant_select(db_session, tenant_a):
    await set_rls_context(db_session, tenant_a["org"].id)
    result = await db_session.execute(
        select(AuditEvent).where(AuditEvent.org_id == tenant_a["org"].id)
    )
    rows = result.scalars().all()
    assert len(rows) >= 1
    assert any("Acme" in (r.masked_content or "") for r in rows)


@pytest.mark.asyncio
async def test_rls_blocks_insert_wrong_org(db_session, tenant_a, tenant_b):
    await set_rls_context(db_session, tenant_a["org"].id)
    event = AuditEvent(
        id=uuid.uuid4(),
        org_id=tenant_b["org"].id,
        event_type=AuditEventType.PROMPT_SUBMITTED,
        masked_content="Should not insert",
    )
    db_session.add(event)
    with pytest.raises(Exception):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_no_org_context_returns_empty(db_session, tenant_a):
    from sqlalchemy.exc import ProgrammingError

    await db_session.execute(text("RESET app.current_org_id"))
    try:
        result = await db_session.execute(select(AuditEvent))
        rows = result.scalars().all()
        assert len(rows) == 0
    except ProgrammingError:
        pass  # FORCE RLS with no matching policy denies access entirely
