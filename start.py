#!/usr/bin/env python3
"""
Intelligent Lighting System - Single Startup Script
Starts all services and handles clean shutdown with Ctrl+C

IMPORTANT: Run this with the backend venv Python:
  backend\\venv\\Scripts\\python.exe start.py
"""

import subprocess
import sys
import os
import signal
import time
import webbrowser
import asyncio
from pathlib import Path

# Get the root directory
ROOT_DIR = Path(__file__).parent.absolute()
BACKEND_DIR = ROOT_DIR / "backend"
VISUALIZER_DIR = ROOT_DIR / "visualizer"
SCRIPTS_DIR = ROOT_DIR / "scripts"

# Check if we're running in the correct venv
VENV_PYTHON = BACKEND_DIR / "venv" / "Scripts" / "python.exe" if sys.platform == "win32" else BACKEND_DIR / "venv" / "bin" / "python"

# If not running from venv, restart with venv Python
if str(VENV_PYTHON) not in sys.executable and VENV_PYTHON.exists():
    print(f"Restarting with venv Python...")
    # Use subprocess to handle paths with spaces correctly
    result = subprocess.run([str(VENV_PYTHON), str(Path(__file__).absolute())] + sys.argv[1:])
    sys.exit(result.returncode)

# Now we're in venv - import packages
try:
    if sys.platform == "win32":
        import pyaudiowpatch as pyaudio
    else:
        import pyaudio
    import numpy as np
    import websockets
except ImportError as e:
    print(f"ERROR: Missing package: {e}")
    if sys.platform == "win32":
        print("Make sure the backend venv has all dependencies installed:")
        print("  cd backend && venv\\Scripts\\pip install pyaudiowpatch numpy websockets")
    else:
        print("Make sure the backend venv has all dependencies installed:")
        print("  cd backend && source venv/bin/activate && pip install pyaudio numpy websockets")
        if sys.platform == "darwin":
            print("  (You may need: brew install portaudio)")
    sys.exit(1)

# Add scripts dir to path
sys.path.insert(0, str(SCRIPTS_DIR))
from launch_helpers import (  # noqa: E402
    backend_answers, backend_ws_url, mint_local_token, pick_device,
    reactive_on_message, rig_id_from_env,
)

BACKEND_URL = "http://localhost:8000"

# Store processes globally for cleanup
processes = []
audio_capture_instance = None
running = True


def start_backend():
    """Start the FastAPI backend server."""
    print("[1/3] Starting Backend API (port 8000)...")

    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    )
    return proc


def start_visualizer():
    """Start the visualizer HTTP server."""
    print("[2/3] Starting Visualizer Server (port 8080)...")

    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "http.server", "8080"],
        cwd=str(VISUALIZER_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    )
    return proc


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


def stop_children():
    """Stop every service this script started, so a failed start leaves nothing behind."""
    for name, proc in processes:
        if proc and proc.poll() is None:
            print(f"  Stopping {name}...")
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def cleanup(signum=None, frame=None):
    """Clean up all processes."""
    global audio_capture_instance, running

    running = False
    print("\n\nShutting down all services...")

    # Stop audio capture
    if audio_capture_instance:
        print("  Stopping Audio Capture...")
        try:
            audio_capture_instance.stop()
        except:
            pass

    stop_children()

    print("All services stopped.")
    os._exit(0)


class InlineAudioCapture:
    """Simplified audio capture that runs in the main script."""

    def __init__(self):
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
        backoff = 1.0
        while self.running_allowed():
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
            if not self.running_allowed():
                break
            # A session that ran a while earns a quick retry; repeated quick
            # failures back off so a missing device doesn't spin.
            backoff = 1.0 if time.time() - started > 30 else min(backoff * 2, 30.0)
            print(f"  Reconnecting audio in {backoff:.0f}s...")
            await asyncio.sleep(backoff)

    def running_allowed(self):
        return self.running and running

    async def _session(self, device_info, rig_id, token):
        import json

        self.running = True
        sample_rate = int(device_info['sample_rate'])
        channels = device_info['channels']

        ws_url = backend_ws_url(BACKEND_URL, "/ws/audio", token)
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
        while self.running_allowed():
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
        """Stop capture (from the signal handler; the socket closes with the process)."""
        self.running = False
        self._close_stream()


def backend_output_reader(proc):
    """Read and print backend output in a thread."""
    try:
        while proc.poll() is None:
            line = proc.stdout.readline()
            if line:
                print(f"[Backend] {line.strip()}")
    except:
        pass


async def main_async(selected_device, rig_id, token):
    """Async main function."""
    global audio_capture_instance

    audio_capture_instance = InlineAudioCapture()
    audio_capture_instance.running = True
    await audio_capture_instance.run(selected_device, rig_id=rig_id, token=token)


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(description="Start the Intelligent Lighting System")
    parser.add_argument("--device", default=os.getenv("ILS_AUDIO_DEVICE"),
                        help="Audio device index or part of its name (or set ILS_AUDIO_DEVICE)")
    parser.add_argument("--rig-id", default=None,
                        help="Rig to drive (or set ILS_RIG_ID); default is the active rig")
    parser.add_argument("--no-browser", action="store_true", help="Don't open a browser")
    return parser.parse_args()


def wait_for_backend(backend, seconds=60):
    """Wait until the backend answers. False if it exits or never answers."""
    for i in range(seconds):
        if backend.poll() is not None:
            print(f"  ERROR: the backend exited (code {backend.returncode}); see [Backend] lines above")
            return False
        if backend_answers(f"{BACKEND_URL}/health"):
            print("  Backend is ready!")
            return True
        print(f"  Waiting... ({i+1}s)")
        time.sleep(1)
    print(f"  ERROR: the backend did not answer within {seconds}s")
    return False


def main():
    global processes, audio_capture_instance, running
    import threading

    args = parse_args()
    rig_id = rig_id_from_env(args.rig_id)

    print("=" * 60)
    print("  Intelligent Lighting System")
    print("=" * 60)
    print()
    print(f"  Using Python: {sys.executable}")
    print()

    # Register signal handlers
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, cleanup)

    try:
        backend = start_backend()
        processes.append(("Backend", backend))
        # Read its output from the start: an unread pipe fills while we wait
        # and then blocks the backend itself.
        threading.Thread(target=backend_output_reader, args=(backend,), daemon=True).start()

        print("  Waiting for backend to start...")
        if not wait_for_backend(backend):
            return 1

        visualizer = start_visualizer()
        processes.append(("Visualizer", visualizer))
        time.sleep(1)

        print("\n[3/3] Setting up Audio Capture...")
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
        token = os.getenv("ILS_TOKEN", "").strip() or mint_local_token(VENV_PYTHON if VENV_PYTHON.exists() else sys.executable, BACKEND_DIR)

        print()
        print("=" * 60)
        print("  All services started!")
        print("=" * 60)
        print()
        print("  Visualizer:       http://localhost:8080")
        print("  Operator Console: http://localhost:8080/operator.html")
        print("  Backend API:      http://localhost:8000")
        print("  API Docs:         http://localhost:8000/docs")
        print()
        print("  Press Ctrl+C to stop all services")
        print("=" * 60)
        print()

        if not args.no_browser:
            webbrowser.open("http://localhost:8080")

        asyncio.run(main_async(selected_device, rig_id, token))
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        running = False
        if audio_capture_instance:
            audio_capture_instance.running = False
        stop_children()


if __name__ == "__main__":
    sys.exit(main())
