# Benchmarks — before vs after

Everything here is reproducible with the scripts in `backend/loadtest/` (see its
README). "Before" = the code at the commit before this upgrade; "after" = this code.
Both ran against the same PostgreSQL 16 + Redis 7 instances with the same seeded data.

## Environment — read this before quoting any number

- 2 vCPU sandbox running **everything**: one Uvicorn process under test, Postgres,
  Redis and the load generator. Absolute latencies are therefore pessimistic and
  noisy (±30–40 % run to run); use them as **before/after on identical conditions**,
  not as capacity numbers.
- `--db-latency-ms 2` adds 2 ms to every SQL statement to simulate the network
  round trip to a managed Postgres in the same region. On localhost (~0.1 ms) the
  DB is too fast for query counts to show up as latency. The sleep blocks whichever
  thread runs the query — in the "before" code that is often the event loop, which
  is exactly what happens in production with a real network.
- The sandbox had no PyPI access, so tests ran against real Postgres through a small
  ctypes libpq DB-API shim with psycopg2 semantics. It's slower than real psycopg2,
  which again makes the absolute numbers pessimistic.

## 1. Correctness under concurrency — `bench_races.py`

20 trials × 16 threads released by a barrier, each on its own DB connection.

| Scenario | Before | After |
|---|---|---|
| 16 simultaneous "Start exam" by one student | **19/20 trials** created duplicate active attempts (worst: **7**) | 0/20 |
| 16 simultaneous submits of one attempt | **19/20 trials** had several "successful" submits (worst: **12 successes, 12 answer rows** for one question → double-counted marks) | 0/20 — exactly one success |
| 16 simultaneous violations (5 HP each) | **20/20 trials** lost penalties; **285 lost in total**; worst trial: health 95 instead of 20 (15 of 16 lost) | 0 lost |

## 2. Deadlock at 200 simultaneous "Start exam" — `bench_start_burst.py`

| | Before | After |
|---|---|---|
| 200 concurrent `POST /attempts/start` (distinct students) | **0/200 succeeded** — 160 client timeouts (60 s), 40 × `500 QueuePool limit … timed out` | **200/200**, p50 1.6 s, max 2.5 s |

Diagnosis (thread dump via `faulthandler` + `pg_stat_activity`): 40/40 threads blocked
in pool checkout, event loop idle, 30/30 connections `idle in transaction`. See ADR 0009.

## 3. "Exam goes live" burst — `bench_burst.py --n 500 --db-latency-ms 2`

500 concurrent `GET /exams/{id}/questions`, distinct student tokens. Phases:
**cold** = all Redis keys evicted; **exam-cold** = students already logged in, exam keys
just expired (the realistic moment); **warm** = steady state. `/health` probe = a
trivial request every 50 ms during the burst (event-loop responsiveness).

| Phase | Metric | Before | After |
|---|---|---|---|
| warm | SQL statements per burst | 1,000 | **0** |
| warm | throughput | 61–64 req/s | **89–125 req/s** |
| warm | p99 latency | 7.7–8.0 s | **3.8–5.5 s** |
| warm | `/health` worst latency during burst | 2.4–5.3 s | **0.18–1.1 s** |
| exam-cold | SQL statements per burst | 1,005 | **5** |
| exam-cold | throughput | 60 req/s | **150 req/s** |
| exam-cold | p99 latency | 8.0 s | **3.1 s** |
| cold | SQL statements per burst | 1,001 | 499 (497 = first-ever user lookups) |
| cold | p50 / p99 | 3.6–4.0 s / 7.8–7.9 s | 4.2–6.9 s / 7.4–9.0 s |

**Honest reading of the cold row:** with *every* cache empty, 500 different users
must each be looked up once; those lookups queue FIFO in the 40-thread pool, and the
single-flight winner's question query waits behind them (head-of-line blocking), so a
fully cold start is not faster — it just costs half the DB work. Before, the same
requests ran serially *on the event loop*, which by accident serialised the stampede.
In practice students hit the dashboard and lobby first, so the exam-cold row is the
one that happens.

## 4. Durability under load — `bench_exam_flow.py --n 200 --saves 20`

200 students concurrently: start → state → 20 auto-saves each (≈10 % deliberately
re-sent later with an *older* `client_seq`) → half submit, half never do. Then every
student's last answer per question is compared with Postgres.

| | Before | After |
|---|---|---|
| Answers durably stored | 0 (auto-save discarded; and the run can't start — see §2) | **2,888 / 2,888** |
| Stale overwrites / duplicate rows | n/a | **0 / 0** |
| auto-save latency p50 / p99 (saturated single process) | n/a | 2.6 s / 8.7 s |
| Client-side connection resets | — | 5 of ~4,400 requests |

The auto-save latency here is a throughput ceiling of one Python process on a shared
2-vCPU box (≈ 50 writes/s including all the other flow requests), not per-request cost —
this is precisely what horizontal scaling fixes, and it's now *safe* to add processes
because no correctness-relevant state is per-process.

## 5. Proctoring upload pressure — `bench_frames.py --n 100 --duration 20 --kb 100`

100 students upload a 100 KB frame every 2 s for 20 s while **no** proctoring worker
consumes (the limiting case of "workers fell behind"). API run with `--stub-ml`
(it only enqueues).

| | Before (payload inside each task) | After (latest-frame mailbox) |
|---|---|---|
| Broker queue length after 20 s | **995** and growing linearly | **100** (one per student), flat |
| Redis memory growth | **+187 MB** (~9 MB/s) | **+11.7 MB**, flat |
| Uploads coalesced (older frame dropped) | 0 | 897 of 997 |

Time to fill Redis before: the 25 MB Render plan in ~3 s, the 256 MB compose Redis
in ~27 s. The 640 px frames shrink the "after" number roughly 3× more.

## 6. Health polling — 200 student polls (`GET /monitor/enhanced/attempt/{id}/health`)

| | Before | After |
|---|---|---|
| SQL statements | **800** (user, attempt, settings, `COUNT(*)` cheat_logs × 200) | **0** (Redis snapshot; user from cache) |

## 7. Boot-time migrations — 6 processes run `alembic upgrade head` at once

| | Before (no lock) | After (`pg_advisory_lock`) |
|---|---|---|
| Processes that failed | **2 of 6** ("expected to match one row …") after running the migration body concurrently | **0 of 6** — on an old-schema DB and on a `create_all`-built DB |

## 8. Re-run after round 2 (no regressions)

- 200 simultaneous starts: 200/200 (p50 2.3 s, max 3.2 s).
- Burst of 500, exam-cold: **166 req/s, p99 2.9 s, 2 SQL**; warm: 118 req/s, p99 3.9 s, 0 SQL.
- Races (10 × 16 threads): 0 anomalies in all three scenarios.

## 9. Test suite

89 tests (37 pre-existing + 52 new), all passing against real PostgreSQL 16 and
Redis 7. The auto-save/submit race test was **mutation-tested**: with the
`FOR SHARE` lock removed it fails 10 runs out of 10; with it, 0 of 20.
