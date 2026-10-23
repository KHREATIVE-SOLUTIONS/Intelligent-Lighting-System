"""
WebSocket Endpoints
===================

Real-time communication for audio streaming and updates.
"""

import asyncio
import json
import random
import math
from dataclasses import dataclass, asdict
from typing import List, Set, Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from datetime import datetime
import numpy as np

from ...core.config import settings
from ...core.security import verify_token
from ...schemas.audio import engine_energy, programme_level
from ...services.ml.training_recorder import get_recorder

router = APIRouter()


async def reject_unauthenticated(websocket: WebSocket) -> bool:
    """Close an untokened socket with 1008 and report whether it was rejected.

    Must run before accept(): an accepted socket is already in the broadcast set
    and starts receiving DMX frames and analysis at 30fps.
    """
    # Dev mode: auth disabled -> accept every socket (matches the HTTP gate).
    if not settings.AUTH_ENABLED:
        return False

    token = websocket.query_params.get("token", "")
    try:
        valid = bool(token) and bool(verify_token(token))
    except Exception:
        # Anything that stops validation is a rejection, never a crash.
        valid = False

    if valid:
        return False

    await websocket.close(code=1008)
    return True


def convert_numpy_types(obj):
    """Recursively convert numpy types to Python native types for JSON serialization."""
    if isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, tuple):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.ndarray):
        return convert_numpy_types(obj.tolist())
    elif isinstance(obj, np.generic):
        # Every numpy scalar, not just float32/64 and int32/64: one float16 left
        # in a payload used to fail the send and drop every client.
        return convert_numpy_types(obj.item())
    elif isinstance(obj, float) and not math.isfinite(obj):
        # JSON has no NaN; browsers reject the whole message over one.
        return None
    return obj


# Matches the binary limit: about two seconds of 48 kHz stereo.
MAX_JSON_AUDIO_SAMPLES = 48000 * 2


async def _report_bad_message(websocket: WebSocket, error: Exception) -> None:
    """Tell the client its message was refused and keep the connection open."""
    print(f"[WS] Ignored bad message: {error!r}")
    await websocket.send_json({"type": "error", "message": f"bad message: {str(error)[:200]}"})


async def _receive_or_disconnect(websocket: WebSocket) -> dict:
    """The next message, or WebSocketDisconnect - decoding is the caller's job.

    receive_json() decoded before the handler's error guard could see it, so
    one malformed message closed the connection.
    """
    message = await websocket.receive()
    if message.get("type") == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000))
    return message


class ConnectionManager:
    """Manages WebSocket connections."""

    # A client that cannot take a frame this quickly is dropped, not waited on.
    SEND_TIMEOUT = 0.25

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

        # Encoded once, up front: a payload that cannot be encoded is this
        # message's problem, not a reason to drop every client.
        try:
            text = json.dumps(convert_numpy_types(message))
        except (TypeError, ValueError) as e:
            print(f"Broadcast skipped, payload not serialisable: {e}")
            return

        async def send(connection: WebSocket):
            try:
                await asyncio.wait_for(connection.send_text(text), self.SEND_TIMEOUT)
                return None
            except Exception as e:
                print(f"Broadcast error: {e!r}")
                return connection

        # Sent concurrently with a deadline. Sent one after another with none, a
        # single tablet that stopped reading froze every viewer and - because
        # the audio handler awaits this - the audio feed driving the show.
        # BUG-036 fix: iterate over a snapshot to avoid set mutation during iteration
        results = await asyncio.gather(
            *(send(conn) for conn in list(self.active_connections[channel]))
        )

        # Drop and close the clients that failed, so they reconnect.
        for conn in results:
            if conn is None:
                continue
            self.active_connections[channel].discard(conn)
            try:
                await asyncio.wait_for(conn.close(code=1011), self.SEND_TIMEOUT)
            except Exception:
                pass


manager = ConnectionManager()


