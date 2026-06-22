"""
fingerprinter.py — the BRIDGE that produces a Fingerprint.

This is where Phase 1 and Phase 2 meet:

    URL --extract_frames--> (timestamp, jpeg_bytes) --embedder--> vector
        --> FrameSignature(timestamp, embedding) --> Fingerprint

The output is the `Fingerprint` contract object from schema.py with its
embeddings actually filled in — the compact, video-free signature that Phase 2's
Qdrant store will ingest and Phase 3's matching will compare.

Note what this module does NOT do: it doesn't know how frames are fetched (that's
extractor.py) or how vectors are made (that's the embedder). It only orchestrates.
"""

from __future__ import annotations

from .embedder.base import Embedder
from .extractor import extract_frames, probe_duration
from .schema import Fingerprint, FrameSignature


def fingerprint(
    work_id: str,
    url: str,
    embedder: Embedder,
    interval: float = 5.0,
    max_frames: int | None = None,
) -> Fingerprint:
    """
    Build a Fingerprint for one video.

    Args:
        work_id:    id for the registered work, e.g. "show-x-ep-5".
        url:        http(s) URL (or local path) of the video.
        embedder:   any Embedder backend (CLIP today). Passed IN, not created
                    here — the caller owns the model, so we don't reload a 600MB
                    model on every call (dependency injection).
        interval:   seconds between sampled frames.
        max_frames: cap for quick tests; None = sample the whole video.

    Returns:
        A Fingerprint with one FrameSignature per sampled frame.
    """
    duration = probe_duration(url)

    signatures: list[FrameSignature] = []
    for frame in extract_frames(url, interval=interval, max_frames=max_frames):
        vector = embedder.embed_image(frame.jpeg_bytes)
        signatures.append(
            FrameSignature(timestamp=frame.timestamp, embedding=vector)
        )

    return Fingerprint(
        work_id=work_id,
        source_uri=url,
        duration=duration,
        frames=signatures,
    )
