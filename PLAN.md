# FrameLock — Implementation Plan

> **"Shazam for video copyright."** A rights holder registers content they own.
> When a video appears on YouTube, FrameLock decides *"is this mine?"* — without
> ever storing the video file.

This is the single source of truth. Built phase by phase; each phase is
independently demoable and teaches one concept cluster.

---

## The bullet, decoded

| Resume phrase | Real requirement | Hard part |
|---|---|---|
| Zero-download fingerprinting | Never save the video to disk | Pull only the bytes for sampled frames |
| FFmpeg byte-range seeking | HTTP `Range:` requests feed FFmpeg | Seeking inside a container without the whole file |
| Gemini multimodal embeddings | Each frame → a meaning vector | Embeddings, not pixel hashes (survives re-encode/crop) |
| Qdrant vector DB | Store + nearest-neighbor search | Similarity search at scale (HNSW) |
| Fingerprint without storing video | Fingerprint = vectors + timestamps (KBs) | Sampling strategy |
| YouTube Pub/Sub webhooks | Pushed the instant a channel uploads | PubSubHubbub + webhook verification |
| Celery Beat scheduled scans | Periodic safety-net re-checks | Async queue, idempotency |
| <8-min detection latency | upload→notify→fingerprint→match→alert | Where time goes; async |

---

## Phases

- **Phase 0 — Foundations & scaffold.** Structure, env, the data model (the contract).
  Learn: embeddings & vector similarity (high level).
- **Phase 1 — Zero-download frame extraction.** Pull keyframes from a remote video
  via HTTP range requests; video never saved. Learn: containers, keyframes/I-frames,
  HTTP `Range`, why seeking is hard.
- **Phase 2 — Fingerprinting.** Frames → Gemini embeddings → Qdrant with timestamps.
  Learn: multimodal embeddings, vector DBs, cosine similarity, HNSW.
- **Phase 3 — Registration & matching API.** FastAPI + PostgreSQL. Register a work;
  query a candidate; get a verdict. Learn: FastAPI, the threshold/matching problem.
- **Phase 4 — Async pipeline.** Celery + Redis + Celery Beat. Heavy work off the
  request path; scheduled scans. Learn: task queues, idempotency.
- **Phase 5 — Real-time detection.** YouTube PubSubHubbub webhooks; verify, receive,
  trigger; prove the <8-min budget. Learn: PubSubHubbub, webhook verification.
- **Phase 6 — Alerts, demo, README/blog.**

## Build order (contract-first)
`schema.py` → frame extraction → embedding+store → API → async → webhooks.

## Stack
Python · FastAPI · FFmpeg · Gemini/Vertex embeddings · Qdrant · Celery · Redis · PostgreSQL · Docker