@dataclass
class ReactiveMotionConfig:
    """Runtime-tunable modulation pipeline parameters for legacy reactive mode."""

    # Deadband thresholds for small audio variations
    deadband_bass: float = 0.02
    deadband_mid: float = 0.02

    # Motion smoothing / low-pass constants (0-1, higher = snappier)
    sweep_smoothing: float = 0.24
    lowpass_pan: float = 0.32
    lowpass_tilt: float = 0.30

    # Beat / phrase modulation depth
    beat_mod_depth_pan: float = 5.0
    beat_mod_depth_tilt: float = 3.5
    phrase_mod_depth_pan: float = 10.0
    phrase_mod_depth_tilt: float = 7.0

    # Overall motion range for moving heads
    pan_range: float = 1.25
    tilt_range: float = 1.20

    # Per-section gain scaling
    section_gain_default: float = 1.0
    section_gain_verse: float = 0.85
    section_gain_pre_chorus: float = 1.0
    section_gain_chorus: float = 1.28
    section_gain_drop: float = 1.40
    section_gain_bridge: float = 0.90
    section_gain_breakdown: float = 0.82
    section_gain_peak: float = 1.45


REACTIVE_PRESETS: Dict[str, ReactiveMotionConfig] = {
    "subtle": ReactiveMotionConfig(
        deadband_bass=0.03,
        deadband_mid=0.03,
        sweep_smoothing=0.19,
        lowpass_pan=0.26,
        lowpass_tilt=0.24,
        beat_mod_depth_pan=3.0,
        beat_mod_depth_tilt=2.0,
        phrase_mod_depth_pan=6.0,
        phrase_mod_depth_tilt=4.5,
        pan_range=1.0,
        tilt_range=1.0,
        section_gain_verse=0.8,
        section_gain_chorus=1.15,
        section_gain_drop=1.22,
    ),
    "concert": ReactiveMotionConfig(),
    "festival": ReactiveMotionConfig(
        deadband_bass=0.01,
        deadband_mid=0.01,
        sweep_smoothing=0.32,
        lowpass_pan=0.40,
        lowpass_tilt=0.38,
        beat_mod_depth_pan=8.0,
        beat_mod_depth_tilt=5.5,
        phrase_mod_depth_pan=16.0,
        phrase_mod_depth_tilt=11.0,
        pan_range=1.65,
        tilt_range=1.5,
        section_gain_verse=0.82,
        section_gain_chorus=1.45,
        section_gain_drop=1.6,
        section_gain_peak=1.7,
    ),
}


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _apply_deadband(value: float, threshold: float) -> float:
    if abs(value) <= threshold:
        return 0.0
    return math.copysign((abs(value) - threshold) / max(1e-6, 1.0 - threshold), value)


def _get_reactive_section(analysis: dict) -> str:
    section = (
        analysis.get("ml", {})
        .get("structure", {})
        .get("section", "unknown")
    )
    if not isinstance(section, str):
        return "unknown"
    return section.lower()


def _section_gain(config: ReactiveMotionConfig, section: str) -> float:
    mapping = {
        "verse": config.section_gain_verse,
        "pre_chorus": config.section_gain_pre_chorus,
        "chorus": config.section_gain_chorus,
        "drop": config.section_gain_drop,
        "bridge": config.section_gain_bridge,
        "breakdown": config.section_gain_breakdown,
        "peak": config.section_gain_peak,
    }
    return mapping.get(section, config.section_gain_default)


def _resolve_reactive_config(message: dict | None) -> ReactiveMotionConfig:
    if not message:
        return ReactiveMotionConfig()

    preset_name = str(message.get("preset", "concert")).lower()
    base = REACTIVE_PRESETS.get(preset_name, REACTIVE_PRESETS["concert"])
    merged = asdict(base)

    overrides = message.get("params", {})
    if isinstance(overrides, dict):
        for key, value in overrides.items():
            if key in merged and isinstance(value, (int, float)):
                merged[key] = float(value)
    return ReactiveMotionConfig(**merged)


