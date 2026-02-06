#!/usr/bin/env python3
"""
Persistent Audio Capture - Auto-reconnects when disconnected.
"""
import subprocess
import sys
import time

DEVICE_ID = "30"  # Studio 24c
SCRIPT_PATH = "audio_capture.py"

def main():
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
                [sys.executable, SCRIPT_PATH],
                stdin=subprocess.PIPE,
                stdout=sys.stdout,
                stderr=sys.stderr,
                text=True
            )

            # Send device selection
            proc.stdin.write(f"{DEVICE_ID}\n")
            proc.stdin.flush()
            proc.stdin.close()

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
    main()
