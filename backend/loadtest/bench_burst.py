"""
"The exam just went live": N students open the exam page at the same instant.

Fires N concurrent GET /exams/{id}/questions (distinct student tokens) twice:
  1. COLD  — Redis flushed first (first load / TTL just expired)
  2. WARM  — cache populated
and reports latency percentiles, errors, and how many SQL statements the burst
cost the database (from serve_instrumented's counter).

    python -m loadtest.bench_burst --base http://127.0.0.1:8001 --n 500
"""
import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx
import redis


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


async def burst(client, base, exam_id, tokens):
    async def one(tok):
        t0 = time.perf_counter()
        try:
            r = await client.get(f"{base}/api/v1/exams/{exam_id}/questions",
                                 headers={"Authorization": f"Bearer {tok}"})
            ok = r.status_code == 200
        except Exception:
            ok = False
        return (time.perf_counter() - t0) * 1000, ok

    # Probe: while the burst runs, a trivial GET /health every 50 ms. Its
    # latency is the event loop's responsiveness — if routes block the loop
    # (sync DB calls inside async def), even /health queues behind them.
    probe = []
    done = asyncio.Event()

    async def prober():
        async with httpx.AsyncClient(timeout=60) as pc:
            while not done.is_set():
                t = time.perf_counter()
                try:
                    await pc.get(f"{base}/health")
                    probe.append((time.perf_counter() - t) * 1000)
                except Exception:
                    pass
                await asyncio.sleep(0.05)

    ptask = asyncio.create_task(prober())
    t0 = time.perf_counter()
    res = await asyncio.gather(*[one(t) for t in tokens])
    wall = (time.perf_counter() - t0) * 1000
    done.set()
    await ptask
    lat = [r[0] for r in res]
    return {
        "requests": len(res),
        "errors": sum(1 for r in res if not r[1]),
        "p50_ms": round(pct(lat, 50), 1),
        "p95_ms": round(pct(lat, 95), 1),
        "p99_ms": round(pct(lat, 99), 1),
        "max_ms": round(max(lat), 1),
        "wall_ms": round(wall, 1),
        "throughput_rps": round(len(res) / (wall / 1000), 1),
        "health_probe_p50_ms": round(pct(probe, 50), 1) if probe else None,
        "health_probe_max_ms": round(max(probe), 1) if probe else None,
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8001")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--redis", default="redis://localhost:6379/2")
    ap.add_argument("--fixture", default=str(Path(__file__).with_name("fixture.json")))
    a = ap.parse_args()
    fx = json.loads(Path(a.fixture).read_text())
    tokens = fx["student_tokens"][: a.n]
    r = redis.Redis.from_url(a.redis)

    limits = httpx.Limits(max_connections=a.n, max_keepalive_connections=a.n)
    async with httpx.AsyncClient(timeout=60, limits=limits) as client:
        out = {}
        # cold:        everything evicted (first request of the day)
        # exam_cold:   students already logged in (user cache warm), but the
        #              exam's cache entries just expired — the realistic
        #              "exam goes live / TTL expires mid-exam" moment
        # warm:        steady state
        for phase in ("cold", "exam_cold", "warm"):
            if phase == "cold":
                r.flushdb()
            elif phase == "exam_cold":
                for k in r.scan_iter(match="exam:*"):
                    r.delete(k)
            await client.post(f"{a.base}/__bench/counts/reset")
            stats = await burst(client, a.base, fx["exam_id"], tokens)
            counts = (await client.get(f"{a.base}/__bench/counts")).json()
            stats["sql_total"] = counts.get("total", 0)
            stats["sql_questions"] = counts.get("questions", 0)
            stats["sql_users"] = counts.get("users", 0)
            stats["sql_exams"] = counts.get("exams", 0)
            out[phase] = stats
        print(json.dumps(out, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
