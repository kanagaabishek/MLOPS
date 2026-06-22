# FrameLock

**Zero-download video copyright detection.** Register content you own; FrameLock
detects when a copy appears — *without ever storing the video file*. Think
"Shazam for video copyright."

It fingerprints a remote video by pulling only the keyframe bytes it needs over
HTTP range requests, turns each frame into a vector with an embedding model,
stores those vectors in Qdrant, and detects re-uploads by nearest-neighbor search
plus multi-frame voting. Detection runs async (Celery) and can be triggered in
real time (YouTube WebSub) or on a schedule (Celery Beat).

---

## How it works

```
 register:  URL ──► extract keyframes ──► embed ──► Fingerprint ──► Qdrant
            (FFmpeg -ss byte-range seek)  (CLIP)    (vectors+ts)    (HNSW)

 detect:    upload ──► fingerprint ──► search each frame ──► vote ──► verdict
                                       (Qdrant kNN)   (coverage ≥ threshold)

 triggers:  YouTube WebSub push  ─┐
            Celery Beat schedule ─┴─► Celery task ─► worker ─► detect
```

- **Zero-download:** the video is never saved. A keyframe is fetched via
  `Range: bytes=…`, decoded in memory, embedded, discarded. A 64 MB video → ~12 KB
  of vectors.
- **Robust matching:** embeddings compare *meaning*, so a cropped / re-encoded /
  watermarked copy still matches. Voting across frames (not one) is what separates
  a real copy from coincidental same-domain similarity.

## Architecture

| Component | File | Role |
|---|---|---|
| Contract | `framelock/schema.py` | `Fingerprint` / `FrameSignature` |
| Resolver | `framelock/resolver.py` | YouTube watch URL → direct media stream (yt-dlp) |
| Extractor | `framelock/extractor.py` | keyframes from a URL, no download |
| Embedder | `framelock/embedder/` | `Embedder` port + `ClipEmbedder` (Gemini-swappable) |
| Fingerprinter | `framelock/fingerprinter.py` | extract → embed → `Fingerprint` |
| Store | `framelock/store.py` | Qdrant register + search |
| Matcher | `framelock/matcher.py` | per-frame voting → verdict |
| API | `framelock/app.py` | `/register`, `/detect`, `/jobs/{id}` |
| Async | `framelock/tasks.py` | Celery tasks + Beat scheduled scans |
| Webhooks | `framelock/webhooks.py` | YouTube WebSub real-time trigger |

## Quickstart (Docker)

```bash
docker compose up --build        # qdrant + redis + api + worker + beat
```

Then:

```bash
# register a work
curl -X POST localhost:8077/register -H 'content-type: application/json' \
  -d '{"work_id":"my-show","url":"https://.../video.mp4"}'

# check an upload (returns a job_id)
curl -X POST localhost:8077/detect -H 'content-type: application/json' \
  -d '{"url":"https://.../suspect.mp4"}'

# poll the verdict
curl localhost:8077/jobs/<job_id>
```

Interactive docs: <http://localhost:8077/docs>

## Local dev (no compose)

```bash
brew install ffmpeg
python -m venv .venv && .venv/bin/pip install -r requirements.txt
docker run -d -p 6333:6333 qdrant/qdrant
docker run -d -p 6379:6379 redis

QDRANT_URL=http://localhost:6333 uvicorn framelock.app:app --port 8077
celery -A framelock.tasks worker --pool=solo --loglevel=info   # macOS: --pool=solo
celery -A framelock.tasks beat --loglevel=info                 # scheduled scans
```

Tests (offline, no models/services needed):

```bash
.venv/bin/python -m pytest tests/ -q
```

## Embedding backends

The embedder is a swappable port (`framelock/embedder/base.py`). Ships with local
**CLIP** (free, offline). A **Gemini/Vertex** adapter drops in behind the same
interface — true multimodal image embeddings — by implementing `Embedder`.

## What's real vs. what's a known boundary

- ✅ Real: zero-download extraction, embeddings, Qdrant search, voting verdict,
  async pipeline, scheduled scans, the WebSub protocol (handshake + parse + enqueue),
  and **YouTube `watch?v=…` ingestion** via `resolver.py` (yt-dlp resolves the page
  to a direct, range-seekable stream — still zero-download).
- ⚠️ For *live* webhook delivery the callback must be publicly reachable (e.g.
  `ngrok`). YouTube also actively fights automated access: stream resolution can
  break (PO-token / anti-bot changes), so the resolver uses mobile/tv player
  clients and may need updating over time. The engine always works on any direct
  media URL.

## License

MIT
