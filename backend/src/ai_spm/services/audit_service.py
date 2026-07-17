"""Audit log search, export, and GDPR tenant data operations."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.domain.models import (
    Agent,
    AuditEvent,
    Department,
    LLMProviderConfig,
    Policy,
    User,
)

logger = structlog.get_logger(__name__)


async def hostname_map_for_agents(
    session: AsyncSession, org_id: UUID, agent_ids: set[UUID]
) -> dict[UUID, str]:
    """Return {agent_id: hostname} for the given agents within an org.

    AuditEvent.agent_id is a bare UUID (no FK relationship), so hostnames are
    resolved with a single batched lookup rather than per-row joins.
    """
    if not agent_ids:
        return {}
    result = await session.execute(
        select(Agent.id, Agent.hostname).where(
            Agent.org_id == org_id, Agent.id.in_(agent_ids)
        )
    )
    return {row.id: row.hostname for row in result.all()}


class AuditService:
    async def search(
        self,
        session: AsyncSession,
        org_id: UUID,
        *,
        event_type: str | None = None,
        keyword: str | None = None,
        agent_id: UUID | None = None,
        cursor: UUID | None = None,
        limit: int = 50,
    ) -> tuple[list[AuditEvent], UUID | None]:
        query = (
            select(AuditEvent)
            .where(AuditEvent.org_id == org_id)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(min(limit, 200) + 1)
        )
        if event_type:
            query = query.where(AuditEvent.event_type == event_type)
        if agent_id:
            query = query.where(AuditEvent.agent_id == agent_id)
        if keyword:
            query = query.where(AuditEvent.masked_content.ilike(f"%{keyword}%"))
        if cursor:
            cursor_result = await session.execute(
                select(AuditEvent.created_at).where(AuditEvent.id == cursor)
            )
            cursor_ts = cursor_result.scalar_one_or_none()
            if cursor_ts:
                query = query.where(AuditEvent.created_at <= cursor_ts)

        result = await session.execute(query)
        events = list(result.scalars().all())
        next_cursor = None
        if len(events) > limit:
            events = events[:limit]
            next_cursor = events[-1].id
        return events, next_cursor

    async def export_csv(self, session: AsyncSession, org_id: UUID, days: int = 90) -> str:
        since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        from datetime import timedelta

        since = since - timedelta(days=days)
        result = await session.execute(
            select(AuditEvent)
            .where(AuditEvent.org_id == org_id, AuditEvent.created_at >= since)
            .order_by(AuditEvent.created_at.desc())
            .limit(100_000)
        )
        events = result.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "event_type", "agent_id", "masked_content", "created_at"])
        for e in events:
            writer.writerow([
                str(e.id),
                e.event_type.value,
                str(e.agent_id) if e.agent_id else "",
                (e.masked_content or "")[:500],
                e.created_at.isoformat(),
            ])
        return output.getvalue()


class GDPRService:
    """Tenant data export and erasure per REQ-SaaS-010."""

    async def export_tenant_data(self, session: AsyncSession, org_id: UUID) -> dict:
        users = (await session.execute(select(User).where(User.org_id == org_id))).scalars().all()
        agents = (await session.execute(select(Agent).where(Agent.org_id == org_id))).scalars().all()
        policies = (
            await session.execute(select(Policy).where(Policy.org_id == org_id))
        ).scalars().all()
        audit = (
            await session.execute(
                select(AuditEvent)
                .where(AuditEvent.org_id == org_id)
                .order_by(AuditEvent.created_at.desc())
                .limit(10_000)
            )
        ).scalars().all()
        departments = (
            await session.execute(select(Department).where(Department.org_id == org_id))
        ).scalars().all()

        return {
            "org_id": str(org_id),
            "exported_at": datetime.now(UTC).isoformat(),
            "users": [
                {"id": str(u.id), "email": u.email, "role": u.role.value} for u in users
            ],
            "agents": [
                {"id": str(a.id), "hostname": a.hostname, "status": a.status.value}
                for a in agents
            ],
            "policies": [{"id": str(p.id), "name": p.name, "rules": p.rules} for p in policies],
            "departments": [{"id": str(d.id), "name": d.name} for d in departments],
            "audit_events": [
                {
                    "id": str(e.id),
                    "event_type": e.event_type.value,
                    "masked_content": e.masked_content,
                    "created_at": e.created_at.isoformat(),
                }
                for e in audit
            ],
        }

    async def delete_tenant_data(self, session: AsyncSession, org_id: UUID) -> None:
        """Hard delete tenant-scoped data (retention policy satisfied)."""
        from ai_spm.domain.models import Organization, Subscription, UsageDaily
        from ai_spm.domain.enums import OrganizationStatus

        for model in [AuditEvent, Agent, Policy, User, Department, LLMProviderConfig, UsageDaily]:
            await session.execute(model.__table__.delete().where(model.org_id == org_id))  # type: ignore[attr-defined]

        await session.execute(
            Subscription.__table__.delete().where(Subscription.org_id == org_id)  # type: ignore[attr-defined]
        )
        org_result = await session.execute(
            select(Organization).where(Organization.id == org_id)
        )
        org = org_result.scalar_one_or_none()
        if org:
            org.status = OrganizationStatus.DELETED
            org.name = f"[deleted-{uuid4().hex[:8]}]"
        await session.commit()
        logger.info("tenant_data_deleted", org_id=str(org_id))
