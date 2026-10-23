"""
Live Connections: Bad Messages, Slow Clients and Blocking Work
==============================================================

One malformed message on /ws/audio closed the connection - usually the audio
feed the whole show follows. One tablet that stopped reading froze every
broadcast and the audio input with it, because sends ran one after another
with no deadline. One numpy scalar the encoder did not know dropped every
client. And a clean close raised RuntimeError on every disconnect.
"""

import asyncio
import json
import math
import time

import numpy as np
import pytest
from starlette.testclient import TestClient

from app.api.endpoints import websocket as ws_endpoints
from app.core.config import settings
from app.main import app


class StubAnalyzer:
    is_running = True

    def __init__(self):
        self.chunks = []
        self.sample_rate = 44100

    def set_sample_rate(self, rate):
        self.sample_rate = rate

    async def process_chunk(self, chunk):
        self.chunks.append(chunk)
        return {"frequency": {"rms_energy": np.float16(0.5)}, "beat": {"is_beat": False}}


@pytest.fixture
def open_client(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_ENABLED", False)
    analyzer = StubAnalyzer()
    monkeypatch.setattr(app.state, "audio_analyzer", analyzer, raising=False)
    monkeypatch.setattr(app.state, "effects_engine", None, raising=False)
    monkeypatch.setattr(app.state, "dmx_controller", None, raising=False)
    return TestClient(app), analyzer


def pong_after(ws, message):
    if isinstance(message, str):
        ws.send_text(message)
    else:
        ws.send_json(message)
    ws.send_json({"type": "ping"})
    seen = []
    for _ in range(4):
        reply = ws.receive_json()
        seen.append(reply["type"])
        if reply["type"] == "pong":
            return seen
    return seen


@pytest.mark.parametrize("message", [
    "not json",
    "[1, 2]",
    {"type": "audio_chunk", "data": None},
    {"type": "audio_chunk", "data": 5},
    {"type": "audio_chunk", "data": ["a", "b"]},
    {"type": "audio_chunk", "data": [[1, 2], [3]]},
    {"type": "audio_chunk", "data": [0.0] * (ws_endpoints.MAX_JSON_AUDIO_SAMPLES + 1)},
    {"type": "config", "config": 5},
    {"type": "config", "config": {"sample_rate": "x"}},
])
def test_a_bad_audio_message_does_not_end_the_feed(open_client, message):
    client, _ = open_client
    with client.websocket_connect("/ws/audio") as ws:
        assert pong_after(ws, message)[-1] == "pong"


def test_good_audio_still_flows_after_a_bad_message(open_client):
    client, analyzer = open_client
    with client.websocket_connect("/ws/audio") as ws:
        pong_after(ws, "not json")
        seen = pong_after(ws, {"type": "audio_chunk", "data": [0.1, 0.2, 0.3]})
    assert "analysis" in seen
    assert len(analyzer.chunks) == 1


@pytest.mark.parametrize("message", [
    "not json",
    "[1, 2]",
    {"type": "set_channel", "channel": "abc", "value": 1},
    {"type": "set_channel", "channel": 1, "value": 1e400},
    {"type": "set_channel", "universe": "x", "channel": 1, "value": 1},
])
def test_a_bad_dmx_message_does_not_end_the_connection(open_client, monkeypatch, message):
    from app.services.dmx.dmx_controller import DMXController

    client, _ = open_client
    monkeypatch.setattr(app.state, "dmx_controller", DMXController(), raising=False)
    with client.websocket_connect("/ws/dmx") as ws:
        assert pong_after(ws, message)[-1] == "pong"


def test_a_bad_show_message_does_not_end_the_connection(open_client):
    client, _ = open_client
    with client.websocket_connect("/ws/show") as ws:
        assert pong_after(ws, "not json")[-1] == "pong"


class FakeSocket:
    def __init__(self, delay=0.0, fail=False):
        self.delay = delay
        self.fail = fail
        self.sent = []
        self.closed = False

    async def send_text(self, text):
        if self.fail:
            raise RuntimeError("gone")
        await asyncio.sleep(self.delay)
        self.sent.append(json.loads(text))

    async def close(self, code=1000):
        self.closed = True


async def test_one_stalled_client_does_not_hold_up_the_rest():
    manager = ws_endpoints.ConnectionManager()
    healthy, stalled = FakeSocket(), FakeSocket(delay=30)
    manager.active_connections["audio"] = {healthy, stalled}

    started = time.monotonic()
    await manager.broadcast("audio", {"type": "analysis"})

    assert time.monotonic() - started < 1.0
    assert healthy.sent == [{"type": "analysis"}]
    assert manager.active_connections["audio"] == {healthy}
    assert stalled.closed


async def test_an_odd_numpy_value_reaches_every_client():
    manager = ws_endpoints.ConnectionManager()
    a, b = FakeSocket(), FakeSocket()
    manager.active_connections["audio"] = {a, b}

    await manager.broadcast("audio", {"v": np.float16(0.5), "n": np.uint8(3), "bad": math.nan})

    for client in (a, b):
        assert client.sent == [{"v": 0.5, "n": 3, "bad": None}]
    assert manager.active_connections["audio"] == {a, b}


async def test_an_unencodable_payload_drops_no_one():
    manager = ws_endpoints.ConnectionManager()
    a = FakeSocket()
    manager.active_connections["audio"] = {a}

    await manager.broadcast("audio", {"v": object()})

    assert manager.active_connections["audio"] == {a}
    assert a.sent == []


def test_audio_endpoints_say_unavailable_when_the_analyzer_failed(open_client, monkeypatch):
    client, _ = open_client
    monkeypatch.setattr(app.state, "audio_analyzer", None, raising=False)
    response = client.get("/api/audio/current")
    assert response.status_code == 503


@pytest.mark.parametrize("url", [
    "/api/effects/strobe/burst?duration=nan",
    "/api/effects/strobe/burst?frequency=inf",
    "/api/effects/trigger/buildup?duration=0",
    "/api/effects/pro/flash?duration=nan",
    "/api/effects/pro/movement/speed-ramp?duration=inf",
    "/api/training/manual/strobe?duration=nan",
])
def test_nonsense_effect_timings_are_refused_before_they_are_stored(open_client, url):
    client, _ = open_client
    assert client.post(url).status_code == 422