def fixture_universes(fixtures) -> List[int]:
    """Sorted list of the universes a rig occupies."""
    get_universes = getattr(fixtures, 'get_universes', None)
    if callable(get_universes):
        return sorted(int(u) for u in get_universes())
    return sorted({int(getattr(f, 'universe', 0) or 0) for f in fixtures.fixtures.values()})


def collect_dmx_frames(fixtures) -> Dict[int, List[int]]:
    """Render every universe the rig occupies as universe -> 512-value frame."""
    get_frames = getattr(fixtures, 'get_dmx_frames', None)
    frames = get_frames() if callable(get_frames) else None
    if not frames:
        frames = {u: fixtures.get_dmx_frame(universe=u) for u in fixture_universes(fixtures) or [0]}
    return {int(u): frame for u, frame in frames.items()}


def primary_dmx_universe(frames: Dict[int, List[int]]) -> int:
    """The universe whose frame stands in for the rig in single-universe payloads."""
    if 0 in frames or not frames:
        return 0
    return min(frames)


def serialize_dmx_frames(frames: Dict[int, List[int]]) -> Dict[str, List[int]]:
    """JSON-safe universe -> frame mapping."""
    return {str(u): frames[u] for u in sorted(frames)}


# The engine dataclass and the fixture library disagree on type names, so both
# vocabularies have to resolve to the same reactive role. Strobes get their own
# role: driven as bars they sit permanently lit, which on an atomic strobe is a
# constant blinding flood.
_REACTIVE_ROLE_BY_TYPE = {
    'mover': 'movers',
    'moving_head': 'movers',
    'spot': 'movers',
    'beam': 'movers',
    'wash': 'washes',
    'par': 'washes',
    'led_par': 'washes',
    'bar': 'bars',
    'led_bar': 'bars',
    'strobe': 'strobes',
    'laser': 'strobes',
    'effect': 'strobes',
}


def _can_move(fixture) -> bool:
    """Whether the fixture's profile says it has usable pan travel."""
    try:
        return float(getattr(fixture, 'pan_range', 0.0) or 0.0) > 0.0
    except (TypeError, ValueError):
        return False


def _reactive_role(fixture) -> str:
    """Map a fixture onto the reactive role that drives it."""
    role = _REACTIVE_ROLE_BY_TYPE.get(str(getattr(fixture, 'fixture_type', '') or '').lower())
    if role:
        return role
    return 'movers' if ('pan' in fixture.channels and _can_move(fixture)) else 'bars'


def _reactive_roles(fixtures) -> Dict[str, list]:
    """Split a rig into the movers / washes / bars / strobes roles, left to right."""
    roles: Dict[str, list] = {'movers': [], 'washes': [], 'bars': [], 'strobes': []}
    for fixture in fixtures.fixtures.values():
        roles[_reactive_role(fixture)].append(fixture)
    for group in roles.values():
        group.sort(key=lambda f: (f.x, f.universe, f.dmx_address))
    return roles


def resolve_live_fixtures(app):
    """Get the rig the running show is driving, if there is one."""
    engine = getattr(app.state, 'effects_engine', None)
    fixtures = getattr(engine, 'fixtures', None) if engine is not None else None
    if fixtures is None:
        fixtures = getattr(app.state, 'fixture_manager', None)
    return fixtures


async def resolve_reactive_fixtures(app, rig_id=None):
    """Resolve the rig the reactive path drives: the one requested, else the live one."""
    if rig_id is not None:
        try:
            from ...db.database import AsyncSessionLocal
            from ...services.rig.rig_loader import build_manager_for_rig_id

            async with AsyncSessionLocal() as db:
                manager = await build_manager_for_rig_id(db, int(rig_id))
            if manager is not None and manager.fixtures:
                return manager
            print(f"[WS] Rig {rig_id} has no drivable fixtures - driving the live rig instead")
        except Exception as e:
            print(f"[WS] Could not load rig {rig_id}: {e}")
    return resolve_live_fixtures(app)


