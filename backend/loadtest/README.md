# Load tests & benchmarks

All numbers quoted in `docs/BENCHMARKS.md` come from these scripts.

| Script | What it answers |
|---|---|
| `seed.py` | Creates 1 examiner, N students, a live 30-question exam; writes `fixture.json` (JWTs — git-ignored). |
| `serve_instrumented.py` | Runs the API with a SQL-statement counter (`/__bench/counts`) and optional simulated DB round-trip (`--db-latency-ms`). Benchmark-only. |
| `bench_burst.py` | "The exam just went live": N concurrent question loads — cold / exam-cold / warm cache. Latency, throughput, SQL per burst, event-loop responsiveness (`/health` probe). |
| `bench_start_burst.py` | N distinct students press "Start exam" at the same instant — the pre-upgrade code deadlocks at 200. |
| `bench_races.py` | Runs the same concurrent start / submit / violation scenarios against whichever code is on `PYTHONPATH` and counts anomalies (duplicate attempts, double submits, lost health updates). |
| `bench_exam_flow.py` | N students: start → state → K auto-saves (10% deliberately stale retries) → half submit, half "crash". Then checks every student's last answer against Postgres. |
| `bench_frames.py` | N students upload frames every 2 s with no worker consuming: broker queue length and Redis memory growth (run the server with `--stub-ml`). |
| `locustfile.py` | Same exam session as a Locust scenario, for running against a real deployment. |

```bash
cd backend
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/quizzie_bench
export REDIS_URL=redis://localhost:6379/2
python -m loadtest.seed --students 500
python -m loadtest.serve_instrumented --port 8002 --db-latency-ms 2 &
python -m loadtest.bench_burst --base http://127.0.0.1:8002 --n 500
python -m loadtest.bench_exam_flow --base http://127.0.0.1:8002 --n 200 --saves 20
python -m loadtest.bench_races --trials 20 --threads 16
```
