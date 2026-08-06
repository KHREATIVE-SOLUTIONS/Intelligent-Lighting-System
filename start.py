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


def select_audio_device(devices):
    """Let user select an audio device."""
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
    print("\nEnter device number (or press Enter for recommended): ", end="", flush=True)

    try:
        user_input = input().strip()

        if user_input:
            device_index = int(user_input)
            for dev in devices:
                if dev['index'] == device_index:
                    return dev
            print(f"Device {device_index} not found, using recommended")
            return recommended
        else:
            return recommended

    except (ValueError, EOFError):
        return recommended


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

    # Stop other processes
    for name, proc in processes:
        if proc and proc.poll() is None:
            print(f"  Stopping {name}...")
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except:
                try:
                    proc.kill()
                except:
                    pass

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

    async def run(self, device_info):
        """Run audio capture."""
        global running

        self.running = True
        sample_rate = int(device_info['sample_rate'])
        channels = device_info['channels']

        # Connect to WebSocket with retries
        ws_url = "ws://localhost:8000/ws/audio"
        for attempt in range(10):
            try:
                self.ws = await websockets.connect(ws_url, ping_interval=20, ping_timeout=10)
                print(f"  Connected to backend WebSocket")

                # Enable reactive mode
                await self.ws.send('{"type": "reactive_on", "rig_id": 5}')
                response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                print(f"  Reactive lighting enabled!")
                break

            except Exception as e:
                if attempt < 9:
                    print(f"  WebSocket connection attempt {attempt+1} failed, retrying...")
                    await asyncio.sleep(1)
                else:
                    print(f"  ERROR: Could not connect to backend after 10 attempts: {e}")
                    return

        # Open audio stream
        try:
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

        except Exception as e:
            print(f"  ERROR: Could not open audio stream: {e}")
            return

        # Main capture loop
        last_status_time = time.time()
        try:
            while self.running and running:
                try:
                    # Read audio data
                    data = self.stream.read(2048, exception_on_overflow=False)
                    audio_array = np.frombuffer(data, dtype=np.float32)

                    # Convert to mono if needed
                    if channels > 1:
                        audio_array = audio_array.reshape(-1, channels).mean(axis=1)

                    self.chunks_received += 1

                    # Send to backend
                    if self.ws:
                        import json
                        message = {
                            "type": "audio_chunk",
                            "sample_rate": sample_rate,
                            "data": audio_array.tolist()
                        }
                        await self.ws.send(json.dumps(message))
                        self.chunks_sent += 1

                        # Receive and discard responses to prevent buffer buildup
                        try:
                            while True:
                                response = await asyncio.wait_for(self.ws.recv(), timeout=0.001)
                        except asyncio.TimeoutError:
                            pass
                        except:
                            pass

                    # Print status every second
                    now = time.time()
                    if now - last_status_time >= 1.0:
                        rms = np.sqrt(np.mean(audio_array ** 2))
                        level = int(rms * 50)
                        bar = "|" * min(level, 30)
                        print(f"\r  Audio: [{bar:30s}] Chunks: {self.chunks_sent:5d}  ", end="", flush=True)
                        last_status_time = now

                    await asyncio.sleep(0.01)

                except Exception as e:
                    if self.running:
                        print(f"\n  Audio error: {e}")
                    break

        except asyncio.CancelledError:
            pass
        finally:
            self.stop()

    def stop(self):
        """Stop capture."""
        self.running = False

        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass

        if self.pa:
            try:
                self.pa.terminate()
            except:
                pass

        if self.ws:
            try:
                asyncio.get_event_loop().run_until_complete(self.ws.close())
            except:
                pass


def backend_output_reader(proc):
    """Read and print backend output in a thread."""
    try:
        while proc.poll() is None:
            line = proc.stdout.readline()
            if line:
                print(f"[Backend] {line.strip()}")
    except:
        pass


async def main_async(selected_device, backend_proc):
    """Async main function."""
    global audio_capture_instance
    import threading

    # Start thread to read backend output
    output_thread = threading.Thread(target=backend_output_reader, args=(backend_proc,), daemon=True)
    output_thread.start()

    audio_capture_instance = InlineAudioCapture()
    await audio_capture_instance.run(selected_device)


def main():
    global processes, audio_capture_instance, running

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

    # Start backend
    backend = start_backend()
    if backend:
        processes.append(("Backend", backend))

    print("  Waiting for backend to start...")

    # Wait for backend to be ready (up to 30 seconds)
    import urllib.request
    for i in range(30):
        try:
            urllib.request.urlopen("http://localhost:8000/health", timeout=2)
            print("  Backend is ready!")
            break
        except:
            print(f"  Waiting... ({i+1}s)")
            time.sleep(1)
    else:
        print("  WARNING: Backend may not be fully started yet")

    # Start visualizer
    visualizer = start_visualizer()
    if visualizer:
        processes.append(("Visualizer", visualizer))

    time.sleep(1)

    # List audio devices
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
        return

    selected_device = select_audio_device(devices)

    if not selected_device:
        print("  ERROR: No device selected!")
        return

    print(f"\n  Selected: {selected_device['name'][:50]}")

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

    # Open browser
    webbrowser.open("http://localhost:8080")

    # Run audio capture
    try:
        asyncio.run(main_async(selected_device, backend))
    except KeyboardInterrupt:
        cleanup()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        cleanup()


if __name__ == "__main__":
    main()
