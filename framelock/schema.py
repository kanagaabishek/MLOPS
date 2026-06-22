"""
schema.py — THE CONTRACT.

A "fingerprint" is the heart of FrameLock. It is what we store *instead of*
the video file. Every later phase produces or consumes these structures:

  Phase 1 (extract)   -> produces FrameSignature.timestamp (no embedding yet)
  Phase 2 (embed)     -> fills FrameSignature.embedding, builds a Fingerprint
  Phase 2 (Qdrant)    -> each FrameSignature becomes one vector-DB point
  Phase 3 (match)     -> compares a candidate Fingerprint against stored ones

We design this BEFORE the code that fills it — same reason you design a DB
schema before the code that writes to it.
"""

from __future__ import annotations  # lets us use `list[float]` style hints on Python 3.9

from dataclasses import dataclass, field


# The version of THIS data shape. When we change the fields later (e.g. add a
# perceptual hash in a future phase), we bump this. A stored fingerprint then
# carries the version it was made with, so old and new can coexist.
SCHEMA_VERSION = "1"


@dataclass
class FrameSignature:
    """One sampled frame, reduced to a vector. This is the atom of a fingerprint."""

    timestamp: float
    # WHERE in the video this frame is, in seconds (e.g. 12.5 = 12.5s in).
    # We need this so a match can say "your content appears at 00:12 of their
    # upload" instead of just "yes, somewhere". It is the only thing tying a
    # vector back to a position in time.

    embedding: list[float] = field(default_factory=list)
    # The MEANING of the frame as a list of numbers (a vector). Two frames that
    # look alike — even after re-encoding, cropping, or watermarking — produce
    # nearby vectors. Empty in Phase 1 (we only have the timestamp then); filled
    # in Phase 2 by the embedding model. default_factory=list avoids the classic
    # "mutable default argument" bug (a shared list across all instances).


@dataclass
class Fingerprint:
    """The full, video-free signature of one piece of content."""

    work_id: str
    # Which registered work this belongs to, e.g. "show-x-ep-5". Lets us answer
    # "WHOSE content matched" after a vector search returns a hit.

    source_uri: str
    # WHERE the content came from (a URL). We store the pointer, never the bytes.
    # This is the literal meaning of "without storing the video file".

    duration: float
    # Total length in seconds. Useful for sampling decisions and for reporting
    # "matched 30s of a 45s clip".

    frames: list[FrameSignature] = field(default_factory=list)
    # The ordered list of sampled-frame signatures. A whole broadcast collapses
    # to a few hundred of these — kilobytes, not gigabytes.

    schema_version: str = SCHEMA_VERSION
    # Stamped automatically so every fingerprint records the contract it was
    # built against.
