from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi import Request
from app.core.config import settings

# Ensure all models are imported so SQLAlchemy knows about them before create_all
import app.models  # noqa: F401  — registers User, Exam, Question, Attempt, CheatLog, ProctoringSettings

# Import routers one by one to catch errors
from app.api.v1 import auth
from app.api.v1 import exams
from app.api.v1 import questions
from app.api.v1 import attempts
from app.api.v1 import analytics
from app.api.v1 import monitoring

# Import enhanced_monitoring separately to see any errors
try:
    from app.api.v1 import enhanced_monitoring
    print("✅ Enhanced monitoring imported successfully!")
except Exception as e:
    print(f"❌ Error importing enhanced_monitoring: {e}")
    enhanced_monitoring = None

app = FastAPI(
    title=settings.APP_NAME,
    description="Online Quiz Platform with AI Proctoring",
    version=settings.VERSION,
    redirect_slashes=False,  # Prevent 307 redirects that drop Authorization headers
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    import traceback
    print("--- VALIDATION ERROR ---")
    print(exc.errors())
    print("BODY:", exc.body)
    print("------------------------")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": exc.body},
    )

# CORS — dev localhost origins are always included; add production URLs via CORS_ORIGINS env var
_cors_origins = settings.all_cors_origins
print(f"✅ CORS allowed origins: {_cors_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(exams.router, prefix="/api/v1/exams", tags=["Exams"])
app.include_router(questions.router, prefix="/api/v1/exams", tags=["Questions"])
app.include_router(attempts.router, prefix="/api/v1/attempts", tags=["Attempts"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["Analytics"])
app.include_router(monitoring.router, prefix="/api/v1/monitor", tags=["Monitoring"])

# Add enhanced monitoring if it loaded successfully
if enhanced_monitoring is not None:
    app.include_router(enhanced_monitoring.router, prefix="/api/v1/monitor/enhanced", tags=["Enhanced Monitoring"])
    print("✅ Enhanced monitoring router registered!")
else:
    print("❌ Enhanced monitoring router NOT registered!")

@app.on_event("startup")
def run_migrations():
    """
    Auto-run Alembic migrations on every startup.
    This applies any pending migrations (new columns, tables, etc.) safely.
    Existing data is never destroyed — Alembic is idempotent.
    """
    import subprocess, sys, os
    try:
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=backend_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("✅ Alembic migrations applied successfully.")
            if result.stdout.strip():
                print(result.stdout)
        else:
            print("⚠️  Alembic migration warning (falling back to create_all):")
            print(result.stderr)
            # Fallback: at least create missing tables
            from app.core.database import Base, engine
            Base.metadata.create_all(bind=engine)
            print("✅ Database tables verified / created via create_all.")
    except Exception as e:
        print(f"⚠️  Migration runner error: {e} — falling back to create_all")
        from app.core.database import Base, engine
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables verified / created via create_all.")


@app.get("/")
def root():
    return {
        "message": "Quizzie API is running",
        "version": settings.VERSION,
        "docs": "/docs"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}