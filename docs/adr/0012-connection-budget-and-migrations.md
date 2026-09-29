# ADR 0012 — Connection budget, PgBouncer, and migrations under multi-process boot

**Status:** accepted · **Code:** `core/config.py` (`DB_*`, `THREADPOOL_SIZE`, `MIGRATION_DATABASE_URL`), `core/database.py`, `main._run_migrations_locked`, `docker-compose.yml`, migrations `006`/`007`

## Context

1. **Connections.** Each process had a hard-coded pool of 10 + 20 overflow. The
   compose file runs `WORKERS=4` API processes plus 6 Celery processes, so the
   possible peak was 4×30 + 6×30 = 300 connections. Postgres allows 100 by default.
   Adding API replicas "because the API is stateless now" would have exhausted
   Postgres first.
2. **Migrations.** Every API process ran `alembic upgrade head` at boot. With 4
   workers × N replicas booting together, they raced. Measured with 6 concurrent
   boots against a database at revision 005: **2 of 6 failed** ("expected to match
   one row when updating 005 → 006") after running the migration body concurrently.
   The failure path then ran `create_all`, which cannot add columns to existing
   tables — a quiet route to a schema older than the code.

## Decision

**Budget, not guesswork.** Because of the `run_db` rule (ADR 0009), a process only
holds a connection inside a thread-pool call, so it never needs more than
`THREADPOOL_SIZE` connections. Pool sizes are now environment settings, and the
compose file states the sum:

```
backend 4 workers × (10 + 5)       = 60
celery_proctoring 4 × (2 + 0)      =  8     (one task at a time per process)
celery_evaluation 2 × (2 + 0)      =  4     → 72 of 100, 28 spare
```

Past that, add **PgBouncer in transaction-pooling mode** (an optional compose
profile): thousands of client connections share about 40 server connections.
That's compatible with this code because nothing depends on session state
(no session-level `SET`, no prepared statements, no advisory locks on app
connections), with one exception, handled below.

**Migrations run once, under a lock.** `_run_migrations_locked` takes
`pg_advisory_lock(<constant>)` on a dedicated connection, runs alembic, and
releases the lock. Concurrent boots queue: the first migrates, the rest find the
schema at head. The lock is session-level, so it uses `MIGRATION_DATABASE_URL`
(direct to Postgres, bypassing PgBouncer). Migrations 006/007 are idempotent
(`ADD COLUMN IF NOT EXISTS`, guarded constraint creation), so they also succeed on
local databases where the `create_all` fallback already added the columns.

## Consequences

- 6 concurrent boots → **0 failures** on an old-schema database and on a
  `create_all`-built one (both verified).
- The `create_all` fallback stays for empty local databases (the migration chain
  doesn't create the base tables) but now logs an error saying it's only safe on
  an empty database.
- PgBouncer is configured but **not exercised in this repo's tests**; pin the image
  version and test the transaction-mode assumptions before relying on it.
- Better long-term: run migrations as a one-off release step (Render
  `preDeployCommand`, a Kubernetes Job) instead of at app boot. The lock makes
  boot-time migrations safe, not ideal.
