"""
End-to-end exam flow under load + a durability check.

N students concurrently: start -> state -> K auto-saves (each changes one
answer; ~10% are deliberately re-sent stale, i.e. an older client_seq arrives
after a newer one) -> half submit, half "crash" (never submit).
Afterwards every student's LAST answer per question is compared with the DB.

    python -m loadtest.bench_exam_flow --base http://127.0.0.1:8002 --n 200 --saves 20
"""
import argparse
import asyncio
import json
import random
import statistics
import time
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))], 1) if xs else None


async def student(client, base, fx, token, saves, submit, lat, errors, rnd):
    try:
        return await _student(client, base, fx, token, saves, submit, lat, errors, rnd)
    except Exception as e:
        errors.append(("exception", repr(e)[:120]))
        return None, {}


async def _student(client, base, fx, token, saves, submit, lat, errors, rnd):
    h = {"Authorization": f"Bearer {token}"}
    t = time.perf_counter()
    r = await client.post(f"{base}/api/v1/attempts/start", json={"exam_id": fx["exam_id"]}, headers=h)
    lat.setdefault("start", []).append((time.perf_counter() - t) * 1000)
    r.raise_for_status()
    aid = r.json()["id"]
    (await client.get(f"{base}/api/v1/attempts/{aid}/state", headers=h)).raise_for_status()

    truth = {}          # question -> (seq, option) the student last chose
    seq = 0
    stale = []
    for _ in range(saves):
        q = rnd.choice(fx["questions"])
        opt = rnd.choice(q["options"])
        seq += 1
        body = {"responses": [{"question_id": q["id"], "selected_option_ids": [opt], "client_seq": seq}]}
        truth[q["id"]] = (seq, opt)
        if rnd.random() < 0.1:
            stale.append(body)                 # will be re-sent later (older seq)
        t = time.perf_counter()
        r = await client.post(f"{base}/api/v1/attempts/{aid}/auto-save", json=body, headers=h)
        lat["autosave"].append((time.perf_counter() - t) * 1000)
        if r.status_code != 200:
            errors.append(("autosave", r.status_code))
        await asyncio.sleep(rnd.uniform(0, 0.05))
    for body in stale:                          # delayed retries arriving late
        await client.post(f"{base}/api/v1/attempts/{aid}/auto-save", json=body, headers=h)

    if submit:
        t = time.perf_counter()
        r = await client.post(f"{base}/api/v1/attempts/{aid}/submit", json={"responses": []},
                              headers={**h, "Idempotency-Key": f"k-{aid}"})
        lat["submit"].append((time.perf_counter() - t) * 1000)
        if r.status_code != 200:
            errors.append(("submit", r.status_code))
    return aid, {q: o for q, (_, o) in truth.items()}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8002")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--saves", type=int, default=20)
    ap.add_argument("--db", default="postgresql://postgres:postgres123@localhost:5432/quizzie_bench")
    ap.add_argument("--fixture", default=str(Path(__file__).with_name("fixture.json")))
    a = ap.parse_args()
    fx = json.loads(Path(a.fixture).read_text())
    tokens = fx["student_tokens"][: a.n]
    lat = {"autosave": [], "submit": []}
    errors = []

    limits = httpx.Limits(max_connections=a.n)
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=120, limits=limits) as client:
        results = await asyncio.gather(*[
            student(client, a.base, fx, tok, a.saves, i % 2 == 0, lat, errors, random.Random(i))
            for i, tok in enumerate(tokens)
        ])
    wall = time.perf_counter() - t0

    # Durability check straight from Postgres.
    eng = create_engine(a.db)
    mismatches = 0
    checked = 0
    with eng.connect() as c:
        for aid, truth in results:
            if aid is None:
                continue
            rows = dict(c.execute(text(
                "SELECT question_id::text, selected_option_ids[1]::text FROM responses WHERE attempt_id = :a"
            ), {"a": aid}).fetchall())
            for q, opt in truth.items():
                checked += 1
                mismatches += rows.get(q) != opt
            dupes = c.execute(text(
                "SELECT count(*) - count(DISTINCT question_id) FROM responses WHERE attempt_id = :a"
            ), {"a": aid}).scalar()
            mismatches += dupes

    print(json.dumps({
        "students": a.n, "autosaves_per_student": a.saves, "wall_s": round(wall, 1),
        "autosave_requests": len(lat["autosave"]),
        "autosave_p50_ms": pct(lat["autosave"], 50), "autosave_p99_ms": pct(lat["autosave"], 99),
        "submit_p50_ms": pct(lat["submit"], 50), "submit_p99_ms": pct(lat["submit"], 99),
        "start_p50_ms": pct(lat.get("start", []), 50), "start_p99_ms": pct(lat.get("start", []), 99),
        "http_errors": len(errors),
        "error_examples": sorted(set(map(str, errors)))[:5],
        "answers_checked": checked,
        "answers_lost_or_stale": mismatches,
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
