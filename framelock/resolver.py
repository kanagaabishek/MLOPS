"""
resolver.py — turn a page URL into a direct media stream URL.

Our extractor seeks into *media* files via HTTP range requests. A
`youtube.com/watch?v=...` page is HTML, not a media file — FFmpeg can't open it.
This module resolves such pages to a direct, range-seekable stream URL using
yt-dlp, WITHOUT downloading the video. Direct media URLs (e.g. a .mp4) are
returned unchanged, so the rest of the pipeline never needs to care.

Honest caveat: YouTube actively fights automated access. yt-dlp resolution can
fail (sign-in walls, bot checks, rate limits, format changes). We surface a
clear error rather than pretend; the engine still works on any direct media URL.
"""

from __future__ import annotations

from urllib.parse import urlparse

_YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "music.youtube.com", "youtu.be",
}

# Prefer a small progressive MP4 (itag 18 ≈ 360p, audio+video muxed, range-
# seekable). Fall back to any mp4. Low res is fine — CLIP downsizes anyway, and
# smaller = fewer bytes per range request.
_FORMAT = "18/best[ext=mp4][vcodec!=none]/worst[ext=mp4]/worst"


def is_youtube(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in _YOUTUBE_HOSTS


def resolve_stream_url(url: str) -> tuple[str, dict]:
    """Resolve `url` to (media_url, http_headers).

    - Non-YouTube URLs return (url, {}) — already direct media, no headers needed.
    - YouTube pages resolve to a temporary signed stream URL plus the HTTP headers
      (notably User-Agent) that the CDN REQUIRES. Without those headers FFmpeg gets
      403 Forbidden, so we hand them back for the extractor to replay.
    """
    if not is_youtube(url):
        return url, {}

    # Imported lazily so the rest of FrameLock doesn't require yt-dlp installed.
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,   # we only want the stream URL, never the bytes
        "format": _FORMAT,
        # The default WEB client now hands back URLs that 403 without a PO-token.
        # The mobile/tv clients return stream URLs that play without one, so we
        # ask yt-dlp to use those player clients instead.
        "extractor_args": {"youtube": {"player_client": ["ios", "android", "tv", "web"]}},
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise RuntimeError(f"could not resolve YouTube stream for {url}: {e}") from e

    stream = info.get("url")
    headers = info.get("http_headers") or {}
    if not stream and info.get("requested_formats"):
        # DASH case: yt-dlp returns separate streams; take the (video) first.
        fmt = info["requested_formats"][0]
        stream = fmt.get("url")
        headers = fmt.get("http_headers") or headers
    if not stream:
        raise RuntimeError(f"no playable stream URL found for {url}")
    return stream, headers


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m framelock.resolver <video-url>")
        raise SystemExit(1)
    media_url, headers = resolve_stream_url(sys.argv[1])
    print("stream:", media_url[:110], "...")
    print("headers:", list(headers.keys()))
