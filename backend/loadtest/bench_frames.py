"""
Proctoring upload pressure: what happens to the task broker when frames
arrive faster than workers analyse them?

N students upload a frame every `interval` seconds for `duration` seconds
while NO proctoring worker is consuming (the limiting case of "workers fell
behind"). Every second we sample the broker queue length (LLEN proctoring)
and Redis used_memory.

Run the server with --stub-ml (the API only enqueues; it never needs MediaPipe):
    python -m loadtest.serve_instrumented --port 8002 --stub-ml
    python -m loadtest.bench_frames --base http://127.0.0.1:8002 --n 100 --duration 20
"""
import argparse
import asyncio
import json
import os
import time
from collections import Counter
from pathlib import Path

import httpx
import redis


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8002")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--offset", type=int, default=300)
    ap.add_argument("--duration", type=float, default=20)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--kb", type=int, default=100, help="frame size (1280x720 JPEG ~100 KB)")
    ap.add_argument("--redis", default="redis://localhost:6379/2")
    ap.add_argument("--fixture", default=str(Path(__file__).with_name("fixture.json")))
    a = ap.parse_args()
    fx = json.loads(Path(a.fixture).read_text())
    tokens = fx["student_tokens"][a.offset: a.offset + a.n]
    r = redis.Redis.from_url(a.redis)
    payload = os.urandom(a.kb * 1024)

    async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=a.n)) as c:
        attempts = []
        for t in tokens:
            h = {"Authorization": f"Bearer {t}"}
            res = await c.post(f"{a.base}/api/v1/attempts/start", json={"exam_id": fx["exam_id"]}, headers=h)
            attempts.append((h, res.json()["id"]))

        r.delete("proctoring")
        mem0 = r.info("memory")["used_memory"]
        samples, codes = [], Counter()
        stop = time.monotonic() + a.duration

        async def student(h, aid, phase):
            await asyncio.sleep(phase)
            while time.monotonic() < stop:
                try:
                    res = await c.post(f"{a.base}/api/v1/monitor/frame", data={"attempt_id": aid},
                                       files={"file": ("f.jpg", payload, "image/jpeg")}, headers=h)
                    body = res.json() if res.status_code == 200 else {}
                    codes["coalesced" if body.get("coalesced") else str(res.status_code)] += 1
                except Exception as e:
                    codes[type(e).__name__] += 1
                await asyncio.sleep(a.interval)

        async def sampler():
            while time.monotonic() < stop:
                samples.append((r.llen("proctoring"), r.info("memory")["used_memory"] - mem0))
                await asyncio.sleep(1)

        await asyncio.gather(sampler(), *[
            student(h, aid, i * a.interval / len(attempts)) for i, (h, aid) in enumerate(attempts)
        ])
        final = (r.llen("proctoring"), r.info("memory")["used_memory"] - mem0)

    print(json.dumps({
        "students": a.n, "seconds": a.duration, "frame_kb": a.kb,
        "uploads": dict(codes),
        "queue_len_max": max(s[0] for s in samples + [final]),
        "queue_len_end": final[0],
        "redis_mem_growth_mb_max": round(max(s[1] for s in samples + [final]) / 2**20, 1),
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
