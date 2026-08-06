"""
Audio Analysis API Endpoints
============================

Endpoints for audio analysis operations.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_db
from app.models.audio import AudioAnalysis, AudioFingerprint
from app.schemas.audio import (
    AudioStreamConfig, AudioAnalysisResponse, AudioAnalysisHistoryResponse,
    AudioFingerprintResponse, BeatResponse, MoodResponse, FrequencyResponse,
)
from app.services.lighting.section_manager import SongSection
from app.services.lighting.pro_effects import ACCENT_OFF_POLICIES

router = APIRouter()


@router.get("/config", response_model=AudioStreamConfig)
async def get_audio_config():
    """Get current audio stream configuration."""
    return AudioStreamConfig()


@router.post("/config", response_model=AudioStreamConfig)
async def update_audio_config(
    config: AudioStreamConfig,
    request: Request,
):
    """Update audio stream configuration."""
    if hasattr(request.app.state, 'audio_analyzer'):
        await request.app.state.audio_analyzer.update_config(config)
    return config


@router.get("/status")
async def get_audio_status(request: Request):
    """Get current audio analysis status."""
    if not hasattr(request.app.state, 'audio_analyzer'):
        return {"status": "not_initialized"}

    analyzer = request.app.state.audio_analyzer
    return {
        "status": "running" if analyzer.is_running else "stopped",
        "sample_rate": analyzer.sample_rate,
        "buffer_size": analyzer.buffer_size,
        "latency_ms": analyzer.latency_ms,
    }


@router.post("/start")
async def start_audio_analysis(request: Request):
    """Start real-time audio analysis."""
    if not hasattr(request.app.state, 'audio_analyzer'):
        raise HTTPException(status_code=500, detail="Audio analyzer not initialized")

    await request.app.state.audio_analyzer.start()
    return {"status": "started"}


@router.post("/stop")
async def stop_audio_analysis(request: Request):
    """Stop real-time audio analysis."""
    if not hasattr(request.app.state, 'audio_analyzer'):
        raise HTTPException(status_code=500, detail="Audio analyzer not initialized")

    await request.app.state.audio_analyzer.stop()
    return {"status": "stopped"}


@router.get("/current", response_model=AudioAnalysisResponse)
async def get_current_analysis(request: Request):
    """Get the most recent audio analysis result."""
    if not hasattr(request.app.state, 'audio_analyzer'):
        raise HTTPException(status_code=500, detail="Audio analyzer not initialized")

    analysis = request.app.state.audio_analyzer.get_current_analysis()
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis available")

    return analysis


@router.get("/beat", response_model=BeatResponse)
async def get_current_beat(request: Request):
    """Get the current beat detection result."""
    if not hasattr(request.app.state, 'audio_analyzer'):
        raise HTTPException(status_code=500, detail="Audio analyzer not initialized")

    return request.app.state.audio_analyzer.get_beat_info()


@router.get("/mood", response_model=MoodResponse)
async def get_current_mood(request: Request):
    """Get the current mood classification result."""
    if not hasattr(request.app.state, 'audio_analyzer'):
        raise HTTPException(status_code=500, detail="Audio analyzer not initialized")

    return request.app.state.audio_analyzer.get_mood_info()


@router.get("/frequency", response_model=FrequencyResponse)
async def get_current_frequency(request: Request):
    """Get the current frequency analysis result."""
    if not hasattr(request.app.state, 'audio_analyzer'):
        raise HTTPException(status_code=500, detail="Audio analyzer not initialized")

    return request.app.state.audio_analyzer.get_frequency_info()


# History endpoints
@router.get("/history", response_model=List[AudioAnalysisHistoryResponse])
async def get_analysis_history(
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Get recent audio analysis history."""
    query = select(AudioAnalysis).order_by(
        AudioAnalysis.timestamp.desc()
    ).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.delete("/history", status_code=204)
async def clear_analysis_history(
    db: AsyncSession = Depends(get_db),
):
    """Clear audio analysis history."""
    query = select(AudioAnalysis)
    result = await db.execute(query)
    for analysis in result.scalars():
        await db.delete(analysis)
    await db.commit()


