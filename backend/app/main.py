"""
Main FastAPI Application
========================

Entry point for the Intelligent Lighting System backend.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import get_route_path

from app.api.endpoints import (
    shows, rigs, fixtures, audio, dmx, websocket, effects, training, lfo,
    fixture_library, rig_patching, fixture_test, wizard, templates,
    rig_import_export, discovery, qr_scanning, demo, auth, rig_identify,
)
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.core.security import refresh_token, should_refresh, verify_token
from app.db.database import engine, Base
from app.db.startup import init_database
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
from app.schemas.audio import engine_energy, programme_level

logger = logging.getLogger(__name__)

# Venue preset the show falls back to when no rig has been patched yet.
DEMO_VENUE_PRESET = "pro_beam_room"


async def _load_active_rig_manager():
    """Build a fixture manager from the rig the user patched.

    Returns (manager, rig), both None when the database holds no usable rig.
    """
    from app.db.database import AsyncSessionLocal
    from app.services.rig.rig_loader import get_rig_diagnostics, load_active_rig

    async with AsyncSessionLocal() as db:
        manager, rig = await load_active_rig(db)

    diagnostics = get_rig_diagnostics(manager)
    if diagnostics is not None:
        logger.info("Rig load: %s", diagnostics.summary())
        for entry in diagnostics.skipped:
            logger.warning("Rig load skipped a fixture: %s", entry)
        for entry in diagnostics.truncated:
            logger.warning("Rig load: fixture runs past the end of its universe: %s", entry)
        for entry in diagnostics.group_conflicts:
            logger.warning("Rig load: %s", entry)
        for message in diagnostics.errors:
            logger.warning("Rig load: %s", message)

    return manager, rig


def _install_fixture_manager(app: FastAPI, manager, *, demo: bool = False):
    """Point the running show at a fixture manager.

    A demo rig is rendered (the visualizer and previews still work) but held
    off the wire unless DEMO_RIG_DMX_OUTPUT says otherwise; a patched rig
    releases the hold.
    """
    app.state.dmx_output_held = demo and not settings.DEMO_RIG_DMX_OUTPUT
    engine = getattr(app.state, 'effects_engine', None)
    if engine is not None:
        setter = getattr(engine, 'set_fixture_manager', None)
        if callable(setter):
            setter(manager)
        else:
            engine.fixtures = manager
    app.state.fixture_manager = manager


def _send_engine_frame(app: FastAPI, universe: int, frame: list):
    """Hand one rendered universe to the DMX controller, unless output is held."""
    if getattr(app.state, "dmx_output_held", False):
        return
    controller = getattr(app.state, "dmx_controller", None)
    if controller:
        # Directly update universe data (frame is a 512-element list)
        if universe not in controller.universes:
            from app.schemas.dmx import DMXUniverse
            controller.universes[universe] = DMXUniverse(universe=universe)
        controller.universes[universe].data = frame


def _install_demo_rig(app: FastAPI):
    """Install the bundled demo venue so a fresh install still produces a show."""
    from app.services.demo.venue_presets import create_venue_rig
    from app.services.lighting.key_lighting import PerformerZone, KeyLightConfig

    manager, preset = create_venue_rig(DEMO_VENUE_PRESET)
    if not manager:
        logger.error("Demo venue preset '%s' is unavailable - no rig installed", DEMO_VENUE_PRESET)
        print(f"Warning: no rig installed (demo preset '{DEMO_VENUE_PRESET}' unavailable)")
        return

    _install_fixture_manager(app, manager, demo=True)
    # Read by /api/effects/status so the dashboard can say the demo is running.
    app.state.live_rig = {"id": None, "name": DEMO_VENUE_PRESET, "demo": True, "fixtures": len(preset.fixtures)}
    for zone_spec in preset.key_zones:
        try:
            zone = PerformerZone(zone_spec.zone)
            app.state.effects_engine.key_lighting.configure_zone(
                zone,
                KeyLightConfig(zone=zone, min_intensity=zone_spec.min_intensity, active=zone_spec.active)
            )
            app.state.effects_engine.key_lighting.assign_fixtures(zone, zone_spec.fixture_ids)
        except (ValueError, Exception):
            pass

    logger.warning(
        "No rig loaded from the database - running demo rig '%s' (%d fixtures)",
        DEMO_VENUE_PRESET, len(preset.fixtures),
    )
    print(
        f"Running DEMO rig '{DEMO_VENUE_PRESET}' ({len(preset.fixtures)} fixtures) - "
        "no rig configured in the database"
    )
    if app.state.dmx_output_held:
        print(
            "DMX output held until a rig is patched and activated "
            "(set DEMO_RIG_DMX_OUTPUT=true to send the demo to the network)"
        )


async def _boot_rig(app: FastAPI):
    """Drive the show from the rig the user patched, or the demo venue if there is none."""
    from app.api.endpoints.websocket import fixture_universes

    app.state.fixture_manager = getattr(app.state.effects_engine, 'fixtures', None)

    manager = None
    rig = None
    try:
        manager, rig = await _load_active_rig_manager()
    except ImportError as e:
        logger.warning("Rig loader unavailable (%s) - falling back to the demo rig", e)
    except Exception as e:
        logger.error("Could not load the active rig: %s", e, exc_info=True)
        print(f"Warning: could not load the active rig: {e}")

    if manager is None or not manager.fixtures:
        _install_demo_rig(app)
        return

    _install_fixture_manager(app, manager)
    universes = fixture_universes(manager)
    rig_name = getattr(rig, 'name', None) or 'active rig'
    app.state.live_rig = {
        "id": getattr(rig, 'id', None), "name": rig_name, "demo": False, "fixtures": len(manager.fixtures),
    }
    logger.info(
        "Rig '%s' installed: %d fixtures across universes %s",
        rig_name, len(manager.fixtures), universes,
    )
    print(
        f"Rig '{rig_name}' loaded from database: "
        f"{len(manager.fixtures)} fixtures, universes {universes}"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    configure_logging()
    print("Starting Intelligent Lighting System...")

    try:
        # Schema + fixture library must be ready before anything touches the DB
        print(" Initializing database...")
        app.state.database_ready = False
        db_summary = await init_database()
        app.state.database_ready = True
        logger.info("Database initialized: %s", db_summary)
        print(
            f" Database ready (schema={db_summary['schema']}, "
            f"fixtures={db_summary['fixtures_total']}, "
            f"seeded={db_summary['fixtures_seeded']})"
        )
        for error in db_summary["errors"]:
            print(f"Warning: database init: {error}")
    except Exception as e:
        logger.error("Database initialization failed: %s", e, exc_info=True)
        print(f"Warning: Database initialization failed: {e}")

    try:
        # Contract §4: the setup code belongs on the console the installer is
        # already watching, and a pending local reset has to take effect on the
        # boot that follows it - neither can wait for someone to make a request.
        from app.db.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await auth.prepare_first_run(db)
    except Exception as e:
        logger.error("First-run check failed: %s", e, exc_info=True)
        print(f"Warning: could not check first-run state: {e}")

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

    app.state.fixture_manager = None
    try:
        # Initialize Effects Engine - AI busker mode (autonomous show control)
        print(" Creating effects engine...")
        app.state.effects_engine = EffectsEngine(EffectsConfig(
            fps=60.0,
            auto_mode=True,
            movement_enabled=True,
            dimmer_enabled=True,
            # Accents on, conservative. A drop that reads needs a discrete
            # event, but a venue crowd includes people with photosensitive
            # epilepsy, so the flash rate is held at the three-per-second
            # general-audience limit and the accent governor spends the
            # genre budget. Switching accessibility_mode back to "no_strobe"
            # remains a complete off switch.
            strobe_enabled=True,
            accessibility_mode="conservative",
            strobe_hz_cap=3.0,
            strobe_max_duty_cycle=0.34,
            strobe_burst_max_s=0.10,
            strobe_refractory_s=0.30,
        ))

        # Connect effects engine to DMX controller
        if app.state.dmx_controller:
            def dmx_callback(universe: int, frame: list):
                _send_engine_frame(app, universe, frame)

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
                min_intensity=0.0,
                color_temp="genre",
                active=True,
            )
        )

        # Keep pro lighting enabled by default so section/chase logic is always active.
        app.state.effects_engine.enable_pro_lighting(True)

        # One owner for every accent: budget, Hz cap and anticipation.
        from app.services.lighting.pro_effects import attach_accent_governor
        app.state.accent_governor = attach_accent_governor(app.state.effects_engine)
        print("Professional lighting modules initialized and enabled")

        # Wire effects engine to demo module
        from app.api.endpoints.demo import set_demo_effects_engine
        set_demo_effects_engine(app.state.effects_engine)

        # The show drives the rig the user patched; the demo venue is only a
        # fresh-install fallback and never overwrites a configured rig.
        await _boot_rig(app)

        # Start the effects engine async loop (BUG-016 fix: store task reference)
        app.state.effects_engine_task = asyncio.create_task(app.state.effects_engine.run())

        # Start a WebSocket broadcast task that pushes DMX state to all connected clients at ~30fps
        # This is needed because server-side audio capture bypasses the WebSocket input path
        async def _broadcast_lighting_state():
            from app.api.endpoints.websocket import (
                manager, convert_numpy_types, collect_dmx_frames,
                primary_dmx_universe, serialize_dmx_frames,
            )
            from app.services.lighting.look_spec import build_lighting_look_spec
            from datetime import datetime
            frame_count = 0
            while True:
                try:
                    await asyncio.sleep(1.0 / 30.0)  # ~30fps
                    ee = app.state.effects_engine
                    if ee is None:
                        continue

                    # Build a DMX frame per universe the rig occupies
                    dmx_frames = collect_dmx_frames(ee.fixtures)
                    primary_universe = primary_dmx_universe(dmx_frames)
                    dmx_frame = dmx_frames.get(primary_universe, [0] * 512)
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
                        'dmx_universe': primary_universe,
                        'dmx_frames': serialize_dmx_frames(dmx_frames),
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
                        "data": {
                            "universe": primary_universe,
                            "frame": dmx_frame,
                            "frames": serialize_dmx_frames(dmx_frames),
                        },
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
        fixture_manager = getattr(app.state, 'fixture_manager', None)
        app.state.lfo_engine.set_fixture_count(
            len(fixture_manager.fixtures) if fixture_manager else 8
        )
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
                                    energy=engine_energy(freq.get("rms_energy", 0.0)),
                                    programme_level=programme_level(
                                        freq.get("normalized_energy")
                                    ),
                                    bass=min(1.0, float(bass_energy)),
                                    mid=min(1.0, float(mid_energy)),
                                    high=min(1.0, float(high_energy)),
                                    is_beat=bool(beat.get("is_beat", False)),
                                    beat_number=int(beat.get("beat_count", beat.get("beat_position", 1))),
                                    valence=float(mood.get("valence", 0.0)),
                                    arousal=float(mood.get("arousal", 0.0)),
                                    spectral_flux=min(1.0, float(freq.get("spectral_flux", 0.0)) * 10.0),
                                    bpm=float(beat.get("bpm", 128.0)),
                                    tempo_confidence=beat.get("tempo_confidence"),
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

    if not settings.AUTH_ENABLED:
        logging.getLogger(__name__).warning(
            "AUTH_ENABLED=false: every API route and websocket is open. Anyone on "
            "this network can drive the lights. Development use only."
        )
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

# The three requests an operator has to make before they hold a token. Everything
# else under /api needs one. /health, the OpenAPI docs and any static mount live
# outside /api and are never gated.
PUBLIC_API_ROUTES = frozenset({
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/setup"),
    ("GET", "/api/auth/status"),
})

# Carries a reissued token back to the operator's browser on an active session.
OPERATOR_TOKEN_HEADER = "X-Operator-Token"


def route_requires_auth(method: str, path: str) -> bool:
    """Single source of truth for what the operator token protects."""
    # Dev escape hatch: AUTH_ENABLED=false bypasses the gate for every route.
    if not settings.AUTH_ENABLED:
        return False
    path = path.rstrip("/") or "/"
    if path != "/api" and not path.startswith("/api/"):
        return False
    return (method.upper(), path) not in PUBLIC_API_ROUTES


def request_token(request: Request) -> str:
    """Pull the operator token out of an Authorization: Bearer header."""
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def request_claims(request: Request):
    """Claims of the request's token, or None when it has no usable one."""
    token = request_token(request)
    if not token:
        return None
    try:
        return verify_token(token)
    except Exception:
        # Anything that stops validation is a rejection, never a 500.
        return None


