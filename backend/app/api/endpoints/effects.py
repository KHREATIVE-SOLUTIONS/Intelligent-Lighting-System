"""
Effects Engine API Endpoints
Controls the intelligent lighting effects system.
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum

from ...services.effects import (
    EffectsEngine, EffectsConfig,
    MovementType, StaticLook, MovementParams, MOVEMENT_PRESETS,
    DimmerType, DimmerParams, DIMMER_PRESETS, BEAT_PATTERNS,
    StrobeMode, StrobeParams, STROBE_PRESETS,
    ColorPalette,
    LightingState
)
from ...services.lighting.genre_profiles import Genre, GENRE_PROFILES
from ...services.lighting.section_manager import SongSection
from ...services.lighting.movement_patterns import ProMovementPattern, PRO_MOVEMENT_PRESETS
from ...services.lighting.pro_effects import ProStrobeMode
from ...services.lighting.key_lighting import PerformerZone, KeyLightConfig
from ...schemas.lighting_look import LightingLookSpec
from ...services.lighting.look_spec import build_lighting_look_spec

router = APIRouter(prefix="/effects", tags=["effects"])

# The engine dataclass and the fixture library name moving heads differently.
MOVER_TYPE_NAMES = frozenset({"mover", "moving_head", "spot", "beam"})

# Global effects engine instance (initialized in main.py)
_effects_engine: Optional[EffectsEngine] = None


def get_effects_engine() -> EffectsEngine:
    """Get the effects engine instance."""
    if _effects_engine is None:
        raise HTTPException(status_code=503, detail="Effects engine not initialized")
    return _effects_engine


def set_effects_engine(engine: EffectsEngine):
    """Set the effects engine instance."""
    global _effects_engine
    _effects_engine = engine


# === Request/Response Models ===

class EffectsStatus(BaseModel):
    """Effects engine status."""
    running: bool
    engine_time: float
    engine_id: int
    auto_mode: bool
    current_state: str
    bpm: float
    palette: str

    # Current effects
    movement_pattern: str
    static_look: str
    dimmer_effect: str
    strobe_mode: str

    # Layer status
    movement_enabled: bool
    dimmer_enabled: bool
    strobe_enabled: bool
    color_enabled: bool


class MovementRequest(BaseModel):
    """Request to set movement pattern."""
    pattern: str = Field(..., description="Movement pattern name")
    base_look: Optional[str] = Field("all_center", description="Base static look")
    pan_speed: Optional[float] = Field(None, description="Pan speed in Hz")
    tilt_speed: Optional[float] = Field(None, description="Tilt speed in Hz")
    pan_amplitude: Optional[float] = Field(None, description="Pan amplitude in degrees")
    tilt_amplitude: Optional[float] = Field(None, description="Tilt amplitude in degrees")


class DimmerRequest(BaseModel):
    """Request to set dimmer effect."""
    effect: str = Field(..., description="Dimmer effect name")
    speed: Optional[float] = Field(None, description="Effect speed in Hz")
    min_intensity: Optional[float] = Field(None, description="Minimum intensity (0-1)")
    base_intensity: Optional[float] = Field(None, description="Base intensity (0-1)")
    beat_pattern: Optional[str] = Field(None, description="Beat pattern name")


class StrobeRequest(BaseModel):
    """Request to set strobe mode."""
    mode: str = Field(..., description="Strobe mode name")
    frequency: Optional[float] = Field(None, description="Strobe frequency in Hz")
    duration: Optional[float] = Field(None, description="Burst duration in seconds")


class ColorRequest(BaseModel):
    """Request to set color palette."""
    palette: str = Field(..., description="Color palette name")


class StateRequest(BaseModel):
    """Request to force a lighting state."""
    state: str = Field(..., description="Lighting state name")


class AutoModeRequest(BaseModel):
    """Request to toggle auto mode."""
    enabled: bool = Field(..., description="Enable auto-pilot mode")


class PresetRequest(BaseModel):
    """Request to load a preset."""
    preset: str = Field(..., description="Preset name")


class SafetyProfileRequest(BaseModel):
    """Request to apply a research-pack safety profile."""
    profile: str = Field("performance", description="no_strobe | conservative | performance")
    camera_mode: Optional[bool] = Field(None, description="Enable stricter anti-flicker camera mode")
    venue_mode: Optional[str] = Field(None, description="theatre | broadcast | corporate | concert | club")


class MLTargetGatingRequest(BaseModel):
    """Request to tune ML confidence gates for target switching."""
    enabled: Optional[bool] = None

    genre_confidence_on: Optional[float] = Field(None, ge=0.0, le=1.0)
    genre_confidence_off: Optional[float] = Field(None, ge=0.0, le=1.0)
    genre_consecutive_frames: Optional[int] = Field(None, ge=1, le=30)
    genre_min_hold_ms: Optional[int] = Field(None, ge=0, le=5000)
    genre_min_confidence_delta: Optional[float] = Field(None, ge=0.0, le=1.0)

    section_confidence_on: Optional[float] = Field(None, ge=0.0, le=1.0)
    section_confidence_off: Optional[float] = Field(None, ge=0.0, le=1.0)
    section_consecutive_frames: Optional[int] = Field(None, ge=1, le=30)
    section_min_hold_ms: Optional[int] = Field(None, ge=0, le=5000)
    section_min_confidence_delta: Optional[float] = Field(None, ge=0.0, le=1.0)


# === Endpoints ===

@router.get("/fixture-states")
async def get_fixture_states(request: Request):
    """Get current fixture state snapshot for visualizer."""
    engine = getattr(request.app.state, "effects_engine", None) or get_effects_engine()
    fixture_states = engine.get_fixture_state_snapshot()
    if not fixture_states:
        fixture_states = []
        for fixture in engine.fixtures.fixtures.values():
            fixture_states.append({
                'id': fixture.id, 'pan': fixture.pan, 'tilt': fixture.tilt,
                'dimmer': fixture.dimmer, 'r': fixture.red, 'g': fixture.green,
                'b': fixture.blue, 'zoom': getattr(fixture, 'zoom', 0.5),
                'gobo': getattr(fixture, 'gobo_index', 0.0),
            })
    section = ""
    try:
        section = engine._rebuild_section or ""
    except Exception:
        pass
    return {"fixture_states": fixture_states, "section": section}


@router.get("/status", response_model=EffectsStatus)
async def get_status(request: Request):
    """Get current effects engine status."""
    engine = getattr(request.app.state, "effects_engine", None) or get_effects_engine()

    return EffectsStatus(
        running=engine.running,
        engine_time=engine.time,
        engine_id=id(engine),
        auto_mode=engine.config.auto_mode,
        current_state=engine.decision.state.value,
        bpm=engine.config.bpm,
        palette=engine.config.palette.value,
        movement_pattern=engine.movement.params.pattern.value,
        static_look=engine.movement.params.base_look.value,
        dimmer_effect=engine.dimmer.params.effect_type.value,
        strobe_mode=engine.strobe.params.mode.value,
        movement_enabled=engine.config.movement_enabled,
        dimmer_enabled=engine.config.dimmer_enabled,
        strobe_enabled=engine.config.strobe_enabled,
        color_enabled=engine.config.color_enabled
    )


@router.get("/look-spec", response_model=LightingLookSpec)
async def get_look_spec(request: Request):
    """Get the current typed beam/spot look specification."""
    engine = getattr(request.app.state, "effects_engine", None) or get_effects_engine()
    return build_lighting_look_spec(engine)


@router.post("/start")
async def start_effects():
    """Start the effects engine."""
    engine = get_effects_engine()
    if not engine.running:
        import asyncio
        asyncio.create_task(engine.run())
    return {"status": "started"}


@router.post("/stop")
async def stop_effects():
    """Stop the effects engine."""
    engine = get_effects_engine()
    engine.stop()
    return {"status": "stopped"}




@router.get("/ml-target-gating")
async def get_ml_target_gating(request: Request):
    """Get ML confidence-gating config for section/genre target switching."""
    engine = getattr(request.app.state, "effects_engine", None) or get_effects_engine()
    cfg = engine.config
    return {
        "enabled": cfg.ml_target_gating_enabled,
        "genre": {
            "confidence_on": cfg.ml_genre_confidence_on,
            "confidence_off": cfg.ml_genre_confidence_off,
            "consecutive_frames": cfg.ml_genre_consecutive_frames,
            "min_hold_ms": cfg.ml_genre_min_hold_ms,
            "min_confidence_delta": cfg.ml_genre_min_confidence_delta,
        },
        "section": {
            "confidence_on": cfg.ml_section_confidence_on,
            "confidence_off": cfg.ml_section_confidence_off,
            "consecutive_frames": cfg.ml_section_consecutive_frames,
            "min_hold_ms": cfg.ml_section_min_hold_ms,
            "min_confidence_delta": cfg.ml_section_min_confidence_delta,
        },
    }


@router.post("/ml-target-gating")
async def set_ml_target_gating(payload: MLTargetGatingRequest, request: Request):
    """Update ML confidence-gating config for section/genre target switching."""
    engine = getattr(request.app.state, "effects_engine", None) or get_effects_engine()
    cfg = engine.config

    if payload.enabled is not None:
        cfg.ml_target_gating_enabled = payload.enabled

    if payload.genre_confidence_on is not None:
        cfg.ml_genre_confidence_on = payload.genre_confidence_on
    if payload.genre_confidence_off is not None:
        cfg.ml_genre_confidence_off = payload.genre_confidence_off
    if payload.genre_consecutive_frames is not None:
        cfg.ml_genre_consecutive_frames = payload.genre_consecutive_frames
    if payload.genre_min_hold_ms is not None:
        cfg.ml_genre_min_hold_ms = payload.genre_min_hold_ms
    if payload.genre_min_confidence_delta is not None:
        cfg.ml_genre_min_confidence_delta = payload.genre_min_confidence_delta

    if payload.section_confidence_on is not None:
        cfg.ml_section_confidence_on = payload.section_confidence_on
    if payload.section_confidence_off is not None:
        cfg.ml_section_confidence_off = payload.section_confidence_off
    if payload.section_consecutive_frames is not None:
        cfg.ml_section_consecutive_frames = payload.section_consecutive_frames
    if payload.section_min_hold_ms is not None:
        cfg.ml_section_min_hold_ms = payload.section_min_hold_ms
    if payload.section_min_confidence_delta is not None:
        cfg.ml_section_min_confidence_delta = payload.section_min_confidence_delta

    return await get_ml_target_gating(request)

@router.post("/auto-mode")
async def set_auto_mode(request: AutoModeRequest):
    """Enable or disable auto-pilot mode."""
    engine = get_effects_engine()
    engine.set_auto_mode(request.enabled)
    return {"auto_mode": request.enabled}


# === Movement Control ===

@router.get("/movement/patterns")
async def get_movement_patterns():
    """Get available movement patterns."""
    return {
        "patterns": [m.value for m in MovementType],
        "presets": list(MOVEMENT_PRESETS.keys()),
        "static_looks": [s.value for s in StaticLook]
    }


@router.post("/movement")
async def set_movement(request: MovementRequest):
    """Set movement pattern."""
    engine = get_effects_engine()

    # Parse pattern
    try:
        pattern = MovementType(request.pattern)
    except ValueError:
        raise HTTPException(400, f"Invalid pattern: {request.pattern}")

    # Parse base look
    try:
        base_look = StaticLook(request.base_look) if request.base_look else StaticLook.ALL_CENTER
    except ValueError:
        base_look = StaticLook.ALL_CENTER

    # Build kwargs
    kwargs = {}
    if request.pan_speed is not None:
        kwargs["pan_speed"] = request.pan_speed
    if request.tilt_speed is not None:
        kwargs["tilt_speed"] = request.tilt_speed
    if request.pan_amplitude is not None:
        kwargs["pan_amplitude"] = request.pan_amplitude
    if request.tilt_amplitude is not None:
        kwargs["tilt_amplitude"] = request.tilt_amplitude

    engine.set_movement(pattern, base_look, **kwargs)
    return {"status": "ok", "pattern": request.pattern}


@router.post("/movement/preset/{preset_name}")
async def set_movement_preset(preset_name: str):
    """Set movement from preset."""
    engine = get_effects_engine()

    if preset_name not in MOVEMENT_PRESETS:
        raise HTTPException(400, f"Invalid preset: {preset_name}")

    engine.movement.params = MOVEMENT_PRESETS[preset_name]
    return {"status": "ok", "preset": preset_name}


@router.post("/movement/static/{look}")
async def set_static_look(look: str):
    """Set a static look (stops movement)."""
    engine = get_effects_engine()

    try:
        static_look = StaticLook(look)
    except ValueError:
        raise HTTPException(400, f"Invalid look: {look}")

    engine.set_static_look(static_look)
    return {"status": "ok", "look": look}


# === Dimmer Control ===

@router.get("/dimmer/effects")
async def get_dimmer_effects():
    """Get available dimmer effects."""
    return {
        "effects": [d.value for d in DimmerType],
        "presets": list(DIMMER_PRESETS.keys()),
        "beat_patterns": list(BEAT_PATTERNS.keys())
    }


@router.post("/dimmer")
async def set_dimmer(request: DimmerRequest):
    """Set dimmer effect."""
    engine = get_effects_engine()

    try:
        effect = DimmerType(request.effect)
    except ValueError:
        raise HTTPException(400, f"Invalid effect: {request.effect}")

    kwargs = {}
    if request.speed is not None:
        kwargs["speed"] = request.speed
    if request.min_intensity is not None:
        kwargs["min_intensity"] = request.min_intensity
    if request.base_intensity is not None:
        kwargs["base_intensity"] = request.base_intensity

    engine.set_dimmer_effect(effect, **kwargs)

    if request.beat_pattern and request.beat_pattern in BEAT_PATTERNS:
        engine.dimmer.params.beat_pattern = BEAT_PATTERNS[request.beat_pattern]

    return {"status": "ok", "effect": request.effect}


@router.post("/dimmer/preset/{preset_name}")
async def set_dimmer_preset(preset_name: str):
    """Set dimmer from preset."""
    engine = get_effects_engine()

    if preset_name not in DIMMER_PRESETS:
        raise HTTPException(400, f"Invalid preset: {preset_name}")

    engine.dimmer.params = DIMMER_PRESETS[preset_name]
    return {"status": "ok", "preset": preset_name}


@router.post("/dimmer/beat-pattern/{pattern_name}")
async def set_beat_pattern(pattern_name: str):
    """Set beat pattern."""
    engine = get_effects_engine()

    if pattern_name not in BEAT_PATTERNS:
        raise HTTPException(400, f"Invalid pattern: {pattern_name}")

    engine.set_beat_pattern(pattern_name)
    return {"status": "ok", "pattern": pattern_name}


# === Strobe Control ===

@router.get("/strobe/modes")
async def get_strobe_modes():
    """Get available strobe modes."""
    return {
        "modes": [s.value for s in StrobeMode],
        "presets": list(STROBE_PRESETS.keys())
    }


@router.post("/strobe")
async def set_strobe(request: StrobeRequest):
    """Set strobe mode."""
    engine = get_effects_engine()

    try:
        mode = StrobeMode(request.mode)
    except ValueError:
        raise HTTPException(400, f"Invalid mode: {request.mode}")

    kwargs = {}
    if request.frequency is not None:
        kwargs["frequency"] = request.frequency

    engine.set_strobe(mode, **kwargs)
    return {"status": "ok", "mode": request.mode}


@router.post("/strobe/burst")
async def trigger_strobe_burst(duration: float = 2.0, frequency: float = 12.0):
    """Trigger a strobe burst."""
    engine = get_effects_engine()
    engine.trigger_strobe_burst(duration, frequency)
    return {"status": "ok", "duration": duration, "frequency": frequency}


@router.post("/strobe/stop")
async def stop_strobe():
    """Stop strobing."""
    engine = get_effects_engine()
    engine.strobe.stop()
    return {"status": "ok"}


# === Color Control ===

@router.get("/color/palettes")
async def get_color_palettes():
    """Get available color palettes."""
    return {
        "palettes": [p.value for p in ColorPalette]
    }


@router.post("/color/palette")
async def set_color_palette(request: ColorRequest):
    """Set color palette."""
    engine = get_effects_engine()

    try:
        palette = ColorPalette(request.palette)
    except ValueError:
        raise HTTPException(400, f"Invalid palette: {request.palette}")

    engine.set_color_palette(palette)
    return {"status": "ok", "palette": request.palette}


# === State Control ===

@router.get("/states")
async def get_states():
    """Get available lighting states."""
    return {
        "states": [s.value for s in LightingState],
        "current": get_effects_engine().decision.state.value
    }


@router.post("/state")
async def force_state(request: StateRequest):
    """Force a specific lighting state."""
    engine = get_effects_engine()

    try:
        state = LightingState(request.state)
    except ValueError:
        raise HTTPException(400, f"Invalid state: {request.state}")

    engine.force_state(state)
    return {"status": "ok", "state": request.state}


# === Triggers ===

@router.post("/trigger/drop")
async def trigger_drop():
    """Trigger a drop sequence (strobe + static look)."""
    engine = get_effects_engine()
    engine.trigger_drop_strobe()
    engine.decision.trigger_drop()
    return {"status": "ok", "trigger": "drop"}


@router.post("/trigger/buildup")
async def trigger_buildup(duration: float = 4.0):
    """Trigger a build-up sequence."""
    engine = get_effects_engine()
    engine.trigger_buildup(duration)
    return {"status": "ok", "trigger": "buildup", "duration": duration}


@router.post("/trigger/blackout")
async def trigger_blackout():
    """Blackout all fixtures."""
    engine = get_effects_engine()
    engine.blackout()
    return {"status": "ok", "trigger": "blackout"}


@router.post("/trigger/restore")
async def trigger_restore():
    """Restore from blackout."""
    engine = get_effects_engine()
    engine.restore()
    return {"status": "ok", "trigger": "restore"}


@router.post("/trigger/clean-stage")
async def trigger_clean_stage():
    """Clean-stage macro: stop FX/strobes and return to safe readable base."""
    engine = get_effects_engine()
    engine.clean_stage()
    return {"status": "ok", "trigger": "clean_stage"}


@router.get("/safety")
async def get_safety_settings(request: Request):
    """Get current safety profile and active constraints."""
    engine = getattr(request.app.state, "effects_engine", None) or get_effects_engine()
    state = engine.get_pro_lighting_state() if engine._pro_lighting_enabled else {"constraints": {}}
    return state.get("constraints", {})


@router.post("/safety/profile")
async def set_safety_profile(payload: SafetyProfileRequest, request: Request):
    """Apply safety profile presets from the busking research pack."""
    engine = getattr(request.app.state, "effects_engine", None) or get_effects_engine()
    return engine.set_safety_profile(
        profile=payload.profile,
        camera_mode=payload.camera_mode,
        venue_mode=payload.venue_mode,
    )


@router.get("/programming/artifacts")
async def get_programming_artifacts(request: Request, safety_limit: int = 50):
    """Expose programming artifacts recommended by professional workflow research."""
    engine = getattr(request.app.state, "effects_engine", None) or get_effects_engine()
    return {
        "ownership_priority_map": {
            "intensity": {"blend": "HTP", "layers": ["base", "dimmer", "strobe", "key"]},
            "color_position_beam": {"blend": "LTP", "layers": ["palette", "movement", "effects", "manual_override"]},
        },
        "palette_index": {
            "current": engine.config.palette.value,
            "available": [p.value for p in ColorPalette],
            "palette_locked": bool(getattr(engine, "_palette_locked", False)),
            "palette_version": int(getattr(engine, "_palette_version", 1)),
        },
        "effect_library_sheet": {
            "movement_presets": sorted(list(MOVEMENT_PRESETS.keys())),
            "dimmer_presets": sorted(list(DIMMER_PRESETS.keys())),
            "strobe_presets": sorted(list(STROBE_PRESETS.keys())),
            "pro_movement_presets": sorted(list(PRO_MOVEMENT_PRESETS.keys())),
            "pro_strobe_modes": [m.value for m in ProStrobeMode],
            "safety_macros": ["clean_stage", "blackout", "restore", "pro/blackout"],
        },
        "safety_policy_log": engine.get_safety_events(limit=safety_limit),
    }


# === Presets ===

@router.get("/presets")
async def get_presets():
    """Get available combined presets."""
    return {
        "presets": ["chill", "hype", "drop", "breakdown"]
    }


@router.post("/preset/{preset_name}")
async def load_preset(preset_name: str):
    """Load a combined effect preset."""
    engine = get_effects_engine()
    engine.load_preset(preset_name)
    return {"status": "ok", "preset": preset_name}


# === Layer Enable/Disable ===

@router.post("/layers/movement/{enabled}")
async def set_movement_enabled(enabled: bool):
    """Enable/disable movement layer."""
    engine = get_effects_engine()
    engine.config.movement_enabled = enabled
    return {"status": "ok", "movement_enabled": enabled}


@router.post("/layers/dimmer/{enabled}")
async def set_dimmer_enabled(enabled: bool):
    """Enable/disable dimmer layer."""
    engine = get_effects_engine()
    engine.config.dimmer_enabled = enabled
    return {"status": "ok", "dimmer_enabled": enabled}


@router.post("/layers/strobe/{enabled}")
async def set_strobe_enabled(enabled: bool):
    """Enable/disable strobe layer."""
    engine = get_effects_engine()
    engine.set_strobe_layer_enabled(enabled)
    return {"status": "ok", "strobe_enabled": enabled}


@router.post("/layers/color/{enabled}")
async def set_color_enabled(enabled: bool):
    """Enable/disable color layer."""
    engine = get_effects_engine()
    engine.config.color_enabled = enabled
    return {"status": "ok", "color_enabled": enabled}


@router.get("/debug/frame")
async def get_debug_frame(universe: int = 0):
    """Debug: Get current DMX frame from effects engine."""
    engine = get_effects_engine()

    # Force an update cycle
    engine.update()

    # Get the DMX frame
    frame = engine.fixtures.get_dmx_frame(universe=universe)

    # Get fixture states
    fixtures = []
    for fixture in engine.fixtures.fixtures.values():
        fixtures.append({
            'id': fixture.id,
            'universe': fixture.universe,
            'dmx_address': fixture.dmx_address,
            'pan': fixture.pan,
            'tilt': fixture.tilt,
            'dimmer': fixture.dimmer,
            'strobe': fixture.strobe,
            'r': fixture.red,
            'g': fixture.green,
            'b': fixture.blue
        })

    non_zero = sum(1 for v in frame if v > 0)
    return {
        "universe": universe,
        "universes": engine.fixtures.get_universes(),
        "non_zero_channels": non_zero,
        "first_50_channels": frame[:50],
        "fixtures": fixtures,
        "audio_energy": engine.audio_features.energy,
        "callback_set": engine._dmx_callback is not None
    }


@router.get("/debug/pipeline")
async def get_debug_pipeline(universe: int = 0):
    """Debug: Get complete pipeline state for troubleshooting."""
    engine = get_effects_engine()

    # Force an update cycle to get fresh data
    engine.update()

    # Get DMX frame
    frame = engine.fixtures.get_dmx_frame(universe=universe)

    # Sample the first mover patched in this universe, read through its own
    # channel map - a rig patches wherever it likes.
    in_universe = [f for f in engine.fixtures.fixtures.values() if f.universe == universe]
    in_universe.sort(key=lambda f: f.dmx_address)
    sampled = next((f for f in in_universe if f.fixture_type in MOVER_TYPE_NAMES), None)
    if sampled is None:
        sampled = in_universe[0] if in_universe else None

    mover_dmx = {}
    if sampled is not None:
        base = sampled.dmx_address - 1
        mover_dmx = {'id': sampled.id, 'dmx_address': sampled.dmx_address}
        for name in ('pan', 'tilt', 'dimmer', 'shutter', 'red', 'green', 'blue'):
            offset = sampled.channels.get(name)
            addr = base + offset if offset is not None else None
            mover_dmx[name] = frame[addr] if addr is not None and 0 <= addr < len(frame) else None

    # Get fixture states
    fixtures = []
    for fixture in list(engine.fixtures.fixtures.values())[:4]:
        fixtures.append({
            'id': fixture.id,
            'universe': fixture.universe,
            'dmx_address': fixture.dmx_address,
            'dimmer': round(fixture.dimmer, 3),
            'strobe': round(fixture.strobe, 3),
            'pan': round(fixture.pan, 1),
            'tilt': round(fixture.tilt, 1),
            'rgb': (round(fixture.red, 2), round(fixture.green, 2), round(fixture.blue, 2))
        })

    # Audio features
    audio = {
        'energy': round(engine.audio_features.energy, 3),
        'bass': round(engine.audio_features.bass, 3),
        'mid': round(engine.audio_features.mid, 3),
        'high': round(engine.audio_features.high, 3),
        'valence': round(engine.audio_features.valence, 3),
        'arousal': round(engine.audio_features.arousal, 3),
        'is_beat': engine.audio_features.is_beat,
    }

    # Config state
    config = {
        'running': engine.running,
        'auto_mode': engine.config.auto_mode,
        'bpm': engine.config.bpm,
        'movement_enabled': engine.config.movement_enabled,
        'dimmer_enabled': engine.config.dimmer_enabled,
        'strobe_enabled': engine.config.strobe_enabled,
        'color_enabled': engine.config.color_enabled,
    }

    # Effect states
    effects = {
        'movement_pattern': engine.movement.params.pattern.value,
        'dimmer_effect': engine.dimmer.params.effect_type.value,
        'dimmer_base_intensity': engine.dimmer.params.base_intensity,
        'strobe_mode': engine.strobe.params.mode.value,
        'color_palette': engine.config.palette.value,
        'lighting_state': engine.decision.state.value,
    }

    non_zero = sum(1 for v in frame if v > 0)

    return {
        "status": "ok",
        "summary": {
            "universe": universe,
            "universes": engine.fixtures.get_universes(),
            "non_zero_dmx_channels": non_zero,
            "dmx_callback_set": engine._dmx_callback is not None,
            "first_mover_dmx": mover_dmx,
        },
        "audio_features": audio,
        "engine_config": config,
        "effect_states": effects,
        "fixtures_sample": fixtures,
        "troubleshooting": {
            "if_dimmer_0": "Check if audio capture is running and sending data",
            "if_no_audio": "Run: python scripts/audio_capture.py",
            "if_colors_black": "Check RGB values in fixtures_sample",
            "visualizer_url": "http://localhost:5173/",
        }
    }


# =============================================================================
# PROFESSIONAL LIGHTING ENDPOINTS
# =============================================================================

class GenreRequest(BaseModel):
    """Request to set active genre."""
    genre: str = Field(..., description="Genre name: edm, rock, pop, hip_hop, jazz")
    crossfade: bool = Field(True, description="Use crossfade transition")


class SectionRequest(BaseModel):
    """Request to trigger a song section."""
    section: str = Field(..., description="Section name: intro, verse, chorus, drop, etc.")
    immediate: bool = Field(False, description="Skip crossfade if True")


class ProMovementRequest(BaseModel):
    """Request to set pro movement pattern."""
    pattern: str = Field(..., description="Pro movement pattern name")
    beat_divisor: Optional[float] = Field(None)
    pan_amplitude: Optional[float] = Field(None)
    tilt_amplitude: Optional[float] = Field(None)
    phase_spread: Optional[float] = Field(None)


class ProStrobeRequest(BaseModel):
    """Request to trigger pro strobe effect."""
    mode: str = Field(..., description="Strobe mode: burst, beat_locked, blinder, progressive")
    frequency: Optional[float] = Field(None)
    duration: Optional[float] = Field(None)


class ProBuildRequest(BaseModel):
    """Request to trigger a build-up effect."""
    duration_beats: float = Field(16.0, description="Build-up duration in beats")
    curve: str = Field("quadratic", description="Ramp curve: linear, quadratic, exponential")


class KeyLightZoneRequest(BaseModel):
    """Request to configure a key lighting zone."""
    zone: str = Field(..., description="Zone name: dj_booth, stage_center, etc.")
    active: bool = Field(True, description="Whether zone is active")
    min_intensity: Optional[float] = Field(None, description="Minimum intensity 0-1")
    fixture_ids: Optional[List[str]] = Field(None, description="Fixture IDs for this zone")


@router.post("/pro/enable")
async def enable_pro_lighting(enabled: bool = True):
    """Enable or disable professional lighting integration."""
    engine = get_effects_engine()
    engine.enable_pro_lighting(enabled)
    return {"status": "ok", "pro_lighting_enabled": enabled}


@router.get("/pro/status")
async def get_pro_lighting_status():
    """Get professional lighting state."""
    engine = get_effects_engine()
    return engine.get_pro_lighting_state()


@router.get("/pro/genres")
async def get_genres():
    """Get available genre profiles."""
    return {
        "genres": [g.value for g in Genre],
        "current": get_effects_engine().genre_manager.current_genre.value,
        "profiles": {
            g.value: {
                "name": p.name,
                "description": p.description,
                "front_light_style": p.front_light_style,
                "haze_level": p.haze_level,
            }
            for g, p in GENRE_PROFILES.items()
        }
    }


@router.post("/pro/genre")
async def set_genre(request: GenreRequest):
    """Set active genre profile."""
    engine = get_effects_engine()
    try:
        genre = Genre(request.genre)
    except ValueError:
        raise HTTPException(400, f"Invalid genre: {request.genre}")
    engine.set_genre(genre, crossfade=request.crossfade)
    return {"status": "ok", "genre": request.genre}


@router.get("/pro/sections")
async def get_sections():
    """Get available song sections and current state."""
    engine = get_effects_engine()
    return {
        "sections": [s.value for s in SongSection],
        "current": engine.section_manager.current_section.value,
        "intensity": round(engine.section_manager.get_intensity(), 3),
        "movement_energy": round(engine.section_manager.get_movement_energy(), 3),
        "strobe_allowed": engine.section_manager.is_strobe_allowed(),
    }


@router.post("/pro/section")
async def set_section(request: SectionRequest):
    """Trigger a song section change."""
    engine = get_effects_engine()
    try:
        section = SongSection(request.section)
    except ValueError:
        raise HTTPException(400, f"Invalid section: {request.section}")
    engine.set_section(section, immediate=request.immediate)
    return {"status": "ok", "section": request.section}


@router.get("/pro/movement/patterns")
async def get_pro_movement_patterns():
    """Get available professional movement patterns and presets."""
    return {
        "patterns": [p.value for p in ProMovementPattern],
        "presets": list(PRO_MOVEMENT_PRESETS.keys()),
        "current": get_effects_engine().pro_movement.params.pattern.value,
    }


@router.post("/pro/movement")
async def set_pro_movement(request: ProMovementRequest):
    """Set professional movement pattern."""
    engine = get_effects_engine()
    try:
        pattern = ProMovementPattern(request.pattern)
    except ValueError:
        raise HTTPException(400, f"Invalid pattern: {request.pattern}")
    kwargs = {}
    if request.beat_divisor is not None:
        kwargs["beat_divisor"] = request.beat_divisor
    if request.pan_amplitude is not None:
        kwargs["pan_amplitude"] = request.pan_amplitude
    if request.tilt_amplitude is not None:
        kwargs["tilt_amplitude"] = request.tilt_amplitude
    if request.phase_spread is not None:
        kwargs["phase_spread"] = request.phase_spread
    engine.pro_movement.set_pattern(pattern, **kwargs)
    return {"status": "ok", "pattern": request.pattern}


@router.post("/pro/movement/preset/{preset_name}")
async def set_pro_movement_preset(preset_name: str):
    """Set professional movement from preset."""
    engine = get_effects_engine()
    if preset_name not in PRO_MOVEMENT_PRESETS:
        raise HTTPException(400, f"Invalid preset: {preset_name}")
    engine.pro_movement.params = PRO_MOVEMENT_PRESETS[preset_name]
    return {"status": "ok", "preset": preset_name}


@router.post("/pro/movement/speed-ramp")
async def start_movement_speed_ramp(
    duration: float = 8.0,
    start_mult: float = 0.25,
    end_mult: float = 2.0,
):
    """Start a movement speed ramp (buildup acceleration)."""
    engine = get_effects_engine()
    engine.pro_movement.start_speed_ramp(duration, start_mult, end_mult)
    return {"status": "ok", "duration": duration, "start_mult": start_mult, "end_mult": end_mult}


@router.post("/pro/movement/speed-ramp/stop")
async def stop_movement_speed_ramp():
    """Stop the movement speed ramp."""
    engine = get_effects_engine()
    engine.pro_movement.stop_speed_ramp()
    return {"status": "ok"}


@router.post("/pro/strobe")
async def trigger_pro_strobe(request: ProStrobeRequest):
    """Trigger a professional strobe effect."""
    engine = get_effects_engine()
    try:
        mode = ProStrobeMode(request.mode)
    except ValueError:
        raise HTTPException(400, f"Invalid mode: {request.mode}")
    kwargs = {}
    if request.frequency is not None:
        kwargs["frequency"] = request.frequency
    if request.duration is not None:
        if mode == ProStrobeMode.BURST:
            kwargs["burst_duration"] = request.duration
        elif mode == ProStrobeMode.BLINDER:
            kwargs["blinder_duration"] = request.duration
    engine.pro_effects.strobe.set_mode(mode, **kwargs)
    return {"status": "ok", "mode": request.mode}


@router.post("/pro/strobe/stop")
async def stop_pro_strobe():
    """Stop professional strobe effects."""
    engine = get_effects_engine()
    engine.pro_effects.strobe.stop()
    return {"status": "ok"}


@router.post("/pro/build")
async def trigger_pro_build(request: ProBuildRequest):
    """Trigger a professional build-up effect."""
    engine = get_effects_engine()
    engine.pro_effects.build.trigger(request.duration_beats, request.curve)
    return {"status": "ok", "duration_beats": request.duration_beats, "curve": request.curve}


@router.post("/pro/flash")
async def trigger_pro_flash(duration: float = 0.1):
    """Trigger a blinder flash."""
    engine = get_effects_engine()
    engine.pro_effects.flash(duration)
    return {"status": "ok", "duration": duration}


@router.post("/pro/blackout")
async def trigger_pro_blackout():
    """Kill all professional effects."""
    engine = get_effects_engine()
    engine.pro_effects.blackout()
    return {"status": "ok"}


@router.get("/pro/key-lighting")
async def get_key_lighting_status():
    """Get key lighting status."""
    engine = get_effects_engine()
    return {
        "active_zones": [z.value for z in engine.key_lighting.get_active_zones()],
        "available_zones": [z.value for z in PerformerZone],
    }


@router.post("/pro/key-lighting")
async def configure_key_lighting(request: KeyLightZoneRequest):
    """Configure a key lighting zone."""
    engine = get_effects_engine()
    try:
        zone = PerformerZone(request.zone)
    except ValueError:
        raise HTTPException(400, f"Invalid zone: {request.zone}")

    engine.key_lighting.set_zone_active(zone, request.active)

    if request.min_intensity is not None:
        config = engine.key_lighting._configs.get(zone)
        if config:
            config.min_intensity = request.min_intensity

    if request.fixture_ids is not None:
        engine.key_lighting.assign_fixtures(zone, request.fixture_ids)

    return {"status": "ok", "zone": request.zone, "active": request.active}
