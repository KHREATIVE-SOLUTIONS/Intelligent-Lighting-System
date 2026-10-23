"""
DMX Control API Endpoints
=========================

Endpoints for DMX/ArtNet control operations.
"""

import asyncio
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.dmx import (
    DMXFrame, DMXUniverse, ArtNetConfig,
    DMXFixtureState, DMXSceneState,
    DMXCueCommand, DMXBlackoutCommand,
)

router = APIRouter()


@router.get("/config", response_model=ArtNetConfig)
async def get_dmx_config(request: Request):
    """Get current DMX/ArtNet configuration."""
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    return request.app.state.dmx_controller.get_config()


@router.put("/config", response_model=ArtNetConfig)
async def update_dmx_config(
    config: ArtNetConfig,
    request: Request,
):
    """Update DMX/ArtNet configuration."""
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    await request.app.state.dmx_controller.update_config(config)
    return config


@router.get("/status")
async def get_dmx_status(request: Request):
    """Get current DMX controller status."""
    controller = getattr(request.app.state, 'dmx_controller', None)
    if controller is None:
        return {"status": "not_initialized"}

    return {
        "status": "connected" if controller.is_connected else "disconnected",
        "universes": controller.active_universes,
        "fps": controller.current_fps,
        "packets_sent": controller.packets_sent,
        **controller.get_transmit_status(),
    }


@router.get("/transmit-status")
async def get_transmit_status(request: Request):
    """Get real ArtNet output health (is anything actually leaving the socket)."""
    # main.py parks None on app.state when DMX init fails, so hasattr is not enough.
    controller = getattr(request.app.state, 'dmx_controller', None)
    if controller is None:
        return {
            "connected": False,
            "transmitting": False,
            "target_ip": None,
            "port": None,
            "broadcast": False,
            "frames_sent": 0,
            "send_error_count": 0,
            "last_send_error": "DMX controller not initialized",
            "last_send_time": None,
        }

    return controller.get_transmit_status()


@router.post("/connect")
async def connect_dmx(request: Request):
    """Connect to DMX interface."""
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    await request.app.state.dmx_controller.connect()
    return {"status": "connected"}


@router.post("/disconnect")
async def disconnect_dmx(request: Request):
    """Disconnect from DMX interface."""
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    await request.app.state.dmx_controller.disconnect()
    return {"status": "disconnected"}


@router.get("/universe/{universe}", response_model=DMXUniverse)
async def get_universe(
    universe: int,
    request: Request,
):
    """Get current state of a DMX universe."""
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    if universe < 0 or universe > 32767:
        raise HTTPException(status_code=400, detail="Universe must be 0-32767")

    return request.app.state.dmx_controller.get_universe(universe)


@router.post("/universe/{universe}")
async def set_universe(
    universe: int,
    frame: DMXFrame,
    request: Request,
):
    """Set DMX values for a universe."""
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    if universe < 0 or universe > 32767:
        raise HTTPException(status_code=400, detail="Universe must be 0-32767")

    await request.app.state.dmx_controller.set_frame(universe, frame)
    return {"status": "sent", "universe": universe}


@router.post("/channel")
async def set_channel(
    universe: int,
    channel: int,
    value: int,
    request: Request,
):
    """Set a single DMX channel value."""
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    if universe < 0 or universe > 32767:
        raise HTTPException(status_code=400, detail="Universe must be 0-32767")
    if channel < 1 or channel > 512:
        raise HTTPException(status_code=400, detail="Channel must be 1-512")
    if value < 0 or value > 255:
        raise HTTPException(status_code=400, detail="Value must be 0-255")

    await request.app.state.dmx_controller.set_channel(universe, channel, value)
    return {"status": "set", "universe": universe, "channel": channel, "value": value}


async def _fade_engine_to_blackout(engine, fade_time: float) -> None:
    """Ramp the engine's grand master to zero, latch the blackout, put the master back.

    The master is restored once the latch holds, so a later restore() returns the
    room to the level the operator had set rather than to zero.
    """
    start = engine.grand_master
    steps = int(fade_time * 30) if fade_time > 0 else 0
    try:
        for step in range(1, steps + 1):
            if engine.blackout_active:
                break
            engine.set_grand_master(start * (1 - step / steps))
            await asyncio.sleep(fade_time / steps)
    finally:
        engine.blackout()
        engine.set_grand_master(start)


@router.post("/blackout")
async def blackout(
    command: DMXBlackoutCommand,
    request: Request,
):
    """Execute a blackout on specified universes."""
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    # The effects engine rewrites every universe each frame, so a blackout made
    # only here would last one frame. A full blackout latches the engine too, and
    # the engine fades with the controller rather than holding full for the whole
    # fade and then snapping to black.
    engine = getattr(request.app.state, "effects_engine", None)
    controller_blackout = request.app.state.dmx_controller.blackout(
        universes=command.universes,
        fade_time=command.fade_time
    )
    if not command.universes and engine is not None:
        await asyncio.gather(
            controller_blackout,
            _fade_engine_to_blackout(engine, command.fade_time),
        )
    else:
        await controller_blackout
    return {"status": "blackout", "universes": command.universes or "all"}


