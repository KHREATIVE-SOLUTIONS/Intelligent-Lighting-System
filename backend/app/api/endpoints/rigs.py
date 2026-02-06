"""
Rigs API Endpoints
==================

CRUD operations for lighting rigs.
"""

import io
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Body, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
import numpy as np

from app.db.database import get_db
from app.models.rig import Rig, RigFixture
from app.models.fixture import Fixture, FixtureType
from app.schemas.rig import (
    RigCreate, RigUpdate, RigResponse, RigListResponse,
    RigFixtureCreate, RigFixtureUpdate, RigFixtureResponse,
)
from app.services.rig.rig_detector import RigDetector, DemoRigGenerator, PatternGenerator

router = APIRouter()


# Rig CRUD
@router.get("/", response_model=RigListResponse)
async def list_rigs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    active_only: bool = False,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all rigs with pagination."""
    query = select(Rig).options(
        selectinload(Rig.fixtures).selectinload(RigFixture.fixture)
    )

    if active_only:
        query = query.where(Rig.is_active == True)
    if search:
        query = query.where(Rig.name.ilike(f"%{search}%"))

    # Count total
    count_query = select(func.count()).select_from(Rig)
    if active_only:
        count_query = count_query.where(Rig.is_active == True)
    if search:
        count_query = count_query.where(Rig.name.ilike(f"%{search}%"))

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    query = query.offset((page - 1) * size).limit(size).order_by(Rig.updated_at.desc())
    result = await db.execute(query)
    rigs = result.scalars().all()

    return RigListResponse(
        items=rigs,
        total=total,
        page=page,
        size=size,
        pages=(total + size - 1) // size,
    )


@router.post("/", response_model=RigResponse, status_code=201)
async def create_rig(
    rig_data: RigCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new rig."""
    rig_dict = rig_data.model_dump()
    # Convert UniverseConfig objects to dicts
    if 'universes' in rig_dict:
        rig_dict['universes'] = [u.model_dump() if hasattr(u, 'model_dump') else u for u in rig_dict['universes']]

    rig = Rig(**rig_dict)
    db.add(rig)
    await db.flush()
    await db.refresh(rig)
    return rig


