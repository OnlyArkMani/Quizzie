# ADR 0010 — Proctoring uploads: latest-frame mailbox (bounded queue, load shedding)

**Status:** accepted · **Code:** `app/core/frame_mailbox.py`, `monitoring._enqueue`, `proctoring_tasks.analyze_latest_task`, `CameraProctoring.tsx`

## Context

Capacity maths (HLD §5) says proctoring compute is the real ceiling: 500 students ×
one frame / 2 s = 250 frames/s × 200–400 ms of MediaPipe CPU ≈ 75 cores; the
compose file has 4 workers (~13 frames/s). So in practice **workers will fall
behind**. What happened then:

- Every upload became a Celery message carrying the image (base64, +33 %).
- Queue length and Redis memory grew linearly with the backlog, without limit.
  Measured with no consumer, 100 students, 100 KB frames: **995 queued tasks and
  +187 MB of Redis in 20 s**. The Render plan is 25 MB (full in ~3 s); the compose
  Redis is 256 MB (~27 s).
- Frames were analysed in arrival order, so under backlog every verdict was about
  a frame that was already tens of seconds old — useless for live proctoring.

## Options

1. **More workers** — necessary eventually, but doesn't change the failure mode: any burst above capacity still grows the queue without bound.
2. **Object storage for images, reference in the message** — removes bytes from the broker, but the backlog (and staleness) still grows without limit.
3. **Drop tasks when the queue is long** (max length / TTL on messages) — bounded, but drops arbitrary frames, including the newest.
4. **Latest-value mailbox per attempt** *(chosen)* — keep only the newest frame per attempt and at most one queued task per attempt.
5. **Client-side detection** (MediaPipe in the browser; upload only on anomaly) — the biggest lever on compute; not done here (see Consequences).

## Decision

Per `(kind, attempt)` Redis holds one slot: `frame:<kind>:<attempt>` (the newest
payload, TTL 10 s) and `pending:<kind>:<attempt>` (a task is queued).

- **Upload:** `SET frame` (overwrite) and `SET pending NX` in one MULTI/EXEC. If the
  flag was newly set, enqueue a tiny task `{attempt, kind}`. If it was already set,
  do nothing — the queued task will read this newer frame. The older one is
  dropped (*coalesced*) and counted in `stats:coalesced:<kind>`.
- **Worker:** `DEL pending`, then `GETDEL frame`, then analyse. Deleting the flag
  first means a frame that arrives mid-analysis enqueues a fresh task rather than
  being stranded; the worst case is one no-op task.
- `max_retries=0`: retrying would only analyse an even older frame; the next upload re-enqueues.
- If enqueueing fails, the flag is cleared so the next upload retries; without Redis
  the API still falls back to inline analysis.
- **Client:** frames are downscaled to 640 px wide at JPEG q = 0.7 (from native
  1280×720 at q = 0.8): roughly 4× fewer pixels and about 3× fewer bytes.
  MediaPipe's detectors resize to small fixed inputs anyway.
- Optional `CELERY_BROKER_URL` lets the broker live on its own Redis (`noeviction`).

## Consequences

- Same test after the change: **queue capped at 100 (one per student), Redis
  +11.7 MB and flat**; 897 of 997 uploads coalesced. Memory is O(active students),
  not O(backlog). With the smaller frames the +11.7 MB would be about a third of that.
- Under overload each student is analysed **less often, never later**. Graceful
  degradation is visible as a metric, not as an outage.
- The trade-off is explicit: when overloaded we deliberately skip frames. That's
  acceptable for proctoring, where only the current frame matters. It would be
  wrong for data that must be processed in full (for example answers), which is
  why answers never go through this path.
- **Not done:** client-side detection. It would cut server compute by an order of
  magnitude, but it needs a new front-end ML dependency and a false-positive
  evaluation on real webcams. The downscale also needs that evaluation before
  production — a smaller input changes detection behaviour.
