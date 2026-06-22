"""
webhooks.py — YouTube PubSubHubbub / WebSub real-time notifications (Phase 5).

Two endpoints implement the WebSub protocol:

    GET  /webhooks/youtube   the verification handshake — echo hub.challenge back
    POST /webhooks/youtube   a push notification — parse the video id, enqueue detect

Plus a subscribe() helper that asks Google's hub to start sending us a channel's
uploads. The callback URL must be PUBLICLY reachable (use ngrok/cloudflared in
dev) — the hub on the open internet has to be able to GET/POST it.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import xml.etree.ElementTree as ET

import requests
from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse

from .tasks import detect_task

HUB_URL = "https://pubsubhubbub.appspot.com/subscribe"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")  # shared with the hub for HMAC

# XML namespaces used by YouTube's Atom feed.
_NS = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/youtube")
async def verify(request: Request):
    """WebSub handshake: the hub sends hub.challenge; we echo it to confirm.

    Query params have dots (hub.challenge), which aren't valid Python identifiers,
    so we read them straight off the raw query string.
    """
    challenge = request.query_params.get("hub.challenge")
    if challenge is None:
        return Response(status_code=400)
    # Echoing the challenge (HTTP 200) tells the hub "yes, subscribe me."
    return PlainTextResponse(challenge)


@router.post("/youtube")
async def notify(request: Request):
    """A push from the hub: a channel uploaded. Parse the video id, enqueue detect."""
    body = await request.body()

    # 1) Verify the push is really from the hub (HMAC over the raw body).
    if WEBHOOK_SECRET and not _signature_ok(request, body):
        return Response(status_code=403)

    # 2) Parse the Atom XML to find the new video id.
    video_id = _extract_video_id(body)
    if not video_id:
        return Response(status_code=204)  # deletion / no entry — nothing to do

    # 3) Kick off detection asynchronously; respond fast (the hub wants a 2xx now).
    url = f"https://www.youtube.com/watch?v={video_id}"
    job = detect_task.delay(url)
    return {"video_id": video_id, "job_id": job.id}


def _signature_ok(request: Request, body: bytes) -> bool:
    """Constant-time compare of X-Hub-Signature against HMAC-SHA1(secret, body)."""
    header = request.headers.get("X-Hub-Signature", "")
    if not header.startswith("sha1="):
        return False
    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha1).hexdigest()
    return hmac.compare_digest(header[len("sha1="):], expected)


def _extract_video_id(body: bytes) -> str | None:
    try:
        entry = ET.fromstring(body).find("atom:entry", _NS)
        return entry.findtext("yt:videoId", namespaces=_NS) if entry is not None else None
    except ET.ParseError:
        return None


def subscribe(channel_id: str, callback_url: str, mode: str = "subscribe") -> int:
    """Ask the hub to (un)subscribe our callback to a channel's upload feed."""
    topic = f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}"
    data = {
        "hub.callback": callback_url,
        "hub.topic": topic,
        "hub.verify": "async",
        "hub.mode": mode,  # "subscribe" or "unsubscribe"
    }
    if WEBHOOK_SECRET:
        data["hub.secret"] = WEBHOOK_SECRET
    resp = requests.post(HUB_URL, data=data, timeout=15)
    return resp.status_code  # 202 = accepted (verification will follow)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("usage: python -m framelock.webhooks <channel_id> <public_callback_url>")
        raise SystemExit(1)
    print("hub responded:", subscribe(sys.argv[1], sys.argv[2]))
