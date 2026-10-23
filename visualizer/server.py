#!/usr/bin/env python3
"""
ILS Visualizer Server
Receives Art-Net UDP packets and relays DMX/audio data to web clients via WebSocket.
"""

import asyncio
import json
import logging
import os
import struct
from contextlib import asynccontextmanager
from typing import Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import aiohttp

logger = logging.getLogger(__name__)


# BUG-039 fix: use lifespan context manager instead of deprecated @app.on_event
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown lifecycle."""
    await start_artnet_receiver()
    asyncio.create_task(data_polling_loop())
    asyncio.create_task(backend_ws_relay())
    yield
    global _http_session
    if _http_session and not _http_session.closed:
        await _http_session.close()


app = FastAPI(title="ILS Visualizer", lifespan=lifespan)

# ILS Backend URL
ILS_BACKEND_URL = os.getenv("ILS_BACKEND_URL", "http://127.0.0.1:8014")
# Operator token for a backend with login on. Without it every poll got 401 and
# the audio WebSocket was closed, so the visualizer showed nothing.
ILS_TOKEN = os.getenv("ILS_TOKEN", "").strip()


# Rig to drive. Unset means the active rig; rig 5 used to be hardcoded, which
# on any other database was someone else's rig or none.
ILS_RIG_ID = os.getenv("ILS_RIG_ID", "").strip()


def _reactive_on() -> dict:
    message = {"type": "reactive_on"}
    if ILS_RIG_ID.isdigit() and int(ILS_RIG_ID) > 0:
        message["rig_id"] = int(ILS_RIG_ID)
    return message


def _backend_ws_url(path: str) -> str:
    base = ILS_BACKEND_URL.replace("http://", "ws://").replace("https://", "wss://")
    url = f"{base}{path}"
    if ILS_TOKEN:
        from urllib.parse import quote
        url += f"?token={quote(ILS_TOKEN)}"
    return url

# Connected WebSocket clients
clients: Set[WebSocket] = set()

# Current DMX universe data (512 channels)
dmx_data = bytearray(512)

# Current audio data
audio_data = None
look_spec_data = None
visualizer_settings = {
    "haze_level": 1.0,
    "contrast_level": 1.0,
    "blackout_threshold": 0.02,
}

# Shared HTTP session for polling (BUG-020 fix)
_http_session: aiohttp.ClientSession = None

# Art-Net configuration
ARTNET_PORT = 6454
ARTNET_HEADER = b'Art-Net\x00'
ARTNET_OPCODE_DMX = 0x5000


class ArtNetReceiver:
    """Receives Art-Net packets and updates DMX data."""

    def __init__(self):
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        print(f"Art-Net receiver listening on port {ARTNET_PORT}")

    def datagram_received(self, data, addr):
        global dmx_data

        if len(data) < 18 or data[:8] != ARTNET_HEADER:
            return

        opcode = struct.unpack('<H', data[8:10])[0]
        if opcode != ARTNET_OPCODE_DMX:
            return

        universe = struct.unpack('<H', data[14:16])[0]
        length = struct.unpack('>H', data[16:18])[0]

        if universe > 1:
            return

        dmx_values = data[18:18 + min(length, 512)]
        for i, val in enumerate(dmx_values):
            if i < 512:
                dmx_data[i] = val

        asyncio.create_task(broadcast_dmx())

    def error_received(self, exc):
        print(f"Art-Net error: {exc}")

    def connection_lost(self, exc):
        print("Art-Net connection closed")


async def broadcast_dmx():
    """Send current DMX data to all connected clients."""
    if not clients:
        return

    message = json.dumps({"type": "dmx", "data": list(dmx_data)})

    disconnected = set()
    for client in list(clients):
        try:
            await client.send_text(message)
        except Exception:
            disconnected.add(client)
    clients.difference_update(disconnected)


async def broadcast_dmx_data(dmx_frame):
    """Send specific DMX frame data to all connected clients."""
    global dmx_data
    for i, val in enumerate(dmx_frame):
        if i < 512:
            dmx_data[i] = int(val) & 0xFF
    await broadcast_dmx()


async def broadcast_audio():
    """Send current audio data to all connected clients."""
    global audio_data
    if not clients or audio_data is None:
        return

    message = json.dumps({"type": "audio", "data": audio_data})

    disconnected = set()
    for client in list(clients):
        try:
            await client.send_text(message)
        except Exception:
            disconnected.add(client)
    clients.difference_update(disconnected)


async def _get_http_session():
    """Get or create the shared HTTP session (BUG-020 fix)."""
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=1),
            headers={"Authorization": f"Bearer {ILS_TOKEN}"} if ILS_TOKEN else None,
        )
    return _http_session


async def fetch_audio_data():
    """Fetch audio analysis data from ILS backend."""
    global audio_data

    try:
        session = await _get_http_session()
        async with session.get(f"{ILS_BACKEND_URL}/api/audio/current") as resp:
            if resp.status == 200:
                data = await resp.json()
                freq = data.get("frequency", {})
                bands = freq.get("bands", [])

                # Extract band energies for spectrum display
                spectrum = []
                for band in bands:
                    energy = band.get("energy", 0) * 255
                    spectrum.extend([int(energy)] * 4)  # 4 bars per band

                # Pad to 32 bars
                while len(spectrum) < 32:
                    spectrum.append(0)

                audio_data = {
                    "spectrum": spectrum[:32],
                    "rms": freq.get("rms_energy", 0),
                    "bass": bands[1].get("energy", 0) if len(bands) > 1 else 0,
                    "mid": bands[3].get("energy", 0) if len(bands) > 3 else 0,
                    "high": bands[5].get("energy", 0) if len(bands) > 5 else 0,
                    "beat": data.get("beat", {}).get("is_beat", False),
                    "look_spec": look_spec_data,
                    "visualizer_settings": visualizer_settings,
                }
                return True
    except Exception:
        pass
    return False


async def fetch_look_spec():
    """Fetch current typed beam/spot look specification from backend."""
    global look_spec_data
    try:
        session = await _get_http_session()
        async with session.get(f"{ILS_BACKEND_URL}/api/look-spec") as resp:
            if resp.status == 200:
                look_spec_data = await resp.json()
                return True
    except Exception:
        pass
    return False


async def fetch_dmx_data():
    """Fetch DMX data from ILS backend."""
    global dmx_data

    try:
        session = await _get_http_session()
        async with session.get(f"{ILS_BACKEND_URL}/api/dmx/universe/0") as resp:
            if resp.status == 200:
                data = await resp.json()
                values = data.get("data", [])
                for i, val in enumerate(values):
                    if i < 512:
                        dmx_data[i] = int(val) & 0xFF
                return True
    except Exception:
        pass
    return False


async def fetch_fixture_state():
    """Fetch fixture state snapshot from ILS backend effects engine."""
    try:
        session = await _get_http_session()
        async with session.get(f"{ILS_BACKEND_URL}/api/effects/fixture-states") as resp:
            if resp.status == 200:
                data = await resp.json()
                fixtures = data.get("fixture_states", [])
                section = data.get("section", "")
                if fixtures:
                    message = json.dumps({
                        "type": "analysis",
                        "section": section,
                        "lighting": {"fixtures": fixtures, "section": section}
                    })
                    disconnected = set()
                    for client in list(clients):
                        try:
                            await client.send_text(message)
                        except Exception:
                            disconnected.add(client)
                    clients.difference_update(disconnected)
                    return True
    except Exception:
        pass
    return False


async def data_polling_loop():
    """Continuously poll for audio, DMX, and fixture state data from ILS backend."""
    print("Starting data polling loop at 30Hz...")
    while True:
        try:
            # Fetch audio, DMX, and fixture state concurrently
            audio_task = fetch_audio_data()
            dmx_task = fetch_dmx_data()
            fixture_task = fetch_fixture_state()
            look_task = fetch_look_spec()
            audio_ok, dmx_ok, fixture_ok, _ = await asyncio.gather(
                audio_task, dmx_task, fixture_task, look_task
            )

            if audio_ok:
                await broadcast_audio()
            if dmx_ok:
                await broadcast_dmx()
        except Exception as e:
            # BUG-040 fix: log polling errors instead of silencing them
            logger.debug(f"Polling error: {e}")
        await asyncio.sleep(0.033)  # 30 Hz polling


async def backend_ws_relay():
    """Connect to the backend WebSocket and relay analysis messages to browser clients.

    This gives the visualizer access to per-fixture state (gobo, zoom, iris, frost, prism)
    and full analysis data that the REST polling loop doesn't provide.
    """
    import websockets as ws_lib

    # Convert http URL to ws URL
    ws_url = _backend_ws_url("/ws/audio")

    while True:
        try:
            print(f"Connecting to backend WebSocket at {ws_url.split('?')[0]}...")
            async with ws_lib.connect(ws_url, ping_interval=20, ping_timeout=10) as backend_ws:
                print(f"Connected to backend WebSocket!")

                # Enable reactive mode so the backend starts sending analysis data
                await backend_ws.send(json.dumps(_reactive_on()))

                async for message in backend_ws:
                    try:
                        # Relay the full analysis message to all browser clients
                        # This includes fixture states with gobo/zoom/iris/frost/prism
                        if clients:
                            disconnected = set()
                            for client in list(clients):
                                try:
                                    await client.send_text(message)
                                except Exception:
                                    disconnected.add(client)
                            clients.difference_update(disconnected)
                    except Exception as e:
                        logger.debug(f"Relay error: {e}")

        except Exception as e:
            print(f"Backend WebSocket connection failed: {e}, retrying in 3s...")
            await asyncio.sleep(3)


# Shared backend audio WS connection for proxying browser audio
_backend_audio_ws = None
_backend_audio_ws_lock = asyncio.Lock()


async def _get_backend_audio_ws():
    """Get or create a persistent WebSocket connection to the backend audio endpoint."""
    global _backend_audio_ws
    import websockets as ws_lib
    async with _backend_audio_ws_lock:
        if _backend_audio_ws is not None:
            try:
                await _backend_audio_ws.ping()
                return _backend_audio_ws
            except Exception:
                _backend_audio_ws = None
        ws_url = _backend_ws_url("/ws/audio")
        try:
            _backend_audio_ws = await ws_lib.connect(ws_url, ping_interval=20, ping_timeout=10)
            # Enable reactive mode
            await _backend_audio_ws.send(json.dumps(_reactive_on()))
            print(f"Audio proxy: connected to backend at {ws_url.split('?')[0]}")
            return _backend_audio_ws
        except Exception as e:
            print(f"Audio proxy: failed to connect to backend: {e}")
            return None


@app.websocket("/ws/audio-proxy")
async def audio_proxy_endpoint(websocket: WebSocket):
    """Proxy browser-captured audio to the backend audio WebSocket."""
    await websocket.accept()
    print("Audio proxy: browser client connected")
    chunks_forwarded = 0
    try:
        while True:
            # Receive binary PCM audio from browser
            data = await websocket.receive_bytes()
            backend_ws = await _get_backend_audio_ws()
            if backend_ws:
                try:
                    await backend_ws.send(data)
                    chunks_forwarded += 1
                    if chunks_forwarded % 100 == 0:
                        print(f"Audio proxy: forwarded {chunks_forwarded} chunks")
                except Exception as e:
                    global _backend_audio_ws
                    _backend_audio_ws = None
                    print(f"Audio proxy: send failed, will reconnect: {e}")
    except WebSocketDisconnect:
        print(f"Audio proxy: browser disconnected after {chunks_forwarded} chunks")
    except Exception as e:
        print(f"Audio proxy: error: {e}")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time data."""
    global audio_data
    await websocket.accept()
    clients.add(websocket)
    print(f"Client connected. Total clients: {len(clients)}")

    try:
        # Send current state immediately
        await websocket.send_text(json.dumps({"type": "dmx", "data": list(dmx_data)}))
        if audio_data:
            await websocket.send_text(json.dumps({"type": "audio", "data": audio_data}))

        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

            elif msg_type == "analysis":
                # BUG-009 fix: translate backend analysis format to visualizer format
                # Backend sends: {"type": "analysis", "beat": {...}, "frequency": {...}, ...}
                # Visualizer expects: {"type": "dmx", "data": [...]} and {"type": "audio", "data": {...}}
                lighting = msg.get("lighting", {})
                if lighting and "dmx_frame" in lighting:
                    await broadcast_dmx_data(lighting["dmx_frame"])
                freq = msg.get("frequency", {})
                beat = msg.get("beat", {})
                if freq or beat:
                    bands = freq.get("bands", [])
                    translated = {
                        "spectrum": [int(b.get("energy", 0) * 255) for b in bands for _ in range(4)][:32],
                        "rms": freq.get("rms_energy", 0),
                        "bass": bands[1].get("energy", 0) if len(bands) > 1 else 0,
                        "mid": bands[3].get("energy", 0) if len(bands) > 3 else 0,
                        "high": bands[5].get("energy", 0) if len(bands) > 5 else 0,
                        "beat": beat.get("is_beat", False),
                    }
                    audio_data = translated
                    await broadcast_audio()

    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(websocket)
        print(f"Client disconnected. Total clients: {len(clients)}")


