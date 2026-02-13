from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import engine, Base
from app.api.v1 import auth, exams, questions, attempts, analytics, monitoring

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_NAME,
    description="Online Quiz Platform with AI Proctoring",
    version=settings.VERSION
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
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