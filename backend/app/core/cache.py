"""
Redis cache layer for Quizzie.

Usage:
    from app.core.cache import cache
    await cache.get("key")
    await cache.set("key", value, ttl=60)
    await cache.delete("key")
    await cache.delete_pattern("exam:*")
"""
import json
import logging
from typing import Any, Optional
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(self):
        self._client: Optional[aioredis.Redis] = None

    async def connect(self):
        """Initialise async Redis connection pool."""
        try:
            self._client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50,
            )
            await self._client.ping()
            logger.info("✅ Redis connected: %s", settings.REDIS_URL)
        except Exception as e:
            logger.warning("⚠️  Redis unavailable (%s) — cache disabled, app continues.", e)
            self._client = None

    async def disconnect(self):
        if self._client:
            await self._client.aclose()

    # ── Core ops ──────────────────────────────────────────────────────────────

    async def get(self, key: str) -> Optional[Any]:
        if not self._client:
            return None
        try:
            raw = await self._client.get(key)
            return json.loads(raw) if raw is not None else None
        except Exception as e:
            logger.debug("Cache GET error for %s: %s", key, e)
            return None

    async def set(self, key: str, value: Any, ttl: int = 60) -> bool:
        if not self._client:
            return False
        try:
            await self._client.set(key, json.dumps(value, default=str), ex=ttl)
            return True
        except Exception as e:
            logger.debug("Cache SET error for %s: %s", key, e)
            return False

    async def delete(self, key: str) -> bool:
        if not self._client:
            return False
        try:
            await self._client.delete(key)
            return True
        except Exception as e:
            logger.debug("Cache DEL error for %s: %s", key, e)
            return False

    async def delete_pattern(self, pattern: str):
        """Delete all keys matching a glob pattern (use sparingly)."""
        if not self._client:
            return
        try:
            keys = await self._client.keys(pattern)
            if keys:
                await self._client.delete(*keys)
        except Exception as e:
            logger.debug("Cache DEL pattern error for %s: %s", pattern, e)

    async def increment(self, key: str, ttl: int = 60) -> int:
        """Atomic increment — used for rate limiting counters."""
        if not self._client:
            return 0
        try:
            pipe = self._client.pipeline()
            await pipe.incr(key)
            await pipe.expire(key, ttl)
            results = await pipe.execute()
            return results[0]
        except Exception as e:
            logger.debug("Cache INCR error for %s: %s", key, e)
            return 0

    @property
    def is_available(self) -> bool:
        return self._client is not None


# Singleton — imported everywhere
cache = RedisCache()


# ── Key builders (centralised so we never typo a key) ──────────────────────────

def key_exam_questions(exam_id: str) -> str:
    return f"exam:{exam_id}:questions"

def key_exam_meta(exam_id: str) -> str:
    return f"exam:{exam_id}:meta"

def key_leaderboard(exam_id: str) -> str:
    return f"exam:{exam_id}:leaderboard"

def key_user(user_id: str) -> str:
    return f"user:{user_id}"

def key_rate_limit(ip: str, endpoint: str) -> str:
    return f"ratelimit:{endpoint}:{ip}"

def key_attempt_health(attempt_id: str) -> str:
    return f"attempt:{attempt_id}:health"
