"""
Run the API (one Uvicorn process) with a SQL statement counter attached, so a
benchmark can report "how many DB queries did that burst cost".

    python -m loadtest.serve_instrumented --port 8001

GET /__bench/counts        -> {"questions": n, "users": n, "exams": n, "total": n}
--db-latency-ms N          -> add N ms to every SQL statement (simulated RTT)
POST /__bench/counts/reset
Benchmark-only; never import this from the app.
"""
import argparse
import faulthandler
import re
import signal
import time

faulthandler.register(signal.SIGUSR1, all_threads=True)   # `kill -USR1 <pid>` dumps stacks
from collections import Counter

import sys
import types

# --stub-ml must act BEFORE the app (and so the Celery task modules) import:
# the API process never runs MediaPipe on the fast path — it only needs the
# task objects to enqueue — so benchmark machines without mediapipe/opencv
# can stub the detector modules out.
if "--stub-ml" in sys.argv:
    for mod, cls in (("app.ai_monitor.face_detector", "FaceDetector"),
                     ("app.ai_monitor.audio_analyzer", "AudioAnalyzer")):
        m = types.ModuleType(mod)
        setattr(m, cls, type(cls, (), {}))
        sys.modules[mod] = m

import uvicorn
from sqlalchemy import event

from app.core.database import engine
from app.main import app

counts: Counter = Counter()
_FROM = re.compile(r"\bFROM\s+(\w+)", re.I)


DB_LATENCY_S = 0.0


@event.listens_for(engine, "before_cursor_execute")
def _count(conn, cursor, statement, params, context, executemany):
    counts["total"] += 1
    if DB_LATENCY_S:
        # Simulated network round-trip to a managed Postgres. It blocks
        # whichever thread runs the query — which, in an async route that calls
        # the sync ORM directly, is the event loop itself. That is the point.
        time.sleep(DB_LATENCY_S)
    m = _FROM.search(statement)
    if m:
        counts[m.group(1).lower()] += 1


@app.get("/__bench/counts", include_in_schema=False)
def bench_counts():
    return dict(counts)


@app.post("/__bench/counts/reset", include_in_schema=False)
def bench_reset():
    counts.clear()
    return {}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--stub-ml", action="store_true",
                    help="stub MediaPipe/OpenCV detector modules (enqueue-path benchmarks only)")
    ap.add_argument("--db-latency-ms", type=float, default=0.0,
                    help="simulated DB network RTT added to every statement")
    a = ap.parse_args()
    DB_LATENCY_S = a.db_latency_ms / 1000
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning", backlog=4096)
