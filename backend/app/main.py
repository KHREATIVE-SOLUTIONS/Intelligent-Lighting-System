"""
Main FastAPI Application
========================

Entry point for the Intelligent Lighting System backend.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import shows, rigs, fixtures, audio, dmx, websocket, effects, training, lfo
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    print("Starting Intelligent Lighting System...")

    try:
        # Initialize ML models
        app.state.model_manager = ModelManager()
        await app.state.model_manager.load_models()
    except Exception as e:
        print(f"Warning: Could not load ML models: {e}")
        app.state.model_manager = None

    try:
        # Initialize audio analyzer
        app.state.audio_analyzer = AudioAnalyzer(app.state.model_manager)
    except Exception as e:
        print(f"Warning: Could not initialize audio analyzer: {e}")
        app.state.audio_analyzer = None

    try:
        # Initialize DMX controller
        app.state.dmx_controller = DMXController()
        await app.state.dmx_controller.connect()
    except Exception as e:
        print(f"Warning: Could not connect DMX controller: {e}")
        app.state.dmx_controller = None

    try:
        # Initialize Effects Engine - TRAINING MODE (no auto-reactivity)
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

        # Start the effects engine async loop (BUG-016 fix: store task reference)
        import asyncio
        app.state.effects_engine_task = asyncio.create_task(app.state.effects_engine.run())
        print("Effects engine initialized (TRAINING MODE - manual control only)")
    except Exception as e:
        print(f"Warning: Could not initialize effects engine: {e}")
        import traceback
        traceback.print_exc()
        app.state.effects_engine = None

    # Initialize Training Recorder for ML data collection
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

    print("Startup complete!")

    yield

    # Shutdown
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
