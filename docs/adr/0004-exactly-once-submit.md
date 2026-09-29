# ADR 0004 — Exactly-once submit (compare-and-set + idempotency key)

**Status:** accepted · **Code:** `AttemptService._close_attempt / submit / save_responses`, `TakeExam.tsx` (`confirmSubmit`)

## Context

`submit_exam` read the status (`IN_PROGRESS?`), then inserted answer rows and set
`SUBMITTED` — check-then-act again, with no uniqueness on answers. With 16
simultaneous submits (double click + network retry + timer auto-submit + health
auto-submit can all fire together): **19 of 20 trials** had several "successful"
submits; worst case **12 successes and 12 answer rows for one question**, which
evaluation summed → inflated scores. Four different code paths close an attempt
(submit, deadline, health = 0, legacy 24 h expiry) and each wrote the status its own way.

## Options

1. **Pessimistic lock:** `SELECT … FOR UPDATE` the attempt, check, write. Correct; holds the lock across the read-check-write round trips.
2. **Optimistic `version` column:** read version, write `WHERE version = :v`, retry on conflict. Correct; more machinery than needed for a one-way state transition.
3. **Compare-and-set on the status itself** *(chosen)*:
   ```sql
   UPDATE exam_attempts SET status='SUBMITTED', submitted_at=..., submit_idempotency_key=:k
   WHERE id = :id AND status = 'IN_PROGRESS'
   ```
   `rowcount == 1` → you won; `0` → someone already closed it.

## Decision

- **One transition function** (`_close_attempt`) used by submit, deadline finalization
  and health auto-submit. Exactly one caller can ever win.
- Submit runs the CAS **first**, then upserts the final answers, then commits — all in
  one transaction. The CAS's row-exclusive lock is held until commit.
- Auto-save takes `SELECT … FOR SHARE` on the attempt row. SHARE locks don't block
  each other (many saves proceed together) but do conflict with the submit's
  exclusive lock, so a save either commits before the submit (and is included) or
  waits, re-checks, sees `SUBMITTED` and gets `409`. No answer can land on a closed
  attempt (`test_autosave_never_lands_after_submit`).
- **Idempotency-Key:** the client generates one UUID per page and reuses it for
  every retry of *that* submit. It's stored on the attempt; a repeat with the same key
  returns `200 {idempotent_replay: true}` instead of `400`. A different key still gets
  `400 "Attempt already submitted"` (a genuinely different submit). No separate
  idempotency table is needed because an attempt can be submitted only once.
- Answer uniqueness (ADR 0001) is the second line of defence: even a bug elsewhere
  can't create a duplicate answer row.

## Consequences

- After: **0 anomalies in 20 × 16-thread trials**; 16 concurrent retries with one key → 16 successes, 1 effect.
- The client can safely retry a submit that timed out (it does, 3× with backoff) — the classic "did my payment go through?" problem, solved the same way payment APIs do.
- Evaluation still runs after commit (Celery, or inline fallback); evaluation is itself re-runnable (it recomputes from stored answers), so a retried Celery task is harmless.
