#!/usr/bin/env python3
"""
Audio Capture for Intelligent Lighting System
==============================================

Captures system audio OUTPUT using WASAPI loopback (pyaudiowpatch)
and sends it to the backend for real-time analysis and DMX control.

Requirements:
    pip install pyaudiowpatch numpy websockets

Usage:
    python audio_capture.py
"""

import asyncio
import json
import sys
import time
import queue
import threading
from typing import Optional, List

try:
    import numpy as np
except ImportError:
    print("Missing numpy. Please install:")
    print("  pip install numpy")
    sys.exit(1)

try:
    import pyaudiowpatch as pyaudio
except ImportError:
    print("Missing pyaudiowpatch. Please install:")
    print("  pip install pyaudiowpatch")
    sys.exit(1)

try:
    import websockets
except ImportError:
    print("Missing websockets. Please install:")
    print("  pip install websockets")
    sys.exit(1)


# Configuration
BACKEND_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws/audio"
CHUNK_SIZE = 2048


def list_loopback_devices():
    """List WASAPI loopback devices (output devices you can capture FROM)."""
    print("\n" + "=" * 70)
    print("  WASAPI Loopback Devices - Capture system audio output")
    print("=" * 70)

    p = pyaudio.PyAudio()
    loopback_devices = []

    try:
        # Get WASAPI host API info
        wasapi_info = None
        for i in range(p.get_host_api_count()):
            api_info = p.get_host_api_info_by_index(i)
            if 'WASAPI' in api_info['name']:
                wasapi_info = api_info
                break

        if wasapi_info is None:
            print("WASAPI not available!")
            return []

        print(f"\n  Found WASAPI with {wasapi_info['deviceCount']} devices\n")
        print("  LOOPBACK DEVICES (capture what you hear):")
        print("-" * 70)

        # Find loopback devices
        for i in range(p.get_device_count()):
            device_info = p.get_device_info_by_index(i)

            # Check if it's a loopback device
            if device_info.get('isLoopbackDevice', False):
                name = device_info['name']
                channels = device_info['maxInputChannels']
                sample_rate = int(device_info['defaultSampleRate'])

                # Mark Studio 24c as recommended
                marker = ""
                if 'studio 24c' in name.lower() or 'main out' in name.lower():
                    marker = " << YOUR INTERFACE"
                elif 'speakers' in name.lower() or 'headphones' in name.lower():
                    marker = " [Default Output]"

                print(f"  [{i:2d}] {name[:55]:55s}{marker}")
                print(f"       Channels: {channels}, Sample Rate: {sample_rate} Hz")
                loopback_devices.append({
                    'index': i,
                    'name': name,
                    'channels': channels,
                    'sample_rate': sample_rate,
                    'info': device_info
                })

        print("-" * 70)

    finally:
        p.terminate()

    if not loopback_devices:
        print("\n  No loopback devices found!")
        print("  Make sure your audio output is active.")

    return loopback_devices