def update_effects_engine_audio(effects_engine, analysis: dict) -> dict:
    """
    Process audio and update effects engine state.

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
    energy = engine_energy(rms_energy)
    normalized_energy = programme_level(freq.get('normalized_energy'))
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

    # Update effects engine with audio data
    # Note: LFO effects are applied by the effects engine's main loop
    effects_engine.update_audio(
        energy=energy,
        programme_level=normalized_energy,
        bass=min(1.0, bass_energy),
        mid=min(1.0, mid_energy),
        high=min(1.0, high_energy),
        is_beat=is_beat,
        beat_number=beat_count,
        valence=valence,
        arousal=arousal,
        spectral_flux=spectral_flux,
        bpm=bpm,
        tempo_confidence=beat.get('tempo_confidence'),
        ml_data=ml_data,
    )

    # Get the current DMX frames (already updated by effects engine loop)
    dmx_frames = collect_dmx_frames(effects_engine.fixtures)
    primary_universe = primary_dmx_universe(dmx_frames)
    dmx_frame = dmx_frames.get(primary_universe, [0] * 512)

    # Get fixture states for visualization (atomic snapshot - BUG-001 fix)
    fixture_states = effects_engine.get_fixture_state_snapshot()
    if not fixture_states:
        # Fallback if no snapshot yet (first frame)
        fixture_states = []
        for fixture in effects_engine.fixtures.fixtures.values():
            fixture_states.append({
                'id': fixture.id,
                'dmx_address': int(getattr(fixture, 'dmx_address', 0) or 0),
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
        'dmx_universe': primary_universe,
        'dmx_frames': serialize_dmx_frames(dmx_frames),
        'fixtures': fixture_states,
        'state': 'auto' if effects_engine.config.auto_mode else 'manual',
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
    if await reject_unauthenticated(websocket):
        return

    app = websocket.app
    await manager.connect(websocket, "audio")

    # Reactive lighting state
    reactive_mode = False
    reactive_rig_id = None
    reactive_fixtures = None

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

                # receive() hands back the disconnect as a message rather than
                # raising; calling it again raised RuntimeError on every close.
                if data.get("type") == "websocket.disconnect":
                    break

                if data.get("bytes") is not None:
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

                    # 16-bit PCM: a trailing odd byte is a torn sample, not audio.
                    if len(audio_bytes) % 2:
                        audio_bytes = audio_bytes[:-1]
                    if not audio_bytes:
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
                                dmx_controller, analysis, reactive_rig_id,
                                fixtures=reactive_fixtures,
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

                elif data.get("text") is not None:
                    # JSON control message
                    message = json.loads(data["text"])
                    if not isinstance(message, dict):
                        raise ValueError("expected a JSON object")
                    msg_type = message.get("type", "")

                    if msg_type == "ping":
                        await websocket.send_json({"type": "pong"})

                    elif msg_type == "audio_chunk":
                        # JSON audio data from capture script
                        audio_data = message.get("data")
                        sample_rate = message.get("sample_rate", 44100)

                        if not isinstance(audio_data, list) or not audio_data:
                            continue
                        if len(audio_data) > MAX_JSON_AUDIO_SAMPLES:
                            raise ValueError(
                                f"audio chunk too large ({len(audio_data)} samples, "
                                f"max {MAX_JSON_AUDIO_SAMPLES})"
                            )

                        if audio_analyzer:
                            audio_float = np.asarray(audio_data, dtype=np.float32).reshape(-1)

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
                                    dmx_controller, analysis, reactive_rig_id,
                                    fixtures=reactive_fixtures,
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
                        reactive_fixtures = await resolve_reactive_fixtures(app, reactive_rig_id)
                        resolved = _resolve_reactive_config(message)
                        if hasattr(apply_reactive_lighting, '_state'):
                            apply_reactive_lighting._state['config'] = resolved
                        await websocket.send_json({
                            "type": "reactive_enabled",
                            "rig_id": reactive_rig_id,
                            "fixture_count": len(reactive_fixtures.fixtures) if reactive_fixtures else 0,
                            "preset": message.get("preset", "concert"),
                            "params": asdict(resolved),
                        })

                    elif msg_type == "reactive_config":
                        resolved = _resolve_reactive_config(message)
                        state = getattr(apply_reactive_lighting, '_state', None)
                        if state is None:
                            apply_reactive_lighting._state = {
                                'look_family': 'performer_focus',
                                'bar_direction': 1.0,
                                'sweep_pan': 0.0,
                                'sweep_tilt': 0.0,
                                'pan_mod': 0.0,
                                'tilt_mod': 0.0,
                                'last_bar_count': -1,
                                'last_phrase_count': -1,
                                'phase': 0.0,
                                'phrase_phase': 0.0,
                                'config': resolved,
                            }
                        else:
                            state['config'] = resolved
                        await websocket.send_json({
                            "type": "reactive_config_updated",
                            "preset": message.get("preset", "concert"),
                            "params": asdict(resolved),
                        })

                    elif msg_type == "reactive_presets":
                        await websocket.send_json({
                            "type": "reactive_presets",
                            "presets": {name: asdict(cfg) for name, cfg in REACTIVE_PRESETS.items()},
                        })

                    elif msg_type == "reactive_off":
                        # Disable reactive lighting mode
                        reactive_mode = False
                        reactive_fixtures = None
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
                raise
            except Exception as e:
                # One malformed message used to end this connection - and this
                # connection is usually the audio feed the whole show follows.
                await _report_bad_message(websocket, e)

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, "audio")


async def apply_reactive_lighting(dmx_controller, analysis: dict, rig_id: int = None, fixtures=None):
    """
    Apply reactive lighting based on hierarchical timing events.

    Timing hierarchy:
    - Beat events (fast): subtle modulation only (micro oscillation + dimmer accent)
    - Bar/downbeat events (medium): moderate directional changes
    - Phrase/section events (slow): choose scene/look family

    Output is addressed through `fixtures`, the rig currently patched. Without a
    rig nothing is emitted - guessing at addresses drives whatever hardware
    happens to be listening there.
    """
    if fixtures is None or not getattr(fixtures, 'fixtures', None):
        return

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
            'pan_mod': 0.0,
            'tilt_mod': 0.0,
            'last_bar_count': -1,
            'last_phrase_count': -1,
            'phase': 0.0,
            'phrase_phase': 0.0,
            'config': REACTIVE_PRESETS['concert'],
        }
        apply_reactive_lighting._state = state

    config: ReactiveMotionConfig = state.get('config', REACTIVE_PRESETS['concert'])

    # Get energy levels from frequency bands
    bands = {b['name']: b['energy'] for b in freq.get('bands', [])}
    bass_energy = bands.get('bass', 0) + bands.get('sub_bass', 0)
    mid_energy = bands.get('mid', 0) + bands.get('low_mid', 0)
    high_energy = bands.get('high', 0) + bands.get('high_mid', 0)
    bass_mod = _apply_deadband(bass_energy, config.deadband_bass)
    mid_mod = _apply_deadband(mid_energy, config.deadband_mid)

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
    section = _get_reactive_section(analysis)
    section_gain = _section_gain(config, section)

    # Phrase/section-level look family selection (slow lane)
    if (is_section or is_phrase) and phrase_count != state['last_phrase_count']:
        if energy_level > 0.72:
            state['look_family'] = 'big_air'
        elif energy_level < 0.32:
            state['look_family'] = 'ambient_wash'
        else:
            state['look_family'] = 'performer_focus'
        state['last_phrase_count'] = phrase_count
        state['phrase_phase'] = (state['phrase_phase'] + (math.pi / 2.0)) % (math.pi * 2)

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
    sweep_scale = (0.35 + (energy_level * 0.95)) * section_gain
    if state['look_family'] == 'ambient_wash':
        pan_base = 128
        tilt_base = 120
        pan_amp = 22 * sweep_scale * config.pan_range
        tilt_amp = 14 * sweep_scale * config.tilt_range
    elif state['look_family'] == 'performer_focus':
        pan_base = 128
        tilt_base = 110
        pan_amp = 34 * sweep_scale * config.pan_range
        tilt_amp = 22 * sweep_scale * config.tilt_range
    else:  # big_air
        pan_base = 128
        tilt_base = 100
        pan_amp = 52 * sweep_scale * config.pan_range
        tilt_amp = 30 * sweep_scale * config.tilt_range

    # Use bar cadence to bias direction, but keep continuity with smoothing
    target_sweep_pan = state['bar_direction'] * (0.35 + bass_mod * 0.65) * pan_amp
    target_sweep_tilt = (0.2 + mid_mod * 0.8) * tilt_amp
    state['sweep_pan'] += (target_sweep_pan - state['sweep_pan']) * config.sweep_smoothing
    state['sweep_tilt'] += (target_sweep_tilt - state['sweep_tilt']) * config.sweep_smoothing

    # Beat micro-oscillation is intentionally tiny and additive
    state['phase'] = (state['phase'] + 0.18) % (math.pi * 2)
    phrase_pan = math.sin(state['phrase_phase']) * config.phrase_mod_depth_pan * (1.0 if (is_phrase or is_section) else 0.35)
    phrase_tilt = math.cos(state['phrase_phase']) * config.phrase_mod_depth_tilt * (1.0 if (is_phrase or is_section) else 0.35)
    micro_pan = math.sin(state['phase']) * config.beat_mod_depth_pan * beat_micro
    micro_tilt = math.cos(state['phase']) * config.beat_mod_depth_tilt * beat_micro

    pan_signal = state['sweep_pan'] + micro_pan + phrase_pan
    tilt_signal = state['sweep_tilt'] + micro_tilt + phrase_tilt
    state['pan_mod'] += (pan_signal - state['pan_mod']) * config.lowpass_pan
    state['tilt_mod'] += (tilt_signal - state['tilt_mod']) * config.lowpass_tilt

    # Open shutter
    shutter_open = 255

    async def write(fixture, channel_name: str, value: float):
        offset = fixture.channels.get(channel_name)
        if offset is None:
            return
        # A fixture with no travel must never be given movement, whatever its
        # channel map claims - the engine's own renderer applies the same rule.
        if channel_name in ('pan', 'pan_fine', 'tilt', 'tilt_fine') and not _can_move(fixture):
            return
        if channel_name in ('tilt', 'tilt_fine'):
            try:
                if float(getattr(fixture, 'tilt_range', 0.0) or 0.0) <= 0.0:
                    return
            except (TypeError, ValueError):
                return
        await dmx_controller.set_channel(
            fixture.universe,
            fixture.dmx_address + offset,
            int(_clamp(value, 0, 255)),
        )

    async def write_color(fixture, intensity: float):
        # Colour must carry the intensity on fixtures with no dimmer channel,
        # or they sit at full brightness whatever the show decides.
        scale = 1.0 if 'dimmer' in fixture.channels else _clamp(intensity, 0, 255) / 255.0
        await write(fixture, 'red', r * scale)
        await write(fixture, 'green', g * scale)
        await write(fixture, 'blue', b * scale)

    def center_x_of(group) -> float:
        return sum(f.x for f in group) / len(group) if group else 0.0

    try:
        roles = _reactive_roles(fixtures)

        movers = roles['movers']
        mover_center = center_x_of(movers)
        for fixture in movers:
            mirror = 1.0 if fixture.x <= mover_center else -1.0

            await write(fixture, 'pan', pan_base + mirror * state['pan_mod'])
            await write(fixture, 'tilt', tilt_base + state['tilt_mod'])
            await write(fixture, 'dimmer', dimmer)
            await write(fixture, 'shutter', shutter_open)
            await write_color(fixture, dimmer)

        washes = roles['washes']
        wash_center = center_x_of(washes)
        zoom = 128 + arousal * 100
        for fixture in washes:
            mirror = 1.0 if fixture.x <= wash_center else -1.0

            await write(fixture, 'pan', pan_base + mirror * state['pan_mod'] * 0.5)
            await write(fixture, 'tilt', 118 + state['tilt_mod'] * 0.35)
            await write(fixture, 'dimmer', dimmer)
            await write(fixture, 'shutter', shutter_open)
            await write_color(fixture, dimmer)
            await write(fixture, 'zoom', zoom)

        for i, fixture in enumerate(roles['bars']):
            # Beat accents are mild; avoid full-on hard flashes.
            parity_match = (i % 2) == (beat_position % 2)
            accent = 18 if (is_beat and parity_match) else 0
            bar_dimmer = _clamp(dimmer + accent, 0, 255)

            strobe = 0
            if arousal > 0.75 and is_section:
                strobe = 80

            await write(fixture, 'dimmer', bar_dimmer)
            await write(fixture, 'strobe', strobe)
            await write(fixture, 'shutter', shutter_open)
            await write_color(fixture, bar_dimmer)

        # Strobes idle dark and only fire on a high-arousal section change.
        firing = arousal > 0.75 and is_section
        for fixture in roles['strobes']:
            await write(fixture, 'dimmer', 255 if firing else 0)
            await write(fixture, 'strobe', 160 if firing else 0)
            await write(fixture, 'shutter', shutter_open if firing else 0)
            await write_color(fixture, 255 if firing else 0)

    except Exception:
        pass  # Ignore errors in reactive mode


@router.websocket("/dmx")
async def dmx_websocket(websocket: WebSocket, request: Request = None):
    """
    WebSocket endpoint for real-time DMX updates.

    Server sends: DMX frame updates (JSON)
    Client sends: DMX commands (JSON)
    """
    if await reject_unauthenticated(websocket):
        return

    app = websocket.app
    await manager.connect(websocket, "dmx")

    try:
        dmx_controller = getattr(app.state, 'dmx_controller', None)

        # Subscribe to DMX updates
        # Bounded: a client that stops reading must not grow memory all night.
        # The controller drops updates for a full queue.
        update_queue = asyncio.Queue(maxsize=256)

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
                raw = await _receive_or_disconnect(websocket)
                try:
                    data = json.loads(raw.get("text") or raw.get("bytes") or "")
                    if not isinstance(data, dict):
                        raise ValueError("expected a JSON object")
                    msg_type = data.get("type", "")

                    if msg_type == "ping":
                        await websocket.send_json({"type": "pong"})

                    elif msg_type == "set_channel":
                        if dmx_controller:
                            from app.schemas.dmx import DMXChannel
                            # Validated here: "abc", NaN or 1e400 used to close
                            # the socket from inside the controller.
                            command = DMXChannel(
                                channel=data.get("channel", 1),
                                value=data.get("value", 0),
                            )
                            await dmx_controller.set_channel(
                                data.get("universe", 0), command.channel, command.value
                            )

                    elif msg_type == "set_frame":
                        if dmx_controller:
                            from app.schemas.dmx import DMXFrame
                            frame = DMXFrame(**data.get("frame", {}))
                            await dmx_controller.set_frame(data.get("universe", 0), frame)

                    elif msg_type == "blackout":
                        if dmx_controller:
                            await dmx_controller.blackout()
                except WebSocketDisconnect:
                    raise
                except Exception as e:
                    await _report_bad_message(websocket, e)

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
    if await reject_unauthenticated(websocket):
        return

    app = websocket.app
    await manager.connect(websocket, "show")

    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    _receive_or_disconnect(websocket),
                    timeout=30.0
                )
                try:
                    data = json.loads(raw.get("text") or raw.get("bytes") or "")
                    if not isinstance(data, dict):
                        raise ValueError("expected a JSON object")
                except ValueError as e:
                    await _report_bad_message(websocket, e)
                    continue

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
