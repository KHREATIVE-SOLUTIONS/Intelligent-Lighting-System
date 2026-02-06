"""
Training Data Recording API Endpoints

Provides endpoints for:
- Starting/stopping training data recording sessions
- Manual lighting control during recording
- Exporting training data for Skip-BART model training
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from ...services.ml.training_recorder import (
    TrainingRecorder,
    ManualLightingController,
    get_recorder,
    set_recorder
)
from ...services.midi.midi_controller import get_midi_controller

router = APIRouter(prefix="/training", tags=["training"])

# Global instances
_manual_controller: Optional[ManualLightingController] = None


def get_manual_controller() -> ManualLightingController:
    """Get the manual controller instance."""
    if _manual_controller is None:
        raise HTTPException(status_code=503, detail="Manual controller not initialized")
    return _manual_controller


def set_manual_controller(controller: ManualLightingController):
    """Set the manual controller instance."""
    global _manual_controller
    _manual_controller = controller


# === Request/Response Models ===

class RecordingStatus(BaseModel):
    """Recording session status."""
    recording: bool
    session_name: str
    frame_count: int
    audio_frames: int
    lighting_frames: int
    duration_seconds: float
    fps: float


class StartRecordingRequest(BaseModel):
    """Request to start a recording session."""
    session_name: Optional[str] = Field(None, description="Session name (auto-generated if not provided)")


class ManualColorRequest(BaseModel):
    """Request to set manual color."""
    r: float = Field(..., ge=0, le=1, description="Red value (0-1)")
    g: float = Field(..., ge=0, le=1, description="Green value (0-1)")
    b: float = Field(..., ge=0, le=1, description="Blue value (0-1)")


class ManualDimmerRequest(BaseModel):
    """Request to set manual dimmer."""
    value: float = Field(..., ge=0, le=1, description="Dimmer value (0-1)")


class ManualMovementRequest(BaseModel):
    """Request to set movement pattern."""
    pattern: str = Field(..., description="Movement pattern name")


class ManualState(BaseModel):
    """Current manual controller state."""
    manual_mode: bool
    global_dimmer: float
    global_color: List[float]
    movement_pattern: str
    strobe_active: bool


# === Recording Control Endpoints ===

@router.get("/status", response_model=RecordingStatus)
async def get_recording_status():
    """Get current recording status."""
    recorder = get_recorder()
    stats = recorder.get_stats()
    return RecordingStatus(**stats)


@router.post("/start")
async def start_recording(request: StartRecordingRequest):
    """Start a new training data recording session."""
    recorder = get_recorder()

    if recorder.recording:
        raise HTTPException(400, "Already recording. Stop current session first.")

    recorder.start_recording(request.session_name)

    return {
        "status": "recording_started",
        "session_name": recorder.session_name
    }


@router.post("/stop")
async def stop_recording():
    """Stop the current recording session."""
    recorder = get_recorder()

    if not recorder.recording:
        raise HTTPException(400, "Not currently recording.")

    frame_count = recorder.stop_recording()

    return {
        "status": "recording_stopped",
        "session_name": recorder.session_name,
        "frame_count": frame_count
    }


@router.post("/export")
async def export_training_data(filename: Optional[str] = None):
    """Export recorded data to JSONL format for training."""
    recorder = get_recorder()

    if recorder.recording:
        raise HTTPException(400, "Stop recording before exporting.")

    if not recorder.frames:
        raise HTTPException(400, "No recorded frames to export.")

    filepath = recorder.export_training_data(filename)

    return {
        "status": "exported",
        "filepath": filepath,
        "frame_count": len(recorder.frames)
    }


@router.get("/sessions")
async def list_sessions():
    """List available recorded sessions."""
    recorder = get_recorder()

    sessions = []
    for meta_file in recorder.output_dir.glob("*_meta.json"):
        import json
        try:
            with open(meta_file) as f:
                metadata = json.load(f)
                sessions.append(metadata)
        except Exception:
            pass

    return {"sessions": sessions}


# === Manual Control Endpoints ===

@router.get("/manual/status", response_model=ManualState)
async def get_manual_status():
    """Get current manual controller state."""
    controller = get_manual_controller()

    return ManualState(
        manual_mode=controller.manual_mode,
        global_dimmer=controller.global_dimmer,
        global_color=list(controller.global_color),
        movement_pattern=controller.movement_pattern,
        strobe_active=controller.strobe_active
    )


@router.post("/manual/enable")
async def enable_manual_mode():
    """Enable manual control mode (disable auto mode)."""
    controller = get_manual_controller()
    controller.set_manual_mode(True)

    return {"status": "manual_mode_enabled"}


@router.post("/manual/disable")
async def disable_manual_mode():
    """Disable manual control mode (enable auto mode)."""
    controller = get_manual_controller()
    controller.set_manual_mode(False)

    return {"status": "manual_mode_disabled"}


@router.post("/manual/dimmer")
async def set_manual_dimmer(request: ManualDimmerRequest):
    """Set global dimmer value."""
    controller = get_manual_controller()
    controller.set_global_dimmer(request.value)

    return {"status": "ok", "dimmer": request.value}


@router.post("/manual/color")
async def set_manual_color(request: ManualColorRequest):
    """Set global color (RGB)."""
    controller = get_manual_controller()
    controller.set_global_color(request.r, request.g, request.b)

    return {"status": "ok", "color": [request.r, request.g, request.b]}


@router.post("/manual/color/preset/{preset}")
async def set_color_preset(preset: str):
    """Set color from preset name."""
    controller = get_manual_controller()

    valid_presets = [
        'white', 'red', 'green', 'blue', 'cyan',
        'magenta', 'yellow', 'orange', 'purple', 'pink', 'amber'
    ]

    if preset not in valid_presets:
        raise HTTPException(400, f"Invalid preset. Valid: {valid_presets}")

    controller.set_color_preset(preset)

    return {"status": "ok", "preset": preset}


@router.post("/manual/movement/{pattern}")
async def set_manual_movement(pattern: str):
    """Set movement pattern."""
    controller = get_manual_controller()

    valid_patterns = ['none', 'circle', 'sweep', 'tilt', 'figure8', 'chase', 'ballyhoo']

    if pattern not in valid_patterns:
        raise HTTPException(400, f"Invalid pattern. Valid: {valid_patterns}")

    controller.set_movement(pattern)

    return {"status": "ok", "pattern": pattern}


@router.post("/manual/strobe")
async def trigger_manual_strobe(duration: float = 0.5):
    """Trigger a strobe burst."""
    controller = get_manual_controller()
    controller.trigger_strobe(duration)

    return {"status": "ok", "duration": duration}


@router.post("/manual/blackout")
async def trigger_blackout():
    """Trigger momentary blackout."""
    controller = get_manual_controller()
    controller.trigger_blackout()

    return {"status": "ok", "action": "blackout"}


@router.post("/manual/flash")
async def trigger_flash():
    """Trigger full white flash."""
    controller = get_manual_controller()
    controller.trigger_flash()

    return {"status": "ok", "action": "flash"}


# === Keyboard Shortcuts Reference ===

@router.get("/manual/shortcuts")
async def get_keyboard_shortcuts():
    """Get recommended keyboard shortcuts for manual control."""
    return {
        "shortcuts": {
            "1-9": "Dimmer levels (1=10%, 9=90%, 0=100%)",
            "Q": "White",
            "W": "Red",
            "E": "Orange",
            "R": "Yellow",
            "T": "Green",
            "Y": "Cyan",
            "U": "Blue",
            "I": "Purple",
            "O": "Magenta",
            "P": "Pink",
            "A": "No movement",
            "S": "Circle movement",
            "D": "Sweep movement",
            "F": "Figure-8 movement",
            "G": "Chase movement",
            "Space": "Strobe burst",
            "B": "Blackout",
            "N": "Flash",
        },
        "tip": "Use a MIDI controller or keyboard to quickly operate during live recording"
    }


# === MIDI Control Endpoints ===

@router.get("/midi/status")
async def get_midi_status():
    """Get MIDI controller status and available devices."""
    midi = get_midi_controller()
    return midi.get_status()


@router.get("/midi/devices")
async def list_midi_devices():
    """List available MIDI input devices."""
    midi = get_midi_controller()
    devices = midi.list_devices()
    return {"devices": devices}


@router.post("/midi/start")
async def start_midi(device_name: Optional[str] = None):
    """Start listening for MIDI input."""
    midi = get_midi_controller()

    # Attach manual controller if available
    controller = get_manual_controller()
    if controller:
        midi.set_manual_controller(controller)

    success = midi.start(device_name)
    if success:
        return {"status": "started", "device": midi.input_port.name if midi.input_port else None}
    else:
        raise HTTPException(400, "Failed to start MIDI. Check if device is available.")


@router.post("/midi/stop")
async def stop_midi():
    """Stop listening for MIDI input."""
    midi = get_midi_controller()
    midi.stop()
    return {"status": "stopped"}


@router.post("/midi/learn")
async def midi_learn_mode():
    """Enter MIDI learn mode - next MIDI input will be mapped."""
    # TODO: Implement MIDI learn
    return {"status": "not_implemented", "message": "MIDI learn coming soon"}


@router.get("/midi/mappings")
async def get_midi_mappings():
    """Get current MIDI mappings."""
    midi = get_midi_controller()
    mappings = []
    for m in midi.mappings:
        mappings.append({
            'type': m.midi_type.name,
            'channel': m.channel,
            'control': m.control,
            'function': m.function,
            'min': m.min_value,
            'max': m.max_value
        })
    return {"mappings": mappings}


@router.post("/midi/mappings/reset")
async def reset_midi_mappings():
    """Reset MIDI mappings to grandMA2 defaults."""
    midi = get_midi_controller()
    midi.load_grandma2_mappings()
    return {"status": "reset", "mapping_count": len(midi.mappings)}
