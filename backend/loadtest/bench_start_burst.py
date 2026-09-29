"""
N students click "Start exam" at the same instant (distinct users).

The pre-upgrade code deadlocks here at N=200 (thread pool vs DB pool, see
docs/adr/0009); this prints the status-code histogram and latency.

    python -m loadtest.bench_start_burst --base http://127.0.0.1:8002 --n 200 --offset 0
"""
import argparse
import asyncio
import json
import time
from collections import Counter
from pathlib import Path

import httpx


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8002")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--offset", type=int, default=0, help="first student index (use fresh students)")
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--fixture", default=str(Path(__file__).with_name("fixture.json")))
    a = ap.parse_args()
    fx = json.loads(Path(a.fixture).read_text())
    tokens = fx["student_tokens"][a.offset: a.offset + a.n]

    async with httpx.AsyncClient(timeout=a.timeout, limits=httpx.Limits(max_connections=a.n)) as c:
        async def one(tok):
            t = time.perf_counter()
            try:
                r = await c.post(f"{a.base}/api/v1/attempts/start", json={"exam_id": fx["exam_id"]},
                                 headers={"Authorization": f"Bearer {tok}"})
                return r.status_code, time.perf_counter() - t
            except Exception as e:
                return type(e).__name__, time.perf_counter() - t

        res = await asyncio.gather(*[one(t) for t in tokens])
    lat = sorted(r[1] for r in res)
    print(json.dumps({
        "requests": len(res),
        "outcomes": dict(Counter(str(r[0]) for r in res)),
        "p50_s": round(lat[len(lat) // 2], 2),
        "max_s": round(lat[-1], 2),
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
