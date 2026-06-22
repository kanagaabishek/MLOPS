"""
app.py — the FastAPI service (Phase 3, made async in Phase 4).

The API is now a thin "front desk": it validates requests, ENQUEUES Celery tasks,
and hands back a job id. It does NOT load CLIP or touch Qdrant directly anymore —
the worker processes (tasks.py) own all of that. So this process starts instantly
and stays responsive no matter how heavy the jobs are.

    POST /register   { work_id, url }  -> { job_id }     (work runs in a worker)
    POST /detect     { url }           -> { job_id }
    GET  /jobs/{id}                    -> { state, result? }
    GET  /health                       -> liveness
"""

from __future__ import annotations

import os
from typing import Optional

from celery.result import AsyncResult
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .tasks import celery_app, detect_task, register_task
from .webhooks import router as webhooks_router

app = FastAPI(title="FrameLock", version="0.1.0")
app.include_router(webhooks_router)

_STATIC = os.path.join(os.path.dirname(__file__), "static")


@app.get("/", include_in_schema=False)
def ui() -> FileResponse:
    """Serve the single-page console."""
    return FileResponse(os.path.join(_STATIC, "index.html"))


class RegisterRequest(BaseModel):
    work_id: str
    url: str
    interval: float = 5.0
    max_frames: Optional[int] = 12


class DetectRequest(BaseModel):
    url: str
    interval: float = 5.0
    max_frames: Optional[int] = 12
    per_frame_threshold: float = 0.85
    min_coverage: float = 0.30


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/register")
def register(req: RegisterRequest) -> dict:
    # .delay() drops a message on the queue and returns at once — no blocking.
    job = register_task.delay(req.work_id, req.url, req.interval, req.max_frames)
    return {"job_id": job.id, "status": "queued"}


@app.post("/detect")
def detect_endpoint(req: DetectRequest) -> dict:
    job = detect_task.delay(
        req.url, req.interval, req.max_frames, req.per_frame_threshold, req.min_coverage
    )
    return {"job_id": job.id, "status": "queued"}


@app.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    # AsyncResult reads the task's state/result from the Redis result backend.
    res = AsyncResult(job_id, app=celery_app)
    body = {"job_id": job_id, "state": res.state}  # PENDING / STARTED / SUCCESS / FAILURE
    if res.successful():
        body["result"] = res.result
    elif res.failed():
        body["error"] = str(res.result)
    return body