@router.get("/{rig_id}", response_model=RigResponse)
async def get_rig(
    rig_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific rig by ID."""
    query = select(Rig).where(Rig.id == rig_id).options(
        selectinload(Rig.fixtures).selectinload(RigFixture.fixture)
    )
    result = await db.execute(query)
    rig = result.scalar_one_or_none()

    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")

    return rig


@router.put("/{rig_id}", response_model=RigResponse)
async def update_rig(
    rig_id: int,
    rig_data: RigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a rig."""
    query = select(Rig).where(Rig.id == rig_id)
    result = await db.execute(query)
    rig = result.scalar_one_or_none()

    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")

    update_data = rig_data.model_dump(exclude_unset=True)
    # Convert UniverseConfig objects to dicts
    if 'universes' in update_data:
        update_data['universes'] = [u.model_dump() if hasattr(u, 'model_dump') else u for u in update_data['universes']]

    for field, value in update_data.items():
        setattr(rig, field, value)

    await db.flush()
    await db.refresh(rig)
    return rig


@router.delete("/{rig_id}", status_code=204)
async def delete_rig(
    rig_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a rig."""
    query = select(Rig).where(Rig.id == rig_id)
    result = await db.execute(query)
    rig = result.scalar_one_or_none()

    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")

    await db.delete(rig)


@router.post("/{rig_id}/activate", response_model=RigResponse)
async def activate_rig(
    rig_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Set a rig as the active rig (deactivates others)."""
    # Deactivate all rigs
    all_rigs_query = select(Rig)
    all_rigs_result = await db.execute(all_rigs_query)
    for rig in all_rigs_result.scalars():
        rig.is_active = False

    # Activate the selected rig
    query = select(Rig).where(Rig.id == rig_id)
    result = await db.execute(query)
    rig = result.scalar_one_or_none()

    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")

    rig.is_active = True
    await db.flush()
    await db.refresh(rig)
    return rig


# Rig Fixture CRUD
@router.get("/{rig_id}/fixtures", response_model=List[RigFixtureResponse])
async def list_rig_fixtures(
    rig_id: int,
    universe: Optional[int] = None,
    group: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all fixtures in a rig."""
    query = select(RigFixture).where(RigFixture.rig_id == rig_id).options(
        selectinload(RigFixture.fixture)
    )

    if universe is not None:
        query = query.where(RigFixture.universe == universe)
    if group:
        query = query.where(RigFixture.group_name == group)

    query = query.order_by(RigFixture.universe, RigFixture.dmx_address)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{rig_id}/fixtures", response_model=RigFixtureResponse, status_code=201)
async def add_fixture_to_rig(
    rig_id: int,
    fixture_data: RigFixtureCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a fixture to a rig."""
    # Verify rig exists
    rig_query = select(Rig).where(Rig.id == rig_id)
    rig_result = await db.execute(rig_query)
    if not rig_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Rig not found")

    # Check for address conflict
    conflict_query = select(RigFixture).where(
        RigFixture.rig_id == rig_id,
        RigFixture.universe == fixture_data.universe,
        RigFixture.dmx_address == fixture_data.dmx_address
    )
    conflict_result = await db.execute(conflict_query)
    if conflict_result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"DMX address {fixture_data.dmx_address} already in use on universe {fixture_data.universe}"
        )

    rig_fixture = RigFixture(rig_id=rig_id, **fixture_data.model_dump())
    db.add(rig_fixture)
    await db.flush()
    await db.refresh(rig_fixture)
    return rig_fixture


@router.put("/{rig_id}/fixtures/{fixture_id}", response_model=RigFixtureResponse)
async def update_rig_fixture(
    rig_id: int,
    fixture_id: int,
    fixture_data: RigFixtureUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a fixture in a rig."""
    query = select(RigFixture).where(
        RigFixture.id == fixture_id,
        RigFixture.rig_id == rig_id
    ).options(selectinload(RigFixture.fixture))
    result = await db.execute(query)
    rig_fixture = result.scalar_one_or_none()

    if not rig_fixture:
        raise HTTPException(status_code=404, detail="Rig fixture not found")

    update_data = fixture_data.model_dump(exclude_unset=True)

    # Check for address conflict if address is being changed
    if 'dmx_address' in update_data or 'universe' in update_data:
        new_universe = update_data.get('universe', rig_fixture.universe)
        new_address = update_data.get('dmx_address', rig_fixture.dmx_address)

        conflict_query = select(RigFixture).where(
            RigFixture.rig_id == rig_id,
            RigFixture.universe == new_universe,
            RigFixture.dmx_address == new_address,
            RigFixture.id != fixture_id
        )
        conflict_result = await db.execute(conflict_query)
        if conflict_result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"DMX address {new_address} already in use on universe {new_universe}"
            )

    for field, value in update_data.items():
        setattr(rig_fixture, field, value)

    await db.flush()
    await db.refresh(rig_fixture)
    return rig_fixture


@router.delete("/{rig_id}/fixtures/{fixture_id}", status_code=204)
async def remove_fixture_from_rig(
    rig_id: int,
    fixture_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Remove a fixture from a rig."""
    query = select(RigFixture).where(
        RigFixture.id == fixture_id,
        RigFixture.rig_id == rig_id
    )
    result = await db.execute(query)
    rig_fixture = result.scalar_one_or_none()

    if not rig_fixture:
        raise HTTPException(status_code=404, detail="Rig fixture not found")

    await db.delete(rig_fixture)


@router.get("/{rig_id}/groups", response_model=List[str])
async def list_fixture_groups(
    rig_id: int,
    db: AsyncSession = Depends(get_db),
):
    """List all unique fixture groups in a rig."""
    query = select(RigFixture.group_name).where(
        RigFixture.rig_id == rig_id,
        RigFixture.group_name.isnot(None)
    ).distinct()
    result = await db.execute(query)
    groups = [row[0] for row in result.all() if row[0]]
    return groups


# Demo Rig Generation
@router.post("/demo/create", status_code=201)
async def create_demo_rig(
    num_movers_per_side: int = Query(4, ge=1, le=10, description="Number of moving heads per side"),
    num_washes_per_side: int = Query(3, ge=1, le=10, description="Number of wash lights per side"),
    num_bars_per_side: int = Query(2, ge=1, le=10, description="Number of LED/tetra bars per side"),
    stage_width: float = Query(12.0, gt=0, description="Stage width in meters"),
    stage_depth: float = Query(10.0, gt=0, description="Stage depth in meters"),
    stage_height: float = Query(8.0, gt=0, description="Stage height in meters"),
    db: AsyncSession = Depends(get_db),
):
    """Create a demo symmetric rig with movers, washes, and tetra bars.

    This creates a complete rig configuration with fixtures positioned
    symmetrically on each side of the stage, suitable for testing and previs.
    """
    # Generate demo rig configuration
    demo_config = DemoRigGenerator.create_symmetric_rig(
        num_movers_per_side=num_movers_per_side,
        num_washes_per_side=num_washes_per_side,
        num_bars_per_side=num_bars_per_side,
        stage_width=stage_width,
        stage_depth=stage_depth,
        stage_height=stage_height,
    )

    # First, ensure we have fixture types in the database
    fixture_type_map = {}
    for fixture_type in ['moving_head', 'wash', 'led_bar']:
        # Check if fixture type exists
        query = select(Fixture).where(Fixture.fixture_type == fixture_type).limit(1)
        result = await db.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            fixture_type_map[fixture_type] = existing.id
        else:
            # Create a generic fixture for this type
            new_fixture = Fixture(
                manufacturer="Generic",
                model=f"Demo {fixture_type.replace('_', ' ').title()}",
                fixture_type=FixtureType(fixture_type),
                has_rgb=True,
                pan_range=540.0 if fixture_type == 'moving_head' else 0,
                tilt_range=270.0 if fixture_type in ['moving_head', 'wash'] else 0,
            )
            db.add(new_fixture)
            await db.flush()
            fixture_type_map[fixture_type] = new_fixture.id

    # Create the rig
    rig = Rig(
        name=demo_config['name'],
        description=demo_config['description'],
        venue=demo_config['venue'],
        stage_width=demo_config['stage_width'],
        stage_depth=demo_config['stage_depth'],
        stage_height=demo_config['stage_height'],
        universes=demo_config['universes'],
        is_active=True,
    )
    db.add(rig)
    await db.flush()

    # Add fixtures to the rig
    for fixture_config in demo_config['fixtures']:
        rig_fixture = RigFixture(
            rig_id=rig.id,
            fixture_id=fixture_type_map.get(fixture_config['fixture_type'], 1),
            name=fixture_config['name'],
            universe=fixture_config['universe'],
            dmx_address=fixture_config['dmx_address'],
            position_x=fixture_config['position']['x'],
            position_y=fixture_config['position']['y'],
            position_z=fixture_config['position']['z'],
            rotation_x=fixture_config.get('rotation', {}).get('x', 0),
            rotation_y=fixture_config.get('rotation', {}).get('y', 0),
            rotation_z=fixture_config.get('rotation', {}).get('z', 0),
            group_name=fixture_config['group_name'],
            tags=fixture_config.get('tags', []),
            is_active=True,
        )
        db.add(rig_fixture)

    await db.flush()

    # Reload with all relationships for proper response serialization
    query = select(Rig).where(Rig.id == rig.id).options(
        selectinload(Rig.fixtures).selectinload(RigFixture.fixture)
    )
    result = await db.execute(query)
    rig = result.scalar_one()

    # Manually serialize to avoid pydantic validation issues
    return {
        "id": rig.id,
        "name": rig.name,
        "description": rig.description,
        "venue": rig.venue,
        "stage_width": rig.stage_width,
        "stage_depth": rig.stage_depth,
        "stage_height": rig.stage_height,
        "universes": rig.universes or [],
        "created_at": rig.created_at.isoformat() if rig.created_at else None,
        "updated_at": rig.updated_at.isoformat() if rig.updated_at else None,
        "created_by": rig.created_by,
        "is_active": rig.is_active,
        "fixtures": [
            {
                "id": rf.id,
                "rig_id": rf.rig_id,
                "fixture_id": rf.fixture_id,
                "name": rf.name,
                "fixture_number": rf.fixture_number,
                "universe": rf.universe,
                "dmx_address": rf.dmx_address,
                "mode_id": rf.mode_id,
                "position_x": rf.position_x,
                "position_y": rf.position_y,
                "position_z": rf.position_z,
                "rotation_x": rf.rotation_x,
                "rotation_y": rf.rotation_y,
                "rotation_z": rf.rotation_z,
                "group_name": rf.group_name,
                "tags": rf.tags or [],
                "is_active": rf.is_active,
                "is_inverted": rf.is_inverted,
                "fixture": {
                    "manufacturer": rf.fixture.manufacturer,
                    "model": rf.fixture.model,
                    "fixture_type": rf.fixture.fixture_type.value if rf.fixture.fixture_type else None,
                } if rf.fixture else None
            }
            for rf in rig.fixtures
        ],
        "total_fixtures": len(rig.fixtures),
        "total_dmx_channels": demo_config['total_dmx_channels'],
    }


# Photo Upload for Auto-Detection
@router.post("/detect-from-image")
async def detect_fixtures_from_image(
    request: Request,
    image: UploadFile = File(..., description="Image of the lighting rig"),
    confidence_threshold: float = Query(0.3, ge=0.1, le=1.0),
    stage_width: float = Query(10.0, gt=0),
    stage_depth: float = Query(8.0, gt=0),
    stage_height: float = Query(6.0, gt=0),
):
    """Detect fixtures in an uploaded rig image using YOLOv9.

    Upload a photo of your lighting rig and the system will:
    1. Detect fixtures using YOLOv9 object detection
    2. Determine fixture positions from the image
    3. Generate a layout configuration with DMX addresses

    Returns a layout that can be used to create a new rig.
    """
    # Check file type
    if not image.content_type.startswith('image/'):
        raise HTTPException(
            status_code=400,
            detail="File must be an image (JPEG, PNG, etc.)"
        )

    try:
        # Read image data
        contents = await image.read()

        # Convert to numpy array
        import cv2
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            raise HTTPException(status_code=400, detail="Could not decode image")

        # Get model manager from app state
        if not hasattr(request.app.state, 'model_manager') or request.app.state.model_manager is None:
            raise HTTPException(
                status_code=503,
                detail="ML model manager not initialized. Please run install_models.py"
            )

        # Create detector
        detector = RigDetector(request.app.state.model_manager)

        # Detect fixtures
        detections = await detector.detect_fixtures_in_image(
            img,
            confidence_threshold=confidence_threshold
        )

        # Create layout from detections
        layout = detector.create_layout_from_detections(
            detections,
            stage_width=stage_width,
            stage_depth=stage_depth,
            stage_height=stage_height,
            auto_group=True
        )

        return JSONResponse(content={
            "success": True,
            "detections_count": len(detections),
            "layout": layout,
            "message": f"Detected {len(detections)} fixtures in the image"
        })

    except ImportError as e:
        # YOLOv9 not available - return error with instructions
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "Object detection model not available",
                "message": "YOLOv9 model is not loaded. Please run install_models.py first.",
                "details": str(e)
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing image: {str(e)}")


@router.post("/create-from-layout", response_model=RigResponse, status_code=201)
async def create_rig_from_layout(
    layout: Dict[str, Any] = Body(..., description="Layout from detect-from-image"),
    name: str = Body("Auto-Generated Rig", description="Name for the new rig"),
    db: AsyncSession = Depends(get_db),
):
    """Create a rig from an auto-detected layout.

    Use the layout returned from /detect-from-image to create a new rig.
    """
    # First, ensure we have fixture types in the database
    fixture_type_map = {}

    for fixture_config in layout.get('fixtures', []):
        fixture_type = fixture_config.get('fixture_type', 'other')

        if fixture_type not in fixture_type_map:
            # Check if fixture type exists
            query = select(Fixture).where(Fixture.fixture_type == fixture_type).limit(1)
            result = await db.execute(query)
            existing = result.scalar_one_or_none()

            if existing:
                fixture_type_map[fixture_type] = existing.id
            else:
                # Create generic fixture
                try:
                    ft = FixtureType(fixture_type)
                except ValueError:
                    ft = FixtureType.OTHER

                new_fixture = Fixture(
                    manufacturer="Auto-Detected",
                    model=f"{fixture_type.replace('_', ' ').title()}",
                    fixture_type=ft,
                    has_rgb=True,
                )
                db.add(new_fixture)
                await db.flush()
                fixture_type_map[fixture_type] = new_fixture.id

    # Create the rig
    stage_dims = layout.get('stage_dimensions', {})
    rig = Rig(
        name=name,
        description=f"Auto-generated from image with {layout.get('total_count', 0)} fixtures",
        stage_width=stage_dims.get('width', 10.0),
        stage_depth=stage_dims.get('depth', 8.0),
        stage_height=stage_dims.get('height', 6.0),
        universes=[{'universe': 0, 'protocol': 'artnet', 'port': 6454}],
        is_active=True,
    )
    db.add(rig)
    await db.flush()

    # Add fixtures
    for fixture_config in layout.get('fixtures', []):
        fixture_type = fixture_config.get('fixture_type', 'other')
        position = fixture_config.get('position', {})

        rig_fixture = RigFixture(
            rig_id=rig.id,
            fixture_id=fixture_type_map.get(fixture_type, 1),
            name=fixture_config.get('name', 'Fixture'),
            universe=fixture_config.get('universe', 0),
            dmx_address=fixture_config.get('dmx_address', 1),
            position_x=position.get('x', 0),
            position_y=position.get('y', 0),
            position_z=position.get('z', 0),
            group_name=fixture_config.get('group_name'),
            is_active=True,
        )
        db.add(rig_fixture)

    await db.flush()
    await db.refresh(rig, attribute_names=['fixtures'])

    return rig


# Pattern Generation
@router.post("/{rig_id}/patterns/{pattern_type}")
async def generate_pattern(
    rig_id: int,
    pattern_type: str,
    intensity: int = Query(255, ge=0, le=255),
    color_r: int = Query(255, ge=0, le=255),
    color_g: int = Query(255, ge=0, le=255),
    color_b: int = Query(255, ge=0, le=255),
    position: float = Query(0.5, ge=0, le=1, description="For sweep patterns"),
    width: float = Query(0.2, ge=0.1, le=1, description="For sweep patterns"),
    side: str = Query("left", description="For side patterns: left or right"),
    db: AsyncSession = Depends(get_db),
):
    """Generate DMX values for a pattern on the rig.

    Available patterns:
    - **x_pattern**: X-shaped lighting across the stage
    - **centered**: Brighter in center, fading to edges
    - **left_side** / **right_side**: One side only
    - **alternating**: Odd/even fixtures alternate
    - **sweep_horizontal**: Horizontal sweep/wipe effect
    - **sweep_vertical**: Vertical sweep/wipe effect
    - **all_on**: All fixtures at full intensity
    - **blackout**: All fixtures off

    Returns DMX channel values that can be sent to the DMX controller.
    """
    # Get rig with fixtures and their fixture definitions
    query = select(Rig).where(Rig.id == rig_id).options(
        selectinload(Rig.fixtures).selectinload(RigFixture.fixture)
    )
    result = await db.execute(query)
    rig = result.scalar_one_or_none()

    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")

    # Convert rig fixtures to the format expected by PatternGenerator
    fixtures = []
    for rf in rig.fixtures:
        fixtures.append({
            'fixture_type': rf.fixture.fixture_type.value if rf.fixture else 'other',
            'name': rf.name,
            'dmx_address': rf.dmx_address,
            'universe': rf.universe,
            'position': {
                'x': rf.position_x,
                'y': rf.position_y,
                'z': rf.position_z
            },
            'group_name': rf.group_name,
        })

    color = {'r': color_r, 'g': color_g, 'b': color_b}
    generator = PatternGenerator()

    # Generate pattern based on type
    if pattern_type == 'x_pattern':
        dmx_values = generator.generate_x_pattern(fixtures, intensity, color)
    elif pattern_type == 'centered':
        dmx_values = generator.generate_centered_pattern(fixtures, intensity, color)
    elif pattern_type == 'left_side':
        dmx_values = generator.generate_side_pattern(fixtures, 'left', intensity, color)
    elif pattern_type == 'right_side':
        dmx_values = generator.generate_side_pattern(fixtures, 'right', intensity, color)
    elif pattern_type == 'alternating':
        dmx_values = generator.generate_alternating_pattern(
            fixtures,
            group_a_intensity=intensity,
            group_b_intensity=0,
            color_a=color
        )
    elif pattern_type == 'sweep_horizontal':
        dmx_values = generator.generate_sweep_pattern(
            fixtures, position, width, 'horizontal', intensity, color
        )
    elif pattern_type == 'sweep_vertical':
        dmx_values = generator.generate_sweep_pattern(
            fixtures, position, width, 'vertical', intensity, color
        )
    elif pattern_type == 'all_on':
        dmx_values = {}
        for fixture in fixtures:
            values = generator._create_fixture_values(
                fixture.get('fixture_type', 'other'),
                intensity,
                color
            )
            for offset, value in enumerate(values):
                key = f"{fixture['universe']}:{fixture['dmx_address'] + offset}"
                dmx_values[key] = value
    elif pattern_type == 'blackout':
        dmx_values = {}
        for fixture in fixtures:
            # Get channel count based on fixture type
            channel_counts = {
                'moving_head': 16, 'wash': 14, 'led_bar': 12,
                'led_par': 8, 'strobe': 4, 'other': 4
            }
            ch_count = channel_counts.get(fixture.get('fixture_type', 'other'), 4)
            for offset in range(ch_count):
                key = f"{fixture['universe']}:{fixture['dmx_address'] + offset}"
                dmx_values[key] = 0
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown pattern type: {pattern_type}. "
                   f"Available: x_pattern, centered, left_side, right_side, "
                   f"alternating, sweep_horizontal, sweep_vertical, all_on, blackout"
        )

    return {
        "pattern": pattern_type,
        "rig_id": rig_id,
        "fixture_count": len(fixtures),
        "dmx_values": dmx_values,
        "total_channels": len(dmx_values)
    }


@router.post("/{rig_id}/patterns/{pattern_type}/apply")
async def apply_pattern(
    request: Request,
    rig_id: int,
    pattern_type: str,
    intensity: int = Query(255, ge=0, le=255),
    color_r: int = Query(255, ge=0, le=255),
    color_g: int = Query(255, ge=0, le=255),
    color_b: int = Query(255, ge=0, le=255),
    position: float = Query(0.5, ge=0, le=1),
    width: float = Query(0.2, ge=0.1, le=1),
    side: str = Query("left"),
    fade_time: float = Query(0.0, ge=0, le=10, description="Fade time in seconds"),
    db: AsyncSession = Depends(get_db),
):
    """Generate and apply a pattern directly to the DMX controller.

    Same as /patterns/{pattern_type} but immediately sends values to DMX output.
    """
    # Generate the pattern
    pattern_result = await generate_pattern(
        rig_id, pattern_type, intensity,
        color_r, color_g, color_b,
        position, width, side, db
    )

    # Apply to DMX controller
    if not hasattr(request.app.state, 'dmx_controller') or request.app.state.dmx_controller is None:
        raise HTTPException(status_code=503, detail="DMX controller not initialized")

    dmx_controller = request.app.state.dmx_controller

    try:
        for channel_str, value in pattern_result['dmx_values'].items():
            parts = channel_str.split(':')
            universe = int(parts[0])
            channel = int(parts[1])

            if fade_time > 0:
                # Start fade in background
                import asyncio
                asyncio.create_task(
                    dmx_controller._fade_channel(universe, channel, value, fade_time)
                )
            else:
                await dmx_controller.set_channel(universe, channel, value)

        return {
            "success": True,
            "pattern": pattern_type,
            "applied_channels": len(pattern_result['dmx_values']),
            "fade_time": fade_time
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to apply pattern to DMX controller: {str(e)}"
        )
