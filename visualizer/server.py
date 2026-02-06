#!/usr/bin/env python3
"""
ILS Visualizer Server
Receives Art-Net UDP packets and relays DMX/audio data to web clients via WebSocket.
"""

import asyncio
import json
import logging
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
    yield
    global _http_session
    if _http_session and not _http_session.closed:
        await _http_session.close()


app = FastAPI(title="ILS Visualizer", lifespan=lifespan)

# ILS Backend URL
ILS_BACKEND_URL = "http://localhost:8000"

# Connected WebSocket clients
clients: Set[WebSocket] = set()

# Current DMX universe data (512 channels)
dmx_data = bytearray(512)

# Current audio data
audio_data = None

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
            timeout=aiohttp.ClientTimeout(total=1)
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
                    "beat": data.get("beat", {}).get("is_beat", False)
                }
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


async def data_polling_loop():
    """Continuously poll for audio and DMX data from ILS backend."""
    print("Starting data polling loop at 60Hz...")
    while True:
        try:
            # Fetch both audio and DMX data concurrently
            audio_task = fetch_audio_data()
            dmx_task = fetch_dmx_data()
            audio_ok, dmx_ok = await asyncio.gather(audio_task, dmx_task)

            if audio_ok:
                await broadcast_audio()
            if dmx_ok:
                await broadcast_dmx()
        except Exception as e:
            # BUG-040 fix: log polling errors instead of silencing them
            logger.debug(f"Polling error: {e}")
        await asyncio.sleep(0.016)  # 60 Hz polling


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time data."""
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
                    global audio_data
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
    uvicorn.run(app, host="0.0.0.0", port=8080)
