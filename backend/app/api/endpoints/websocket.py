"""
WebSocket Endpoints
===================

Real-time communication for audio streaming and updates.
"""

import asyncio
import json
import random
import math
from typing import Set, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from datetime import datetime
import numpy as np

from ...services.ml.training_recorder import get_recorder

router = APIRouter()


def convert_numpy_types(obj):
    """Recursively convert numpy types to Python native types for JSON serialization."""
    if isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.float32, np.float64)):
        return float(obj)
    elif isinstance(obj, (np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    return obj


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {
            "audio": set(),
            "dmx": set(),
            "show": set(),
        }

    async def connect(self, websocket: WebSocket, channel: str):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = set()
        self.active_connections[channel].add(websocket)

    def disconnect(self, websocket: WebSocket, channel: str):
        """Remove a WebSocket connection."""
        if channel in self.active_connections:
            self.active_connections[channel].discard(websocket)

    async def broadcast(self, channel: str, message: Dict[str, Any]):
        """Broadcast a message to all connections on a channel."""
        if channel not in self.active_connections:
            print(f"No connections for channel {channel}")
            return

        num_connections = len(self.active_connections[channel])
        # BUG-037 fix: random moved to module-level import
        if random.random() < 0.02:
            print(f"Broadcasting to {num_connections} clients on {channel}")

        disconnected = set()
        # BUG-036 fix: iterate over a snapshot to avoid set mutation during iteration
        for connection in list(self.active_connections[channel]):
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Broadcast error: {e}")
                disconnected.add(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.active_connections[channel].discard(conn)


manager = ConnectionManager()


def update_effects_engine_audio(effects_engine, analysis: dict) -> dict:
    """
    TRAINING MODE: Process audio and record training data.

    - Extracts audio features for training data recording
    - Updates effects engine with audio/BPM info
    - Records training data pairs (audio + lighting)
    - Returns fixture states for visualizer

    NOTE: LFO effects are now applied by the effects engine's main loop.
    This function just extracts audio features and records training data.
    """
    beat = analysis.get('beat', {})
    mood = analysis.get('mood', {})
    freq = analysis.get('frequency', {})

    # Extract frequency bands
    bands = {b['name']: b['energy'] for b in freq.get('bands', [])}
    bass_energy = bands.get('bass', 0) + bands.get('sub_bass', 0)
    mid_energy = bands.get('mid', 0) + bands.get('low_mid', 0)
    high_energy = bands.get('high', 0) + bands.get('high_mid', 0)

    # Get RMS and spectral flux
    rms_energy = freq.get('rms_energy', 0)
    spectral_flux = min(1.0, float(freq.get('spectral_flux', 0.0)) * 10.0)

    # Get beat info
    is_beat = beat.get('is_beat', False)
    beat_position = beat.get('beat_position', 1)
    beat_count = beat.get('beat_count', beat_position)
    bpm = beat.get('bpm', 128)

    # Get mood
    valence = mood.get('valence', 0.5)
    arousal = mood.get('arousal', 0.5)

    # Extract ML pipeline data if available
    ml_data = analysis.get('ml', None)

    # Update effects engine with audio data (for BPM sync and training recording)
    # Note: LFO effects are applied by the effects engine's main loop
    effects_engine.update_audio(
        energy=min(1.0, rms_energy * 2),
        bass=min(1.0, bass_energy),
        mid=min(1.0, mid_energy),
        high=min(1.0, high_energy),
        is_beat=is_beat,
        beat_number=beat_count,
        valence=valence,
        arousal=arousal,
        spectral_flux=spectral_flux,
        bpm=bpm,
        ml_data=ml_data,
    )

    # Get the current DMX frame (already updated by effects engine loop)
    dmx_frame = effects_engine.fixtures.get_dmx_frame(universe=0)

    # Get fixture states for visualization (atomic snapshot - BUG-001 fix)
    fixture_states = effects_engine.get_fixture_state_snapshot()
    if not fixture_states:
        # Fallback if no snapshot yet (first frame)
        fixture_states = []
        for fixture in effects_engine.fixtures.fixtures.values():
            fixture_states.append({
                'id': fixture.id,
                'pan': fixture.pan,
                'tilt': fixture.tilt,
                'dimmer': fixture.dimmer,
                'r': fixture.red,
                'g': fixture.green,
                'b': fixture.blue
            })

    # Record training data if recording is active
    try:
        recorder = get_recorder()
        if recorder and recorder.recording:
            # Record audio features
            recorder.record_audio(
                bpm=bpm,
                energy=min(1.0, rms_energy * 2),
                bass=min(1.0, bass_energy),
                mid=min(1.0, mid_energy),
                high=min(1.0, high_energy),
                valence=valence,
                arousal=arousal,
                spectral_flux=spectral_flux,
                is_beat=is_beat,
                beat_position=beat_position
            )
            # Record lighting state
            recorder.record_lighting(
                fixtures=fixture_states,
                dmx_frame=dmx_frame
            )
    except Exception:
        pass  # Don't let recording errors affect main pipeline

    # Get active LFO effect name for display
    active_lfo = "none"
    try:
        lfo_engine = effects_engine.get_lfo_engine()
        if lfo_engine:
            active = lfo_engine.get_active_effects()
            active_lfo = active[0] if active else "none"
    except Exception:
        pass

    # Get pro lighting state if available
    pro_state = None
    try:
        pro_state = effects_engine.get_pro_lighting_state()
    except Exception:
        pass

    result = {
        'dmx_frame': dmx_frame,
        'fixtures': fixture_states,
        'state': 'training',  # Always in training mode
        'movement': active_lfo,  # Show active LFO effect
        'dimmer': 'manual'
    }
    try:
        from ...services.lighting.look_spec import build_lighting_look_spec
        result['look_spec'] = build_lighting_look_spec(effects_engine).model_dump(mode="json")
    except Exception:
        pass
    if pro_state:
        result['pro_lighting'] = pro_state
    # Include ML pipeline data in WebSocket response for frontend display
    if ml_data:
        if 'emotion_vector' in ml_data:
            result['emotion_vector'] = ml_data['emotion_vector']
        if 'structure' in ml_data:
            result['detected_section'] = ml_data['structure'].get('section', 'unknown')
            result['section_transition'] = ml_data['structure'].get('transition', {})
        if 'genre' in ml_data:
            result['detected_genre'] = ml_data['genre'].get('genre', 'unknown')
            result['genre_confidence'] = ml_data['genre'].get('genre_confidence', 0.0)
    return result


@router.websocket("/audio")
async def audio_websocket(websocket: WebSocket, request: Request = None):
    """
    WebSocket endpoint for real-time audio streaming and analysis.

    Client sends: Raw audio data (binary) or control messages (JSON)
    Server sends: Audio analysis results (JSON)
    """
    app = websocket.app
    await manager.connect(websocket, "audio")

    # Reactive lighting state
    reactive_mode = False
    reactive_rig_id = None
    last_beat_flash = 0

    try:
        # Get services from app state
        audio_analyzer = getattr(app.state, 'audio_analyzer', None)
        dmx_controller = getattr(app.state, 'dmx_controller', None)
        effects_engine = getattr(app.state, 'effects_engine', None)

        while True:
            try:
                # Receive data (can be binary audio or JSON control)
                data = await asyncio.wait_for(
                    websocket.receive(),
                    timeout=300.0  # 5 minute timeout for audio streaming
                )

                if "bytes" in data:
                    # Binary audio data
                    audio_bytes = data["bytes"]

                    # BUG-047 fix: reject oversized binary payloads (max ~2 seconds of 48kHz stereo 16-bit)
                    max_audio_bytes = 48000 * 2 * 2 * 2  # 384KB
                    if len(audio_bytes) > max_audio_bytes:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Audio data too large ({len(audio_bytes)} bytes, max {max_audio_bytes})"
                        })
                        continue

                    if audio_analyzer:
                        # Convert bytes to numpy array (assuming 16-bit PCM)
                        audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
                        audio_float = audio_array.astype(np.float32) / 32768.0

                        # Process audio
                        analysis = await audio_analyzer.process_chunk(audio_float)

                        # Update effects engine with audio data
                        lighting_data = None
                        if effects_engine:
                            lighting_data = update_effects_engine_audio(effects_engine, analysis)

                        # Apply reactive lighting if enabled (legacy mode)
                        if reactive_mode and dmx_controller and not effects_engine:
                            await apply_reactive_lighting(
                                dmx_controller, analysis, reactive_rig_id
                            )

                        # Send analysis results with lighting data (convert numpy types for JSON)
                        response = {
                            "type": "analysis",
                            "timestamp": datetime.utcnow().isoformat(),
                            **convert_numpy_types(analysis)
                        }
                        if lighting_data:
                            response["lighting"] = lighting_data

                        # Broadcast to all audio websocket clients (including visualizer)
                        await manager.broadcast("audio", response)

                elif "text" in data:
                    # JSON control message
                    message = json.loads(data["text"])
                    msg_type = message.get("type", "")

                    if msg_type == "ping":
                        await websocket.send_json({"type": "pong"})

                    elif msg_type == "audio_chunk":
                        # JSON audio data from capture script
                        audio_data = message.get("data", [])
                        sample_rate = message.get("sample_rate", 44100)

                        if audio_analyzer and len(audio_data) > 0:
                            audio_float = np.array(audio_data, dtype=np.float32)

                            # Process audio
                            analysis = await audio_analyzer.process_chunk(audio_float)

                            # Update effects engine with audio data
                            lighting_data = None
                            if effects_engine:
                                try:
                                    lighting_data = update_effects_engine_audio(effects_engine, analysis)
                                except Exception as e:
                                    print(f"[WS Error] Effects engine update failed: {e}")
                                    import traceback
                                    traceback.print_exc()
                            else:
                                # Log once that effects engine is missing
                                if not hasattr(audio_websocket, '_warned_no_engine'):
                                    print("[WS Warning] No effects engine available!")
                                    audio_websocket._warned_no_engine = True

                            # Apply reactive lighting if enabled (legacy mode)
                            if reactive_mode and dmx_controller and not effects_engine:
                                await apply_reactive_lighting(
                                    dmx_controller, analysis, reactive_rig_id
                                )

                            # Send analysis results with lighting data (convert numpy types for JSON)
                            response = {
                                "type": "analysis",
                                "timestamp": datetime.utcnow().isoformat(),
                                **convert_numpy_types(analysis)
                            }
                            if lighting_data:
                                response["lighting"] = lighting_data
                            else:
                                # Debug: why no lighting data?
                                if not hasattr(audio_websocket, '_warned_no_lighting'):
                                    print(f"[WS Debug] No lighting data. effects_engine={effects_engine is not None}")
                                    audio_websocket._warned_no_lighting = True

                            # Broadcast to all audio websocket clients (including visualizer)
                            await manager.broadcast("audio", response)

                    elif msg_type == "reactive_on":
                        # Enable reactive lighting mode
                        reactive_mode = True
                        reactive_rig_id = message.get("rig_id")
                        await websocket.send_json({
                            "type": "reactive_enabled",
                            "rig_id": reactive_rig_id
                        })

                    elif msg_type == "reactive_off":
                        # Disable reactive lighting mode
                        reactive_mode = False
                        await websocket.send_json({"type": "reactive_disabled"})

                    elif msg_type == "config":
                        # Update audio config (BUG-013 fix: construct Pydantic model)
                        if audio_analyzer:
                            from app.schemas.audio import AudioStreamConfig
                            config = AudioStreamConfig(**message.get("config", {}))
                            await audio_analyzer.update_config(config)
                        await websocket.send_json({
                            "type": "config_updated",
                            "config": message.get("config", {})
                        })

                    elif msg_type == "start":
                        if audio_analyzer:
                            await audio_analyzer.start()
                        await websocket.send_json({"type": "started"})

                    elif msg_type == "stop":
                        if audio_analyzer:
                            await audio_analyzer.stop()
                        await websocket.send_json({"type": "stopped"})

            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, "audio")


