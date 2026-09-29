# ADR 0005 — Proctoring health: arithmetic inside the UPDATE

**Status:** accepted · **Code:** `app/ai_monitor/health.py` (`record_violations`, `recover`)

## Context

`record_violations` read `current_health` into Python, subtracted, and wrote it
back. Frame analysis and audio analysis for the same attempt run in *different*
Celery worker processes, and client-reported events arrive through the API at the
same time. Two writers read 100, both write 100 − p: one penalty vanishes (a
**lost update**). `bench_races.py`, 16 concurrent `looking_away` violations:
**every trial lost penalties; worst trial kept 1 of 16** (health 95 instead of 20);
285 penalties lost across 20 trials.

## Options

1. **`SELECT … FOR UPDATE`, then compute in Python, then `UPDATE`** — correct; lock held across two round trips; needed only if the new value depends on logic SQL can't express.
2. **Optimistic concurrency (`version` column, retry on conflict)** — correct; retries under exactly the contention we're describing.
3. **Single atomic statement** *(chosen)*:
   ```sql
   UPDATE exam_attempts
   SET current_health = GREATEST(0, COALESCE(current_health, :max) - :penalty),
       cheating_flags = COALESCE(cheating_flags, 0) + :n
   WHERE id = :id
   RETURNING current_health
   ```

## Decision

Use (3). Under READ COMMITTED, when two transactions update the same row the
second waits for the first's row lock, then **re-evaluates the expression against
the committed value** — so both penalties apply. `COALESCE` also folds the old
"lazy-initialise NULL health" step into the same statement. `RETURNING` gives the
new value without a second read. Recovery uses the mirror image
(`LEAST(max, health + amount)`, only while `IN_PROGRESS`).

Zero health then goes through the shared compare-and-set (ADR 0004), so a health
auto-submit racing a manual submit resolves to exactly one close.

## Consequences

- After: **0 lost penalties** (20 × 16-thread trials; `test_concurrent_violations_lose_no_penalty`).
- Rule of thumb this ADR records: *pick the concurrency tool by the shape of the
  update* — a counter/decrement belongs in SQL; a decision that needs application
  logic between read and write needs a lock or a version.
- Recovery was also a trust bug: the client decided when and how much to heal.
  The server now grants at most 3 HP, only after 60 s without violations, at most
  once per 60 s per attempt (a Redis-backed limiter, so switching replicas doesn't help).
