# FrameLock image — used by the api, worker, and beat services (same code, different command).
FROM python:3.11-slim

# ffmpeg/ffprobe are required by the extractor (system deps, not pip).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so this layer caches across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY framelock ./framelock

# Default command is the API; compose overrides it for worker/beat.
EXPOSE 8000
CMD ["uvicorn", "framelock.app:app", "--host", "0.0.0.0", "--port", "8000"]
