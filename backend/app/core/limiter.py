"""
One shared slowapi Limiter for HTTP-level rate limits (login, register, ...).

Counters live in Redis (``storage_uri``) so "20 logins/minute" means 20 across
ALL API processes. slowapi's default in-memory storage gives each Uvicorn
worker/replica its own counter, i.e. the real limit silently becomes
20 x number_of_processes.

``in_memory_fallback_enabled`` + ``swallow_errors``: if Redis goes down we
degrade to per-process limits instead of failing every login request.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL,
    in_memory_fallback_enabled=True,
    swallow_errors=True,
    key_prefix="quizzie",
)
