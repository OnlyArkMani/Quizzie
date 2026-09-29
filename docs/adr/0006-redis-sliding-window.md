# ADR 0006 — Shared sliding windows in Redis (rate limiting and flag smoothing)

**Status:** accepted · **Code:** `app/core/rate_limit.py`, `app/ai_monitor/smoothing.py`, `app/core/limiter.py`, `api/v1/monitoring.py`

## Context

Three pieces of state were kept in per-process Python dicts:

| State | Effect with N processes |
|---|---|
| Frame/audio upload limit (8 per 5 s per attempt) | N × the limit — each process has its own budget |
| Flag smoothing ("look away" must be seen 2× in 12 s to count) | Frames of one attempt are spread over Celery's worker processes; each sees ~1/N of the sightings, so real sustained violations may never confirm |
| slowapi login limits (in-memory storage) | 20 logins/min becomes 20 × N |

The README's own diagram has 3 API replicas × 5 Uvicorn workers and 4 proctoring workers.

## Options

1. **Sticky routing** (hash attempt → process) — pushes state affinity into the load balancer and Celery routing; breaks on every deploy/restart.
2. **Fixed-window counter** (`INCR` + `EXPIRE`) — one op, O(1) memory; allows ~2× the limit across a window boundary.
3. **Token bucket** — good for burst shaping; more state and math than "N per window" needs.
4. **Sliding-window log in a sorted set, as one Lua script** *(chosen)*.

## Decision

```lua
local now = redis.call('TIME')            -- Redis's clock, not each replica's
ZREMRANGEBYSCORE key -inf (now - window)   -- forget old events
if ZCARD key >= limit then return 0 end    -- over the limit
ZADD key now <unique-id>; PEXPIRE key window; return 1
```

- One Lua script = atomic across all replicas (no check-then-act between two commands).
- `TIME` inside the script: replicas with skewed clocks still agree on the window.
- Exact at window edges (unlike fixed windows); memory is O(limit) per key — here ≤ 8 entries.
- Smoothing uses the same structure (`hit_and_check_sync`): record a sighting, confirm and reset when the threshold is reached within the window.
- slowapi is pointed at Redis storage.
- **Failure mode:** if Redis is unreachable, fall back to the in-process window. Degraded (per-process) protection beats either failing every request or disabling limits entirely.

**Login throttling (found while writing the interview handbook).** The login limit
was "20/minute per IP", but uvicorn ran without `--proxy-headers`, so behind nginx
every request's IP was nginx's: the limit was effectively *global* — the 21st
student logging in within a minute got 429 on exam morning. Now: uvicorn trusts
`X-Forwarded-For` from nginx, the per-IP limit is loose (300/min — a class behind
one campus NAT shares an IP), and brute-force protection is **per account**
(10 attempts/min, same Redis sliding window). Tested: the 11th attempt on one
account → 429; a classmate on the same IP still logs in.

## Consequences

- Two "replicas" hammering one key admit exactly the limit (`test_limit_is_shared_across_replicas`); the in-process fallback demonstrably admits 2× (`test_in_process_fallback_is_per_process`).
- Each check is one Redis round trip (~0.2 ms same-AZ).
- A connect failure is remembered for 30 s (`redis_client`), so a Redis outage doesn't add a timeout to every request.
