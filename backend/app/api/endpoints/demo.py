"""
Demo Simulation and Venue Preset API Endpoints
Controls the demo mode for showcasing the lighting system without live audio.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict

from ...services.demo.demo_simulation import DemoSimulation, DemoConfig
from ...services.demo.venue_presets import VENUE_PRESETS, VenuePreset, create_venue_rig
from ...services.effects.fixture_groups import canonical_channel_name

router = APIRouter()

# Global demo simulation instance
_demo: Optional[DemoSimulation] = None
_effects_engine = None


def set_demo_effects_engine(engine):
    """Set the effects engine for demo mode to control."""
    global _effects_engine
    _effects_engine = engine


def get_demo() -> DemoSimulation:
    """Get or create the demo simulation."""
    global _demo
    if _demo is None:
        _demo = DemoSimulation()
    return _demo


# === Request Models ===

class DemoStartRequest(BaseModel):
    genre: str = Field("edm", description="Genre: edm, rock, pop, hip_hop, jazz")
    speed: float = Field(1.0, description="Playback speed: 0.25 to 8.0")
    loop: bool = Field(False, description="Loop when finished")
    venue_preset: Optional[str] = Field(None, description="Apply venue preset before starting")


class DemoSpeedRequest(BaseModel):
    speed: float = Field(..., description="Playback speed: 0.25 to 8.0")


# === Demo Simulation Endpoints ===

@router.post("/demo/start")
async def start_demo(request: DemoStartRequest):
    """Start the demo simulation.

    Generates synthetic audio data to drive the lighting system through a
    complete set progression (intro -> verse -> buildup -> drop -> breakdown -> outro).
    """
    global _demo

    # Apply venue preset if requested
    if request.venue_preset:
        if request.venue_preset not in VENUE_PRESETS:
            raise HTTPException(400, f"Unknown venue preset: {request.venue_preset}. "
                                f"Available: {list(VENUE_PRESETS.keys())}")
        if _effects_engine:
            manager, preset = create_venue_rig(request.venue_preset)
            if manager:
                _effects_engine.set_fixture_manager(manager)
                # Apply default genre from venue
                from ...services.lighting.genre_profiles import Genre
                try:
                    _effects_engine.set_genre(Genre(preset.default_genre))
                except ValueError:
                    pass

    # Create new demo with config
    config = DemoConfig(
        genre=request.genre,
        speed=max(0.25, min(8.0, request.speed)),
        loop=request.loop,
    )
    _demo = DemoSimulation(config)
    _demo.start()

    # Enable pro lighting and auto mode
    if _effects_engine:
        _effects_engine.enable_pro_lighting(True)
        _effects_engine.config.auto_mode = True
        _effects_engine.config.movement_enabled = True
        _effects_engine.config.dimmer_enabled = True
        _effects_engine.set_strobe_layer_enabled(True)
        _effects_engine.config.color_enabled = True

        # Set genre
        from ...services.lighting.genre_profiles import Genre
        try:
            _effects_engine.set_genre(Genre(request.genre))
        except ValueError:
            pass

    return {
        "status": "started",
        "genre": request.genre,
        "speed": config.speed,
        "loop": config.loop,
        "total_duration": round(_demo.total_duration, 1),
        "venue_preset": request.venue_preset,
    }


@router.post("/demo/stop")
async def stop_demo():
    """Stop the demo simulation."""
    demo = get_demo()
    demo.stop()

    # Restore default AI busker runtime after demo ends
    if _effects_engine:
        _effects_engine.config.auto_mode = True
        _effects_engine.config.movement_enabled = True
        _effects_engine.config.dimmer_enabled = True
        _effects_engine.set_strobe_layer_enabled(False)

    return {"status": "stopped"}


@router.get("/demo/status")
async def get_demo_status():
    """Get current demo simulation state."""
    demo = get_demo()
    status = demo.get_status()

    # Add effects engine state if available
    if _effects_engine:
        status["pro_lighting_enabled"] = _effects_engine._pro_lighting_enabled
        try:
            status["pro_state"] = _effects_engine.get_pro_lighting_state()
        except Exception:
            pass

    return status


@router.post("/demo/speed")
async def set_demo_speed(request: DemoSpeedRequest):
    """Change demo playback speed."""
    demo = get_demo()
    demo.set_speed(request.speed)
    return {"status": "ok", "speed": demo.config.speed}


@router.post("/demo/update")
async def demo_update_tick(delta_time: float = 1.0 / 60.0):
    """Manually advance the demo by one tick.

    Useful for step-through debugging. In normal operation, the effects
    engine loop calls demo.update() automatically.
    """
    demo = get_demo()
    if not demo.running:
        raise HTTPException(400, "Demo not running. Call /demo/start first.")

    data = demo.update(delta_time)
    if data is None:
        return {"status": "finished"}

    # Feed into effects engine
    if _effects_engine:
        # Map section to SongSection
        from ...services.lighting.section_manager import SongSection
        section_str = data.get("section", "unknown")
        try:
            section = SongSection(section_str)
            _effects_engine.set_section(section)
        except ValueError:
            pass

        _effects_engine.update_audio(
            energy=data["energy"],
            bass=data["bass"],
            mid=data["mid"],
            high=data["high"],
            is_beat=data["is_beat"],
            beat_number=data["beat_number"],
            valence=data["valence"],
            arousal=data["arousal"],
            spectral_flux=data["spectral_flux"],
            bpm=data["bpm"],
        )

    return {"status": "ok", "data": data}


# === Venue Preset Endpoints ===

@router.get("/venues/presets")
async def list_venue_presets():
    """List all available venue presets."""
    presets = {}
    for name, preset in VENUE_PRESETS.items():
        presets[name] = {
            "display_name": preset.display_name,
            "description": preset.description,
            "size": preset.size.value,
            "stage": {
                "width": preset.stage.width,
                "depth": preset.stage.depth,
                "height": preset.stage.height,
                "truss_lines": preset.stage.truss_lines,
            },
            "fixture_counts": preset.fixture_counts,
            "total_fixtures": len(preset.fixtures),
            "key_zones": len(preset.key_zones),
            "default_genre": preset.default_genre,
            "default_bpm": preset.default_bpm,
        }
    return {"presets": presets}


@router.get("/venues/presets/{preset_name}")
async def get_venue_preset(preset_name: str):
    """Get detailed info about a specific venue preset."""
    preset = VENUE_PRESETS.get(preset_name)
    if preset is None:
        raise HTTPException(404, f"Venue preset not found: {preset_name}. "
                            f"Available: {list(VENUE_PRESETS.keys())}")

    return {
        "name": preset.name,
        "display_name": preset.display_name,
        "description": preset.description,
        "size": preset.size.value,
        "stage": {
            "width": preset.stage.width,
            "depth": preset.stage.depth,
            "height": preset.stage.height,
            "truss_lines": preset.stage.truss_lines,
        },
        "fixture_counts": preset.fixture_counts,
        "total_fixtures": len(preset.fixtures),
        "fixtures": [
            {
                "id": f.id,
                "name": f.name,
                "type": f.fixture_type,
                "dmx_address": f.dmx_address,
                "universe": f.universe,
                "position": {"x": f.x, "y": f.y, "z": f.z},
            }
            for f in preset.fixtures
        ],
        "key_zones": [
            {
                "zone": z.zone,
                "fixture_ids": z.fixture_ids,
                "active": z.active,
                "min_intensity": z.min_intensity,
            }
            for z in preset.key_zones
        ],
        "default_genre": preset.default_genre,
        "default_bpm": preset.default_bpm,
    }


@router.get("/demo/rig")
async def get_demo_rig(preset: str = "pro_beam_room"):
    """Get a demo rig as a Rig-compatible JSON for the 3D visualizer.

    This returns fixture data shaped like the frontend's Rig type so the
    visualizer can render without needing a database rig.
    """
    venue = VENUE_PRESETS.get(preset)
    if venue is None:
        raise HTTPException(404, f"Unknown preset: {preset}. Available: {list(VENUE_PRESETS.keys())}")

    # Map fixture type -> FixtureType enum value used by frontend
    TYPE_MAP = {
        "mover": "moving_head",
        "wash": "wash",
        "bar": "led_bar",
        "strobe": "strobe",
        "spot": "spot",
    }

    # Channel maps per fixture type (key → 1-indexed channel_number)
    from ...services.demo.venue_presets import (
        MOVER_CHANNELS, WASH_CHANNELS, BAR_CHANNELS, STROBE_CHANNELS, SPOT_CHANNELS,
        MOVER_CH_COUNT, WASH_CH_COUNT, BAR_CH_COUNT, STROBE_CH_COUNT, SPOT_CH_COUNT,
    )
    CH_MAPS = {
        "mover": (MOVER_CHANNELS, MOVER_CH_COUNT),
        "wash": (WASH_CHANNELS, WASH_CH_COUNT),
        "bar": (BAR_CHANNELS, BAR_CH_COUNT),
        "strobe": (STROBE_CHANNELS, STROBE_CH_COUNT),
        "spot": (SPOT_CHANNELS, SPOT_CH_COUNT),
    }

    rig_fixtures = []
    for idx, f in enumerate(venue.fixtures):
        ch_map, ch_count = CH_MAPS.get(f.fixture_type, (BAR_CHANNELS, BAR_CH_COUNT))
        channels = []
        for ch_name, offset in ch_map.items():
            channels.append({
                "id": idx * 100 + offset,
                "mode_id": idx + 1,
                "channel_number": offset + 1,  # 1-indexed
                "channel_type": canonical_channel_name(ch_name),
                "name": ch_name.replace("_", " ").title(),
                "default_value": 0,
                "min_value": 0,
                "max_value": 255,
                "is_fine": ch_name.endswith("_fine"),
                "coarse_channel": None,
            })

        fixture_type = TYPE_MAP.get(f.fixture_type, "other")
        is_mover = f.fixture_type in ("mover", "wash", "spot")

        rig_fixtures.append({
            "id": idx + 1,
            "rig_id": 0,
            "fixture_id": idx + 1,
            "name": f.name,
            "fixture_number": idx + 1,
            "universe": f.universe,
            "dmx_address": f.dmx_address,
            "mode_id": None,
            "position_x": f.x,
            "position_y": f.y,
            "position_z": f.z,
            "rotation_x": 0,
            "rotation_y": 0,
            "rotation_z": 0,
            "group_name": f.fixture_type,
            "tags": [f.fixture_type],
            "is_active": True,
            "is_inverted": False,
            "is_address_locked": False,
            "serial_number": None,
            "qr_code_data": None,
            "fixture": {
                "id": idx + 1,
                "manufacturer": "Demo",
                "model": f.name,
                "fixture_type": fixture_type,
                "weight": None,
                "power": None,
                "beam_angle": 25 if is_mover else 40,
                "pan_range": 540 if is_mover else 0,
                "tilt_range": 270 if is_mover else 0,
                "has_rgb": True,
                "has_cmy": False,
                "has_color_wheel": f.fixture_type == "mover",
                "modes": [{
                    "id": idx + 1,
                    "fixture_id": idx + 1,
                    "name": "Standard",
                    "channel_count": ch_count,
                    "description": None,
                    "channels": channels,
                }],
            },
        })

    return {
        "id": 0,
        "name": venue.display_name,
        "description": venue.description,
        "venue": venue.name,
        "stage_width": venue.stage.width,
        "stage_depth": venue.stage.depth,
        "stage_height": venue.stage.height,
        "universes": [{"universe": 0, "protocol": "artnet", "ip_address": None, "port": 6454}],
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "created_by": "demo",
        "is_active": True,
        "fixtures": rig_fixtures,
    }


@router.post("/venues/presets/{preset_name}/apply")
async def apply_venue_preset(preset_name: str):
    """Apply a venue preset - creates the rig and configures the system."""
    if _effects_engine is None:
        raise HTTPException(503, "Effects engine not initialized")

    manager, preset = create_venue_rig(preset_name)
    if manager is None:
        raise HTTPException(404, f"Venue preset not found: {preset_name}")

    # Replace the effects engine's fixture manager
    _effects_engine.set_fixture_manager(manager)

    # Apply key lighting zones
    for zone_spec in preset.key_zones:
        try:
            from ...services.lighting.key_lighting import PerformerZone, KeyLightConfig
            zone = PerformerZone(zone_spec.zone)
            _effects_engine.key_lighting.configure_zone(
                zone,
                KeyLightConfig(
                    zone=zone,
                    min_intensity=zone_spec.min_intensity,
                    active=zone_spec.active,
                )
            )
            _effects_engine.key_lighting.assign_fixtures(zone, zone_spec.fixture_ids)
        except (ValueError, Exception):
            pass  # Skip unknown zones

    # Set default genre
    from ...services.lighting.genre_profiles import Genre
    try:
        _effects_engine.set_genre(Genre(preset.default_genre))
    except ValueError:
        pass

    _effects_engine.config.bpm = preset.default_bpm

    return {
        "status": "ok",
        "preset": preset_name,
        "display_name": preset.display_name,
        "fixture_count": len(preset.fixtures),
        "fixture_types": preset.fixture_counts,
        "key_zones": len(preset.key_zones),
        "genre": preset.default_genre,
        "bpm": preset.default_bpm,
    }
