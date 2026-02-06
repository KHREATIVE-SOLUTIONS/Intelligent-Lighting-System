"""
LFO Effects Engine API Endpoints

Controls the grandMA2-style LFO effects system for professional lighting effects.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from ...services.effects.lfo_engine import (
    LFOEngine, LFOConfig, EffectPreset,
    WaveformType, PhaseDistribution, EffectDirection, EffectAttribute,
    create_circle_effect, create_dimmer_chase
)

router = APIRouter(prefix="/lfo", tags=["lfo"])

# Global LFO engine instance
_lfo_engine: Optional[LFOEngine] = None


def get_lfo_engine() -> LFOEngine:
    """Get the LFO engine instance."""
    global _lfo_engine
    if _lfo_engine is None:
        _lfo_engine = LFOEngine()
    return _lfo_engine


def set_lfo_engine(engine: LFOEngine):
    """Set the LFO engine instance."""
    global _lfo_engine
    _lfo_engine = engine


# === Request/Response Models ===

class LFOStatus(BaseModel):
    """LFO engine status."""
    master_bpm: float
    master_speed: float
    fixture_count: int
    active_effects: List[str]
    available_effects: List[str]


class SetBPMRequest(BaseModel):
    """Request to set master BPM."""
    bpm: float = Field(..., ge=1, le=300, description="BPM (1-300)")


class SetSpeedRequest(BaseModel):
    """Request to set master speed multiplier."""
    speed: float = Field(..., ge=0, le=2, description="Speed multiplier (0-2)")


class ActivateEffectRequest(BaseModel):
    """Request to activate an effect."""
    effect_name: str = Field(..., description="Name of effect to activate")
    exclusive: bool = Field(False, description="Deactivate other effects first")


class CreateLFORequest(BaseModel):
    """Request to create a custom LFO."""
    waveform: str = Field("sine", description="Waveform type")
    attribute: str = Field("dimmer", description="Target attribute")
    low_value: float = Field(0.0, ge=-1, le=1, description="Low value")
    high_value: float = Field(1.0, ge=-1, le=1, description="High value")
    rate_multiplier: float = Field(1.0, ge=0.125, le=8, description="Speed multiplier")
    phase_start: float = Field(0, ge=0, le=360, description="Start phase degrees")
    phase_end: float = Field(360, ge=0, le=720, description="End phase degrees")
    distribution: str = Field("linear", description="Phase distribution mode")
    distribution_param: int = Field(1, ge=1, description="Distribution parameter")
    direction: str = Field("forward", description="Direction")
    pwm_width: float = Field(50, ge=0, le=100, description="PWM duty cycle")


class CreateEffectRequest(BaseModel):
    """Request to create a custom effect preset."""
    name: str = Field(..., description="Effect name")
    description: str = Field("", description="Effect description")
    lfos: List[CreateLFORequest] = Field(..., description="LFO configurations")


class CreateCircleRequest(BaseModel):
    """Request to create a circle effect."""
    name: str = Field("custom_circle", description="Effect name")
    pan_amplitude: float = Field(0.15, ge=0, le=0.5, description="Pan amplitude (0-0.5)")
    tilt_amplitude: float = Field(0.1, ge=0, le=0.5, description="Tilt amplitude (0-0.5)")
    rate: float = Field(1.0, ge=0.125, le=8, description="Speed multiplier")
    distribution: str = Field("linear", description="Phase distribution")
    phase_spread: float = Field(360, ge=0, le=720, description="Phase spread degrees")


class CreateChaseRequest(BaseModel):
    """Request to create a dimmer chase effect."""
    name: str = Field("custom_chase", description="Effect name")
    low: float = Field(0.0, ge=0, le=1, description="Low dimmer value")
    high: float = Field(1.0, ge=0, le=1, description="High dimmer value")
    rate: float = Field(1.0, ge=0.125, le=8, description="Speed multiplier")
    waveform: str = Field("sine", description="Waveform type")
    distribution: str = Field("linear", description="Phase distribution")


# === Endpoints ===

@router.get("/status", response_model=LFOStatus)
async def get_status():
    """Get LFO engine status."""
    engine = get_lfo_engine()
    return LFOStatus(
        master_bpm=engine.master_bpm,
        master_speed=engine.master_speed,
        fixture_count=engine.fixture_count,
        active_effects=engine.get_active_effects(),
        available_effects=engine.get_effect_names()
    )


@router.get("/effects")
async def list_effects():
    """List all available effects with details."""
    engine = get_lfo_engine()
    effects = {}
    for name in engine.get_effect_names():
        effects[name] = engine.get_effect_info(name)
    return {"effects": effects}


@router.get("/effects/{effect_name}")
async def get_effect_info(effect_name: str):
    """Get information about a specific effect."""
    engine = get_lfo_engine()
    info = engine.get_effect_info(effect_name)
    if info is None:
        raise HTTPException(404, f"Effect not found: {effect_name}")
    return info


@router.post("/bpm")
async def set_bpm(request: SetBPMRequest):
    """Set master BPM."""
    engine = get_lfo_engine()
    engine.set_master_bpm(request.bpm)
    return {"status": "ok", "bpm": engine.master_bpm}


@router.post("/speed")
async def set_speed(request: SetSpeedRequest):
    """Set master speed multiplier."""
    engine = get_lfo_engine()
    engine.set_master_speed(request.speed)
    return {"status": "ok", "speed": engine.master_speed}


@router.post("/fixtures/{count}")
async def set_fixture_count(count: int):
    """Set number of fixtures."""
    if count < 1 or count > 64:
        raise HTTPException(400, "Fixture count must be 1-64")
    engine = get_lfo_engine()
    engine.set_fixture_count(count)
    return {"status": "ok", "fixture_count": count}


@router.post("/activate")
async def activate_effect(request: ActivateEffectRequest):
    """Activate an effect."""
    engine = get_lfo_engine()

    if request.effect_name not in engine.effects:
        raise HTTPException(404, f"Effect not found: {request.effect_name}")

    if request.exclusive:
        engine.set_single_effect(request.effect_name)
    else:
        engine.activate_effect(request.effect_name)

    return {
        "status": "ok",
        "effect": request.effect_name,
        "active_effects": engine.get_active_effects()
    }


@router.post("/deactivate/{effect_name}")
async def deactivate_effect(effect_name: str):
    """Deactivate an effect."""
    engine = get_lfo_engine()
    engine.deactivate_effect(effect_name)
    return {
        "status": "ok",
        "deactivated": effect_name,
        "active_effects": engine.get_active_effects()
    }


@router.post("/deactivate-all")
async def deactivate_all():
    """Deactivate all effects."""
    engine = get_lfo_engine()
    engine.deactivate_all()
    return {"status": "ok", "active_effects": []}


# === Quick Effect Shortcuts ===

@router.post("/quick/circle")
async def quick_circle():
    """Activate circle movement effect."""
    engine = get_lfo_engine()
    engine.set_single_effect("circle")
    return {"status": "ok", "effect": "circle"}


@router.post("/quick/circle-wings")
async def quick_circle_wings():
    """Activate symmetric circle movement."""
    engine = get_lfo_engine()
    engine.set_single_effect("circle_wings")
    return {"status": "ok", "effect": "circle_wings"}


@router.post("/quick/ballyhoo")
async def quick_ballyhoo():
    """Activate ballyhoo/figure-8 movement."""
    engine = get_lfo_engine()
    engine.set_single_effect("ballyhoo")
    return {"status": "ok", "effect": "ballyhoo"}


@router.post("/quick/dimmer-chase")
async def quick_dimmer_chase():
    """Activate dimmer chase effect."""
    engine = get_lfo_engine()
    engine.set_single_effect("dimmer_chase")
    return {"status": "ok", "effect": "dimmer_chase"}


@router.post("/quick/dimmer-pulse")
async def quick_dimmer_pulse():
    """Activate dimmer pulse effect."""
    engine = get_lfo_engine()
    engine.set_single_effect("dimmer_pulse")
    return {"status": "ok", "effect": "dimmer_pulse"}


@router.post("/quick/odd-even")
async def quick_odd_even():
    """Activate odd/even dimmer effect."""
    engine = get_lfo_engine()
    engine.set_single_effect("dimmer_odd_even")
    return {"status": "ok", "effect": "dimmer_odd_even"}


@router.post("/quick/strobe")
async def quick_strobe():
    """Activate strobe effect."""
    engine = get_lfo_engine()
    engine.set_single_effect("strobe")
    return {"status": "ok", "effect": "strobe"}


@router.post("/quick/pan-sweep")
async def quick_pan_sweep():
    """Activate pan sweep effect."""
    engine = get_lfo_engine()
    engine.set_single_effect("pan_sweep")
    return {"status": "ok", "effect": "pan_sweep"}


@router.post("/quick/tilt-sweep")
async def quick_tilt_sweep():
    """Activate tilt sweep effect."""
    engine = get_lfo_engine()
    engine.set_single_effect("tilt_sweep")
    return {"status": "ok", "effect": "tilt_sweep"}


@router.post("/quick/color-chase")
async def quick_color_chase():
    """Activate color chase effect."""
    engine = get_lfo_engine()
    engine.set_single_effect("color_chase")
    return {"status": "ok", "effect": "color_chase"}


# === Custom Effect Creation ===

@router.post("/create/circle")
async def create_custom_circle(request: CreateCircleRequest):
    """Create and activate a custom circle effect."""
    engine = get_lfo_engine()

    # Parse distribution
    try:
        dist = PhaseDistribution(request.distribution)
    except ValueError:
        dist = PhaseDistribution.LINEAR

    effect = create_circle_effect(
        pan_amplitude=request.pan_amplitude,
        tilt_amplitude=request.tilt_amplitude,
        rate=request.rate,
        distribution=dist,
        phase_spread=request.phase_spread
    )

    engine.effects[request.name] = effect
    engine.set_single_effect(request.name)

    return {"status": "ok", "effect": request.name}


@router.post("/create/chase")
async def create_custom_chase(request: CreateChaseRequest):
    """Create and activate a custom dimmer chase effect."""
    engine = get_lfo_engine()

    # Parse waveform
    try:
        waveform = WaveformType(request.waveform)
    except ValueError:
        waveform = WaveformType.SINE

    # Parse distribution
    try:
        dist = PhaseDistribution(request.distribution)
    except ValueError:
        dist = PhaseDistribution.LINEAR

    effect = create_dimmer_chase(
        low=request.low,
        high=request.high,
        rate=request.rate,
        distribution=dist,
        waveform=waveform
    )

    engine.effects[request.name] = effect
    engine.set_single_effect(request.name)

    return {"status": "ok", "effect": request.name}


@router.post("/create/effect")
async def create_custom_effect(request: CreateEffectRequest):
    """Create a fully custom effect with multiple LFOs."""
    engine = get_lfo_engine()

    lfo_configs = []
    for lfo_req in request.lfos:
        try:
            waveform = WaveformType(lfo_req.waveform)
        except ValueError:
            waveform = WaveformType.SINE

        try:
            attribute = EffectAttribute(lfo_req.attribute)
        except ValueError:
            attribute = EffectAttribute.DIMMER

        try:
            distribution = PhaseDistribution(lfo_req.distribution)
        except ValueError:
            distribution = PhaseDistribution.LINEAR

        try:
            direction = EffectDirection(lfo_req.direction)
        except ValueError:
            direction = EffectDirection.FORWARD

        lfo_configs.append(LFOConfig(
            waveform=waveform,
            attribute=attribute,
            low_value=lfo_req.low_value,
            high_value=lfo_req.high_value,
            rate_multiplier=lfo_req.rate_multiplier,
            phase_start=lfo_req.phase_start,
            phase_end=lfo_req.phase_end,
            distribution=distribution,
            distribution_param=lfo_req.distribution_param,
            direction=direction,
            pwm_width=lfo_req.pwm_width,
        ))

    engine.create_custom_effect(request.name, lfo_configs, request.description)
    engine.set_single_effect(request.name)

    return {"status": "ok", "effect": request.name, "lfo_count": len(lfo_configs)}


# === Output ===

@router.get("/output")
async def get_current_output():
    """Get current LFO output values for all fixtures.

    BUG-041 fix: read cached _outputs instead of calling engine.update(),
    which advances the LFO phase and would double the effect speed when polled.
    """
    engine = get_lfo_engine()
    return {"outputs": engine._outputs, "active_effects": engine.get_active_effects()}


@router.get("/output/{fixture_index}")
async def get_fixture_output(fixture_index: int):
    """Get current LFO output for a specific fixture.

    BUG-041 fix: read cached output instead of calling engine.update().
    """
    engine = get_lfo_engine()
    if fixture_index < 0 or fixture_index >= engine.fixture_count:
        raise HTTPException(400, f"Invalid fixture index. Valid: 0-{engine.fixture_count-1}")

    output = engine.get_fixture_output(fixture_index)
    return {"fixture_index": fixture_index, "output": output}


# === Reference ===

@router.get("/waveforms")
async def list_waveforms():
    """List available waveform types."""
    return {"waveforms": [w.value for w in WaveformType]}


@router.get("/distributions")
async def list_distributions():
    """List available phase distribution modes."""
    return {"distributions": [d.value for d in PhaseDistribution]}


@router.get("/attributes")
async def list_attributes():
    """List available effect attributes."""
    return {"attributes": [a.value for a in EffectAttribute]}


@router.get("/directions")
async def list_directions():
    """List available effect directions."""
    return {"directions": [d.value for d in EffectDirection]}