async def apply_reactive_lighting(dmx_controller, analysis: dict, rig_id: int = None):
    """
    Apply reactive lighting based on hierarchical timing events.

    Timing hierarchy:
    - Beat events (fast): subtle modulation only (micro oscillation + dimmer accent)
    - Bar/downbeat events (medium): moderate directional changes
    - Phrase/section events (slow): choose scene/look family
    """
    beat = analysis.get('beat', {})
    mood = analysis.get('mood', {})
    freq = analysis.get('frequency', {})

    # Function-scoped controller state (persists between calls in this process)
    state = getattr(apply_reactive_lighting, '_state', None)
    if state is None:
        state = {
            'look_family': 'performer_focus',
            'bar_direction': 1.0,
            'sweep_pan': 0.0,
            'sweep_tilt': 0.0,
            'last_bar_count': -1,
            'last_phrase_count': -1,
            'phase': 0.0,
        }
        apply_reactive_lighting._state = state

    # Get energy levels from frequency bands
    bands = {b['name']: b['energy'] for b in freq.get('bands', [])}
    bass_energy = bands.get('bass', 0) + bands.get('sub_bass', 0)
    mid_energy = bands.get('mid', 0) + bands.get('low_mid', 0)
    high_energy = bands.get('high', 0) + bands.get('high_mid', 0)

    # Overall energy
    rms_energy = float(freq.get('rms_energy', 0))
    energy_level = max(0.0, min(1.0, rms_energy * 2.5))

    # Mood affects color
    valence = mood.get('valence', 0)
    arousal = mood.get('arousal', 0)

    # Map mood to color (valence-arousal model)
    if arousal > 0.3:
        if valence > 0.2:
            base_r, base_g, base_b = 255, int(180 + valence * 75), 0
        else:
            base_r, base_g, base_b = 255, 0, int(100 + abs(valence) * 100)
    elif arousal < -0.2:
        if valence > 0.2:
            base_r, base_g, base_b = 50, 255, int(200 + valence * 55)
        else:
            base_r, base_g, base_b = int(80 + abs(valence) * 50), 0, 255
    else:
        base_r = int(220 + valence * 35)
        base_g = 255
        base_b = int(220 - valence * 35)

    # Timing events from analyzer hierarchy
    is_beat = bool(beat.get('is_beat', False))
    is_downbeat = bool(beat.get('is_downbeat', False))
    is_bar = bool(beat.get('is_bar', is_downbeat))
    is_phrase = bool(beat.get('is_phrase', False))
    is_section = bool(beat.get('is_section', False))
    beat_position = int(beat.get('beat_position', 1))
    bar_count = int(beat.get('bar_count', 0))
    phrase_count = int(beat.get('phrase_count', 0))

    # Phrase/section-level look family selection (slow lane)
    if (is_section or is_phrase) and phrase_count != state['last_phrase_count']:
        if energy_level > 0.72:
            state['look_family'] = 'big_air'
        elif energy_level < 0.32:
            state['look_family'] = 'ambient_wash'
        else:
            state['look_family'] = 'performer_focus'
        state['last_phrase_count'] = phrase_count

    # Bar-level moderate directional change (medium lane)
    if is_bar and bar_count != state['last_bar_count']:
        state['bar_direction'] *= -1.0
        state['last_bar_count'] = bar_count

    # Base dimmer from RMS energy + arousal
    intensity_mult = 0.4 + abs(arousal) * 0.6
    base_dimmer = int(min(255, rms_energy * 400 * intensity_mult))
    base_dimmer = max(30, base_dimmer)

    # Beat-level subtle modulation only (no full target rewrites)
    beat_accent = 22 if is_beat else 0
    beat_micro = 1.0 + (0.08 if is_beat else 0.0)
    dimmer = max(0, min(255, base_dimmer + beat_accent))

    # Apply color with intensity
    r = int(min(255, base_r * intensity_mult))
    g = int(min(255, base_g * intensity_mult))
    b = int(min(255, base_b * intensity_mult))

    # Smooth trajectory + intensity-based sweep scaling
    sweep_scale = 0.35 + (energy_level * 0.95)
    if state['look_family'] == 'ambient_wash':
        pan_base = 128
        tilt_base = 120
        pan_amp = 22 * sweep_scale
        tilt_amp = 14 * sweep_scale
    elif state['look_family'] == 'performer_focus':
        pan_base = 128
        tilt_base = 110
        pan_amp = 34 * sweep_scale
        tilt_amp = 22 * sweep_scale
    else:  # big_air
        pan_base = 128
        tilt_base = 100
        pan_amp = 52 * sweep_scale
        tilt_amp = 30 * sweep_scale

    # Use bar cadence to bias direction, but keep continuity with smoothing
    target_sweep_pan = state['bar_direction'] * (0.35 + bass_energy * 0.65) * pan_amp
    target_sweep_tilt = (0.2 + mid_energy * 0.8) * tilt_amp
    state['sweep_pan'] += (target_sweep_pan - state['sweep_pan']) * 0.12
    state['sweep_tilt'] += (target_sweep_tilt - state['sweep_tilt']) * 0.12

    # Beat micro-oscillation is intentionally tiny and additive
    state['phase'] = (state['phase'] + 0.18) % (math.pi * 2)
    micro_pan = math.sin(state['phase']) * 3.0 * beat_micro
    micro_tilt = math.cos(state['phase']) * 2.0 * beat_micro

    # Open shutter
    shutter_open = 255

    try:
        mover_addresses = [1, 17, 33, 49, 65, 81, 97, 113]

        for i, addr in enumerate(mover_addresses):
            is_left = i < 4
            mirror = 1 if is_left else -1

            pan = int(max(0, min(255, pan_base + mirror * state['sweep_pan'] + micro_pan)))
            tilt = int(max(0, min(255, tilt_base + state['sweep_tilt'] + micro_tilt)))

            await dmx_controller.set_channel(0, addr + 0, pan)
            await dmx_controller.set_channel(0, addr + 2, tilt)
            await dmx_controller.set_channel(0, addr + 5, dimmer)
            await dmx_controller.set_channel(0, addr + 6, shutter_open)
            await dmx_controller.set_channel(0, addr + 7, r)
            await dmx_controller.set_channel(0, addr + 8, g)
            await dmx_controller.set_channel(0, addr + 9, b)

        wash_addresses = [129, 143, 157, 171, 185, 199]
        for i, addr in enumerate(wash_addresses):
            is_left = i < 3
            mirror = 1 if is_left else -1
            wash_pan = int(max(0, min(255, pan_base + mirror * state['sweep_pan'] * 0.5)))
            wash_tilt = int(max(0, min(255, 118 + state['sweep_tilt'] * 0.35)))
            zoom = int(128 + arousal * 100)

            await dmx_controller.set_channel(0, addr + 0, wash_pan)
            await dmx_controller.set_channel(0, addr + 2, wash_tilt)
            await dmx_controller.set_channel(0, addr + 5, dimmer)
            await dmx_controller.set_channel(0, addr + 6, shutter_open)
            await dmx_controller.set_channel(0, addr + 7, r)
            await dmx_controller.set_channel(0, addr + 8, g)
            await dmx_controller.set_channel(0, addr + 9, b)
            await dmx_controller.set_channel(0, addr + 12, zoom)

        bar_addresses = [213, 225, 237, 249]
        for i, addr in enumerate(bar_addresses):
            # Beat accents are mild; avoid full-on hard flashes.
            parity_match = (i % 2) == (beat_position % 2)
            accent = 18 if (is_beat and parity_match) else 0
            bar_dimmer = int(max(0, min(255, dimmer + accent)))

            strobe = 0
            if arousal > 0.75 and is_section:
                strobe = 80

            await dmx_controller.set_channel(0, addr + 0, bar_dimmer)
            await dmx_controller.set_channel(0, addr + 1, strobe)
            await dmx_controller.set_channel(0, addr + 2, r)
            await dmx_controller.set_channel(0, addr + 3, g)
            await dmx_controller.set_channel(0, addr + 4, b)

    except Exception:
        pass  # Ignore errors in reactive mode