@router.post("/restore")
async def restore_from_blackout(
    fade_time: float = 0.0,
    request: Request = None,
):
    """Restore from blackout to previous state."""
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    await request.app.state.dmx_controller.restore(fade_time=fade_time)
    engine = getattr(request.app.state, "effects_engine", None)
    if engine is not None:
        engine.restore()
    return {"status": "restored"}


@router.get("/scene", response_model=DMXSceneState)
async def get_current_scene(request: Request):
    """Get the current scene state (all fixtures)."""
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    state = request.app.state.dmx_controller.get_scene_state()
    engine = getattr(request.app.state, "effects_engine", None)
    if engine is not None:
        state.master_intensity = engine.output_master
    return state


@router.post("/cue")
async def execute_cue(
    command: DMXCueCommand,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Execute a specific cue."""
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    # Load cue from database
    from app.models.show import ShowCue
    from sqlalchemy import select

    query = select(ShowCue).where(ShowCue.id == command.cue_id)
    result = await db.execute(query)
    cue = result.scalar_one_or_none()

    if not cue:
        raise HTTPException(status_code=404, detail="Cue not found")

    await request.app.state.dmx_controller.execute_cue(
        cue=cue,
        fade_time=command.fade_time,
        delay=command.delay,
    )

    return {"status": "executing", "cue_id": command.cue_id}


@router.post("/fixture/{rig_fixture_id}")
async def set_fixture_state(
    rig_fixture_id: int,
    state: DMXFixtureState,
    request: Request,
):
    """Set the state of a specific fixture."""
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    await request.app.state.dmx_controller.set_fixture_state(rig_fixture_id, state)
    return {"status": "set", "rig_fixture_id": rig_fixture_id}


@router.post("/test/pattern")
async def run_test_pattern(
    universe: int = Query(0, ge=0, le=32767),
    pattern: str = "chase",
    request: Request = None,
):
    """Run a test pattern on a universe. BUG-035 fix: POST for state-changing operation."""
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    valid_patterns = ["chase", "rainbow", "strobe", "fade", "all_on", "all_off"]
    if pattern not in valid_patterns:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pattern. Must be one of: {', '.join(valid_patterns)}"
        )

    await request.app.state.dmx_controller.run_test_pattern(universe, pattern)
    return {"status": "running", "pattern": pattern, "universe": universe}


@router.post("/test/stop")
async def stop_test_pattern(request: Request):
    """Stop any running test pattern."""
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    await request.app.state.dmx_controller.stop_test_pattern()
    return {"status": "stopped"}


# DMX Control 3 / Previs Configuration
@router.get("/previs/setup-guide")
async def get_previs_setup_guide():
    """Get setup guide for DMX Control 3 and other previs software.

    Returns configuration instructions for connecting to popular
    DMX visualization software.
    """
    return {
        "title": "DMX Previs Setup Guide",
        "software": {
            "dmx_control_3": {
                "name": "DMX Control 3",
                "description": "Free open-source DMX control and visualization",
                "download_url": "https://www.dmxcontrol.org/",
                "setup_steps": [
                    "1. Install DMX Control 3 from dmxcontrol.org",
                    "2. Open DMX Control 3 and go to Setup > Inputs/Outputs",
                    "3. Add a new 'Art-Net Input' device",
                    "4. Configure Art-Net Input:",
                    "   - Bind Address: 0.0.0.0 (or your network IP)",
                    "   - Port: 6454 (default Art-Net port)",
                    "   - Universe: 0 (or match your backend config)",
                    "5. Enable 'Broadcast Mode' in this backend's DMX config",
                    "6. Click 'Enable' in DMX Control 3 to start receiving",
                ],
                "tips": [
                    "Both applications must be on the same network",
                    "If using multiple universes, add multiple Art-Net inputs",
                    "Use broadcast mode (255.255.255.255) for easiest setup",
                    "Disable firewall or allow UDP port 6454"
                ]
            },
            "capture": {
                "name": "Capture (by Capture Sweden)",
                "description": "Professional lighting design and previs software",
                "setup_steps": [
                    "1. Open Capture and create/load your project",
                    "2. Go to File > Edit Universes",
                    "3. Add Art-Net input for each universe",
                    "4. Set Net/Subnet/Universe to match backend config",
                    "5. Enable Art-Net reception"
                ]
            },
            "vectorworks": {
                "name": "Vectorworks Vision",
                "description": "Professional 3D visualization",
                "setup_steps": [
                    "1. Open Vision with your Vectorworks file",
                    "2. Go to Devices > Art-Net",
                    "3. Configure Art-Net input settings",
                    "4. Map universes to fixtures in Vision"
                ]
            },
            "ma3d": {
                "name": "MA 3D",
                "description": "grandMA2/grandMA3 visualizer",
                "setup_steps": [
                    "1. Launch MA 3D",
                    "2. Configure Art-Net input in Network settings",
                    "3. Patch fixtures to match backend universe/address"
                ]
            }
        },
        "quick_test": {
            "description": "Quick test to verify connection",
            "steps": [
                "1. Use /api/dmx/test/pattern endpoint with pattern='rainbow'",
                "2. You should see changing values in your previs software",
                "3. Use /api/dmx/test/stop to stop the test"
            ]
        },
        "troubleshooting": [
            "Ensure both apps are on the same network subnet",
            "Check firewall allows UDP traffic on port 6454",
            "Verify universe numbers match in both applications",
            "Try using broadcast mode if unicast doesn't work",
            "Check if any other software is using port 6454"
        ]
    }


@router.post("/previs/configure-broadcast")
async def configure_for_broadcast(
    request: Request,
    universes: Optional[List[int]] = None,
):
    """Configure Art-Net for broadcast mode (for previs software).

    This sets up the DMX controller to broadcast Art-Net packets
    on 255.255.255.255, which DMX Control 3 and other previs
    software can easily receive.
    """
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    # Create broadcast configuration
    config = ArtNetConfig(
        ip_address="255.255.255.255",  # Broadcast address
        port=6454,
        broadcast=True,
        # Keep the rig's Net/Sub-Net: zeroing them moved every universe.
        net=request.app.state.dmx_controller.config.net,
        subnet=request.app.state.dmx_controller.config.subnet,
        universes=universes or [0],
    )

    await request.app.state.dmx_controller.update_config(config)

    return {
        "status": "configured",
        "mode": "broadcast",
        "message": "Art-Net is now broadcasting. Your previs software should receive data.",
        "config": config.model_dump(),
        "next_steps": [
            "Open DMX Control 3 or your previs software",
            "Configure Art-Net Input on port 6454",
            "Use /api/dmx/test/pattern to test the connection"
        ]
    }


@router.post("/previs/configure-unicast")
async def configure_for_unicast(
    request: Request,
    target_ip: str,
    universes: Optional[List[int]] = None,
):
    """Configure Art-Net for unicast mode (direct to specific IP).

    Use this if you want to send Art-Net data to a specific computer
    running your previs software.
    """
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    # Validate IP address format
    import ipaddress
    try:
        ipaddress.ip_address(target_ip)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid IP address: {target_ip}")

    config = ArtNetConfig(
        ip_address=target_ip,
        port=6454,
        broadcast=False,
        net=request.app.state.dmx_controller.config.net,
        subnet=request.app.state.dmx_controller.config.subnet,
        universes=universes or [0],
    )

    await request.app.state.dmx_controller.update_config(config)

    return {
        "status": "configured",
        "mode": "unicast",
        "target": target_ip,
        "message": f"Art-Net is now sending to {target_ip}",
        "config": config.model_dump()
    }


@router.post("/previs/test-connection")
async def test_previs_connection(
    request: Request,
    duration: float = Query(3.0, gt=0, le=30),
):
    """Send a test pattern to verify previs connection.

    Sends a quick chase pattern for the specified duration,
    which should be visible in your previs software.
    """
    if not hasattr(request.app.state, 'dmx_controller'):
        raise HTTPException(status_code=500, detail="DMX controller not initialized")

    controller = request.app.state.dmx_controller

    # Run a quick test pattern
    async def test_sequence():
        # Flash the first few channels in sequence until the deadline. Counting
        # passes instead made a 3 second test run for 18.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration
        try:
            while loop.time() < deadline:
                for i in range(12):
                    await controller.set_channel(0, i + 1, 255)
                    await asyncio.sleep(0.05)
                    await controller.set_channel(0, i + 1, 0)
                    if loop.time() >= deadline:
                        break
        finally:
            for i in range(12):
                controller.get_universe(0).set_channel(i + 1, 0)

    # Held as the controller's test pattern so /test/stop and a blackout end it,
    # and so the task is not garbage-collected mid-run.
    await controller.stop_test_pattern()
    controller.test_pattern_task = asyncio.create_task(test_sequence())

    return {
        "status": "testing",
        "duration": duration,
        "message": f"Running test pattern for {duration} seconds. Check your previs software!"
    }


@router.get("/previs/status")
async def get_previs_status(request: Request):
    """Get current Art-Net configuration and status for previs."""
    controller = getattr(request.app.state, 'dmx_controller', None)
    if controller is None:
        return {
            "status": "not_initialized",
            "ready_for_previs": False
        }

    config = controller.get_config()
    transmit = controller.get_transmit_status()

    return {
        "status": "connected" if controller.is_connected else "disconnected",
        "ready_for_previs": transmit["transmitting"],
        "mode": "broadcast" if transmit["broadcast"] else "unicast",
        "target": transmit["target_ip"],
        "port": transmit["port"],
        "universes": config.universes,
        "current_fps": controller.current_fps,
        "packets_sent": controller.packets_sent,
        "transmitting": transmit["transmitting"],
        "send_error_count": transmit["send_error_count"],
        "last_send_error": transmit["last_send_error"],
        "recommendations": [
            "Use broadcast mode for easiest previs setup",
            f"Current target: {'Broadcast (all devices)' if transmit['broadcast'] else transmit['target_ip']}",
        ]
    }
