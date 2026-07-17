from uuid import UUID

import redis.asyncio as aioredis

from ai_spm.config import get_settings

_settings = get_settings()
_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(str(_settings.redis_url), decode_responses=True)
    return _redis


def tenant_key(org_id: UUID, key: str) -> str:
    return f"tenant:{org_id}:{key}"


async def cache_get(org_id: UUID, key: str) -> str | None:
    redis = await get_redis()
    return await redis.get(tenant_key(org_id, key))


async def cache_set(org_id: UUID, key: str, value: str, ttl_seconds: int = 3600) -> None:
    redis = await get_redis()
    await redis.set(tenant_key(org_id, key), value, ex=ttl_seconds)


async def cache_delete(org_id: UUID, key: str) -> None:
    redis = await get_redis()
    await redis.delete(tenant_key(org_id, key))


async def rate_limit_check(key: str, limit: int, window_seconds: int = 3600) -> bool:
    """Returns True if under limit, False if exceeded."""
    redis = await get_redis()
    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, window_seconds)
    return current <= limit
