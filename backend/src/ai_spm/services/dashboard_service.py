"""Dashboard metrics, security score, and enterprise report aggregations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from collections import Counter

from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.domain.enums import AgentStatus, AuditEventType
from ai_spm.domain.models import Agent, AuditEvent, Policy
from ai_spm.services.severity import classify_event_severity
from ai_spm.services.web_audit_text import humanize_prompt_text

_PROMPT_TYPES = (
    AuditEventType.PROMPT_SUBMITTED,
    AuditEventType.PII_DETECTED,
)
_BLOCK_TYPES = (
    AuditEventType.PROMPT_BLOCKED,
    AuditEventType.POLICY_VIOLATION,
    AuditEventType.THREAT_DETECTED,
)
_REPORT_EVENT_TYPES = (
    AuditEventType.PROMPT_SUBMITTED,
    AuditEventType.PROMPT_BLOCKED,
    AuditEventType.POLICY_VIOLATION,
    AuditEventType.PII_DETECTED,
    AuditEventType.THREAT_DETECTED,
)


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
                    AuditEventType.PII_DETECTED,
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
                "severity": classify_event_severity(e.event_type, e.metadata_ or {}),
                "masked_content": (
                    humanize_prompt_text(e.masked_content) or (e.masked_content or "")
                )[:500],
                "original_content": humanize_prompt_text(
                    (e.metadata_ or {}).get("original_content")
                )
                or (e.metadata_ or {}).get("original_content"),
                "metadata": e.metadata_,
                "pii_entities": list((e.metadata_ or {}).get("pii_entities") or []),
                "pii_hit_count": int((e.metadata_ or {}).get("pii_hit_count") or 0),
                "created_at": e.created_at.isoformat(),
                "agent_id": str(e.agent_id) if e.agent_id else None,
                "hostname": hostnames.get(e.agent_id) if e.agent_id else None,
                "provider": (e.metadata_ or {}).get("provider"),
            }
            for e in events
        ]

    async def get_report(
        self,
        session: AsyncSession,
        org_id: UUID,
        *,
        days: int = 30,
        event_type: str | None = None,
        provider: str | None = None,
        device: str | None = None,
        entity: str | None = None,
    ) -> dict:
        """Tenant-scoped security posture report for a rolling window."""
        days = max(1, min(int(days), 365))
        now = datetime.now(UTC)
        since = now - timedelta(days=days)

        filters = [
            AuditEvent.org_id == org_id,
            AuditEvent.created_at >= since,
            AuditEvent.event_type.in_(_REPORT_EVENT_TYPES),
        ]
        if event_type:
            try:
                et = AuditEventType(event_type)
            except ValueError as exc:
                raise ValueError(f"Invalid event_type: {event_type}") from exc
            if et not in _REPORT_EVENT_TYPES:
                raise ValueError(f"Unsupported event_type: {event_type}")
            filters.append(AuditEvent.event_type == et)
        if provider:
            filters.append(
                cast(AuditEvent.metadata_["provider"], String) == provider
            )
        if entity:
            filters.append(
                AuditEvent.metadata_["pii_entities"].contains([entity])
            )
        if device:
            device_agent_ids = (
                select(Agent.id)
                .where(Agent.org_id == org_id, Agent.hostname == device)
                .scalar_subquery()
            )
            filters.append(AuditEvent.agent_id.in_(device_agent_ids))

        type_counts_result = await session.execute(
            select(AuditEvent.event_type, func.count().label("count"))
            .where(*filters)
            .group_by(AuditEvent.event_type)
        )
        type_counts: dict[str, int] = {
            row.event_type.value: int(row.count) for row in type_counts_result.all()
        }

        prompts = sum(type_counts.get(t.value, 0) for t in _PROMPT_TYPES)
        blocks = sum(type_counts.get(t.value, 0) for t in _BLOCK_TYPES)
        pii = type_counts.get(AuditEventType.PII_DETECTED.value, 0)
        threats = type_counts.get(AuditEventType.THREAT_DETECTED.value, 0)
        policy_violations = type_counts.get(AuditEventType.POLICY_VIOLATION.value, 0)
        prompt_blocked = type_counts.get(AuditEventType.PROMPT_BLOCKED.value, 0)
        total_events = sum(type_counts.values())

        daily_raw = await session.execute(
            select(
                func.date_trunc("day", AuditEvent.created_at).label("day"),
                AuditEvent.event_type,
                func.count().label("count"),
            )
            .where(*filters)
            .group_by("day", AuditEvent.event_type)
            .order_by("day")
        )
        daily_map: dict[str, dict[str, int]] = {}
        for row in daily_raw.all():
            key = row.day.date().isoformat()
            bucket = daily_map.setdefault(
                key,
                {
                    "total": 0,
                    "prompts": 0,
                    "blocks": 0,
                    "pii": 0,
                    "threats": 0,
                    "policy_violations": 0,
                },
            )
            et = row.event_type
            n = int(row.count)
            bucket["total"] += n
            if et in _PROMPT_TYPES:
                bucket["prompts"] += n
            if et in _BLOCK_TYPES:
                bucket["blocks"] += n
            if et == AuditEventType.PII_DETECTED:
                bucket["pii"] += n
            if et == AuditEventType.THREAT_DETECTED:
                bucket["threats"] += n
            if et == AuditEventType.POLICY_VIOLATION:
                bucket["policy_violations"] += n

        # Fill every calendar day in the window so charts have continuous axes.
        daily_activity: list[dict] = []
        for i in range(days - 1, -1, -1):
            d = (now - timedelta(days=i)).date().isoformat()
            bucket = daily_map.get(
                d,
                {
                    "total": 0,
                    "prompts": 0,
                    "blocks": 0,
                    "pii": 0,
                    "threats": 0,
                    "policy_violations": 0,
                },
            )
            daily_activity.append({"date": d, **bucket})

        peak_day = None
        peak_day_count = 0
        for point in daily_activity:
            if point["total"] >= peak_day_count:
                peak_day = point["date"]
                peak_day_count = point["total"]

        provider_result = await session.execute(
            select(
                cast(AuditEvent.metadata_["provider"], String).label("provider"),
                func.count().label("count"),
            )
            .where(*filters)
            .group_by("provider")
            .order_by(func.count().desc())
            .limit(12)
        )
        by_provider = [
            {"name": (row.provider or "unknown").strip() or "unknown", "count": int(row.count)}
            for row in provider_result.all()
            if row.provider and str(row.provider).strip().lower() not in ("", "unknown", "null")
        ]

        device_result = await session.execute(
            select(Agent.hostname, func.count().label("count"))
            .select_from(AuditEvent)
            .join(Agent, Agent.id == AuditEvent.agent_id)
            .where(*filters, Agent.org_id == org_id)
            .group_by(Agent.hostname)
            .order_by(func.count().desc())
            .limit(12)
        )
        by_device = [
            {"name": row.hostname, "count": int(row.count)}
            for row in device_result.all()
            if row.hostname
        ]

        entity_meta = await session.execute(
            select(AuditEvent.metadata_).where(*filters).limit(8000)
        )
        entity_counter: Counter[str] = Counter()
        for (meta,) in entity_meta.all():
            for ent in (meta or {}).get("pii_entities") or []:
                if isinstance(ent, str) and ent.strip():
                    entity_counter[ent.strip()] += 1
        by_entity = [
            {"name": name, "count": count}
            for name, count in entity_counter.most_common(20)
        ]

        source_result = await session.execute(
            select(
                cast(AuditEvent.metadata_["source"], String).label("source"),
                func.count().label("count"),
            )
            .where(*filters)
            .group_by("source")
            .order_by(func.count().desc())
            .limit(8)
        )
        by_source = [
            {
                "name": (row.source or "api").strip() or "api",
                "count": int(row.count),
            }
            for row in source_result.all()
        ]

        agent_status_result = await session.execute(
            select(Agent.status, func.count().label("count"))
            .where(Agent.org_id == org_id)
            .group_by(Agent.status)
        )
        agent_status = {
            row.status.value: int(row.count) for row in agent_status_result.all()
        }
        agents_total = sum(agent_status.values())
        agents_online = agent_status.get(AgentStatus.ONLINE.value, 0)
        agents_offline = agent_status.get(AgentStatus.OFFLINE.value, 0)
        agents_pending = agent_status.get(AgentStatus.PENDING.value, 0)
        agents_revoked = agent_status.get(AgentStatus.REVOKED.value, 0)

        policies_active = await session.scalar(
            select(func.count())
            .select_from(Policy)
            .where(Policy.org_id == org_id, Policy.is_active.is_(True))
        )

        # Unfiltered option lists for the selected window (ignore drill-down filters).
        base_window = [
            AuditEvent.org_id == org_id,
            AuditEvent.created_at >= since,
            AuditEvent.event_type.in_(_REPORT_EVENT_TYPES),
        ]
        opt_events = await session.execute(
            select(AuditEvent.event_type)
            .where(*base_window)
            .distinct()
        )
        opt_providers = await session.execute(
            select(cast(AuditEvent.metadata_["provider"], String).label("provider"))
            .where(*base_window)
            .distinct()
        )
        opt_devices = await session.execute(
            select(Agent.hostname)
            .select_from(AuditEvent)
            .join(Agent, Agent.id == AuditEvent.agent_id)
            .where(*base_window, Agent.org_id == org_id)
            .distinct()
        )
        opt_entities_meta = await session.execute(
            select(AuditEvent.metadata_)
            .where(*base_window, AuditEvent.event_type == AuditEventType.PII_DETECTED)
            .limit(8000)
        )
        opt_entity_names: set[str] = set()
        for (meta,) in opt_entities_meta.all():
            for ent in (meta or {}).get("pii_entities") or []:
                if isinstance(ent, str) and ent.strip():
                    opt_entity_names.add(ent.strip())

        security_score = self._compute_score(
            prompts,
            blocks,
            pii,
            threats,
            agents_total,
            agents_online,
        )
        block_rate_pct = round((blocks / prompts) * 100, 1) if prompts > 0 else 0.0
        pii_rate_pct = round((pii / prompts) * 100, 1) if prompts > 0 else 0.0
        avg_daily = round(total_events / days, 1) if days > 0 else 0.0

        by_event_type = [
            {"name": k, "count": v}
            for k, v in sorted(type_counts.items(), key=lambda x: -x[1])
        ]

        return {
            "days": days,
            "period_start": since.isoformat(),
            "period_end": now.isoformat(),
            "total_events": total_events,
            "prompts": prompts,
            "blocks": blocks,
            "pii_detections": pii,
            "threats": threats,
            "policy_violations": policy_violations,
            "prompt_blocked": prompt_blocked,
            "block_rate_pct": block_rate_pct,
            "pii_rate_pct": pii_rate_pct,
            "security_score": security_score,
            "agents_total": agents_total,
            "agents_online": agents_online,
            "agents_offline": agents_offline,
            "agents_pending": agents_pending,
            "agents_revoked": agents_revoked,
            "policies_active": int(policies_active or 0),
            "avg_daily_events": avg_daily,
            "peak_day": peak_day,
            "peak_day_count": peak_day_count,
            "daily_activity": daily_activity,
            "by_event_type": by_event_type,
            "by_provider": by_provider,
            "by_device": by_device,
            "by_entity": by_entity,
            "by_source": by_source,
            "filter_options": {
                "event_types": sorted(
                    {row.event_type.value for row in opt_events.all()}
                ),
                "providers": sorted(
                    {
                        (row.provider or "").strip()
                        for row in opt_providers.all()
                        if row.provider
                        and str(row.provider).strip().lower()
                        not in ("", "unknown", "null")
                    }
                ),
                "devices": sorted(
                    {row.hostname for row in opt_devices.all() if row.hostname}
                ),
                "entities": sorted(opt_entity_names),
            },
        }

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