def request_is_authenticated(request: Request) -> bool:
    """True when the request carries a token the box currently accepts."""
    return request_claims(request) is not None


@app.middleware("http")
async def enforce_operator_auth(request: Request, call_next):
    """Gate every /api route centrally so no endpoint can be forgotten."""
    # get_route_path is what the router itself dispatches on. request.url.path
    # still carries root_path, so behind `--root-path=/lights` the gate and the
    # router would disagree about every path and nothing would be protected.
    path = get_route_path(request.scope)
    if request.method == "OPTIONS" or not route_requires_auth(request.method, path):
        return await call_next(request)

    claims = request_claims(request)
    if claims is None:
        return JSONResponse(
            status_code=401,
            content={"detail": "Operator authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    response = await call_next(request)
    # Sliding session: an operator who is working never reaches the expiry.
    if should_refresh(claims):
        reissued = refresh_token(request_token(request))
        if reissued:
            response.headers[OPERATOR_TOKEN_HEADER] = reissued
    return response


# CORS middleware. Registered after the auth middleware so it wraps it: a 401
# still carries CORS headers, and a preflight OPTIONS never needs a token.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[OPERATOR_TOKEN_HEADER],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
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
app.include_router(rig_identify.router, prefix="/api", tags=["Flash to Identify"])
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


def _audio_input_state() -> str:
    """'live', 'lost' (it was arriving and stopped) or 'waiting' (never arrived)."""
    engine = getattr(app.state, 'effects_engine', None)
    age = getattr(engine, 'audio_age', None) if engine is not None else None
    if age is None:
        return "waiting"
    return "live" if age < engine.AUDIO_STALE_S else "lost"


def _dmx_health():
    """Report DMX state from actual transmit results, not just socket state."""
    controller = getattr(app.state, 'dmx_controller', None)
    if controller is None:
        return "disconnected", {"connected": False, "transmitting": False}

    status_fn = getattr(controller, 'get_transmit_status', None)
    if not callable(status_fn):
        connected = bool(getattr(controller, 'is_connected', False))
        return (
            "connected" if connected else "disconnected",
            {"connected": connected, "transmitting": None, "detail_available": False},
        )

    try:
        detail = dict(status_fn())
    except Exception as e:
        return "unknown", {"error": str(e)}
    detail["output_held_until_rig_patched"] = bool(getattr(app.state, "dmx_output_held", False))

    if not detail.get("connected"):
        state = "disconnected"
    elif detail.get("transmitting"):
        state = "transmitting"
    elif detail.get("last_send_error"):
        state = f"error: {detail['last_send_error']}"
    else:
        state = "connected"
    return state, detail


@app.get("/health")
async def health_check(request: Request):
    """Health check endpoint - reports actual service state.

    Stays open so a watchdog or installer can see the box is alive. An
    unauthenticated caller gets liveness and nothing else: the subsystem map and
    dmx_detail carry ArtNet targets and rig state.
    """
    dmx_state, dmx_detail = _dmx_health()

    services = {
        "api": "running",
        # Without a database the venue cannot patch or load its rig, so a box
        # that booted without one is not healthy even though the demo show runs.
        "database": "connected" if getattr(app.state, 'database_ready', False) else "unavailable",
        "audio_analyzer": "running" if getattr(app.state, 'audio_analyzer', None) else "unavailable",
        "ml_models": "loaded" if getattr(app.state, 'model_manager', None) else "unavailable",
        "dmx": dmx_state,
        "effects_engine": "running" if (
            getattr(app.state, 'effects_engine', None) and app.state.effects_engine.running
        ) else "stopped",
        "lfo_engine": "ready" if getattr(app.state, 'lfo_engine', None) else "unavailable",
        "audio_input": _audio_input_state(),
        "pro_lighting": "enabled" if (
            getattr(app.state, 'effects_engine', None) and
            app.state.effects_engine._pro_lighting_enabled
        ) else "disabled",
    }

    # Determine overall health
    critical_services = ["database", "audio_analyzer", "effects_engine"]
    is_healthy = all(
        services.get(s) in ("running", "loaded", "connected", "ready")
        for s in critical_services
    )

    status_code = 200 if is_healthy else 503
    content = {"status": "healthy" if is_healthy else "degraded"}
    if request_is_authenticated(request):
        content["services"] = services
        content["dmx_detail"] = dmx_detail
    return JSONResponse(status_code=status_code, content=content)


# The same report under /api, for the operator's screen: nginx and the dev
# server only forward /api and /ws to the backend (nginx answers /health
# itself), so the browser cannot reach /health. Under /api it needs the token.
app.add_api_route("/api/health", health_check, methods=["GET"], include_in_schema=False)
