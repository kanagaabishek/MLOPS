"""
Tests for the verdict layer (matcher.detect).

We use a FAKE store so these run offline with no CLIP/Qdrant. The fake encodes
the "nearest hit" directly in each candidate frame's embedding:
    embedding = [score, timestamp]  -> search returns that score for work "w1".
That lets us drive detect()'s voting logic precisely.
"""

from framelock.matcher import detect
from framelock.schema import Fingerprint, FrameSignature


class FakeStore:
    """search() returns a single hit whose score/timestamp come from the query vector."""

    def search(self, vector, top_k=1):
        return [{
            "score": vector[0],
            "work_id": "w1",
            "timestamp": vector[1],
            "source_uri": "u",
            "embedder": "fake",
        }]


def _candidate(scores_and_ts):
    frames = [FrameSignature(timestamp=float(i), embedding=[s, ts])
              for i, (s, ts) in enumerate(scores_and_ts)]
    return Fingerprint(work_id="candidate", source_uri="u", duration=99.0, frames=frames)


def test_strong_match_is_detected():
    # 2 of 3 frames clear 0.85 -> coverage 0.67 >= 0.30 -> detected
    cand = _candidate([(0.90, 10), (0.95, 20), (0.40, 30)])
    d = detect(cand, FakeStore())
    assert d.detected
    assert d.best.work_id == "w1"
    assert d.best.matched_frames == 2
    assert round(d.best.coverage, 2) == 0.67


def test_no_match_when_all_below_threshold():
    cand = _candidate([(0.40, 10), (0.50, 20), (0.30, 30)])
    d = detect(cand, FakeStore())
    assert not d.detected
    assert d.best is None


def test_coverage_floor_blocks_single_lucky_frame():
    # one 0.90 hit among 3 -> coverage 0.33. Detected at default 0.30...
    cand = _candidate([(0.90, 10), (0.50, 20), (0.50, 30)])
    assert detect(cand, FakeStore()).detected
    # ...but NOT if we demand 50% coverage.
    assert not detect(cand, FakeStore(), min_coverage=0.50).detected


def test_segments_map_candidate_to_work_time():
    cand = _candidate([(0.90, 12), (0.95, 34)])
    d = detect(cand, FakeStore())
    # segments = (candidate_timestamp, matched_work_timestamp)
    assert d.best.segments == [(0.0, 12), (1.0, 34)]
    assert round(d.best.avg_score, 3) == 0.925
