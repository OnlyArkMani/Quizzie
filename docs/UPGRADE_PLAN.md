# Quizzie — System-Design Upgrade Plan

Status: **implemented** (September 2026). This file is the index; the reasoning
lives in the ADRs, the pictures in `HLD.md` / `LLD.md`, the numbers in
`BENCHMARKS.md`.

## Why this upgrade exists

The platform claimed "500+ concurrent students". Auditing the code and then
load-testing it showed that claim was not true, and that several exam-integrity
guarantees were only enforced by the browser:

| # | Problem found | How it was found | Severity |
|---|---|---|---|
| 1 | Auto-save was a no-op (server discarded the payload; client sent option *indexes* and its timer reset on every keystroke). A crash before submit lost every answer. | Code audit | Critical |
| 2 | Exam duration enforced only by a client-side countdown; the server accepted submissions up to 24 h late. | Code audit | Critical |
| 3 | The full answer key (`is_correct` on every option) was sent to students. | Code audit (Phase 4) | Critical |
| 4 | 16 simultaneous "Start" clicks created up to 7 active attempts for one student. | `bench_races.py` | High |
| 5 | 16 simultaneous submits → up to 12 "successful" submits and 12 answer rows for one question (double-counted marks). | `bench_races.py` | High |
| 6 | Concurrent violations lost health penalties (worst trial: 15 of 16 penalties lost). | `bench_races.py` | High |
| 7 | **200 simultaneous "Start exam" clicks deadlocked the API** (0/200 succeeded; thread pool and DB pool waiting on each other). | `bench_exam_flow.py` + thread dump | Critical |
| 8 | `async def` routes ran sync DB queries on the event loop: `/health` took up to 5 s during a burst. | `bench_burst.py` | High |
| 9 | Rate limits and flag smoothing lived in per-process dicts — wrong as soon as there are 2 workers. | Code audit | High |
| 10 | Camera/audio health changes (computed in Celery) could never reach the student's WebSocket (different process). | Code audit | Medium |
| 11 | Health "recovery" was client-driven: any client could call `/recover` in a loop and stay at full health. | Code audit (Phase 4) | Medium |
| 12 | Every request queried `users`; no stampede protection on the question cache; Redis pool raised under burst, silently turning cache hits into DB queries. | `bench_burst.py`, stampede test | Medium |

## Scope (what was built), in the order it was done

| Upgrade | ADR | Key idea |
|---|---|---|
| U1 Durable, idempotent auto-save + resume | [0001](adr/0001-durable-idempotent-autosave.md) | `INSERT … ON CONFLICT (attempt_id, question_id) DO UPDATE … WHERE client_seq <= EXCLUDED.client_seq` |
| U2 Server-authoritative deadline | [0002](adr/0002-server-authoritative-deadline.md) | `deadline` column fixed at start; writes rejected after `deadline + grace`; lazy finalization |
| U3 One active attempt per student | [0003](adr/0003-db-enforced-single-active-attempt.md) | Partial unique index; catch `IntegrityError`, return the winner |
| U4 Exactly-once submit | [0004](adr/0004-exactly-once-submit.md) | Compare-and-set `UPDATE … WHERE status='IN_PROGRESS'` + `Idempotency-Key`; SHARE vs row-exclusive lock fences auto-saves |
| U5 Lost-update-free health | [0005](adr/0005-atomic-health-updates.md) | Arithmetic inside the `UPDATE` |
| U6 Distributed rate limiting & smoothing | [0006](adr/0006-redis-sliding-window.md) | Redis sorted-set sliding-window log in one Lua script, Redis clock |
| U7 Cross-process WebSocket fan-out | [0007](adr/0007-pubsub-websocket-fanout.md) | Redis pub/sub of full health snapshots |
| U8 Caching done right | [0008](adr/0008-caching-strategy.md) | User cache-aside, single-flight recompute, answer key stripped per request, invalidate after commit |
| U9 Event-loop & pool discipline | [0009](adr/0009-event-loop-and-connection-discipline.md) | `run_db`: a transaction never outlives the threadpool call that opened it; async `get_db` |

### Round 2 — the bottlenecks that were left