@app.get("/")
async def root():
    """Serve the visualizer HTML."""
    return FileResponse("index.html")


@app.get("/index.html")
async def index_html():
    """Serve the 3D visualizer directly (also embedded by the operator console)."""
    return FileResponse("index.html")


@app.get("/operator.html")
async def operator_console():
    """Serve the dedicated operator console (training mode)."""
    return FileResponse("operator.html")


@app.get("/api/dmx")
async def get_dmx():
    """Get current DMX values."""
    return {"data": list(dmx_data)}


@app.post("/api/dmx")
async def set_dmx(values: dict):
    """Set DMX values for testing."""
    global dmx_data

    if "channel" in values and "value" in values:
        ch = int(values["channel"])
        val = int(values["value"])
        if 0 <= ch < 512 and 0 <= val <= 255:
            dmx_data[ch] = val
    elif "data" in values:
        for i, val in enumerate(values["data"]):
            if i < 512:
                dmx_data[i] = int(val) & 0xFF

    await broadcast_dmx()
    return {"status": "ok"}


@app.get("/api/audio")
async def get_audio():
    """Get current audio data."""
    return {"data": audio_data}


def _clamp_setting(value, lo: float, hi: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = lo
    return max(lo, min(hi, parsed))


@app.get("/api/settings")
async def get_settings():
    """Get current visualizer render settings."""
    return {"data": visualizer_settings}


@app.post("/api/settings")
async def update_settings(values: dict):
    """Update visualizer render settings (optional operator tuning)."""
    global visualizer_settings
    merged = dict(visualizer_settings)
    if "haze_level" in values:
        merged["haze_level"] = _clamp_setting(values["haze_level"], 0.5, 2.0)
    if "contrast_level" in values:
        merged["contrast_level"] = _clamp_setting(values["contrast_level"], 0.6, 1.8)
    if "blackout_threshold" in values:
        merged["blackout_threshold"] = _clamp_setting(values["blackout_threshold"], 0.0, 0.2)
    visualizer_settings = merged
    if audio_data is not None:
        audio_data["visualizer_settings"] = visualizer_settings
    return {"status": "ok", "data": visualizer_settings}


# Mount static files
app.mount("/js", StaticFiles(directory="js"), name="js")
app.mount("/css", StaticFiles(directory="css"), name="css")


async def start_artnet_receiver():
    """Start the Art-Net UDP receiver."""
    loop = asyncio.get_event_loop()
    try:
        transport, _ = await loop.create_datagram_endpoint(
            lambda: ArtNetReceiver(),
            local_addr=('0.0.0.0', ARTNET_PORT)
        )
        return transport
    except OSError as e:
        print(f"Warning: Could not bind to Art-Net port {ARTNET_PORT}: {e}")
        print("Art-Net reception disabled. Use REST API to set DMX values.")
        return None


if __name__ == "__main__":
    # 0.0.0.0 inside a container (compose publishes it on 127.0.0.1 only);
    # set VISUALIZER_HOST=127.0.0.1 when it shares the host's network.
    uvicorn.run(app, host=os.getenv("VISUALIZER_HOST", "0.0.0.0"), port=8080)
