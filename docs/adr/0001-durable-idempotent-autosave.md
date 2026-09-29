# ADR 0001 — Durable, idempotent auto-save

**Status:** accepted · **Code:** `app/services/attempt_service.py` (`save_responses`, `_upsert`), `frontend/src/features/exam/hooks/useAutoSave.ts`, migration `006`

## Context

Answers lived only in the browser (a Zustand `Map`) until one final `POST /submit`.
`POST /auto-save` validated ownership and returned `{"saved": n}` without writing
anything. The client side was also broken: its `setInterval` was recreated on
every answer change (effect dependencies), so an active student could go minutes
without a save, and it sent option *indexes* rather than option UUIDs.
A closed tab, crashed laptop or dropped connection before submit lost the whole exam.
A `beforeunload` beacon tried to *submit* on unload — it could never authenticate
(`sendBeacon` can't set `Authorization`) and, had it worked, would have submitted
every MCQ answer as blank on a page refresh.

## Options

1. **Write every change immediately** — simplest mental model; one request per click/keystroke (coding answers!) → write storm at exam scale.
2. **Client-only persistence (localStorage)** — survives a refresh, not a device change; the server still isn't the source of truth, and proctored exams need the server to be.
3. **Debounced delta saves, upserted server-side** *(chosen)*.

## Decision

- `responses` gets `UNIQUE (attempt_id, question_id)` — the natural key of an answer — and a `client_seq BIGINT`.
- Auto-save is one statement per request, however many answers it carries:

  ```sql
  INSERT INTO responses (...) VALUES (...), (...)
  ON CONFLICT (attempt_id, question_id) DO UPDATE SET ...
  WHERE responses.client_seq <= EXCLUDED.client_seq
  ```

  Replaying a request changes nothing (**idempotent**). An older save that arrives
  late (retry, slow request, second tab) can't overwrite a newer answer — ordering
  comes from the *client's edit sequence*, not network arrival order.
- The client marks an answer dirty with a new `client_seq` on every edit; saves
  are debounced (1.5 s after the last edit, never more than 10 s after the first
  unsaved one), single-flight, retried with capped exponential backoff and flushed
  with `fetch(..., {keepalive: true})` when the tab is hidden. An entry is cleared
  only if its seq wasn't bumped while the request was in flight.
- `GET /attempts/{id}/state` returns saved answers; the exam page rebuilds from it
  on every load. `POST /attempts/start` is idempotent, so a lost `attemptId`
  (new tab) is recovered by calling it again.
- Answers may only reference questions of the attempt's own exam (422 otherwise).

## Consequences

- A crash, refresh or network drop loses at most the last ~1.5–10 s of edits; the
  benchmark (`bench_exam_flow.py`: 200 students × 20 saves, 10% deliberately stale
  retries, half never submit) found **0 of 2,888 answers lost or stale, 0 duplicate rows**.
- Final submit carries the full state as well (belt and braces); an empty submit
  payload is fine because everything was already saved.
- Write load ≈ students ÷ 10 s (e.g. 500 students ≈ 50 small upserts/s) — ordinary OLTP.
- Every index on `responses` is maintained on every upsert, so the now-redundant
  `idx_responses_attempt_id` (a prefix of the unique index) is dropped.
- **Offline durability (round 2):** answers not yet acknowledged by the server are
  mirrored to `localStorage` (`quizzie:pending:<attempt>`) on every edit. On the next
  load they are merged into the server's state **only if their `client_seq` is
  newer**, and the auto-saver uploads them. So closing the tab while offline no
  longer loses those edits. localStorage (not IndexedDB): tiny data, and a
  synchronous write per edit is exactly the behaviour wanted.
- `client_seq` is wall-clock based (`max(Date.now(), last+1)`), so across two tabs
  "last edit wins" is only as good as the two clocks — acceptable, and stated.
