from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.cache import cache

import app.models  # noqa: F401 — registers all models before Alembic

from app.api.v1 import auth, exams, questions, attempts, analytics, monitoring

try:
    from app.api.v1 import enhanced_monitoring
    _enhanced_ok = True
except Exception as e:
    print(f"❌ enhanced_monitoring import failed: {e}")
    _enhanced_ok = False

# ── Rate limiter ───────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

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

@app.on_event("startup")
async def startup():
    # 1. Connect Redis cache
    await cache.connect()

    # 2. Run Alembic migrations
    import subprocess, sys, os
    try:
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=backend_dir, capture_output=True, text=True,
        )
        if result.returncode == 0:
            print("✅ Alembic migrations applied.")
        else:
            print("⚠️  Alembic warning — falling back to create_all:", result.stderr)
            from app.core.database import Base, engine
            Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"⚠️  Migration error: {e} — falling back to create_all")
        from app.core.database import Base, engine
        Base.metadata.create_all(bind=engine)


@app.on_event("shutdown")
async def shutdown():
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
