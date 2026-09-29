# ADR 0013 — Polling paths and the end-of-exam spike

**Status:** accepted · **Code:** `services/evaluation_dispatch.py`, `attempts.get_results`, `core/events.py` (health snapshot), `enhanced_monitoring.get_attempt_health`, `ai_monitor/health.py`, `TakeExam.tsx`, `ExamResults.tsx`, `HealthBar.tsx`

## Context

Four read/write paths repeat on every student, many times per exam:

| Path | Before | Problem |
|---|---|---|
| `GET /results` while evaluation is queued | ran the **full evaluation inline on every call** | end of exam: queue backs up, every refresh re-grades the attempt, racing the Celery task |
| `GET /health` poll (backstop to the WebSocket) | 4 SQL queries: user, attempt, settings, `COUNT(*)` of cheat_logs | 5k students every 15 s ≈ 330 req/s ≈ 1,300 queries/s for a number the server already pushes |
| every violation / health read | `COUNT(*) FROM cheat_logs` | O(violations so far) on the hottest proctoring path, although `cheating_flags` counts the same thing |
| time-up | every student who started together submits in the same second | a thundering herd of submits, then evaluations, then results polls |

## Decisions

1. **Results: 202 while pending, single-flight fallback.** Every way an attempt
   closes (submit, deadline, health = 0) enqueues evaluation and sets
   `eval:pending:<attempt>` (TTL 60 s). `GET /results` returns `202 {"status":
   "evaluating"}` + `Retry-After` while the marker exists; the client polls with
   backoff. With no marker (Celery down, or the worker died and the marker expired),
   only the poller that wins `lock:eval:<attempt>` evaluates inline; the others get 202.
   Evaluation is idempotent, so a rare double-run is wasted CPU, not wrong data.
   `EVALUATION_MODE=inline` exists for tests and single-process dev.
2. **Health read model in Redis.** Every health change already publishes a full
   snapshot (ADR 0007); it now also `SET`s `attempt:<id>:health` with the owner id.
   A student's poll is served from it after an owner check — zero SQL. On a miss
   the DB result is written back with `SET NX`, so a fill can never overwrite a
   newer published snapshot. Examiners and Redis-down fall back to Postgres. The
   client polls every 60 s while the socket is up, every 10 s while it's down.
3. **Counter, not COUNT.** `record_violations` gets the count from `RETURNING
   cheating_flags` in the same atomic UPDATE (ADR 0005). `COUNT(*)` remains only
   in the repair path.
4. **Jittered time-up submit.** At 0 the UI locks immediately and submits after a
   random 0–10 s delay. That's safe because the server accepts submits for 30 s
   after the deadline and every answer is already auto-saved.

## Consequences

- 200 health polls: **800 SQL → 0**. Results refreshes during a queued evaluation
  do **no evaluation work** (tests assert `EvaluationService` isn't touched).
- Jitter turns a one-second spike of N submits into a 10-second ramp. It spends
  10 s of the 30 s grace, leaving 20 s for retries, which the client uses (3 tries with backoff).
- The marker TTL (60 s) is the answer to "what if the worker crashes?": the
  student waits at most one TTL before the API grades it inline.
