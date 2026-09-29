# ADR 0003 — The database enforces "one active attempt per student per exam"

**Status:** accepted · **Code:** `ExamAttempt.__table_args__` (`uq_one_active_attempt`), `AttemptService.start`, migration `006`

## Context

`start_exam` did *check-then-act*: `SELECT` an in-progress attempt; if none,
`INSERT` one. Two concurrent requests (double click, client retry, two tabs) both
see "none" and both insert. `bench_races.py` with 16 simultaneous starts:
**19 of 20 trials** produced duplicates, worst case **7 active attempts** for one student.

## Options

1. **Lock in the application** (Redis `SET NX` per student+exam, or a Python lock) — Python locks don't span processes; a Redis lock adds a dependency, a TTL to tune, and a failure mode (Redis down → can't start exams) for an invariant the database can hold natively.
2. **`SELECT … FOR UPDATE` before inserting** — you can't lock a row that doesn't exist yet. You'd have to lock a parent (the exam row, or the user row), serialising unrelated students' starts.
3. **`SERIALIZABLE` isolation** — works, but every start pays for retry handling of serialization failures.
4. **Partial unique index** *(chosen)*:
   ```sql
   CREATE UNIQUE INDEX uq_one_active_attempt
   ON exam_attempts (exam_id, student_id) WHERE status = 'IN_PROGRESS';
   ```

## Decision

Let the database be the arbiter. `start()` still does the cheap "resume if one
exists" read; if its `INSERT` then fails with `IntegrityError`, another request
won the race — roll back, re-read, and return the winner. Every caller gets the
same attempt; nobody sees an error.

*Partial* because submitted attempts must not block retakes; only the in-progress
state is unique. The migration first repairs existing duplicates (keeps the
newest, closes the rest — closed, not deleted: their answers and proctoring logs
are evidence).

## Consequences

- After: **0 anomalies in 20 × 16-thread trials**; `test_concurrent_start_creates_exactly_one_attempt` guards it.
- No extra infrastructure; the invariant holds for *every* writer (scripts, admin tools, future services), not just code that remembers to take a lock.
- Postgres-specific (partial indexes), which is fine — we are on Postgres.
- The "loser" does one extra round trip (rollback + re-read) — only under an actual race.
