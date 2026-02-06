#!/usr/bin/env python3
"""
Test the audio-to-lighting pipeline.
Run this to verify the entire system is working correctly.
"""

import asyncio
import json
import sys
import time

try:
    import aiohttp
except ImportError:
    print("Missing aiohttp. Install with: pip install aiohttp")
    sys.exit(1)


async def test_backend():
    """Test backend is running and responding."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("http://localhost:8000/health", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    print("[OK] Backend is running")
                    return True
        except Exception as e:
            print(f"[FAIL] Backend not reachable: {e}")
            print("       Run: start_all.bat or start backend manually")
            return False


async def test_effects_engine():
    """Test effects engine state."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("http://localhost:8000/api/effects/status") as resp:
                data = await resp.json()
                running = data.get("running", False)
                auto_mode = data.get("auto_mode", False)
                print(f"[INFO] Effects Engine: running={running}, auto_mode={auto_mode}")

                if not running:
                    print("[WARN] Effects engine not running, starting it...")
                    async with session.post("http://localhost:8000/api/effects/start") as start_resp:
                        print("[OK] Effects engine started")

                return True
        except Exception as e:
            print(f"[FAIL] Could not check effects engine: {e}")
            return False


async def test_debug_pipeline():
    """Test the debug pipeline endpoint."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("http://localhost:8000/api/effects/debug/pipeline") as resp:
                data = await resp.json()

                print("\n" + "=" * 60)
                print("PIPELINE DEBUG INFO")
                print("=" * 60)

                # Summary
                summary = data.get("summary", {})
                print(f"\nDMX Status:")
                print(f"  Non-zero channels: {summary.get('non_zero_dmx_channels', 0)}")
                print(f"  DMX callback set: {summary.get('dmx_callback_set', False)}")

                mover_dmx = summary.get("first_mover_dmx", {})
                print(f"\nFirst Mover DMX Values:")
                print(f"  Pan: {mover_dmx.get('pan', 0)}")
                print(f"  Tilt: {mover_dmx.get('tilt', 0)}")
                print(f"  Dimmer: {mover_dmx.get('dimmer', 0)} {'<-- PROBLEM: Should be > 0!' if mover_dmx.get('dimmer', 0) == 0 else '[OK]'}")
                print(f"  Shutter: {mover_dmx.get('shutter', 0)} {'<-- PROBLEM: Should be >= 32!' if mover_dmx.get('shutter', 0) < 32 else '[OK]'}")
                print(f"  RGB: ({mover_dmx.get('red', 0)}, {mover_dmx.get('green', 0)}, {mover_dmx.get('blue', 0)})")

                # Audio
                audio = data.get("audio_features", {})
                print(f"\nAudio Features:")
                print(f"  Energy: {audio.get('energy', 0)}")
                print(f"  Bass: {audio.get('bass', 0)}")
                print(f"  Is Beat: {audio.get('is_beat', False)}")

                if audio.get('energy', 0) < 0.01:
                    print("  [WARN] Audio energy is very low - is audio capture running?")

                # Config
                config = data.get("engine_config", {})
                print(f"\nEngine Config:")
                print(f"  Running: {config.get('running', False)}")
                print(f"  Auto Mode: {config.get('auto_mode', False)}")
                print(f"  Movement Enabled: {config.get('movement_enabled', False)}")
                print(f"  Dimmer Enabled: {config.get('dimmer_enabled', False)}")

                # Effects
                effects = data.get("effect_states", {})
                print(f"\nEffect States:")
                print(f"  Movement Pattern: {effects.get('movement_pattern', 'N/A')}")
                print(f"  Dimmer Effect: {effects.get('dimmer_effect', 'N/A')}")
                print(f"  Lighting State: {effects.get('lighting_state', 'N/A')}")

                # Fixtures
                fixtures = data.get("fixtures_sample", [])
                print(f"\nFixture States (first {len(fixtures)}):")
                for f in fixtures:
                    dimmer_status = "[OK]" if f.get('dimmer', 0) > 0.1 else "[LOW]"
                    print(f"  {f.get('id')}: dimmer={f.get('dimmer', 0):.2f} {dimmer_status}, "
                          f"rgb={f.get('rgb', (0,0,0))}, pan={f.get('pan', 0):.1f}, tilt={f.get('tilt', 0):.1f}")

                print("\n" + "=" * 60)

                # Diagnosis
                print("\nDIAGNOSIS:")
                problems = []

                if summary.get('non_zero_dmx_channels', 0) == 0:
                    problems.append("No DMX channels have data")

                if mover_dmx.get('dimmer', 0) == 0:
                    problems.append("Dimmer is 0 - lights will be off")

                if mover_dmx.get('shutter', 0) < 32:
                    problems.append("Shutter is closed - beams won't show")

                if audio.get('energy', 0) < 0.01:
                    problems.append("No audio energy - audio capture may not be running")

                if problems:
                    print("  PROBLEMS FOUND:")
                    for p in problems:
                        print(f"    - {p}")
                    print("\n  SOLUTIONS:")
                    print("    1. Make sure audio_capture.py is running")
                    print("    2. Play some music through your audio output")
                    print("    3. Check the backend console for debug messages")
                else:
                    print("  [OK] Pipeline looks healthy!")

                return True

        except Exception as e:
            print(f"[FAIL] Could not get debug info: {e}")
            return False


async def test_websocket():
    """Test WebSocket connection."""
    try:
        import websockets
    except ImportError:
        print("[SKIP] websockets not installed, skipping WS test")
        return True

    try:
        async with websockets.connect("ws://localhost:8000/ws/audio", ping_timeout=3) as ws:
            print("[OK] WebSocket connection successful")

            # Send start message
            await ws.send(json.dumps({"type": "start"}))

            # Wait for a response
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2)
                data = json.loads(msg)
                print(f"[INFO] Received message type: {data.get('type')}")

                if data.get('type') == 'analysis':
                    has_lighting = 'lighting' in data
                    print(f"[INFO] Has lighting data: {has_lighting}")
                    if has_lighting:
                        fixtures = data['lighting'].get('fixtures', [])
                        if fixtures:
                            print(f"[INFO] First fixture dimmer: {fixtures[0].get('dimmer', 0):.2f}")

            except asyncio.TimeoutError:
                print("[INFO] No analysis messages received (audio capture may not be running)")

            return True

    except Exception as e:
        print(f"[FAIL] WebSocket test failed: {e}")
        return False


async def main():
    print("=" * 60)
    print("ILS Pipeline Test")
    print("=" * 60)
    print()

    # Test backend
    if not await test_backend():
        print("\nBackend not running. Start it first!")
        return

    print()

    # Test effects engine
    await test_effects_engine()

    print()

    # Test WebSocket
    await test_websocket()

    # Test debug pipeline
    await test_debug_pipeline()

    print("\nTest complete!")


if __name__ == "__main__":
    asyncio.run(main())