@router.websocket("/dmx")
async def dmx_websocket(websocket: WebSocket, request: Request = None):
    """
    WebSocket endpoint for real-time DMX updates.

    Server sends: DMX frame updates (JSON)
    Client sends: DMX commands (JSON)
    """
    app = websocket.app
    await manager.connect(websocket, "dmx")

    try:
        dmx_controller = getattr(app.state, 'dmx_controller', None)

        # Subscribe to DMX updates
        update_queue = asyncio.Queue()

        if dmx_controller:
            dmx_controller.subscribe(update_queue)

        async def send_updates():
            """Send DMX updates to client."""
            while True:
                try:
                    update = await asyncio.wait_for(update_queue.get(), timeout=1.0)
                    await websocket.send_json({
                        "type": "dmx_update",
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": update
                    })
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    break

        # Start update sender
        update_task = asyncio.create_task(send_updates())

        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type", "")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "set_channel":
                    if dmx_controller:
                        await dmx_controller.set_channel(
                            data.get("universe", 0),
                            data.get("channel", 1),
                            data.get("value", 0)
                        )

                elif msg_type == "set_frame":
                    if dmx_controller:
                        from app.schemas.dmx import DMXFrame
                        frame = DMXFrame(**data.get("frame", {}))
                        await dmx_controller.set_frame(data.get("universe", 0), frame)

                elif msg_type == "blackout":
                    if dmx_controller:
                        await dmx_controller.blackout()

        finally:
            update_task.cancel()
            if dmx_controller:
                dmx_controller.unsubscribe(update_queue)

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, "dmx")


