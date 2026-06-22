"""
Tests for the Phase 1 extractor.

We generate a small synthetic video locally with FFmpeg (no network, fully
deterministic), then assert the extractor reads it correctly. extract_frames
takes a "url", but FFmpeg treats a local path the same way, so a local file is
a perfect stand-in for a remote one in tests.
"""

import subprocess

import pytest

from framelock.extractor import extract_frames, probe_duration


@pytest.fixture
def sample_video(tmp_path):
    """Make a 6-second 320x180 test-pattern clip; return its path as a string."""
    path = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
            "-f", "lavfi",                                   # use FFmpeg's built-in source
            "-i", "testsrc=duration=6:size=320x180:rate=10", # a moving test pattern
            "-c:v", "mpeg4", "-g", "10",                     # keyframe every 10 frames (~1s)
            str(path),
        ],
        check=True,
    )
    return str(path)


def test_probe_duration(sample_video):
    duration = probe_duration(sample_video)
    assert duration == pytest.approx(6.0, abs=0.5)


def test_extract_yields_frames_in_order(sample_video):
    frames = list(extract_frames(sample_video, interval=2.0, max_frames=3))

    assert len(frames) == 3
    # Timestamps must be increasing and spaced by the interval.
    assert [f.timestamp for f in frames] == [0.0, 2.0, 4.0]


def test_frames_are_real_jpeg_bytes(sample_video):
    frame = next(extract_frames(sample_video, interval=2.0, max_frames=1))

    # Output lives in memory as bytes, not a file path.
    assert isinstance(frame.jpeg_bytes, bytes)
    # JPEG files always start with the magic bytes 0xFF 0xD8.
    assert frame.jpeg_bytes[:2] == b"\xff\xd8"


def test_max_frames_caps_output(sample_video):
    frames = list(extract_frames(sample_video, interval=1.0, max_frames=2))
    assert len(frames) == 2
