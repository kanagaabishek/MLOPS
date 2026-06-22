"""
tasks.py — Celery tasks (Phase 4).

The heavy work (fingerprint + match) moves OFF the web request and into worker
processes. The API enqueues a task and returns a job id immediately; a worker
runs it and stores the result in Redis for later retrieval.

Why singletons-per-worker: each worker is its own process. Loading the 600MB CLIP
model on every task would be insane, so we lazily build the embedder and store
ONCE per worker process and reuse them across all tasks that process handles.
"""

from __future__ import annotations

import os

from celery import Celery

from .fingerprinter import fingerprint
from .matcher import detect

# A watchlist of sources to re-check periodically. In a real system these come
# from YouTube search of registered titles; here it's a configurable list.
WATCHLIST = [u for u in os.environ.get("WATCHLIST", "/tmp/mandel.mp4").split(",") if u]
SCAN_INTERVAL = float(os.environ.get("SCAN_INTERVAL", "15"))  # seconds between scans

# Redis is both the broker (pending task queue, db 0) and the result backend
# (finished results, db 1). Configurable via env for real deployments.
BROKER_URL = os.environ.get("CELERY_BROKER", "redis://localhost:6379/0")
RESULT_BACKEND = os.environ.get("CELERY_BACKEND", "redis://localhost:6379/1")

celery_app = Celery("framelock", broker=BROKER_URL, backend=RESULT_BACKEND)
celery_app.conf.update(
    task_track_started=True,     # so a polling client can see "STARTED", not just PENDING->SUCCESS
    result_expires=3600,         # drop results after an hour; don't fill Redis forever
)

# Celery Beat schedule: Beat enqueues "framelock.scan" every SCAN_INTERVAL seconds.
# Beat only SCHEDULES; the worker still does the actual running. (schedule can be a
# number of seconds or a crontab(...) for "every day at 3am" style timing.)
celery_app.conf.beat_schedule = {
    "periodic-scan": {"task": "framelock.scan", "schedule": SCAN_INTERVAL},
}


# --- per-worker singletons (built lazily, after the process starts) ---
_embedder = None
_store = None


def get_embedder():
    global _embedder
    if _embedder is None:
        from .embedder import ClipEmbedder
        _embedder = ClipEmbedder()
    return _embedder


def get_store():
    global _store
    if _store is None:
        from qdrant_client import QdrantClient
        from .store import FingerprintStore

        url = os.environ.get("QDRANT_URL", "http://localhost:6333")
        emb = get_embedder()
        _store = FingerprintStore(dim=emb.dim, embedder_name=emb.name, client=QdrantClient(url=url))
    return _store


_scan_count = 0


@celery_app.task(name="framelock.scan")
def scheduled_scan() -> dict:
    """Periodic safety-net scan: re-check every watchlist source against the store."""
    global _scan_count
    _scan_count += 1
    results = {}
    for url in WATCHLIST:
        try:
            candidate = fingerprint("scan", url, get_embedder(), interval=5, max_frames=4)
            results[url] = detect(candidate, get_store()).detected
        except Exception as e:  # a dead URL shouldn't kill the whole scan
            results[url] = f"error: {e}"
    print(f"[BEAT SCAN #{_scan_count}] checked {len(WATCHLIST)} source(s): {results}", flush=True)
    return {"scan": _scan_count, "results": results}


@celery_app.task(name="framelock.register")
def register_task(work_id: str, url: str, interval: float = 5.0, max_frames=12) -> dict:
    emb = get_embedder()
    fp = fingerprint(work_id, url, emb, interval, max_frames)
    n = get_store().register(fp)
    return {"work_id": fp.work_id, "frames_registered": n, "duration": fp.duration}


@celery_app.task(name="framelock.detect")
def detect_task(
    url: str,
    interval: float = 5.0,
    max_frames=12,
    per_frame_threshold: float = 0.85,
    min_coverage: float = 0.30,
) -> dict:
    emb = get_embedder()
    candidate = fingerprint("candidate", url, emb, interval, max_frames)
    result = detect(candidate, get_store(), per_frame_threshold, min_coverage)
    return {
        "detected": result.detected,
        "candidate_duration": candidate.duration,
        "best_match": (
            {
                "work_id": result.best.work_id,
                "coverage": round(result.best.coverage, 3),
                "matched_frames": result.best.matched_frames,
                "total_frames": result.best.total_frames,
                "avg_score": round(result.best.avg_score, 3),
                "segments": [
                    {"candidate_t": round(a, 1), "work_t": round(b, 1)}
                    for a, b in result.best.segments
                ],
            }
            if result.best
            else None
        ),
    }
