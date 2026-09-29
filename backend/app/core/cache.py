"""
Redis cache layer for Quizzie.

Usage:
    from app.core.cache import cache
    await cache.get("key")
    await cache.set("key", value, ttl=60)
    await cache.delete("key")
    await cache.delete_pattern("exam:*")
"""
import asyncio
import json
import logging
import uuid
from typing import Any, Awaitable, Callable, Optional
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger(__name__)


class RedisCache:
    def __init__(self):
        self._client: Optional[aioredis.Redis] = None

    async def connect(self):
        """Initialise async Redis connection pool."""
        try:
            # Pool sizing matters under burst. The old pool (max 50, default
            # non-blocking) raised "Too many connections" once 50 commands were
            # in flight — and our error handling turned that into a silent
            # cache MISS, i.e. a DB query, exactly under the burst the cache
            # exists for (found by the stampede test: 100 concurrent readers →
            # 51 DB computes instead of 1). A BlockingConnectionPool fixed the
            # test but, on redis-py 5.0.1, leaked connections under overload in
            # the 500-user load test (the process stayed at 8 s/request after
            # the burst). So: a non-blocking pool sized for peak concurrency.
            # Redis handles thousands of clients; 512 per API process is cheap.
            self._client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
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
        """
        Delete all keys matching a glob pattern (use sparingly).
        SCAN, not KEYS: KEYS is O(N) and blocks single-threaded Redis for every
        other client while it walks the whole keyspace.
        """
        if not self._client:
            return
        try:
            batch = []
            async for k in self._client.scan_iter(match=pattern, count=500):
                batch.append(k)
                if len(batch) >= 500:
                    await self._client.delete(*batch)
                    batch = []
            if batch:
                await self._client.delete(*batch)
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

    # ── Stampede-safe read-through ────────────────────────────────────────────

    # Delete the lock only if we still own it (it may have expired and been
    # taken by someone else in the meantime).
    _RELEASE_LUA = """
    if redis.call('GET', KEYS[1]) == ARGV[1] then
      return redis.call('DEL', KEYS[1])
    end
    return 0
    """

    async def get_or_compute(
        self,
        key: str,
        ttl: int,
        compute: Callable[[], Awaitable[Any]],
        lock_ttl: int = 10,
    ) -> Any:
        """
        Cache-aside with single-flight recompute ("dog-pile" protection).

        When a hot key is missing — cold start, or TTL expiry at the moment 500
        students open the exam — plain cache-aside lets EVERY concurrent miss
        query the database. Here only the request holding ``lock:<key>``
        (SET NX EX) recomputes; everyone else polls the cache and reads its
        result. If the holder dies, its lock expires after ``lock_ttl`` and the
        next waiter takes over — so there's still at most one recompute at a
        time. If Redis itself errors we compute directly (availability first).
        """
        value = await self.get(key)
        if value is not None:
            return value
        if not self._client:
            return await compute()

        lock_key = f"lock:{key}"
        token = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        give_up_at = loop.time() + lock_ttl * 2
        delay = 0.01
        while True:
            try:
                got_lock = await self._client.set(lock_key, token, nx=True, ex=lock_ttl)
            except Exception:
                return await compute()

            if got_lock:
                try:
                    # Re-check: the previous holder may have filled it between
                    # our miss and our lock.
                    value = await self.get(key)
                    if value is None:
                        value = await compute()
                        await self.set(key, value, ttl=ttl)
                    return value
                finally:
                    try:
                        await self._client.eval(self._RELEASE_LUA, 1, lock_key, token)
                    except Exception:
                        pass

            await asyncio.sleep(delay)
            delay = min(delay * 2, 0.1)
            value = await self.get(key)
            if value is not None:
                return value
            if loop.time() > give_up_at:
                return await compute()

    @property
    def is_available(self) -> bool:
        return self._client is not None

    @property
    def raw_client(self) -> Optional[aioredis.Redis]:
        """The underlying async client (for Lua scripts, pub/sub, SET NX)."""
        return self._client


# Singleton — imported everywhere
cache = RedisCache()


def invalidate_sync(*keys: str) -> None:
    """Delete cache keys from blocking code (threadpool routes, workers)."""
    from app.core.redis_client import get_sync_redis, mark_failed

    client = get_sync_redis()
    if client is None or not keys:
        return
    try:
        client.delete(*keys)
    except Exception as e:
        logger.debug("Cache sync DEL error for %s: %s", keys, e)
        mark_failed()


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
