"""11-step prompt lifecycle orchestration — policy, PII, threat, LLM, audit."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.domain.enums import AgentStatus, AuditEventType, PolicyAction, PromptDecision
from ai_spm.domain.models import Agent, AuditEvent
from ai_spm.infrastructure.guardrails.adapter import GuardrailsAdapter
import time

from ai_spm.infrastructure.llm.openai_adapter import LLMProviderError, OpenAIAdapter
from ai_spm.infrastructure.metrics import prompt_pipeline_duration, prompts_blocked_total, prompts_total
from ai_spm.infrastructure.presidio.adapter import PresidioAdapter
from ai_spm.services.policy_engine import PolicyEngine
from ai_spm.tenant.quota import increment_prompt_usage

logger = structlog.get_logger(__name__)


class PromptPipelineError(Exception):
    pass


class PromptPipelineService:
    """Full security pipeline: auth context assumed by caller via TenantContext."""

    def __init__(self) -> None:
        self.policy_engine = PolicyEngine()
        self.pii_engine = PresidioAdapter()
        self.threat_engine = GuardrailsAdapter()
        self.openai = OpenAIAdapter()

    async def process_prompt(
        self,
        session: AsyncSession,
        org_id: UUID,
        agent_id: UUID | None,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
        inspect_only: bool = False,
    ) -> dict:
        start = time.perf_counter()
        try:
            return await self._process_prompt_inner(
                session, org_id, agent_id, provider, model, messages, inspect_only
            )
        finally:
            prompt_pipeline_duration.observe(time.perf_counter() - start)

    async def _process_prompt_inner(
        self,
        session: AsyncSession,
        org_id: UUID,
        agent_id: UUID | None,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
        inspect_only: bool = False,
    ) -> dict:
        combined_text = " ".join(m.get("content", "") for m in messages)

        # Step 1-3: Policy evaluation (deny by default for blocked models/topics)
        allowed, policy_reason = await self.policy_engine.evaluate(
            session, org_id, provider, model, topic=combined_text[:200]
        )
        if not allowed:
            event = await self._create_audit(
                session, org_id, agent_id,
                AuditEventType.POLICY_VIOLATION, combined_text[:500],
                PolicyAction.BLOCK,
                {"reason": policy_reason, "provider": provider, "model": model},
            )
            return {
                "decision": PromptDecision.BLOCKED.value,
                "blocked_reason": policy_reason,
                "block_code": "POLICY_BLOCKED",
                "audit_event_id": event.id,
            }
        prompts_blocked_total.labels(reason="policy").inc()

        # Step 4-5: Inbound threat scan (fail-closed on scanner error)
        try:
            threat = self.threat_engine.scan_inbound(combined_text)
        except Exception as exc:
            logger.error("threat_scan_failed_fail_closed", error=str(exc))
            event = await self._create_audit(
                session, org_id, agent_id,
                AuditEventType.PROMPT_BLOCKED, combined_text[:500],
                PolicyAction.BLOCK,
                {
                    "reason": "Threat scanner unavailable",
                    "fail_closed": True,
                    "provider": provider,
                    "model": model,
                },
            )
            return {
                "decision": PromptDecision.BLOCKED.value,
                "blocked_reason": "Request blocked — security scanner unavailable",
                "block_code": "SCANNER_ERROR",
                "audit_event_id": event.id,
            }

        if threat.is_threat:
            event = await self._create_audit(
                session, org_id, agent_id,
                AuditEventType.THREAT_DETECTED, combined_text[:500],
                PolicyAction.BLOCK,
                {
                    "reason": threat.reason,
                    "threat_type": threat.threat_type,
                    "provider": provider,
                    "model": model,
                },
            )
            return {
                "decision": PromptDecision.BLOCKED.value,
                "blocked_reason": threat.reason,
                "block_code": "THREAT_DETECTED",
                "audit_event_id": event.id,
            }

        # Step 6: PII scan + mask inbound (respect org-enabled detection policies)
        enabled_pii = await self.policy_engine.resolve_enabled_pii_entities(session, org_id)
        masked_messages: list[dict[str, str]] = []
        all_pii: list[str] = []
        try:
            for msg in messages:
                content = msg.get("content", "")
                result = self.pii_engine.scan_and_mask(content, entities=enabled_pii)
                all_pii.extend(result.entities)
                masked_messages.append({**msg, "content": result.masked_text})
        except Exception as exc:
            logger.error("pii_scan_failed_fail_closed", error=str(exc))
            event = await self._create_audit(
                session, org_id, agent_id,
                AuditEventType.PROMPT_BLOCKED, combined_text[:500],
                PolicyAction.BLOCK,
                {
                    "reason": "PII scanner unavailable",
                    "fail_closed": True,
                    "provider": provider,
                    "model": model,
                },
            )
            return {
                "decision": PromptDecision.BLOCKED.value,
                "blocked_reason": "Request blocked — PII scanner unavailable",
                "block_code": "SCANNER_ERROR",
                "audit_event_id": event.id,
            }

        masked_combined = " ".join(m["content"] for m in masked_messages)
        decision = PromptDecision.MASKED if all_pii else PromptDecision.ALLOWED

        # MITM inspect-only: return scan result without calling the LLM.
        if inspect_only:
            event_type = AuditEventType.PII_DETECTED if all_pii else AuditEventType.PROMPT_SUBMITTED
            event = await self._create_audit(
                session, org_id, agent_id, event_type, masked_combined[:2000],
                PolicyAction.ALLOW if decision == PromptDecision.ALLOWED else PolicyAction.ALERT,
                {
                    "pii_entities": list(set(all_pii)),
                    "pii_hit_count": len(all_pii),
                    "provider": provider,
                    "model": model,
                    "source": "agent_mitm",
                    "inspect_only": True,
                },
            )
            await increment_prompt_usage(org_id)
            prompts_total.labels(decision=decision.value).inc()
            return {
                "decision": decision.value,
                "masked_messages": masked_messages,
                "response_content": None,
                "pii_masked": list(set(all_pii)),
                "audit_event_id": event.id,
            }

        # Step 7: Forward to LLM
        try:
            response_content = await self._proxy_llm(
                session, org_id, provider, model, masked_messages
            )
        except PromptPipelineError as exc:
            raise
        except Exception as exc:
            logger.error("llm_proxy_failed", error=str(exc))
            raise PromptPipelineError(str(exc)) from exc

        # Step 8: Response PII leakage scan
        try:
            response_pii = self.pii_engine.scan_and_mask(
                response_content, entities=enabled_pii
            )
            if response_pii.entities:
                response_content = response_pii.masked_text
                all_pii = list(set(all_pii + response_pii.entities))
        except Exception as exc:
            logger.error("response_pii_scan_failed_fail_closed", error=str(exc))
            event = await self._create_audit(
                session, org_id, agent_id,
                AuditEventType.PROMPT_BLOCKED, masked_combined[:2000],
                PolicyAction.BLOCK, {"reason": "Response PII scan failed", "fail_closed": True},
            )
            return {
                "decision": PromptDecision.BLOCKED.value,
                "blocked_reason": "Response blocked — leakage scan failed",
                "block_code": "SCANNER_ERROR",
                "audit_event_id": event.id,
            }

        # Step 9: Outbound threat scan
        outbound_threat = self.threat_engine.scan_outbound(response_content)
        if outbound_threat.is_threat:
            event = await self._create_audit(
                session, org_id, agent_id,
                AuditEventType.THREAT_DETECTED, masked_combined[:2000],
                PolicyAction.BLOCK,
                {"reason": outbound_threat.reason, "phase": "response"},
            )
            return {
                "decision": PromptDecision.BLOCKED.value,
                "blocked_reason": outbound_threat.reason,
                "block_code": "RESPONSE_THREAT",
                "audit_event_id": event.id,
            }

        # Step 10: Audit (masked content only — never store originals)
        event_type = AuditEventType.PII_DETECTED if all_pii else AuditEventType.PROMPT_SUBMITTED
        event = await self._create_audit(
            session, org_id, agent_id, event_type, masked_combined[:2000],
            PolicyAction.ALLOW if decision == PromptDecision.ALLOWED else PolicyAction.ALERT,
            {"pii_entities": list(set(all_pii)), "provider": provider, "model": model},
        )

        await increment_prompt_usage(org_id)

        prompts_total.labels(decision=decision.value).inc()
        return {
            "decision": decision.value,
            "masked_messages": masked_messages,
            "response_content": response_content,
            "pii_masked": list(set(all_pii)),
            "audit_event_id": event.id,
        }

    async def _proxy_llm(
        self,
        session: AsyncSession,
        org_id: UUID,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
    ) -> str:
        if provider == "openai":
            try:
                return await self.openai.chat_completion(session, org_id, model, messages)
            except LLMProviderError as exc:
                raise PromptPipelineError(str(exc)) from exc
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        return f"[{provider}/{model}] Processed securely. Echo: {last_user[:200]}"

    async def _create_audit(
        self,
        session: AsyncSession,
        org_id: UUID,
        agent_id: UUID | None,
        event_type: AuditEventType,
        masked_content: str,
        policy_action: PolicyAction,
        metadata: dict,
    ) -> AuditEvent:
        event = AuditEvent(
            id=uuid4(),
            org_id=org_id,
            event_type=event_type,
            agent_id=agent_id,
            masked_content=masked_content,
            policy_action=policy_action,
            metadata_=metadata,
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event


class AgentService:
    async def register(
        self,
        session: AsyncSession,
        org_id: UUID,
        hostname: str,
        os_version: str | None,
        agent_version: str | None,
        org_token: str,
        org_token_hash: str,
        cert_fingerprint: str | None = None,
    ) -> tuple[Agent, str] | None:
        """Returns (agent, session_token) - the plaintext token is shown to
        the caller exactly once, here, then only ever compared by hash (see
        tenant/middleware.py::_verify_agent_session_token). A fresh token is
        issued on every call, including idempotent re-registration, since
        that's the only channel this token is ever handed out on."""
        from ai_spm.infrastructure.auth.password import generate_token, hash_token
        from ai_spm.tenant.quota import QuotaExceededError, check_agent_quota

        if hash_token(org_token) != org_token_hash:
            return None

        session_token = generate_token(48)
        session_token_hash = hash_token(session_token)

        # Idempotent re-registration: reinstalling the agent on the same machine
        # (same org + hostname) must reuse the existing record instead of creating
        # a new one. Otherwise every reinstall consumes an agent slot and eventually
        # exhausts the org quota (429), which silently disables masking.
        existing_result = await session.execute(
            select(Agent).where(
                Agent.org_id == org_id,
                Agent.hostname == hostname,
                Agent.status != AgentStatus.REVOKED,
            )
        )
        existing = existing_result.scalars().first()
        if existing is not None:
            existing.os_version = os_version
            existing.agent_version = agent_version
            existing.status = AgentStatus.ONLINE
            existing.last_heartbeat_at = datetime.now(UTC)
            existing.session_token_hash = session_token_hash
            if cert_fingerprint:
                existing.cert_fingerprint = cert_fingerprint
            await session.commit()
            await session.refresh(existing)
            return existing, session_token

        try:
            await check_agent_quota(org_id)
        except QuotaExceededError:
            raise

        agent = Agent(
            org_id=org_id,
            hostname=hostname,
            os_version=os_version,
            agent_version=agent_version,
            status=AgentStatus.ONLINE,
            last_heartbeat_at=datetime.now(UTC),
            cert_fingerprint=cert_fingerprint,
            session_token_hash=session_token_hash,
        )
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
        return agent, session_token

    async def heartbeat(self, session: AsyncSession, org_id: UUID, agent_id: UUID) -> str:
        """Return 'ok', 'revoked', or 'missing' so callers can respond precisely.

        'missing' lets the endpoint agent know its record was deleted and it should
        re-register; 'revoked' is an intentional admin action and must not self-heal.
        """
        result = await session.execute(
            select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            return "missing"
        if agent.status == AgentStatus.REVOKED:
            return "revoked"
        agent.status = AgentStatus.ONLINE
        agent.last_heartbeat_at = datetime.now(UTC)
        await session.commit()
        return "ok"

    async def revoke(self, session: AsyncSession, org_id: UUID, agent_id: UUID) -> bool:
        result = await session.execute(
            select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            return False
        agent.status = AgentStatus.REVOKED
        await session.commit()
        return True

    async def delete(self, session: AsyncSession, org_id: UUID, agent_id: UUID) -> bool:
        result = await session.execute(
            select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id)
        )
        agent = result.scalar_one_or_none()
        if not agent:
            return False
        await session.delete(agent)
        await session.commit()
        return True

    async def list_agents(self, session: AsyncSession, org_id: UUID) -> list[Agent]:
        result = await session.execute(
            select(Agent).where(Agent.org_id == org_id).order_by(Agent.created_at.desc())
        )
        return list(result.scalars().all())

    async def mark_offline_stale(self, session: AsyncSession, threshold_seconds: int = 120) -> int:
        """Mark agents offline if no heartbeat within threshold."""
        cutoff = datetime.now(UTC).replace(microsecond=0)
        from datetime import timedelta

        cutoff = cutoff - timedelta(seconds=threshold_seconds)
        result = await session.execute(
            select(Agent).where(
                Agent.status == AgentStatus.ONLINE,
                Agent.last_heartbeat_at < cutoff,
            )
        )
        agents = result.scalars().all()
        for agent in agents:
            agent.status = AgentStatus.OFFLINE
        if agents:
            await session.commit()
        return len(agents)
