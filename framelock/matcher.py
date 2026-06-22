"""
matcher.py — the VERDICT layer (Phase 3).

store.search() answers "what's nearest to ONE frame?". That's not a decision —
one coincidental 0.82 should never trigger a copyright alert. detect() turns many
per-frame searches into a single, defensible answer:

    "This candidate IS work X — it matched at N of M frames (coverage C),
     avg score S, at these timestamps."

The key idea is VOTING across frames. A genuine re-upload lights up many frames
against the same registered work; a coincidence lights up one or two. Requiring
both a per-frame score floor AND enough coverage is what separates a real match
from same-domain noise (the 0.89-vs-0.81 problem we saw earlier).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schema import Fingerprint
from .store import FingerprintStore


@dataclass
class WorkMatch:
    """How strongly one registered work was matched by a candidate."""

    work_id: str
    total_frames: int                       # candidate frames examined
    matched_frames: int = 0                  # frames whose best hit (this work) cleared the floor
    score_sum: float = 0.0                   # running sum of matched scores (for the average)
    segments: list[tuple[float, float]] = field(default_factory=list)
    # each segment = (candidate_timestamp, matched_registered_timestamp)

    @property
    def coverage(self) -> float:
        """Fraction of candidate frames that matched this work. The vote share."""
        return self.matched_frames / self.total_frames if self.total_frames else 0.0

    @property
    def avg_score(self) -> float:
        return self.score_sum / self.matched_frames if self.matched_frames else 0.0


@dataclass
class Detection:
    """The overall verdict for one candidate video."""

    detected: bool
    best: WorkMatch | None
    all_matches: list[WorkMatch]


def detect(
    candidate: Fingerprint,
    store: FingerprintStore,
    per_frame_threshold: float = 0.85,
    min_coverage: float = 0.30,
) -> Detection:
    """
    Decide whether `candidate` is a copy of any registered work.

    Args:
        candidate:           fingerprint of the unknown/uploaded video.
        store:               the registered fingerprints to check against.
        per_frame_threshold: a single frame only "votes" if its nearest stored
                             frame scores at least this. Filters weak matches.
        min_coverage:        a work is flagged only if at least this fraction of
                             candidate frames voted for it. This is the multi-frame
                             requirement that kills one-off false positives.

    Returns:
        Detection with the winning WorkMatch (if any) and the per-work breakdown.
    """
    matches: dict[str, WorkMatch] = {}
    total = len(candidate.frames)

    for frame in candidate.frames:
        hits = store.search(frame.embedding, top_k=1)
        if not hits:
            continue
        best = hits[0]
        if best["score"] < per_frame_threshold:
            continue  # nearest neighbor too far -> this frame casts no vote

        work_id = best["work_id"]
        wm = matches.setdefault(work_id, WorkMatch(work_id=work_id, total_frames=total))
        wm.matched_frames += 1
        wm.score_sum += best["score"]
        wm.segments.append((frame.timestamp, best["timestamp"]))

    ranked = sorted(matches.values(), key=lambda m: (m.coverage, m.avg_score), reverse=True)
    top = ranked[0] if ranked else None
    detected = top is not None and top.coverage >= min_coverage
    return Detection(detected=detected, best=top if detected else None, all_matches=ranked)
