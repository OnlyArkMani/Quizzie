from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings

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
    version=settings.VERSION
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
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