# Fingerprint endpoints
@router.get("/fingerprints", response_model=List[AudioFingerprintResponse])
async def list_fingerprints(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List stored audio fingerprints."""
    query = select(AudioFingerprint)

    if search:
        # Escape SQL wildcard characters to prevent injection (BUG-005 fix)
        safe_search = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(
            (AudioFingerprint.track_name.ilike(f"%{safe_search}%")) |
            (AudioFingerprint.artist.ilike(f"%{safe_search}%"))
        )

    query = query.offset((page - 1) * size).limit(size).order_by(
        AudioFingerprint.track_name
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/fingerprints/{fingerprint_id}", response_model=AudioFingerprintResponse)
async def get_fingerprint(
    fingerprint_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific audio fingerprint."""
    query = select(AudioFingerprint).where(AudioFingerprint.id == fingerprint_id)
    result = await db.execute(query)
    fingerprint = result.scalar_one_or_none()

    if not fingerprint:
        raise HTTPException(status_code=404, detail="Fingerprint not found")

    return fingerprint


@router.post("/fingerprints/match")
async def match_fingerprint(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Attempt to match current audio against stored fingerprints."""
    if not hasattr(request.app.state, 'audio_analyzer'):
        raise HTTPException(status_code=500, detail="Audio analyzer not initialized")

    # Get current audio fingerprint
    current_fingerprint = request.app.state.audio_analyzer.get_current_fingerprint()
    if not current_fingerprint:
        raise HTTPException(status_code=400, detail="No audio fingerprint available")

    # Search for matches
    # This is a simplified version - real implementation would use
    # locality-sensitive hashing or similar techniques
    query = select(AudioFingerprint)
    result = await db.execute(query)
    fingerprints = result.scalars().all()

    best_match = None
    best_confidence = 0.0

    for fp in fingerprints:
        # Calculate similarity (placeholder)
        confidence = 0.0  # TODO: Implement actual fingerprint matching
        if confidence > best_confidence and confidence > 0.7:
            best_match = fp
            best_confidence = confidence

    if best_match:
        return {
            "matched": True,
            "fingerprint": AudioFingerprintResponse.model_validate(best_match),
            "confidence": best_confidence,
        }

    return {
        "matched": False,
        "fingerprint": None,
        "confidence": 0.0,
    }


@router.delete("/fingerprints/{fingerprint_id}", status_code=204)
async def delete_fingerprint(
    fingerprint_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete an audio fingerprint."""
    query = select(AudioFingerprint).where(AudioFingerprint.id == fingerprint_id)
    result = await db.execute(query)
    fingerprint = result.scalar_one_or_none()

    if not fingerprint:
        raise HTTPException(status_code=404, detail="Fingerprint not found")

    await db.delete(fingerprint)
    await db.commit()


# Reactive Lighting Mode
@router.post("/reactive/enable")
async def enable_reactive_mode(
    request: Request,
    rig_id: Optional[int] = Query(None, description="Rig ID for fixture mapping"),
):
    """Enable reactive lighting mode.

    When enabled, audio analysis will automatically control DMX output:
    - Beat detection triggers intensity flashes
    - Bass energy controls movement (pan/tilt)
    - Mood/valence affects color temperature
    - Overall energy affects master dimmer

    Use WebSocket /ws/audio to stream audio data for analysis.
    """
    if not hasattr(request.app.state, 'audio_analyzer'):
        raise HTTPException(status_code=500, detail="Audio analyzer not initialized")

    # Store reactive state
    request.app.state.reactive_mode = True
    request.app.state.reactive_rig_id = rig_id

    return {
        "status": "enabled",
        "rig_id": rig_id,
        "message": "Reactive lighting mode enabled. Stream audio via WebSocket to /ws/audio",
        "instructions": [
            "1. Run: python scripts/audio_capture.py",
            "2. Select your audio input device",
            "3. Play music and watch the lights react!",
            "4. POST /api/audio/reactive/disable to stop"
        ]
    }


# === System Audio Capture Endpoints ===

@router.get("/capture/devices")
async def list_capture_devices(request: Request):
    """List all available audio devices for system audio capture."""
    if not hasattr(request.app.state, 'audio_capture') or request.app.state.audio_capture is None:
        return {"devices": [], "error": "Audio capture not initialized (sounddevice may not be installed)"}

    import asyncio
    from app.services.audio.system_audio_capture import SystemAudioCapture
    # Run in executor because soundcard lazy import initializes COM (can block)
    devices = await asyncio.get_event_loop().run_in_executor(
        None, SystemAudioCapture.list_devices
    )
    return {"devices": devices}


@router.get("/capture/status")
async def get_capture_status(request: Request):
    """Get current system audio capture status."""
    if not hasattr(request.app.state, 'audio_capture') or request.app.state.audio_capture is None:
        return {"running": False, "available": False, "device_name": None}

    status = request.app.state.audio_capture.get_status()
    status["available"] = True
    engine = getattr(request.app.state, "effects_engine", None)
    if engine is not None:
        status["effects_engine_id"] = id(engine)
        status["effects_engine_time"] = engine.time
        status["effects_engine_running"] = engine.running
        status["effects_engine_auto_mode"] = engine.config.auto_mode
    return status


@router.post("/capture/start")
async def start_capture(
    request: Request,
    device_index: int = Query(..., description="Explicit audio capture device index"),
):
    """Start system audio capture.

    On Windows uses WASAPI loopback. On macOS uses CoreAudio (virtual audio
    devices like BlackHole provide system audio capture). On Linux uses
    PulseAudio/ALSA monitor devices.

    Args:
        device_index: Specific device index to use.
    """
    if not hasattr(request.app.state, 'audio_capture') or request.app.state.audio_capture is None:
        raise HTTPException(500, "Audio capture not available")

    capture = request.app.state.audio_capture
    if capture.is_running:
        return {"status": "already_running", "device": capture.device_name}

    try:
        devices = capture.list_devices()
        selected = next((d for d in devices if d.get("index") == device_index), None)
        if not selected:
            raise HTTPException(404, f"Audio device index {device_index} not found")
        # On Windows, require loopback device. On macOS/Linux, allow any input
        # device (loopback is provided by virtual audio drivers like BlackHole).
        import sys
        if sys.platform == "win32" and not selected.get("is_loopback", False):
            raise HTTPException(400, "Selected device is not a loopback output-capture device")
        if not selected.get("is_loopback", False) and not selected.get("is_input", False):
            raise HTTPException(400, "Selected device has no input channels")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "Failed to validate selected audio device")

    import asyncio
    loop = asyncio.get_event_loop()

    # Run in executor to avoid blocking the event loop (soundcard COM init is slow)
    success = await loop.run_in_executor(
        None, lambda: capture.start(device_index=device_index, loop=loop)
    )
    if not success:
        raise HTTPException(500, "Failed to start audio capture. Check device availability.")

    # Enable AI busker mode and keep reactive layers active.
    if hasattr(request.app.state, 'effects_engine') and request.app.state.effects_engine:
        effects_engine = request.app.state.effects_engine
        effects_engine.config.auto_mode = True
        effects_engine.config.movement_enabled = True
        effects_engine.config.dimmer_enabled = True
        # Accents follow the accessibility posture the venue is running, so
        # starting capture never re-arms a rig the operator switched to
        # "no_strobe" and never silences one they left on.
        policy = str(getattr(effects_engine.config, "accessibility_mode", "") or "").strip().lower()
        effects_engine.set_strobe_layer_enabled(policy not in ACCENT_OFF_POLICIES)
        effects_engine.enable_pro_lighting(True)
        try:
            effects_engine.set_section(SongSection.VERSE, immediate=True)
        except Exception:
            pass

    return {"status": "started", "device": capture.device_name}


@router.post("/capture/stop")
async def stop_capture(request: Request):
    """Stop system audio capture."""
    if not hasattr(request.app.state, 'audio_capture') or request.app.state.audio_capture is None:
        raise HTTPException(500, "Audio capture not available")

    request.app.state.audio_capture.stop()
    return {"status": "stopped"}


@router.post("/reactive/disable")
async def disable_reactive_mode(request: Request):
    """Disable reactive lighting mode."""
    request.app.state.reactive_mode = False
    request.app.state.reactive_rig_id = None

    # Optionally blackout
    if hasattr(request.app.state, 'dmx_controller'):
        try:
            await request.app.state.dmx_controller.blackout(fade_time=0.5)
        except Exception:
            pass

    return {"status": "disabled", "message": "Reactive lighting mode disabled"}


@router.get("/reactive/status")
async def get_reactive_status(request: Request):
    """Get current reactive lighting mode status."""
    return {
        "enabled": getattr(request.app.state, 'reactive_mode', False),
        "rig_id": getattr(request.app.state, 'reactive_rig_id', None),
        "audio_analyzer": hasattr(request.app.state, 'audio_analyzer') and request.app.state.audio_analyzer is not None,
        "dmx_controller": hasattr(request.app.state, 'dmx_controller') and request.app.state.dmx_controller is not None,
    }
