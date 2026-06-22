"""
Offline tests for the URL resolver — no network.

We only test the routing logic (is_youtube + direct-URL passthrough). Actually
resolving a YouTube URL needs the network and yt-dlp, so that path is exercised
manually / in integration, not here.
"""

from framelock.resolver import is_youtube, resolve_stream_url


def test_is_youtube_detects_hosts():
    assert is_youtube("https://www.youtube.com/watch?v=abc123")
    assert is_youtube("https://youtu.be/abc123")
    assert is_youtube("https://m.youtube.com/watch?v=abc123")
    assert not is_youtube("https://example.com/video.mp4")
    assert not is_youtube("https://download.blender.org/x.mp4")


def test_direct_url_passes_through_unchanged():
    url = "https://example.com/video.mp4"
    media_url, headers = resolve_stream_url(url)
    assert media_url == url      # not a YouTube page -> returned as-is
    assert headers == {}         # no special headers needed
