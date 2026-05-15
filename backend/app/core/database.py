from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# ─── Connection pool sized for production concurrent load ───────────────────
# pool_size: permanent connections kept alive
# max_overflow: extra connections allowed under burst load
# pool_timeout: seconds to wait for a free connection before raising
# pool_pre_ping: tests connection health before use (prevents stale conn errors)
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,   # recycle connections every 30 min to avoid DB-side timeouts
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
