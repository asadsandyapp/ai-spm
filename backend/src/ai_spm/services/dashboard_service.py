"""Dashboard metrics and security score computation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.domain.enums import AgentStatus, AuditEventType
from ai_spm.domain.models import Agent, AuditEvent, UsageDaily


class DashboardService:
    async def get_metrics(self, session: AsyncSession, org_id: UUID) -> dict:
        now = datetime.now(UTC)
        day_ago = now - timedelta(hours=24)
        week_ago = now - timedelta(days=7)

        prompts_24h = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.org_id == org_id,
                AuditEvent.created_at >= day_ago,
                AuditEvent.event_type.in_([
                    AuditEventType.PROMPT_SUBMITTED,
                    AuditEventType.PII_DETECTED,
                ]),
            )
        )

        blocks_24h = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.org_id == org_id,
                AuditEvent.created_at >= day_ago,
                AuditEvent.event_type.in_([
                    AuditEventType.PROMPT_BLOCKED,
                    AuditEventType.POLICY_VIOLATION,
                    AuditEventType.THREAT_DETECTED,
                ]),
            )
        )

        pii_24h = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.org_id == org_id,
                AuditEvent.created_at >= day_ago,
                AuditEvent.event_type == AuditEventType.PII_DETECTED,
            )
        )

        threats_24h = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.org_id == org_id,
                AuditEvent.created_at >= day_ago,
                AuditEvent.event_type == AuditEventType.THREAT_DETECTED,
            )
        )

        total_agents = await session.scalar(
            select(func.count()).select_from(Agent).where(Agent.org_id == org_id)
        )
        online_agents = await session.scalar(
            select(func.count())
            .select_from(Agent)
            .where(Agent.org_id == org_id, Agent.status == AgentStatus.ONLINE)
        )

        security_score = self._compute_score(
            prompts_24h or 0,
            blocks_24h or 0,
            pii_24h or 0,
            threats_24h or 0,
            total_agents or 0,
            online_agents or 0,
        )

        daily_activity = await self._daily_activity(session, org_id, week_ago)

        return {
            "prompts_24h": prompts_24h or 0,
            "blocks_24h": blocks_24h or 0,
            "pii_detections_24h": pii_24h or 0,
            "threats_24h": threats_24h or 0,
            "agents_total": total_agents or 0,
            "agents_online": online_agents or 0,
            "security_score": security_score,
            "daily_activity": daily_activity,
        }

    async def get_threats(
        self, session: AsyncSession, org_id: UUID, limit: int = 50
    ) -> list[dict]:
        result = await session.execute(
            select(AuditEvent)
            .where(
                AuditEvent.org_id == org_id,
                AuditEvent.event_type.in_([
                    AuditEventType.THREAT_DETECTED,
                    AuditEventType.POLICY_VIOLATION,
                    AuditEventType.PROMPT_BLOCKED,
                ]),
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(min(limit, 100))
        )
        events = result.scalars().all()

        agent_ids = {e.agent_id for e in events if e.agent_id}
        hostnames: dict = {}
        if agent_ids:
            host_result = await session.execute(
                select(Agent.id, Agent.hostname).where(
                    Agent.org_id == org_id, Agent.id.in_(agent_ids)
                )
            )
            hostnames = {row.id: row.hostname for row in host_result.all()}

        return [
            {
                "id": str(e.id),
                "event_type": e.event_type.value,
                "severity": "high" if e.event_type == AuditEventType.THREAT_DETECTED else "medium",
                "masked_content": (e.masked_content or "")[:200],
                "metadata": e.metadata_,
                "created_at": e.created_at.isoformat(),
                "agent_id": str(e.agent_id) if e.agent_id else None,
                "hostname": hostnames.get(e.agent_id) if e.agent_id else None,
                "provider": (e.metadata_ or {}).get("provider"),
            }
            for e in events
        ]

    async def _daily_activity(
        self, session: AsyncSession, org_id: UUID, since: datetime
    ) -> list[dict]:
        result = await session.execute(
            select(
                func.date_trunc("day", AuditEvent.created_at).label("day"),
                func.count().label("count"),
            )
            .where(AuditEvent.org_id == org_id, AuditEvent.created_at >= since)
            .group_by("day")
            .order_by("day")
        )
        return [
            {"date": row.day.date().isoformat(), "count": row.count}
            for row in result.all()
        ]

    def _compute_score(
        self,
        prompts: int,
        blocks: int,
        pii: int,
        threats: int,
        total_agents: int,
        online_agents: int,
    ) -> int:
        score = 100
        if prompts > 0:
            block_rate = blocks / prompts
            score -= min(30, int(block_rate * 100))
        score -= min(25, threats * 5)
        score -= min(15, pii * 2)
        if total_agents > 0:
            coverage = online_agents / total_agents
            score -= int((1 - coverage) * 20)
        return max(0, min(100, score))
