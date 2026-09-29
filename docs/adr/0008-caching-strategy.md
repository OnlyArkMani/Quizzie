# ADR 0008 — Caching: what, where, and how it stays correct

**Status:** accepted · **Code:** `app/core/cache.py` (`get_or_compute`, `invalidate_sync`), `api/deps.py` (user cache), `api/v1/exams.py`

## Context

- `GET /exams/{id}/questions` was cached, but the exam status/owner check before it
  hit Postgres on every request, and **every** authenticated request looked the user
  up in Postgres. Warm-cache burst of 500 loads: **1,000 SQL statements**.
- On a cold/expired key every concurrent miss recomputed (no stampede protection).
  The README's "500 students = 1 DB query" was only true because the endpoint
  blocked the event loop and so ran requests one at a time.
- The async Redis pool (max 50) *raised* when exhausted; our error handling turned
  that into a cache miss → a DB query, precisely under burst (stampede test: 100
  concurrent readers → 51 computes).
- The cached payload — sent to students — contained `is_correct` for every option.

## Decisions

1. **Cache-aside for the auth user** (`user:<email>`, 60 s, only the fields handlers
   read). Invalidated on verify/reset. *Alternative:* put id/role in JWT claims — removes
   the lookup entirely, but a role change/deletion would then wait for token expiry
   (120 min) instead of ≤ 60 s. Chosen trade-off: a Redis GET over a stale-authz window.
2. **Cache the exam's status/owner** (`exam:<id>:meta`, 60 s) so a warm request does zero DB work.
3. **Single-flight recompute** (`get_or_compute`): on a miss, only the holder of
   `lock:<key>` (`SET NX EX 10`) computes; others poll the cache with backoff. If the
   holder dies its lock expires and the next waiter takes over. Lock release is
   compare-and-delete in Lua (never delete someone else's lock). *Alternatives:*
   probabilistic early expiration (XFetch) — good for keys that are always hot, but
   doesn't help a cold start; serving stale-while-revalidate — needs a second TTL.
4. **Cache the full payload, project per request.** Students get a view with
   `is_correct` and `reference_answer` removed; the owning examiner gets the full
   one; other examiners get 403. One cache entry, no chance of a student-shaped
   entry leaking to an examiner or vice versa.
5. **Invalidate after commit, not before** (update/delete/status, question add/delete).
   Invalidating first leaves a window where a concurrent reader re-caches the old row
   for a whole TTL.
6. **Leaderboard invalidated when evaluation completes**, not at submit — with async
   evaluation a read in between used to re-cache the old ranking. One cached top-100,
   sliced per request (the old key ignored `limit`).
7. **Pool sized for peak concurrency** (non-blocking pool, 512/process). A
   `BlockingConnectionPool` fixed the stampede test but leaked connections under
   overload on redis-py 5.0.1 in the 500-user run (the process stayed at 8 s/request
   afterwards) — measured, then reverted.
8. `delete_pattern` uses `SCAN`, not `KEYS` (O(N), blocks single-threaded Redis).
9. **Eviction policy `volatile-lru`, not `allkeys-lru`.** The same Redis is the Celery
   broker. With `allkeys-lru`, memory pressure (e.g. a backlog of ~100 KB webcam
   frames on a 25 MB instance) can evict a *queue* — tasks silently vanish.
   `volatile-lru` only evicts keys with a TTL (every cache/lock/window key has one);
   when nothing is evictable Redis rejects writes, which surfaces as errors
   (backpressure) instead of data loss. The real fix at scale is separate Redis
   instances for broker (`noeviction`) and cache (`allkeys-lru`).

## Consequences

- Warm burst of 500: **1,000 → 0 SQL statements**; "exam-cold" burst (users logged in,
  exam keys just expired): **1,005 → 5**. See BENCHMARKS.md.
- A fully cold start still costs one user lookup per student (inherent: 500 different users).
- Staleness bounds are explicit: user 60 s, exam meta 60 s, questions 5 min (invalidated on edit), leaderboard 30 s (invalidated on evaluation).
