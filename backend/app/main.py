from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import asyncio
import logging

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.cache import cache
from app.core import events
from app.core.limiter import limiter

import app.models  # noqa: F401 — registers all models before Alembic

from app.api.v1 import auth, exams, questions, attempts, analytics, monitoring

try:
    from app.api.v1 import enhanced_monitoring
    _enhanced_ok = True
except Exception as e:
    print(f"❌ enhanced_monitoring import failed: {e}")
    _enhanced_ok = False

logger = logging.getLogger(__name__)

settings.assert_production_safe()

app = FastAPI(
    title=settings.APP_NAME,
    description="Online Quiz Platform with AI Proctoring",
    version=settings.VERSION,
    redirect_slashes=False,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )


# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(auth.router,       prefix="/api/v1/auth",       tags=["Authentication"])
app.include_router(exams.router,      prefix="/api/v1/exams",      tags=["Exams"])
app.include_router(questions.router,  prefix="/api/v1/exams",      tags=["Questions"])
app.include_router(attempts.router,   prefix="/api/v1/attempts",   tags=["Attempts"])
app.include_router(analytics.router,  prefix="/api/v1/analytics",  tags=["Analytics"])
app.include_router(monitoring.router, prefix="/api/v1/monitor",    tags=["Monitoring"])

if _enhanced_ok:
    app.include_router(
        enhanced_monitoring.router,
        prefix="/api/v1/monitor/enhanced",
        tags=["Enhanced Monitoring"],
    )


# ── Startup / shutdown ─────────────────────────────────────────────────────────

_subscriber_stop = asyncio.Event()
_subscriber_task = None


@app.on_event("startup")
async def startup():
    global _subscriber_task
    # 1. Connect Redis cache
    await cache.connect()

    # 1b. Real-time proctoring fan-out: this process subscribes to health
    #     events published by workers / other replicas and forwards them to
    #     the WebSockets it holds. Without Redis, events are delivered
    #     in-process via the local dispatcher.
    if _enhanced_ok:
        manager = enhanced_monitoring.manager
        manager.bind_loop(asyncio.get_running_loop())
        events.set_local_dispatcher(manager.dispatch_threadsafe)
        _subscriber_stop.clear()
        _subscriber_task = asyncio.create_task(
            events.run_subscriber(manager.dispatch, _subscriber_stop)
        )

    # 2. Thread pool size (FastAPI runs sync routes / run_db work here).
    import anyio
    anyio.to_thread.current_default_thread_limiter().total_tokens = settings.THREADPOOL_SIZE

    # 3. Run Alembic migrations — once per deployment, not once per process.
    from fastapi.concurrency import run_in_threadpool
    await run_in_threadpool(_run_migrations_locked)


# Arbitrary constant: the id of the Postgres advisory lock that serialises
# migrations across every process that boots at the same time.
_MIGRATION_LOCK_KEY = 7_202_609_29


def _run_migrations_locked():
    """
    Every Uvicorn worker of every replica runs this at boot. Without a lock,
    WORKERS=4 x 3 replicas = 12 processes race to apply the same migration
    (duplicate-column errors at best, a half-applied schema at worst). A
    session-level pg_advisory_lock makes them queue: the first applies the
    migration, the rest find the schema already at head and exit quickly.
    Uses MIGRATION_DATABASE_URL (a direct connection) because session locks
    don't survive PgBouncer's transaction pooling.
    """
    import os
    import subprocess
    import sys

    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    url = settings.MIGRATION_DATABASE_URL or settings.DATABASE_URL
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lock_engine = create_engine(url, poolclass=NullPool)
    try:
        with lock_engine.connect() as conn:
            conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _MIGRATION_LOCK_KEY})
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "alembic", "upgrade", "head"],
                    cwd=backend_dir, capture_output=True, text=True,
                    env={**os.environ, "DATABASE_URL": url},
                )
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _MIGRATION_LOCK_KEY})
                conn.commit()
    except Exception as e:
        logger.error("Migration step failed before running alembic: %s", e)
        return
    finally:
        lock_engine.dispose()

    if result.returncode == 0:
        print("✅ Alembic migrations applied.")
        return
    # Kept for fresh local databases (the migration chain doesn't create the
    # base tables). On an EXISTING database create_all can't add columns, so a
    # failed migration there must be fixed, not ignored — say so loudly.
    logger.error("Alembic upgrade failed — schema may be behind the code:\n%s", result.stderr[-2000:])
    print("⚠️  Alembic failed — falling back to create_all (only safe on an empty database). "
          "Run `alembic current`; see docs/UPGRADE_PLAN.md 'Applying the migrations'.")
    from app.core.database import Base, engine
    Base.metadata.create_all(bind=engine)


@app.on_event("shutdown")
async def shutdown():
    _subscriber_stop.set()
    if _subscriber_task is not None:
        _subscriber_task.cancel()
        try:
            await _subscriber_task
        except (asyncio.CancelledError, Exception):
            pass
    events.set_local_dispatcher(None)
    await cache.disconnect()


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Quizzie API", "version": settings.VERSION, "docs": "/docs"}


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "cache": "connected" if cache.is_available else "unavailable",
    }
