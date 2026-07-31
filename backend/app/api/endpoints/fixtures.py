"""
Fixtures API Endpoints
======================

CRUD operations for the fixture library.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.fixture import Fixture, FixtureMode, FixtureChannel, FixtureType, ChannelType
from app.schemas.fixture import (
    FixtureCreate, FixtureUpdate, FixtureResponse, FixtureListResponse,
    FixtureModeCreate, FixtureModeResponse,
)

router = APIRouter()


@router.get("/", response_model=FixtureListResponse)
async def list_fixtures(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    manufacturer: Optional[str] = None,
    fixture_type: Optional[FixtureType] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all fixtures in the library with pagination."""
    query = select(Fixture).options(
        selectinload(Fixture.modes).selectinload(FixtureMode.channels)
    )

    if manufacturer:
        query = query.where(Fixture.manufacturer.ilike(f"%{manufacturer}%"))
    if fixture_type:
        query = query.where(Fixture.fixture_type == fixture_type)
    if search:
        query = query.where(
            (Fixture.manufacturer.ilike(f"%{search}%")) |
            (Fixture.model.ilike(f"%{search}%"))
        )

    # Count total
    count_query = select(func.count()).select_from(Fixture)
    if manufacturer:
        count_query = count_query.where(Fixture.manufacturer.ilike(f"%{manufacturer}%"))
    if fixture_type:
        count_query = count_query.where(Fixture.fixture_type == fixture_type)
    if search:
        count_query = count_query.where(
            (Fixture.manufacturer.ilike(f"%{search}%")) |
            (Fixture.model.ilike(f"%{search}%"))
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    query = query.offset((page - 1) * size).limit(size).order_by(
        Fixture.manufacturer, Fixture.model
    )
    result = await db.execute(query)
    fixtures = result.scalars().all()

    return FixtureListResponse(
        items=fixtures,
        total=total,
        page=page,
        size=size,
        pages=(total + size - 1) // size,
    )


@router.post("/", response_model=FixtureResponse, status_code=201)
async def create_fixture(
    fixture_data: FixtureCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new fixture in the library."""
    fixture_dict = fixture_data.model_dump(exclude={'modes'})
    fixture = Fixture(**fixture_dict)
    db.add(fixture)
    await db.flush()

    # Create modes and channels
    for mode_data in fixture_data.modes:
        mode_dict = mode_data.model_dump(exclude={'channels'})
        mode = FixtureMode(fixture_id=fixture.id, **mode_dict)
        db.add(mode)
        await db.flush()

        for channel_data in mode_data.channels:
            channel_dict = channel_data.model_dump()
            # Convert value_ranges to dict if needed
            if channel_dict.get('value_ranges'):
                channel_dict['value_ranges'] = [
                    vr.model_dump() if hasattr(vr, 'model_dump') else vr
                    for vr in channel_dict['value_ranges']
                ]
            channel = FixtureChannel(mode_id=mode.id, **channel_dict)
            db.add(channel)

    await db.flush()

    result = await db.execute(
        select(Fixture).where(Fixture.id == fixture.id).options(
            selectinload(Fixture.modes).selectinload(FixtureMode.channels)
        )
    )
    return result.scalar_one()


@router.get("/{fixture_id}", response_model=FixtureResponse)
async def get_fixture(
    fixture_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific fixture by ID."""
    query = select(Fixture).where(Fixture.id == fixture_id).options(
        selectinload(Fixture.modes).selectinload(FixtureMode.channels)
    )
    result = await db.execute(query)
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    return fixture


@router.put("/{fixture_id}", response_model=FixtureResponse)
async def update_fixture(
    fixture_id: int,
    fixture_data: FixtureUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a fixture."""
    query = select(Fixture).where(Fixture.id == fixture_id)
    result = await db.execute(query)
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    update_data = fixture_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(fixture, field, value)

    await db.flush()

    result = await db.execute(
        select(Fixture).where(Fixture.id == fixture.id).options(
            selectinload(Fixture.modes).selectinload(FixtureMode.channels)
        )
    )
    return result.scalar_one()


@router.delete("/{fixture_id}", status_code=204)
async def delete_fixture(
    fixture_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a fixture from the library."""
    query = select(Fixture).where(Fixture.id == fixture_id)
    result = await db.execute(query)
    fixture = result.scalar_one_or_none()

    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    await db.delete(fixture)


@router.get("/manufacturers/list", response_model=List[str])
async def list_manufacturers(
    db: AsyncSession = Depends(get_db),
):
    """List all unique manufacturers."""
    query = select(Fixture.manufacturer).distinct().order_by(Fixture.manufacturer)
    result = await db.execute(query)
    return [row[0] for row in result.all()]


@router.get("/types/list", response_model=List[str])
async def list_fixture_types():
    """List all available fixture types."""
    return [ft.value for ft in FixtureType]


# Mode endpoints
@router.post("/{fixture_id}/modes", response_model=FixtureModeResponse, status_code=201)
async def add_mode(
    fixture_id: int,
    mode_data: FixtureModeCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a mode to a fixture."""
    # Verify fixture exists
    fixture_query = select(Fixture).where(Fixture.id == fixture_id)
    fixture_result = await db.execute(fixture_query)
    if not fixture_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Fixture not found")

    mode_dict = mode_data.model_dump(exclude={'channels'})
    mode = FixtureMode(fixture_id=fixture_id, **mode_dict)
    db.add(mode)
    await db.flush()

    for channel_data in mode_data.channels:
        channel_dict = channel_data.model_dump()
        if channel_dict.get('value_ranges'):
            channel_dict['value_ranges'] = [
                vr.model_dump() if hasattr(vr, 'model_dump') else vr
                for vr in channel_dict['value_ranges']
            ]
        channel = FixtureChannel(mode_id=mode.id, **channel_dict)
        db.add(channel)

    await db.flush()

    result = await db.execute(
        select(FixtureMode).where(FixtureMode.id == mode.id).options(
            selectinload(FixtureMode.channels)
        )
    )
    return result.scalar_one()


@router.delete("/{fixture_id}/modes/{mode_id}", status_code=204)
async def delete_mode(
    fixture_id: int,
    mode_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a mode from a fixture."""
    query = select(FixtureMode).where(
        FixtureMode.id == mode_id,
        FixtureMode.fixture_id == fixture_id
    )
    result = await db.execute(query)
    mode = result.scalar_one_or_none()

    if not mode:
        raise HTTPException(status_code=404, detail="Mode not found")

    await db.delete(mode)


@router.get("/channel-templates/{fixture_type}")
async def get_channel_templates(fixture_type: str):
    """Get suggested channel layout templates for a fixture type."""
    templates = {
        "moving_head": [
            {"channel_number": 1, "channel_type": "pan", "name": "Pan"},
            {"channel_number": 2, "channel_type": "pan_fine", "name": "Pan Fine"},
            {"channel_number": 3, "channel_type": "tilt", "name": "Tilt"},
            {"channel_number": 4, "channel_type": "tilt_fine", "name": "Tilt Fine"},
            {"channel_number": 5, "channel_type": "speed", "name": "Speed"},
            {"channel_number": 6, "channel_type": "dimmer", "name": "Dimmer"},
            {"channel_number": 7, "channel_type": "shutter", "name": "Shutter"},
            {"channel_number": 8, "channel_type": "red", "name": "Red"},
            {"channel_number": 9, "channel_type": "green", "name": "Green"},
            {"channel_number": 10, "channel_type": "blue", "name": "Blue"},
            {"channel_number": 11, "channel_type": "white", "name": "White"},
            {"channel_number": 12, "channel_type": "zoom", "name": "Zoom"},
        ],
        "led_par": [
            {"channel_number": 1, "channel_type": "dimmer", "name": "Dimmer"},
            {"channel_number": 2, "channel_type": "red", "name": "Red"},
            {"channel_number": 3, "channel_type": "green", "name": "Green"},
            {"channel_number": 4, "channel_type": "blue", "name": "Blue"},
            {"channel_number": 5, "channel_type": "white", "name": "White"},
            {"channel_number": 6, "channel_type": "strobe", "name": "Strobe"},
        ],
        "led_bar": [
            {"channel_number": 1, "channel_type": "dimmer", "name": "Dimmer"},
            {"channel_number": 2, "channel_type": "strobe", "name": "Strobe"},
            {"channel_number": 3, "channel_type": "red", "name": "Red"},
            {"channel_number": 4, "channel_type": "green", "name": "Green"},
            {"channel_number": 5, "channel_type": "blue", "name": "Blue"},
        ],
        "wash": [
            {"channel_number": 1, "channel_type": "dimmer", "name": "Dimmer"},
            {"channel_number": 2, "channel_type": "red", "name": "Red"},
            {"channel_number": 3, "channel_type": "green", "name": "Green"},
            {"channel_number": 4, "channel_type": "blue", "name": "Blue"},
            {"channel_number": 5, "channel_type": "white", "name": "White"},
            {"channel_number": 6, "channel_type": "zoom", "name": "Zoom"},
        ],
    }

    if fixture_type not in templates:
        return {"fixture_type": fixture_type, "channels": [], "message": "No template available"}

    return {"fixture_type": fixture_type, "channels": templates[fixture_type]}


@router.post("/import/gdtf")
async def import_gdtf(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Import a fixture from a GDTF file."""
    if not file.filename or not file.filename.lower().endswith(".gdtf"):
        raise HTTPException(status_code=400, detail="File must be a GDTF file (.gdtf)")

    content = await file.read()

    try:
        from app.services.fixture_library.gdtf_parser import parse_gdtf
        fixture_data = parse_gdtf(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check for duplicate by GDTF ID
    gdtf_id = fixture_data.get("gdtf_id")
    if gdtf_id:
        existing_query = select(Fixture).where(Fixture.gdtf_id == gdtf_id)
        existing_result = await db.execute(existing_query)
        existing = existing_result.scalar_one_or_none()
        if existing:
            return {"message": "Fixture already exists", "fixture_id": existing.id}

    modes_data = fixture_data.pop("modes", [])
    fixture = Fixture(
        manufacturer=fixture_data.get("manufacturer", "Unknown"),
        model=fixture_data.get("model", "Unknown"),
        fixture_type=FixtureType(fixture_data.get("fixture_type", "other")),
        gdtf_id=fixture_data.get("gdtf_id"),
        gdtf_file=file.filename,
        weight=fixture_data.get("weight"),
        power=fixture_data.get("power"),
        beam_angle=fixture_data.get("beam_angle"),
        has_rgb=fixture_data.get("has_rgb", False),
        has_color_wheel=fixture_data.get("has_color_wheel", False),
        source="gdtf",
    )
    db.add(fixture)
    await db.flush()

    for mode_data in modes_data:
        channels_data = mode_data.pop("channels", [])
        mode = FixtureMode(
            fixture_id=fixture.id,
            name=mode_data["name"],
            channel_count=mode_data["channel_count"],
        )
        db.add(mode)
        await db.flush()

        for ch_data in channels_data:
            channel = FixtureChannel(
                mode_id=mode.id,
                channel_number=ch_data["channel_number"],
                channel_type=ChannelType(ch_data.get("channel_type", "other")),
                name=ch_data.get("name", f"Channel {ch_data['channel_number']}"),
                default_value=ch_data.get("default_value", 0),
                is_fine=ch_data.get("is_fine", False),
            )
            db.add(channel)

    await db.flush()
    await db.refresh(fixture)

    return {
        "message": "GDTF fixture imported successfully",
        "fixture_id": fixture.id,
        "manufacturer": fixture.manufacturer,
        "model": fixture.model,
        "modes": len(modes_data),
    }
