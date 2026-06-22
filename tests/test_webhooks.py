"""
Tests for the YouTube WebSub endpoints.

We patch detect_task.delay so nothing actually hits Redis/Celery — we're testing
the HTTP protocol handling (handshake echo + XML parsing), not the worker.
"""

import pytest
from fastapi.testclient import TestClient

from framelock import webhooks
from framelock.app import app


@pytest.fixture
def client(monkeypatch):
    # Replace the Celery enqueue with a stub that returns an object with `.id`.
    monkeypatch.setattr(webhooks.detect_task, "delay", lambda *a, **k: type("J", (), {"id": "job-123"})())
    return TestClient(app)


def test_handshake_echoes_challenge(client):
    r = client.get("/webhooks/youtube", params={"hub.mode": "subscribe", "hub.challenge": "xyz789"})
    assert r.status_code == 200
    assert r.text == "xyz789"


def test_handshake_without_challenge_is_400(client):
    r = client.get("/webhooks/youtube")
    assert r.status_code == 400


def test_notification_parses_video_and_enqueues(client):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
      <entry><yt:videoId>abc123XYZ_0</yt:videoId></entry>
    </feed>"""
    r = client.post("/webhooks/youtube", content=xml)
    assert r.status_code == 200
    body = r.json()
    assert body["video_id"] == "abc123XYZ_0"
    assert body["job_id"] == "job-123"


def test_notification_without_entry_is_204(client):
    xml = '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    r = client.post("/webhooks/youtube", content=xml)
    assert r.status_code == 204
