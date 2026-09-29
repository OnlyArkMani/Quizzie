# ADR 0009 — Event-loop and connection-pool discipline (the 200-student deadlock)

**Status:** accepted · **Code:** `app/core/database.py` (`run_db`, `release_connection`, async `get_db`), hot-path routes in `attempts.py`, `exams.py`, `enhanced_monitoring.py`, `monitoring.py`, `analytics.py`

## Context — two separate failures found by load testing

**1. Blocking the event loop.** 17 `async def` routes called the synchronous
SQLAlchemy session directly. In FastAPI an `async def` route runs *on* the event
loop, so every DB round trip froze the whole process: during a 500-request burst a
trivial `GET /health` took up to **5.1 s**. (Plain `def` routes are fine — FastAPI
runs them in a thread pool.)

**2. A resource deadlock at 200 simultaneous "Start exam" clicks** — present in the
original code too: **0 of 200 succeeded** (160 client timeouts, 40 × `QueuePool limit
… timed out`). The thread dump: all 40 thread-pool threads blocked in
`pool.checkout()`, event loop idle. `pg_stat_activity`: all 30 connections
`idle in transaction`. The cycle:

```
route (sync def, thread) commits, then db.refresh(obj)  -> connection checked out again
route returns the ORM object                             -> thread released, connection still held
FastAPI validates the response of a sync route IN THE THREAD POOL -> needs a thread
all 40 threads: new requests blocked waiting for a connection (pool = 30)
=> finished requests hold connections waiting for threads; threads wait for connections
```
The sync `get_db` generator made it worse: its teardown (`db.close()`) also needs a thread.

## Options

1. **Bigger thread pool / bigger DB pool** — moves the cliff, doesn't remove the cycle; more connections also cost Postgres memory.
2. **Rewrite on async SQLAlchemy + asyncpg** — removes the thread pool altogether; touches every query in the codebase. Not now.
3. **A unit-of-work rule** *(chosen)*.

## Decision

> A transaction — and the pooled connection behind it — never outlives the
> thread-pool call that opened it.

- `run_db(db, fn)`: hot-path routes are `async def` and do *all* their DB work in one
  `fn` that returns plain data (dicts / Pydantic), executed in the thread pool;
  `release_connection` ends the transaction before the thread is handed back.
  Serialisation then happens on the loop with no connection held.
- `get_db` is an **async** generator: session teardown runs on the loop and never waits for a thread.
- `get_current_user` returns a detached snapshot and releases its connection immediately.
- Anything that must `await` between DB steps (cache single-flight, uploads) releases first.
- Remaining blocking calls in async routes (Celery `apply_async`, MediaPipe fallback) go through `run_in_threadpool`.

## Consequences

- 200 simultaneous starts: **0/200 → 200/200**; 200 students × 20 auto-saves complete with no pool errors.
- `/health` during a 500-request burst: max **5.1 s → 0.18–1.1 s**; warm-burst throughput ~1.5–2× (single process, see BENCHMARKS.md).
- The rule is visible in code review: an `async def` route containing `db.query` is a bug.
- Low-traffic examiner routes remain plain `def`; the deadlock needs hundreds of concurrent requests to the same process, which those never see — noted, not converted.
