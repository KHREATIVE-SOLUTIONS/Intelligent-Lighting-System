#!/usr/bin/env python3
"""
Persistent Audio Capture - Auto-reconnects when disconnected.
"""
import argparse
import os
import subprocess
import sys
import time

SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "audio_capture.py")

def main(device_id: int, rig_id: int):
    print("=" * 60)
    print("  ILS Persistent Audio Capture")
    print("  Auto-reconnects when WebSocket disconnects")
    print("=" * 60)
    print()

    reconnect_count = 0

    while True:
        reconnect_count += 1
        print(f"\n--- Connection attempt #{reconnect_count} ---\n")

        try:
            # Run audio capture script
            proc = subprocess.Popen(
                [sys.executable, SCRIPT_PATH, "--device", str(device_id), "--rig-id", str(rig_id)],
                stdout=sys.stdout,
                stderr=sys.stderr,
            )

            # Wait for it to complete (i.e., disconnect)
            proc.wait()

        except KeyboardInterrupt:
            print("\n\nStopping persistent audio capture...")
            break
        except Exception as e:
            print(f"\nError: {e}")

        # Brief pause before reconnecting
        print("\n\nReconnecting in 2 seconds...")
        time.sleep(2)

    print(f"\nTotal reconnections: {reconnect_count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Persistent audio capture with reconnect")
    parser.add_argument("--device", type=int, required=True, help="Loopback device index")
    parser.add_argument("--rig-id", type=int, default=5, help="Rig ID for reactive lighting")
    args = parser.parse_args()
    main(device_id=args.device, rig_id=args.rig_id)
