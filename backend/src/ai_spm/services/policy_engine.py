"""Policy evaluation with Redis cache per tenant."""

from __future__ import annotations

import json
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.domain.models import Policy
from ai_spm.infrastructure.cache.redis import cache_get, cache_set

logger = structlog.get_logger(__name__)

POLICY_CACHE_TTL = 300  # 5 minutes

# Sentinel model identifiers that mean "let the provider choose" (e.g. ChatGPT's
# web UI default). These are not user-selected models, so model allow-list
# governance must not block them.
SENTINEL_MODELS = {"", "auto", "unknown", "default"}


class PolicyEngine:
    async def evaluate(
        self,
        session: AsyncSession,
        org_id: UUID,
        provider: str,
        model: str,
        topic: str | None = None,
    ) -> tuple[bool, str | None]:
        policies = await self._load_policies(session, org_id)
        if not policies:
            return True, None

        for policy in policies:
            if isinstance(policy, dict):
                rules = policy.get("rules", {})
                name = policy.get("name", "policy")
            else:
                rules = policy.get("rules", {}) if hasattr(policy, "get") else {}
                name = "policy"

            allowed_models = rules.get("models", {}).get("allowed", [])
            model_norm = (model or "").strip().lower()
            if allowed_models and model_norm not in SENTINEL_MODELS and model not in allowed_models:
                return False, f"Model '{model}' not permitted by policy '{name}'"

            blocked_topics = rules.get("topics", {}).get("blocked", [])
            if topic and blocked_topics:
                topic_lower = topic.lower()
                for blocked in blocked_topics:
                    if blocked.lower() in topic_lower:
                        return False, f"Topic blocked by policy '{name}': {blocked}"

            blocked_providers = rules.get("providers", {}).get("blocked", [])
            if blocked_providers and provider in blocked_providers:
                return False, f"Provider '{provider}' blocked by policy '{name}'"

        return True, None

    async def _load_policies(
        self, session: AsyncSession, org_id: UUID
    ) -> list[dict]:
        cache_key = "policies:active"
        try:
            cached = await cache_get(org_id, cache_key)
            if cached:
                return json.loads(cached)
        except Exception as exc:
            logger.warning("policy_cache_miss", org_id=str(org_id), error=str(exc))

        result = await session.execute(
            select(Policy)
            .where(Policy.org_id == org_id, Policy.is_active.is_(True))
            .order_by(Policy.is_default.desc())
        )
        policies = result.scalars().all()
        serialized = [
            {"name": p.name, "rules": p.rules or {}, "id": str(p.id)} for p in policies
        ]
        try:
            await cache_set(org_id, cache_key, json.dumps(serialized), POLICY_CACHE_TTL)
        except Exception as exc:
            logger.warning("policy_cache_set_failed", org_id=str(org_id), error=str(exc))
        return serialized

    async def invalidate_cache(self, org_id: UUID) -> None:
        from ai_spm.infrastructure.cache.redis import cache_delete

        try:
            await cache_delete(org_id, "policies:active")
        except Exception as exc:
            logger.warning("policy_cache_invalidate_failed", org_id=str(org_id), error=str(exc))
