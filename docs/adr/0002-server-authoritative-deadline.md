# ADR 0002 — Server-authoritative exam deadline

**Status:** accepted · **Code:** `AttemptService.is_expired / finalize_if_expired / submit`, `examStore.ts` (`deadlineMs`, `serverOffsetMs`, `tick`), migration `006`

## Context

The exam duration existed only as a browser `setInterval` decrementing a number.
The server never compared submission time with `started_at + duration`. Pausing JS
in DevTools, sleeping the laptop, or editing the store gave unlimited time; the
server accepted submissions for up to 24 h. Separately, the timer hitting zero set
a flag that nothing read — time-up auto-submit never happened.

## Options

1. **Derive the deadline on the fly** (`started_at + exam.duration_minutes`) — no new column, but an examiner editing the duration mid-exam would move the goalposts for students already writing.
2. **Store `deadline` on the attempt at start** *(chosen)* — fixed contract per attempt.
3. **Only a periodic sweeper (Celery beat) that closes expired attempts** — doesn't stop a late write that arrives before the sweep runs; useful *in addition*, not instead.

## Decision

- `exam_attempts.deadline = started_at + duration` is written once, at start.
- Every write path checks the **server** clock: auto-save and frame uploads after
  `deadline + grace` → `409` and the attempt is closed; submit after it → the
  payload is ignored and the attempt is closed with what was auto-saved in time
  (`submitted_at = deadline`, so `time_taken` never exceeds the duration).
- Closing is **lazy**: whichever request first touches an expired attempt
  (start, state, auto-save, results, frame) runs the same compare-and-set as submit.
- `grace = 30 s` absorbs network latency and clock drift at the boundary.
- The browser never counts down on its own. It stores the deadline and
  `serverOffset = server_now − Date.now()` at load and recomputes
  `remaining = deadline − (Date.now() + offset)` every second — a throttled
  background tab or a sleeping laptop can't drift it. At 0 it submits.
- The "exam paused" overlay no longer claims to pause the timer (it can't).

## Consequences

- Tampering with the client clock or JS can at most use the 30 s grace. The
  trade-off of shrinking the grace: honest students on slow links get rejected.
- An attempt nobody touches stays `IN_PROGRESS` in the DB after its deadline
  (lazy finalization). All readers treat it as expired; a beat task could tidy it.
- `now` is injectable in `AttemptService`, so tests move the deadline instead of sleeping.
- Behaviour change to communicate: the proctoring pause doesn't stop the clock.
