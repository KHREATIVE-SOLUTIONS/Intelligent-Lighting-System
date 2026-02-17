"""
Main FastAPI Application
========================

Entry point for the Intelligent Lighting System backend.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import (
    shows, rigs, fixtures, audio, dmx, websocket, effects, training, lfo,
    fixture_library, rig_patching, fixture_test, wizard, templates,
    rig_import_export, discovery, qr_scanning, demo,
)
from app.core.config import settings
from app.db.database import engine, Base
from app.services.audio.audio_analyzer import AudioAnalyzer
from app.services.dmx.dmx_controller import DMXController
from app.services.ml.model_manager import ModelManager
from app.services.effects import EffectsEngine, EffectsConfig
from app.api.endpoints.effects import set_effects_engine
from app.services.ml.training_recorder import TrainingRecorder, ManualLightingController, set_recorder
from app.api.endpoints.training import set_manual_controller
from app.services.midi.midi_controller import MIDIController, set_midi_controller
from app.services.effects.lfo_engine import LFOEngine
from app.api.endpoints.lfo import set_lfo_engine
from app.services.audio.system_audio_capture import SystemAudioCapture


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    print("Starting Intelligent Lighting System...")

    try:
        # Initialize ML models
        print(" Loading ML models...")
        app.state.model_manager = ModelManager()
        await app.state.model_manager.load_models()
        print(" ML models queued")
    except Exception as e:
        print(f"Warning: Could not load ML models: {e}")
        app.state.model_manager = None

    try:
        # Initialize audio analyzer
        print(" Creating AudioAnalyzer...")
        app.state.audio_analyzer = AudioAnalyzer(app.state.model_manager)

        # Wire ML pipeline models into audio analyzer
        if app.state.model_manager:
            app.state.audio_analyzer.set_ml_models(
                mert_model=app.state.model_manager.mert_model,
                structure_analyzer=app.state.model_manager.structure_analyzer,
                genre_classifier=app.state.model_manager.genre_classifier,
            )
    except Exception as e:
        print(f"Warning: Could not initialize audio analyzer: {e}")
        app.state.audio_analyzer = None

    try:
        # Initialize DMX controller
        print(" Creating DMX controller...")
        app.state.dmx_controller = DMXController()
        await app.state.dmx_controller.connect()
    except Exception as e:
        print(f"Warning: Could not connect DMX controller: {e}")
        app.state.dmx_controller = None

    try:
        # Initialize Effects Engine - TRAINING MODE (no auto-reactivity)
        print(" Creating effects engine...")
        app.state.effects_engine = EffectsEngine(EffectsConfig(
            fps=60.0,
            auto_mode=False,  # Disabled for training - human operates manually
            movement_enabled=False,  # Use LFO engine instead
            dimmer_enabled=False,    # Manual control only
            strobe_enabled=False,    # Manual triggers only
        ))

        # Connect effects engine to DMX controller
        if app.state.dmx_controller:
            def dmx_callback(universe: int, frame: list):
                if app.state.dmx_controller:
                    # Directly update universe data (frame is a 512-element list)
                    if universe not in app.state.dmx_controller.universes:
                        from app.schemas.dmx import DMXUniverse
                        app.state.dmx_controller.universes[universe] = DMXUniverse(universe=universe)
                    app.state.dmx_controller.universes[universe].data = frame

            app.state.effects_engine.set_dmx_callback(dmx_callback)

        # Register with API
        set_effects_engine(app.state.effects_engine)

        # Initialize professional lighting modules
        # Genre profiles, section manager, pro effects, and key lighting
        # are already instantiated inside EffectsEngine - just configure them
        from app.services.lighting.genre_profiles import Genre
        from app.services.lighting.key_lighting import PerformerZone, KeyLightConfig
        from app.services.effects.color_mapper import RGB

        # Set default genre
        app.state.effects_engine.set_genre(Genre.EDM)

        # Configure DJ booth key lighting
        app.state.effects_engine.key_lighting.configure_zone(
            PerformerZone.DJ_BOOTH,
            KeyLightConfig(
                zone=PerformerZone.DJ_BOOTH,
                min_intensity=0.4,
                color_temp="genre",
                active=True,
            )
        )

        # Pro lighting starts disabled - enable via API when ready
        print("Professional lighting modules initialized (use API to enable)")

        # Wire effects engine to demo module
        from app.api.endpoints.demo import set_demo_effects_engine
        set_demo_effects_engine(app.state.effects_engine)

        # Auto-apply medium venue preset so the demo rig has fixtures
        from app.services.demo.venue_presets import create_venue_rig
        manager, preset = create_venue_rig("medium_venue")
        if manager:
            app.state.effects_engine.fixtures = manager
            for zone_spec in preset.key_zones:
                try:
                    from app.services.lighting.key_lighting import PerformerZone, KeyLightConfig
                    zone = PerformerZone(zone_spec.zone)
                    app.state.effects_engine.key_lighting.configure_zone(
                        zone,
                        KeyLightConfig(zone=zone, min_intensity=zone_spec.min_intensity, active=zone_spec.active)
                    )
                    app.state.effects_engine.key_lighting.assign_fixtures(zone, zone_spec.fixture_ids)
                except (ValueError, Exception):
                    pass
            print(f"Auto-applied medium_venue preset ({len(preset.fixtures)} fixtures)")

        # Start the effects engine async loop (BUG-016 fix: store task reference)
        import asyncio
        app.state.effects_engine_task = asyncio.create_task(app.state.effects_engine.run())

        # Start a WebSocket broadcast task that pushes DMX state to all connected clients at ~30fps
        # This is needed because server-side audio capture bypasses the WebSocket input path
        async def _broadcast_lighting_state():
            from app.api.endpoints.websocket import manager, convert_numpy_types
            from app.services.lighting.look_spec import build_lighting_look_spec
            from datetime import datetime
            frame_count = 0
            while True:
                try:
                    await asyncio.sleep(1.0 / 30.0)  # ~30fps
                    ee = app.state.effects_engine
                    if ee is None:
                        continue

                    # Build DMX frame
                    dmx_frame = ee.fixtures.get_dmx_frame(universe=0)
                    fixture_states = ee.get_fixture_state_snapshot()
                    if not fixture_states:
                        fixture_states = []
                        for fixture in ee.fixtures.fixtures.values():
                            fixture_states.append({
                                'id': fixture.id, 'pan': fixture.pan, 'tilt': fixture.tilt,
                                'dimmer': fixture.dimmer, 'r': fixture.red, 'g': fixture.green, 'b': fixture.blue
                            })

                    # Get pro lighting state
                    pro_state = None
                    try:
                        pro_state = ee.get_pro_lighting_state()
                    except Exception:
                        pass

                    lighting_data = {
                        'dmx_frame': dmx_frame,
                        'fixtures': fixture_states,
                        'state': 'auto',
                        'movement': 'auto',
                        'dimmer': 'auto',
                    }
                    if pro_state:
                        lighting_data['genre'] = pro_state.get('genre')
                        lighting_data['section'] = pro_state.get('section')
                        lighting_data['section_intensity'] = pro_state.get('section_intensity')
                        lighting_data['pro_effects'] = {
                            'strobeMode': pro_state.get('pro_strobe_active', False) and 'beat_sync' or 'off',
                            'chaseType': 'off',
                            'movementType': pro_state.get('pro_movement_pattern', 'none'),
                        }

                    response_payload = {
                        "type": "analysis",
                        "timestamp": datetime.utcnow().isoformat(),
                        "lighting": lighting_data,
                    }
                    try:
                        response_payload["look_spec"] = build_lighting_look_spec(ee).model_dump(mode="json")
                    except Exception:
                        pass
                    try:
                        current_analysis = app.state.audio_analyzer.get_current_analysis()
                        if current_analysis:
                            if hasattr(current_analysis, "model_dump"):
                                response_payload.update(current_analysis.model_dump(mode="json"))
                            elif isinstance(current_analysis, dict):
                                response_payload.update(current_analysis)
                    except Exception:
                        pass
                    response = convert_numpy_types(response_payload)

                    await manager.broadcast("audio", response)
                    await manager.broadcast("dmx", {
                        "type": "dmx_update",
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": {"universe": 0, "frame": dmx_frame},
                    })
                except asyncio.CancelledError:
                    break
                except Exception:
                    await asyncio.sleep(0.5)  # Back off on errors

        app.state.broadcast_task = asyncio.create_task(_broadcast_lighting_state())
        print(" Effects engine + WebSocket broadcast ready")
    except Exception as e:
        print(f"Warning: Could not initialize effects engine: {e}")
        import traceback
        traceback.print_exc()
        app.state.effects_engine = None

    # Initialize Training Recorder for ML data collection
    print(" Initializing training recorder...")
    try:
        app.state.training_recorder = TrainingRecorder(
            output_dir="ml_training_data"
        )
        set_recorder(app.state.training_recorder)

        # Initialize Manual Lighting Controller
        if app.state.effects_engine:
            app.state.manual_controller = ManualLightingController(
                app.state.effects_engine
            )
            app.state.manual_controller.attach_recorder(app.state.training_recorder)
            set_manual_controller(app.state.manual_controller)
            print("Training recorder and manual controller initialized")
    except Exception as e:
        print(f"Warning: Could not initialize training recorder: {e}")
        app.state.training_recorder = None
        app.state.manual_controller = None

    # Initialize LFO Engine (grandMA2-style effects)
    print(" Initializing LFO engine...")
    try:
        app.state.lfo_engine = LFOEngine()
        app.state.lfo_engine.set_fixture_count(8)  # Match demo rig
        set_lfo_engine(app.state.lfo_engine)

        # Connect LFO engine to effects engine for frame-by-frame updates
        if app.state.effects_engine:
            app.state.effects_engine.set_lfo_engine(app.state.lfo_engine)
            print("LFO effects engine initialized and connected to effects engine")
        else:
            print("LFO effects engine initialized (standalone)")
    except Exception as e:
        print(f"Warning: Could not initialize LFO engine: {e}")
        app.state.lfo_engine = None

    # Initialize MIDI Controller
    print(" Initializing MIDI controller...")
    try:
        app.state.midi_controller = MIDIController()
        set_midi_controller(app.state.midi_controller)

        # Connect to manual controller if available
        if app.state.manual_controller:
            app.state.midi_controller.set_manual_controller(app.state.manual_controller)

        # List available MIDI devices
        devices = app.state.midi_controller.list_devices()
        if devices:
            print(f"MIDI devices available: {devices}")
            # Auto-start with first device (can be changed via API)
            # app.state.midi_controller.start()
        else:
            print("No MIDI devices found (will check again when requested)")
    except Exception as e:
        print(f"Warning: Could not initialize MIDI controller: {e}")
        app.state.midi_controller = None

    # Initialize System Audio Capture (WASAPI loopback for clean signal)
    # Auto-starts via a delayed async task after the server is listening,
    # so the blocking soundcard COM init never stalls the event loop.
    try:
        # Throttle flag: only one process_chunk at a time to avoid saturating the event loop
        _processing = [False]

        def on_audio_chunk(audio_data):
            """Process captured system audio through the analysis pipeline."""
            if _processing[0]:
                return  # Skip this chunk - previous one still processing
            if not (app.state.audio_analyzer and app.state.effects_engine):
                return
            try:
                _loop = app.state._audio_loop
                if _loop and _loop.is_running():
                    _processing[0] = True
                    future = asyncio.run_coroutine_threadsafe(
                        app.state.audio_analyzer.process_chunk(audio_data),
                        _loop,
                    )
                    def _on_result(fut):
                        _processing[0] = False
                        try:
                            result = fut.result()
                            if result:
                                ml_data = result.get("ml", {})
                                beat = result.get("beat", {})
                                mood = result.get("mood", {})
                                freq = result.get("frequency", {})

                                bands = {b.get("name"): b.get("energy", 0.0) for b in freq.get("bands", [])}
                                bass_energy = bands.get("bass", 0.0) + bands.get("sub_bass", 0.0)
                                mid_energy = bands.get("mid", 0.0) + bands.get("low_mid", 0.0)
                                high_energy = bands.get("high", 0.0) + bands.get("high_mid", 0.0)

                                app.state.effects_engine.update_audio(
                                    energy=min(1.0, float(freq.get("rms_energy", 0.0)) * 2.0),
                                    bass=min(1.0, float(bass_energy)),
                                    mid=min(1.0, float(mid_energy)),
                                    high=min(1.0, float(high_energy)),
                                    is_beat=bool(beat.get("is_beat", False)),
                                    beat_number=int(beat.get("beat_count", beat.get("beat_position", 1))),
                                    valence=float(mood.get("valence", 0.0)),
                                    arousal=float(mood.get("arousal", 0.0)),
                                    spectral_flux=min(1.0, float(freq.get("spectral_flux", 0.0)) * 10.0),
                                    bpm=float(beat.get("bpm", 128.0)),
                                    ml_data=ml_data,
                                )
                        except Exception as e:
                            print(f"Audio pipeline update error: {e}")
                    future.add_done_callback(_on_result)
            except Exception:
                _processing[0] = False

        app.state._audio_loop = asyncio.get_event_loop()
        app.state.audio_capture = SystemAudioCapture(
            sample_rate=settings.AUDIO_SAMPLE_RATE,
            chunk_size=settings.AUDIO_CHUNK_SIZE,
            channels=1,
            on_audio_chunk=on_audio_chunk,
        )

        # Delayed auto-start: waits 2s for server to bind, then starts capture
        # in an executor thread so the blocking soundcard COM init is off the event loop.
        if settings.AUDIO_CAPTURE_AUTO_START:
            async def _delayed_audio_start():
                await asyncio.sleep(2)
                loop = asyncio.get_event_loop()
                try:
                    capture = app.state.audio_capture
                    success = await loop.run_in_executor(
                        None, lambda: capture.start(loop=loop)
                    )
                    if success:
                        print(f"Audio capture started: {capture.device_name}")
                        if app.state.effects_engine:
                            app.state.effects_engine.config.auto_mode = True
                            app.state.effects_engine.enable_pro_lighting(True)
                            print("Auto mode + pro lighting ENABLED")
                    else:
                        print("Audio capture failed to auto-start - use UI/API to configure")
                except Exception as e:
                    print(f"Audio auto-start error: {e}")

            app.state._audio_start_task = asyncio.create_task(_delayed_audio_start())
            print("Audio capture will auto-start after server is ready")
        else:
            app.state._audio_start_task = None
            print("Audio capture auto-start disabled (manual device selection expected)")
    except Exception as e:
        print(f"Warning: Could not initialize audio capture: {e}")
        app.state.audio_capture = None

    print("Startup complete!")

    yield

    # Shutdown
    if hasattr(app.state, '_audio_start_task') and app.state._audio_start_task:
        app.state._audio_start_task.cancel()
    if hasattr(app.state, 'broadcast_task') and app.state.broadcast_task:
        app.state.broadcast_task.cancel()
    if hasattr(app.state, 'audio_capture') and app.state.audio_capture:
        app.state.audio_capture.stop()
    print("Shutting down Intelligent Lighting System...")
    if hasattr(app.state, 'effects_engine') and app.state.effects_engine:
        app.state.effects_engine.stop()
        # BUG-016 fix: cancel and await the effects engine task
        if hasattr(app.state, 'effects_engine_task') and app.state.effects_engine_task:
            app.state.effects_engine_task.cancel()
            try:
                await app.state.effects_engine_task
            except asyncio.CancelledError:
                pass
    if hasattr(app.state, 'dmx_controller') and app.state.dmx_controller:
        await app.state.dmx_controller.disconnect()
    if hasattr(app.state, 'audio_analyzer') and app.state.audio_analyzer:
        await app.state.audio_analyzer.stop()
    print("Shutdown complete.")


app = FastAPI(
    title="Intelligent Lighting System API",
    description="An emotionally intelligent lighting control system with real-time audio analysis",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(shows.router, prefix="/api/shows", tags=["Shows"])
app.include_router(rigs.router, prefix="/api/rigs", tags=["Rigs"])
app.include_router(fixtures.router, prefix="/api/fixtures", tags=["Fixtures"])
app.include_router(audio.router, prefix="/api/audio", tags=["Audio Analysis"])
app.include_router(dmx.router, prefix="/api/dmx", tags=["DMX Control"])
app.include_router(websocket.router, prefix="/ws", tags=["WebSocket"])
app.include_router(effects.router, prefix="/api", tags=["Effects"])
app.include_router(training.router, prefix="/api", tags=["Training"])
app.include_router(lfo.router, prefix="/api", tags=["LFO Effects"])
app.include_router(fixture_library.router, prefix="/api/fixtures/library", tags=["Fixture Library"])
app.include_router(rig_patching.router, prefix="/api/rigs", tags=["Rig Patching"])
app.include_router(fixture_test.router, prefix="/api", tags=["Fixture Test"])
app.include_router(wizard.router, prefix="/api/wizard", tags=["Setup Wizard"])
app.include_router(templates.router, prefix="/api/templates", tags=["Templates"])
app.include_router(rig_import_export.router, prefix="/api", tags=["Import/Export"])
app.include_router(discovery.router, prefix="/api", tags=["Discovery"])
app.include_router(qr_scanning.router, prefix="/api", tags=["QR Scanning"])
app.include_router(demo.router, prefix="/api", tags=["Demo & Venues"])


@app.get("/")
async def root():
    """Root endpoint returning API information."""
    return {
        "name": "Intelligent Lighting System API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint - reports actual service state."""
    from fastapi.responses import JSONResponse

    services = {
        "api": "running",
        "audio_analyzer": "running" if getattr(app.state, 'audio_analyzer', None) else "unavailable",
        "ml_models": "loaded" if getattr(app.state, 'model_manager', None) else "unavailable",
        "dmx": "connected" if (
            getattr(app.state, 'dmx_controller', None) and app.state.dmx_controller.is_connected
        ) else "disconnected",
        "effects_engine": "running" if (
            getattr(app.state, 'effects_engine', None) and app.state.effects_engine.running
        ) else "stopped",
        "lfo_engine": "ready" if getattr(app.state, 'lfo_engine', None) else "unavailable",
        "pro_lighting": "enabled" if (
            getattr(app.state, 'effects_engine', None) and
            app.state.effects_engine._pro_lighting_enabled
        ) else "disabled",
    }

    # Determine overall health
    critical_services = ["audio_analyzer", "effects_engine"]
    is_healthy = all(
        services.get(s) in ("running", "loaded", "connected", "ready")
        for s in critical_services
    )

    status_code = 200 if is_healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if is_healthy else "degraded",
            "services": services,
        }
    )
