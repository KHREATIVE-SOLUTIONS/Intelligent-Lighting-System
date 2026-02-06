#!/usr/bin/env python3
"""
Test script to send DMX data to the visualizer via REST API.
Useful for testing the visualizer without Art-Net.
"""

import requests
import time
import math

VISUALIZER_URL = "http://localhost:8080/api/dmx"

# Fixture addresses from our demo rig
FIXTURES = [
    # Movers (16ch each)
    {"name": "Mover L1", "addr": 1, "type": "mover"},
    {"name": "Mover L2", "addr": 17, "type": "mover"},
    {"name": "Mover L3", "addr": 33, "type": "mover"},
    {"name": "Mover L4", "addr": 49, "type": "mover"},
    {"name": "Mover R1", "addr": 65, "type": "mover"},
    {"name": "Mover R2", "addr": 81, "type": "mover"},
    {"name": "Mover R3", "addr": 97, "type": "mover"},
    {"name": "Mover R4", "addr": 113, "type": "mover"},
    # Washes (14ch each)
    {"name": "Wash L1", "addr": 129, "type": "wash"},
    {"name": "Wash L2", "addr": 143, "type": "wash"},
    {"name": "Wash L3", "addr": 157, "type": "wash"},
    {"name": "Wash R1", "addr": 171, "type": "wash"},
    {"name": "Wash R2", "addr": 185, "type": "wash"},
    {"name": "Wash R3", "addr": 199, "type": "wash"},
    # LED Bars (12ch each)
    {"name": "Bar L1", "addr": 213, "type": "bar"},
    {"name": "Bar L2", "addr": 225, "type": "bar"},
    {"name": "Bar R1", "addr": 237, "type": "bar"},
    {"name": "Bar R2", "addr": 249, "type": "bar"},
]

# Channel offsets for each fixture type
CHANNELS = {
    "mover": {"pan": 0, "tilt": 2, "dimmer": 5, "shutter": 6, "red": 7, "green": 8, "blue": 9},
    "wash": {"pan": 0, "tilt": 2, "dimmer": 5, "shutter": 6, "red": 7, "green": 8, "blue": 9},
    "bar": {"dimmer": 0, "red": 2, "green": 3, "blue": 4},
}


def send_dmx(data):
    """Send DMX data to visualizer."""
    try:
        response = requests.post(VISUALIZER_URL, json={"data": data}, timeout=1)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending DMX: {e}")
        return False


def run_rainbow_chase():
    """Run a rainbow chase pattern across all fixtures."""
    print("Running rainbow chase pattern... (Ctrl+C to stop)")

    dmx = [0] * 512
    t = 0

    try:
        while True:
            for i, fix in enumerate(FIXTURES):
                addr = fix["addr"] - 1  # Convert to 0-indexed
                ch = CHANNELS[fix["type"]]

                # Phase offset based on fixture index
                phase = t + i * 0.3

                # Rainbow color
                r = int((math.sin(phase) * 0.5 + 0.5) * 255)
                g = int((math.sin(phase + 2.1) * 0.5 + 0.5) * 255)
                b = int((math.sin(phase + 4.2) * 0.5 + 0.5) * 255)

                # Set color channels
                dmx[addr + ch["red"]] = r
                dmx[addr + ch["green"]] = g
                dmx[addr + ch["blue"]] = b

                # Set dimmer
                dmx[addr + ch["dimmer"]] = 200

                # Set shutter open for movers/washes
                if "shutter" in ch:
                    dmx[addr + ch["shutter"]] = 255

                # Pan/tilt for movers and washes
                if "pan" in ch:
                    pan_val = int((math.sin(t * 0.3 + i * 0.5) * 0.3 + 0.5) * 255)
                    tilt_val = int((math.sin(t * 0.4 + i * 0.3) * 0.2 + 0.6) * 255)
                    dmx[addr + ch["pan"]] = pan_val
                    dmx[addr + ch["tilt"]] = tilt_val

            send_dmx(dmx)
            t += 0.05
            time.sleep(0.03)  # ~30 FPS

    except KeyboardInterrupt:
        print("\nStopped.")
        # Blackout
        send_dmx([0] * 512)


def run_audio_reactive_sim():
    """Simulate audio-reactive behavior."""
    print("Running audio-reactive simulation... (Ctrl+C to stop)")

    dmx = [0] * 512
    t = 0

    try:
        while True:
            # Simulate beat detection
            beat = math.sin(t * 4) > 0.7  # Periodic "beats"
            bass = (math.sin(t * 2) * 0.5 + 0.5)  # Low frequency
            mid = (math.sin(t * 5) * 0.5 + 0.5)   # Mid frequency
            high = (math.sin(t * 10) * 0.5 + 0.5) # High frequency

            for i, fix in enumerate(FIXTURES):
                addr = fix["addr"] - 1
                ch = CHANNELS[fix["type"]]

                if fix["type"] == "mover":
                    # Movers respond to beats and highs
                    intensity = int(high * 255) if beat else int(high * 100)
                    dmx[addr + ch["dimmer"]] = intensity
                    dmx[addr + ch["red"]] = 255 if beat else 50
                    dmx[addr + ch["green"]] = int(mid * 100)
                    dmx[addr + ch["blue"]] = int(high * 255)
                    dmx[addr + ch["shutter"]] = 255

                    # Movement follows the music
                    pan = int((math.sin(t + i * 0.5) * 0.3 + 0.5) * 255)
                    tilt = int((bass * 0.3 + 0.4) * 255)
                    dmx[addr + ch["pan"]] = pan
                    dmx[addr + ch["tilt"]] = tilt

                elif fix["type"] == "wash":
                    # Washes respond to mids - slower, smoother
                    dmx[addr + ch["dimmer"]] = int(mid * 200 + 55)
                    dmx[addr + ch["red"]] = int(bass * 255)
                    dmx[addr + ch["green"]] = int((1 - mid) * 200)
                    dmx[addr + ch["blue"]] = int(high * 150)
                    dmx[addr + ch["shutter"]] = 255

                    pan = int((math.sin(t * 0.2 + i) * 0.2 + 0.5) * 255)
                    tilt = int(0.6 * 255)
                    dmx[addr + ch["pan"]] = pan
                    dmx[addr + ch["tilt"]] = tilt

                else:  # LED bars
                    # Bars respond to bass
                    dmx[addr + ch["dimmer"]] = int(bass * 255)
                    dmx[addr + ch["red"]] = 255 if beat else int(bass * 200)
                    dmx[addr + ch["green"]] = int((1 - bass) * 100)
                    dmx[addr + ch["blue"]] = int(mid * 150)

            send_dmx(dmx)
            t += 0.03
            time.sleep(0.03)

    except KeyboardInterrupt:
        print("\nStopped.")
        send_dmx([0] * 512)


if __name__ == "__main__":
    import sys

    print("ILS Visualizer Test")
    print("=" * 40)
    print("1. Rainbow chase")
    print("2. Audio-reactive simulation")
    print()

    choice = input("Select pattern (1-2): ").strip()

    if choice == "1":
        run_rainbow_chase()
    elif choice == "2":
        run_audio_reactive_sim()
    else:
        print("Invalid choice")
