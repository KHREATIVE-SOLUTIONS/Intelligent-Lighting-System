#!/usr/bin/env python3
"""
Audio Feed for the Launcher
===========================

Captures this machine's audio and sends it to the backend, reconnecting until
stopped. `python start.py --audio` runs it as a child once the backend is up.

This is the capture loop that used to live inside start.py. It is its own
process now so that a default start needs no audio packages and asks no
questions, and so that it runs under the backend venv, where pyaudio lives.

    backend/venv python scripts/launch_audio.py --backend-url http://127.0.0.1:8000
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from launch_helpers import (  # noqa: E402
    backend_ws_url, mint_local_token, pick_device, reactive_on_message, rig_id_from_env,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"

# Filled in by load_audio_stack(), so importing this module needs no audio packages.
pyaudio = None
np = None
websockets = None


def load_audio_stack() -> bool:
    """Import the audio packages, or say how to install them."""
    global pyaudio, np, websockets
    try:
        if sys.platform == "win32":
            import pyaudiowpatch as _pyaudio
        else:
            import pyaudio as _pyaudio
        import numpy as _np
        import websockets as _websockets
    except ImportError as e:
        print(f"ERROR: Missing package: {e}")
        print("Make sure the backend venv has the audio packages installed:")
        if sys.platform == "win32":
            print("  cd backend && venv\\Scripts\\pip install pyaudiowpatch numpy websockets")
        else:
            print("  cd backend && source venv/bin/activate && pip install pyaudio numpy websockets")
            if sys.platform == "darwin":
                print("  (You may need: brew install portaudio)")
        return False
    pyaudio, np, websockets = _pyaudio, _np, _websockets
    return True


def list_audio_devices():
    """List available audio capture devices (platform-aware)."""
    print("\n" + "=" * 60)
    if sys.platform == "win32":
        print("  AUDIO LOOPBACK DEVICES (WASAPI)")
    elif sys.platform == "darwin":
        print("  AUDIO INPUT DEVICES (CoreAudio)")
        print("  Tip: Install BlackHole for system audio capture")
    else:
        print("  AUDIO INPUT DEVICES")
    print("=" * 60)

    # macOS virtual audio device keywords
    _macos_loopback = ["blackhole", "loopback", "soundflower", "virtual", "aggregate"]

    p = pyaudio.PyAudio()
    loopback_devices = []

    try:
        for i in range(p.get_device_count()):
            device_info = p.get_device_info_by_index(i)

            if sys.platform == "win32":
                # Windows: use pyaudiowpatch loopback flag
                if device_info.get('isLoopbackDevice', False):
                    name = device_info['name']
                    channels = device_info['maxInputChannels']
                    sample_rate = int(device_info['defaultSampleRate'])
                    print(f"  [{i:2d}] {name[:50]}")
                    loopback_devices.append({
                        'index': i, 'name': name, 'channels': channels,
                        'sample_rate': sample_rate, 'info': device_info,
                    })
            else:
                # macOS/Linux: list input devices, highlight virtual ones
                max_in = device_info.get('maxInputChannels', 0)
                if max_in > 0:
                    name = device_info['name']
                    channels = max_in
                    sample_rate = int(device_info['defaultSampleRate'])
                    name_lower = name.lower()
                    is_virtual = any(kw in name_lower for kw in _macos_loopback)
                    marker = " [VIRTUAL]" if is_virtual else ""
                    print(f"  [{i:2d}] {name[:45]}{marker}")
                    loopback_devices.append({
                        'index': i, 'name': name, 'channels': channels,
                        'sample_rate': sample_rate, 'info': device_info,
                    })

    finally:
        p.terminate()

    print("=" * 60)
    return loopback_devices


def select_audio_device(devices, choice=None):
    """Pick the capture device: --device / ILS_AUDIO_DEVICE, else ask, else recommended."""
    if not devices:
        return None

    # Find recommended device
    recommended = None
    for dev in devices:
        name_lower = dev['name'].lower()
        if 'studio 24c' in name_lower or 'main out' in name_lower or 'speakers' in name_lower:
            recommended = dev
            break
    if recommended is None:
        recommended = devices[0]

    print(f"\nRecommended: [{recommended['index']}] {recommended['name'][:45]}")
    return pick_device(devices, recommended, choice=choice)


class InlineAudioCapture:
    """Capture audio and send it to the backend's /ws/audio."""

    def __init__(self, backend_url):
        self.backend_url = backend_url
        self.running = False
        self.ws = None
        self.stream = None
        self.pa = None
        self.chunks_sent = 0
        self.chunks_received = 0

    async def run(self, device_info, rig_id=None, token=None):
        """Capture and send audio, reconnecting until the script is stopped.

        This used to give up for good on the first dropped connection or audio
        error, and the lights then held the last frame for the rest of the night.
        """
        self.running = True
        backoff = 1.0
        while self.running:
            started = time.time()
            try:
                await self._session(device_info, rig_id, token)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"\n  Audio capture stopped: {e}")
            finally:
                self._close_stream()
                await self._close_ws()
            if not self.running:
                break
            # A session that ran a while earns a quick retry; repeated quick
            # failures back off so a missing device doesn't spin.
            backoff = 1.0 if time.time() - started > 30 else min(backoff * 2, 30.0)
            print(f"  Reconnecting audio in {backoff:.0f}s...")
            await asyncio.sleep(backoff)

    async def _session(self, device_info, rig_id, token):
        sample_rate = int(device_info['sample_rate'])
        channels = device_info['channels']

        ws_url = backend_ws_url(self.backend_url, "/ws/audio", token)
        self.ws = await websockets.connect(ws_url, ping_interval=20, ping_timeout=10)
        print("  Connected to backend WebSocket")
        await self.ws.send(reactive_on_message(rig_id))
        await asyncio.wait_for(self.ws.recv(), timeout=5.0)
        print(f"  Reactive lighting enabled ({'rig ' + str(rig_id) if rig_id else 'active rig'})")

        self.pa = pyaudio.PyAudio()
        self.stream = self.pa.open(
            format=pyaudio.paFloat32,
            channels=channels,
            rate=sample_rate,
            input=True,
            input_device_index=device_info['index'],
            frames_per_buffer=2048,
        )
        print(f"  Audio stream opened: {device_info['name'][:40]}")
        print()
        print("=" * 60)
        print("  CAPTURING AUDIO - Play some music!")
        print("=" * 60)
        print()

        last_status_time = time.time()
        while self.running:
            data = self.stream.read(2048, exception_on_overflow=False)
            audio_array = np.frombuffer(data, dtype=np.float32)
            if channels > 1:
                audio_array = audio_array.reshape(-1, channels).mean(axis=1)
            self.chunks_received += 1

            await self.ws.send(json.dumps({
                "type": "audio_chunk",
                "sample_rate": sample_rate,
                "data": audio_array.tolist(),
            }))
            self.chunks_sent += 1

            # Drain replies so they don't pile up; a closed socket raises here
            # or on the next send and the session reconnects.
            try:
                while True:
                    await asyncio.wait_for(self.ws.recv(), timeout=0.001)
            except asyncio.TimeoutError:
                pass

            now = time.time()
            if now - last_status_time >= 1.0:
                rms = np.sqrt(np.mean(audio_array ** 2))
                level = int(rms * 50)
                bar = "|" * min(level, 30)
                print(f"\r  Audio: [{bar:30s}] Chunks: {self.chunks_sent:5d}  ", end="", flush=True)
                last_status_time = now

            await asyncio.sleep(0.01)

    def _close_stream(self):
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        if self.pa:
            try:
                self.pa.terminate()
            except Exception:
                pass
            self.pa = None

    async def _close_ws(self):
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

    def stop(self):
        self.running = False
        self._close_stream()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Feed this machine's audio to the lighting backend")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000",
                        help="Backend address (default http://127.0.0.1:8000)")
    parser.add_argument("--device", default=os.getenv("ILS_AUDIO_DEVICE"),
                        help="Audio device index or part of its name (or set ILS_AUDIO_DEVICE)")
    parser.add_argument("--rig-id", default=None,
                        help="Rig to drive (or set ILS_RIG_ID); default is the active rig")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not load_audio_stack():
        return 1
    rig_id = rig_id_from_env(args.rig_id)

    print("\nSetting up Audio Capture...")
    devices = list_audio_devices()
    if not devices:
        print("  ERROR: No audio capture devices found!")
        if sys.platform == "darwin":
            print("  Install BlackHole (free) to capture system audio:")
            print("    brew install blackhole-2ch")
            print("  Or select a microphone for live input.")
        else:
            print("  Make sure you have audio output devices.")
        return 1

    selected_device = select_audio_device(devices, args.device)
    if not selected_device:
        print("  ERROR: No device selected!")
        return 1
    print(f"\n  Selected: {selected_device['name'][:50]}")

    # With login on, the audio feed needs a token like any other client.
    token = os.getenv("ILS_TOKEN", "").strip() or mint_local_token(sys.executable, BACKEND_DIR)

    capture = InlineAudioCapture(args.backend_url)
    try:
        asyncio.run(capture.run(selected_device, rig_id=rig_id, token=token))
    except KeyboardInterrupt:
        pass
    finally:
        capture.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