class AudioCapture:
    """Captures system audio using WASAPI loopback."""

    def __init__(self):
        self.running = False
        self.ws = None
        self.stream = None
        self.pyaudio = None

        # Thread-safe queue for audio data
        self.audio_queue = queue.Queue(maxsize=100)

        # Stats
        self.chunks_sent = 0
        self.chunks_received = 0
        self.current_bpm = 0
        self.current_emotion = "neutral"

    def audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback - runs in separate thread."""
        if not self.running:
            return (None, pyaudio.paComplete)

        try:
            # Convert bytes to numpy array
            audio_data = np.frombuffer(in_data, dtype=np.float32)

            # Convert to mono if stereo
            if len(audio_data) > frame_count:
                # Reshape to (frames, channels) and take mean
                num_channels = len(audio_data) // frame_count
                audio_data = audio_data.reshape(-1, num_channels).mean(axis=1)

            # Put in queue
            self.audio_queue.put_nowait(audio_data.copy())
            self.chunks_received += 1

        except queue.Full:
            pass
        except Exception as e:
            print(f"\nCallback error: {e}")

        return (None, pyaudio.paContinue)

    async def connect_websocket(self, rig_id: Optional[int] = None):
        """Connect to backend WebSocket."""
        try:
            # Connect with ping/pong keepalive to prevent timeout
            self.ws = await websockets.connect(
                WS_URL,
                ping_interval=20,  # Send ping every 20 seconds
                ping_timeout=10,   # Wait 10 seconds for pong
                close_timeout=5
            )
            print(f"Connected to {WS_URL}")

            # Enable reactive lighting mode
            await self.ws.send(json.dumps({
                "type": "reactive_on",
                "rig_id": rig_id
            }))

            response = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
            data = json.loads(response)

            if data.get('type') == 'reactive_enabled':
                print("Reactive lighting mode ENABLED!")
                print("DMX lights will respond to your music!")

            return True

        except Exception as e:
            print(f"Failed to connect: {e}")
            print("Make sure the backend is running (docker-compose up)")
            return False

    async def send_audio_loop(self):
        """Send audio from queue to WebSocket."""
        while self.running:
            try:
                try:
                    audio_data = self.audio_queue.get(timeout=0.1)
                except queue.Empty:
                    await asyncio.sleep(0.01)
                    continue

                if self.ws and self.running:
                    message = {
                        "type": "audio_chunk",
                        "sample_rate": self.sample_rate,
                        "data": audio_data.tolist()
                    }
                    await self.ws.send(json.dumps(message))
                    self.chunks_sent += 1

            except websockets.ConnectionClosed:
                print("\nWebSocket disconnected")
                break
            except Exception as e:
                print(f"\nSend error: {e}")
                await asyncio.sleep(0.1)

    async def receive_loop(self):
        """Receive analysis results from backend."""
        while self.running and self.ws:
            try:
                message = await asyncio.wait_for(self.ws.recv(), timeout=1.0)
                data = json.loads(message)

                if data.get('type') == 'analysis':
                    beat = data.get('beat', {})
                    mood = data.get('mood', {})

                    self.current_bpm = beat.get('bpm', 0)
                    self.current_emotion = mood.get('primary_emotion', 'neutral')
                    self._print_status(beat, mood)

                elif data.get('type') == 'heartbeat':
                    pass

            except asyncio.TimeoutError:
                self._print_status_simple()
            except websockets.ConnectionClosed:
                break
            except Exception as e:
                if self.running:
                    print(f"\nReceive error: {e}")

    def _print_status(self, beat: dict, mood: dict):
        """Print status with beat visualization."""
        bpm = beat.get('bpm', 0)
        position = beat.get('beat_position', 1)
        is_beat = beat.get('is_beat', False)
        emotion = mood.get('primary_emotion', 'neutral')
        arousal = mood.get('arousal', 0)

        # Beat indicator
        if is_beat:
            bar = "*" * position + "." * (4 - position)
        else:
            bar = "." * 4

        # Energy meter
        energy = "|" * min(10, int(abs(arousal) * 15))

        status = f"\r[{bar}] BPM:{bpm:5.0f} | {emotion:10s} | {energy:10s} | Sent:{self.chunks_sent:5d}"
        print(status, end='', flush=True)

    def _print_status_simple(self):
        """Print simple status."""
        status = f"\rBPM:{self.current_bpm:5.0f} | {self.current_emotion:10s} | Sent:{self.chunks_sent:5d} | Recv:{self.chunks_received:5d}"
        print(status, end='', flush=True)

    async def run(self, device_info: dict, rig_id: Optional[int] = None):
        """Main capture loop."""
        self.running = True
        self.sample_rate = int(device_info['sample_rate'])

        # Connect to backend
        if not await self.connect_websocket(rig_id):
            return

        print(f"\nCapturing from: {device_info['name']}")
        print(f"Sample Rate: {self.sample_rate} Hz")
        print(f"Channels: {device_info['channels']}")
        print("\nPlay music and watch the lights react!")
        print("Press Ctrl+C to stop\n")

        try:
            self.pyaudio = pyaudio.PyAudio()

            # Open WASAPI loopback stream
            self.stream = self.pyaudio.open(
                format=pyaudio.paFloat32,
                channels=device_info['channels'],
                rate=self.sample_rate,
                input=True,
                input_device_index=device_info['index'],
                frames_per_buffer=CHUNK_SIZE,
                stream_callback=self.audio_callback,
            )

            self.stream.start_stream()
            print("Audio capture started!\n")

            # Run async loops
            await asyncio.gather(
                self.send_audio_loop(),
                self.receive_loop(),
            )

        except Exception as e:
            print(f"\nError: {e}")
            import traceback
            traceback.print_exc()
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

        if self.pyaudio:
            try:
                self.pyaudio.terminate()
            except:
                pass

        print("\n\nAudio capture stopped.")
        print(f"Total chunks sent: {self.chunks_sent}")


async def test_backend():
    """Test backend connection."""
    try:
        ws = await asyncio.wait_for(websockets.connect(WS_URL), timeout=3.0)
        await ws.close()
        print(f"Backend connected: {WS_URL}")
        return True
    except Exception as e:
        print(f"Backend not reachable: {e}")
        print("Run: docker-compose up")
        return False


async def main(auto_select=False):
    """Main entry point."""
    print("=" * 70)
    print("  Intelligent Lighting System - WASAPI Loopback Audio Capture")
    print("  Captures what you HEAR through your speakers/interface")
    print("=" * 70)

    # Test backend
    await test_backend()

    # List loopback devices
    devices = list_loopback_devices()

    if not devices:
        print("\nNo loopback devices found.")
        print("Make sure audio is playing through your output device.")
        return

    # Find recommended device (Studio 24c or default)
    recommended = None
    for dev in devices:
        if 'studio 24c' in dev['name'].lower() or 'main out' in dev['name'].lower():
            recommended = dev
            break

    if recommended is None and devices:
        recommended = devices[0]

    # Auto-select or get user selection
    if auto_select:
        selected = recommended
        print(f"\nAuto-selected: {selected['name']}")
    else:
        print(f"\nSelect device to capture FROM (what you hear):")
        if recommended:
            print(f"Recommended: [{recommended['index']}] {recommended['name'][:40]}")

        print("\nEnter device number (or press Enter for recommended):")

        try:
            user_input = input("> ").strip()

            if user_input:
                device_index = int(user_input)
                # Find device by index
                selected = None
                for dev in devices:
                    if dev['index'] == device_index:
                        selected = dev
                        break
                if selected is None:
                    print(f"Device {device_index} not found in loopback devices")
                    return
            else:
                selected = recommended
                print(f"Using: {selected['name']}")

        except ValueError:
            print("Invalid input")
            return
        except EOFError:
            selected = recommended
            print(f"Using: {selected['name']}")

    # Start capture
    rig_id = 5  # Demo rig
    print(f"\nUsing rig ID: {rig_id} (demo rig)")

    capture = AudioCapture()

    try:
        await capture.run(device_info=selected, rig_id=rig_id)
    except KeyboardInterrupt:
        capture.stop()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Audio Capture for ILS")
    parser.add_argument("--auto", action="store_true", help="Auto-select first loopback device")
    args = parser.parse_args()

    try:
        asyncio.run(main(auto_select=args.auto))
    except KeyboardInterrupt:
        print("\n\nExiting...")
