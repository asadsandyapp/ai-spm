from uuid import UUID

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_spm.domain.models import LLMProviderConfig

logger = structlog.get_logger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"


class LLMProviderError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class OpenAIAdapter:
    """Org-scoped OpenAI proxy — uses tenant LLM API keys from database."""

    async def get_api_key(self, session: AsyncSession, org_id: UUID) -> str | None:
        result = await session.execute(
            select(LLMProviderConfig.api_key_encrypted).where(
                LLMProviderConfig.org_id == org_id,
                LLMProviderConfig.provider == "openai",
                LLMProviderConfig.is_active.is_(True),
            )
        )
        encrypted = result.scalar_one_or_none()
        if not encrypted:
            return None
        # MVP: keys stored encrypted-at-rest placeholder; production uses KMS envelope encryption
        return encrypted

    async def chat_completion(
        self,
        session: AsyncSession,
        org_id: UUID,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
    ) -> str:
        api_key = await self.get_api_key(session, org_id)
        if not api_key:
            last_user = next(
                (m["content"] for m in reversed(messages) if m.get("role") == "user"),
                "",
            )
            return f"[mock/openai/{model}] No API key configured. Echo: {last_user[:200]}"

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(OPENAI_CHAT_URL, json=payload, headers=headers)
            if response.status_code >= 400:
                logger.error(
                    "openai_error",
                    org_id=str(org_id),
                    status=response.status_code,
                    body=response.text[:500],
                )
                raise LLMProviderError(
                    f"OpenAI API error: {response.status_code}",
                    status_code=response.status_code,
                )
            data = response.json()
            return data["choices"][0]["message"]["content"]
