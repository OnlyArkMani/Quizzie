from typing import Callable, TypeVar

from fastapi.concurrency import run_in_threadpool
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
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=1800,   # recycle connections every 30 min to avoid DB-side timeouts
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

async def get_db():
    """
    Request-scoped session.

    Deliberately an ASYNC generator even though the session is sync. FastAPI
    runs the teardown of a *sync* generator dependency in the threadpool,
    after the response is sent. Under a burst that deadlocks: every
    threadpool thread is busy in a route waiting for a pooled DB connection,
    while the connections are held by finished requests whose teardown
    (db.close) is queued waiting for a free thread. The load test hit this at
    200 concurrent students ("QueuePool limit ... timed out").
    As an async generator, setup and teardown run on the event loop, so
    returning the connection never waits for a thread. db.close() is a fast
    pool check-in (plus a ROLLBACK if a transaction is open).
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def release_connection(db) -> None:
    """
    End the session's current (read-only) transaction so its pooled connection
    goes back to the pool NOW, instead of when the request finishes.

    Call this in blocking helpers that run before an ``await`` in an async
    route. Holding a connection across an await is how a burst deadlocks:
    N requests park on an await while each holds 1 of the pool's 30
    connections, and the one request that could make progress (e.g. the cache
    single-flight winner) waits for a connection that never frees up.
    (Found by loadtest/bench_burst.py at 500 concurrent requests.)
    """
    db.rollback()


T = TypeVar("T")


async def run_db(db, fn: Callable[..., T], *args, **kwargs) -> T:
    """
    The unit-of-work rule for request handlers:

        A transaction (and the pooled connection behind it) never outlives
        the threadpool call that opened it.

    ``fn`` does all of a route's blocking DB work and returns PLAIN data
    (dicts / pydantic models, not ORM objects). Before the worker thread is
    handed back, the transaction is ended, so the connection is back in the
    pool while the route serialises and sends its response.

    Why: in the pre-upgrade code a sync route that returned an ORM object kept
    its connection "idle in transaction" until FastAPI finished validating
    the response — and FastAPI validates sync routes' responses IN THE
    THREADPOOL. At 200 simultaneous "Start exam" clicks all 40 threads sat
    waiting for a DB connection while all 30 connections were held by
    finished requests waiting for a thread: a deadlock that only ended in
    30 s pool timeouts (reproduced by loadtest/bench_exam_flow.py; the thread
    dump showed 40/40 threads blocked in pool checkout, event loop idle).
    """
    def unit_of_work():
        try:
            return fn(*args, **kwargs)
        finally:
            release_connection(db)

    return await run_in_threadpool(unit_of_work)