| Upgrade | ADR | Key idea |
|---|---|---|
| U10 Bounded proctoring pipeline | [0010](adr/0010-frame-mailbox-load-shedding.md) | Latest-frame mailbox per attempt: ≤ 1 queued task and ≤ 1 stored frame per student; overload skips frames instead of queueing them; frames downscaled to 640 px |
| U11 Token revocation | [0011](adr/0011-token-revocation.md) | `token_version` in the user row and the JWT; logout / password reset bump it |
| U12 Connection budget & safe boot-time migrations | [0012](adr/0012-connection-budget-and-migrations.md) | Env-configured pools with a stated budget, optional PgBouncer, `pg_advisory_lock` around alembic, idempotent migrations |
| U13 Polling & end-of-exam load | [0013](adr/0013-polling-and-end-of-exam-load.md) | Results → 202 while evaluation is pending (single-flight fallback); health polls served from a Redis snapshot; violation counter instead of `COUNT(*)`; jittered time-up submit |
| U14 Offline answer durability | [0001](adr/0001-durable-idempotent-autosave.md) | Unsaved answers mirrored to localStorage; merged back by `client_seq` on the next load |

Smaller fixes shipped alongside: `question_type` serialised as `"QuestionType.MULTIPLE"` (broke multi-select/coding questions in the UI), stale leaderboard after async evaluation, leaderboard cache ignoring `limit`, examiners able to read other examiners' answer keys, WebSocket blocked by nginx, per-process login rate limits, login rate limit that was effectively global behind nginx (now per account + loose per IP), CI type-check made blocking, `KEYS` → `SCAN`, Redis eviction `allkeys-lru` → `volatile-lru` (it could evict Celery queues), known-default `SECRET_KEY` refused in production, shadowed duplicate `GET /questions` route removed, pre-existing `tsc` error fixed.

## Explicitly out of scope (and why)

| Not done | Why not |
|---|---|
| Kafka / RabbitMQ / Redis Streams | Nothing needs durable, replayable events. Health pushes are snapshots (loss is harmless, see ADR 0007); evaluation already has a queue (Celery). |
| Microservices, Kubernetes | One team, one DB, no independent scaling boundary that the current "API replicas + 2 Celery queues" split doesn't already give. Would add network hops and failure modes with nothing to show for it. |
| Refresh tokens / per-device logout | `token_version` (ADR 0011) covers "log out everywhere" and password resets. Per-device logout would need a `jti` denylist too. |
| Client-side proctoring (MediaPipe in the browser) | The largest remaining compute lever (ADR 0010). Needs a new front-end ML dependency and a false-positive study on real webcams. |
| Table partitioning, UUIDv7 keys, read replicas, per-exam pub/sub channels | 50k-student concerns. Triggers: `responses`/`cheat_logs` past ~50–100M rows or vacuum/index bloat hurting; insert-heavy PK index hot spots; analytics measurably slowing the primary; pub/sub fan-out CPU visible on API processes. None of these is true at 500–5k. |
| Role/id in JWT claims (skip the user lookup) | A deliberate trade-off (ADR 0008): one Redis GET per request vs. role changes waiting for token expiry. A cold start still costs one indexed lookup per student — cheap, not a bottleneck. |
| Periodic sweeper (Celery beat) for abandoned attempts | Lazy finalization on any touch covers correctness; the only visible effect is abandoned attempts staying `IN_PROGRESS` in the DB until someone reads them. |
| Multi-tab conflict UI | Server resolves by `client_seq` (last edit wins); no UI tells the student two tabs are fighting. |
| Rewriting the stack async (asyncpg + SQLAlchemy async) | Would remove the thread pool entirely, but touches every file. `run_db` fixes the actual failure with a fraction of the risk. Revisit if thread-pool contention becomes the bottleneck. |
| Server-side verification of tab-switch / fullscreen events | Fundamentally client-reported in a browser. Documented as a trust-boundary limit, not fixed. |

## Applying the migrations (important for existing local databases)

Migrations 006 and 007 are idempotent and run automatically at boot under an
advisory lock. If your local database was created by the app's `create_all`
fallback (so it has no `alembic_version` row), alembic will try to start from 001
and fail. Check and fix it once:

```bash
cd backend
alembic current                            # nothing printed? then:
alembic stamp 005_add_question_types       # mark the pre-upgrade schema as 005
alembic upgrade head                       # applies 006 + 007 (repairs duplicates first)
```

## Known limitations you should be able to state in an interview

- Single-process benchmark numbers come from a 2-vCPU sandbox that also runs Postgres, Redis and the load generator; use them as *relative* before/after evidence, not capacity numbers.
- Pub/sub delivery is at-most-once by design; a missed push is healed by the snapshot sent on reconnect and a 15 s poll.
- The user cache means a role change / deletion takes up to 60 s to apply (we invalidate on the flows that exist).
- The grace window (30 s) exists to absorb network latency and clock drift at the deadline: saves/submits arriving up to 30 s late are accepted, anything later is dropped (only what was durably saved in time counts). The honest cost: a tampered client gets up to 30 extra seconds. Shrinking the grace trades that away against rejecting honest students on slow networks.