@router.websocket("/show")
async def show_websocket(websocket: WebSocket, request: Request = None):
    """
    WebSocket endpoint for real-time show playback updates.

    Server sends: Show state updates, cue triggers (JSON)
    Client sends: Playback controls (JSON)
    """
    app = websocket.app
    await manager.connect(websocket, "show")

    try:
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=30.0
                )

                msg_type = data.get("type", "")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "play":
                    show_id = data.get("show_id")
                    # TODO: Start show playback
                    await websocket.send_json({
                        "type": "show_started",
                        "show_id": show_id
                    })

                elif msg_type == "pause":
                    # TODO: Pause show playback
                    await websocket.send_json({"type": "show_paused"})

                elif msg_type == "stop":
                    # TODO: Stop show playback
                    await websocket.send_json({"type": "show_stopped"})

                elif msg_type == "seek":
                    position = data.get("position", 0)
                    # TODO: Seek to position
                    await websocket.send_json({
                        "type": "show_seeked",
                        "position": position
                    })

                elif msg_type == "trigger_cue":
                    cue_id = data.get("cue_id")
                    # TODO: Manually trigger cue
                    await websocket.send_json({
                        "type": "cue_triggered",
                        "cue_id": cue_id
                    })

            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, "show")


# Helper function for broadcasting from services
async def broadcast_audio_update(analysis: Dict[str, Any]):
    """Broadcast audio analysis update to all connected clients."""
    await manager.broadcast("audio", {
        "type": "analysis",
        "timestamp": datetime.utcnow().isoformat(),
        "data": analysis
    })


async def broadcast_dmx_update(update: Dict[str, Any]):
    """Broadcast DMX update to all connected clients."""
    await manager.broadcast("dmx", {
        "type": "dmx_update",
        "timestamp": datetime.utcnow().isoformat(),
        "data": update
    })


async def broadcast_show_event(event: Dict[str, Any]):
    """Broadcast show event to all connected clients."""
    await manager.broadcast("show", {
        "type": "show_event",
        "timestamp": datetime.utcnow().isoformat(),
        "data": event
    })
