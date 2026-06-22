"""
extractor.py — the PRODUCER (Phase 1).

Turns a remote video URL into a stream of (timestamp, jpeg_bytes) pairs,
WITHOUT downloading the video. Each pair is one sampled keyframe living only
in memory. This is the code form of every CLI experiment we ran:

    ffmpeg -ss <T> -i <URL> -frames:v 1 ... pipe:1

Downstream, Phase 2 will turn each jpeg_bytes into FrameSignature.embedding,
and the timestamp we yield here becomes FrameSignature.timestamp.
"""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass


# A frame smaller than this many bytes is almost certainly near-black or near-
# flat (like the 583-byte scene-transition frame we hit). Such frames embed to
# useless vectors that false-match everything, so we drop them. Tunable.
MIN_FRAME_BYTES = 2_000


@dataclass
class ExtractedFrame:
    """One sampled keyframe held in memory. Note: bytes, never a file path."""

    timestamp: float        # seconds into the source video
    jpeg_bytes: bytes       # the decoded frame, JPEG-encoded, in RAM


def _header_args(headers: dict | None) -> list[str]:
    """Build FFmpeg/ffprobe input flags that replay HTTP headers.

    Some CDNs (e.g. YouTube's googlevideo) reject requests whose User-Agent
    doesn't match the client that minted the signed URL — returning 403. We
    replay the headers yt-dlp used so the byte-range requests are accepted.
    These are INPUT options, so they must appear before -i / the URL.
    """
    if not headers:
        return []
    args: list[str] = []
    ua = headers.get("User-Agent")
    if ua:
        args += ["-user_agent", ua]
    rest = "".join(f"{k}: {v}\r\n" for k, v in headers.items() if k.lower() != "user-agent")
    if rest:
        args += ["-headers", rest]
    return args


def probe_duration(url: str, timeout: float = 30.0, headers: dict | None = None) -> float:
    """Ask ffprobe how long the video is — reads only the index, not the video."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",                     # silence everything except real errors
            *_header_args(headers),            # replay CDN-required headers (before input)
            "-show_entries", "format=duration", # we only want the duration field
            "-of", "csv=p=0",                  # print just the value, no labels
            url,
        ],
        capture_output=True,                   # grab stdout/stderr instead of printing
        text=True,                             # decode bytes -> str for us
        timeout=timeout,                       # don't hang forever on a dead URL
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr.strip()}")
    return float(result.stdout.strip())


def _grab_frame(url: str, timestamp: float, timeout: float = 30.0, headers: dict | None = None) -> bytes:
    """Decode the single keyframe at/just-before `timestamp` into JPEG bytes."""
    result = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",                 # never wait for keyboard input (safe in scripts)
            "-loglevel", "error",       # keep stderr quiet unless something breaks
            *_header_args(headers),     # replay CDN-required headers (input options)
            "-ss", str(timestamp),      # SEEK on input -> Range request, the zero-download path
            "-i", url,                  # ...and -ss is BEFORE -i, so the seek is cheap
            "-frames:v", "1",           # decode exactly one video frame, then stop
            "-an",                      # ignore audio entirely
            "-q:v", "3",                # JPEG quality (2=best..31=worst); 3 is crisp + small
            "-f", "image2pipe",         # output format = raw image stream to a pipe
            "-vcodec", "mjpeg",         # encode that image as JPEG
            "pipe:1",                   # write to stdout (pipe:1) — NOT a file on disk
        ],
        capture_output=True,            # result.stdout now holds the JPEG bytes
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed at t={timestamp}: {result.stderr.decode().strip()}")
    return result.stdout


def extract_frames(
    url: str,
    interval: float = 2.0,
    max_frames: int | None = None,
    headers: dict | None = None,
):
    """
    Yield ExtractedFrame samples taken every `interval` seconds.

    This is a GENERATOR (note `yield`): frames flow out one at a time and are
    never all held at once — important when a long broadcast has hundreds.

    Args:
        url:        http(s) URL of the video (must support Range requests).
        interval:   seconds between samples. Bigger = sparser = fewer reads.
        max_frames: stop after this many good frames (handy for quick tests).
        headers:    optional HTTP headers to replay (e.g. YouTube's User-Agent).
    """
    duration = probe_duration(url, headers=headers)

    count = 0
    t = 0.0
    while t < duration:
        jpeg = _grab_frame(url, t, headers=headers)

        # Filter the low-information frames we learned about (the black-frame trap).
        if len(jpeg) >= MIN_FRAME_BYTES:
            yield ExtractedFrame(timestamp=round(t, 3), jpeg_bytes=jpeg)
            count += 1
            if max_frames is not None and count >= max_frames:
                return

        t += interval


def _main() -> None:
    """CLI: `python -m framelock.extractor <url>` — extract frames and report."""
    parser = argparse.ArgumentParser(description="Zero-download keyframe extractor.")
    parser.add_argument("url", help="http(s) URL (or local path) of the video")
    parser.add_argument("--interval", type=float, default=5.0, help="seconds between samples")
    parser.add_argument("--max-frames", type=int, default=5, help="stop after N good frames")
    parser.add_argument("--save-dir", help="optional dir to write JPEGs into")
    args = parser.parse_args()

    total = 0
    for frame in extract_frames(args.url, interval=args.interval, max_frames=args.max_frames):
        total += len(frame.jpeg_bytes)
        line = f"t={frame.timestamp:8.2f}s  {len(frame.jpeg_bytes):7d} bytes"
        if args.save_dir:
            import os
            os.makedirs(args.save_dir, exist_ok=True)
            path = os.path.join(args.save_dir, f"t{int(frame.timestamp)}.jpg")
            with open(path, "wb") as fh:
                fh.write(frame.jpeg_bytes)
            line += f"  -> {path}"
        print(line)
    print(f"total in-memory frame bytes: {total} (~{total / 1024:.0f} KB) — video never stored")


if __name__ == "__main__":
    _main()
