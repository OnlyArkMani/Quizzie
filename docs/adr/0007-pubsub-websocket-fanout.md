# ADR 0007 — Redis pub/sub fan-out for proctoring WebSockets

**Status:** accepted · **Code:** `app/core/events.py`, `ConnectionManager` in `api/v1/enhanced_monitoring.py`, `main.py` startup

## Context

A student's WebSocket lives in exactly one API process. Health changes are
produced elsewhere: camera/audio analysis in **Celery workers** (always a different
process) and client-reported events on **any API replica**. The old
`ConnectionManager.send()` only reached sockets in its own process, so camera
violations *never* reached the live health bar — the frontend papered over it by
polling every 6 s. Also, the manager stored one socket per attempt, so an examiner
watching an attempt silently replaced the student's socket.

## Options

1. **Keep polling, drop push** — genuinely simple and viable for a single health bar; loses the "instant" feedback the product wants, and every student polling every few seconds is steady load.
2. **Sticky sessions + in-process push** — still can't reach from a Celery worker to a web process.
3. **Durable log (Redis Streams / Kafka)** — replayable, at-least-once; needs consumer groups, offsets, retention. Only worth it if losing a message is harmful.
4. **Redis pub/sub** *(chosen)* — fire-and-forget broadcast to every subscribed API process.

## Decision

- Whoever changes health (worker or API) publishes one message to
  `quizzie:proctoring:health`: `{attempt_id, data: <full health snapshot>, alert?, auto_submitted?}`.
- Every API process runs one subscriber task (started in `startup`, reconnects with
  capped backoff, never dies) and forwards each message to the sockets **it** holds
  for that attempt; other processes ignore it.
- `ConnectionManager` keeps a *set* of sockets per attempt (student + examiners).
- Without Redis (local dev), messages are delivered in-process via a thread-safe
  dispatcher — the old behaviour.

**Why at-most-once is acceptable here:** every message is a *full state snapshot*,
not a delta. A dropped message is superseded by the next one; on (re)connect the
socket is sent the persisted value; the client polls every 15 s as a backstop. If
we ever pushed deltas (e.g. "−5 HP"), a lost message would corrupt client state
and we'd need Streams with acknowledgements instead. That's the line between (3) and (4).

## Consequences

- A violation recorded by a separate process reaches the student's socket
  end-to-end (`test_websocket_receives_update_from_another_process`).
- Cost: one Redis connection per API process for the subscription; each message is
  delivered to all API processes (fine at this fan-out; at thousands of processes
  you'd shard channels, e.g. per exam).
- nginx needed a dedicated `location` for the WebSocket path (it lives under
  `/api/`, whose proxy didn't forward `Upgrade` and had a 120 s read timeout); the
  frontend no longer dials `:8000` directly.
