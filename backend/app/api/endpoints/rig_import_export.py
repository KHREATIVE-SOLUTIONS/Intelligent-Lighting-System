"""
Rig Import/Export Endpoints
============================

API endpoints for importing rigs from MVR, GDTF, and console patch files,
and exporting rigs to various formats.
"""

import csv
import io
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.models.rig import Rig, RigFixture
from app.models.fixture import Fixture, FixtureMode, FixtureChannel, FixtureType, ChannelType
from app.services.fixture_library.gdtf_parser import parse_gdtf
from app.services.fixture_library.mvr_parser import parse_mvr
from app.services.fixture_library.console_parsers import detect_and_parse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/rigs/import/mvr")
async def import_mvr(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Import a rig from an MVR file."""
    if not file.filename or not file.filename.lower().endswith(".mvr"):
        raise HTTPException(status_code=400, detail="File must be an MVR file (.mvr)")

    content = await file.read()

    try:
        mvr_data = parse_mvr(content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Create or match GDTF fixtures
    fixture_map = {}  # gdtf_spec -> fixture_id
    for parsed in mvr_data.get("gdtf_parsed", []):
        modes_data = parsed.pop("modes", [])
        parsed.pop("_gdtf_filename", None)

        # Check if already exists
        existing = None
        if parsed.get("gdtf_id"):
            existing = db.query(Fixture).filter(Fixture.gdtf_id == parsed["gdtf_id"]).first()

        if not existing:
            fixture = Fixture(
                manufacturer=parsed.get("manufacturer", "Unknown"),
                model=parsed.get("model", "Unknown"),
                fixture_type=FixtureType(parsed.get("fixture_type", "other")),
                gdtf_id=parsed.get("gdtf_id"),
                weight=parsed.get("weight"),
                power=parsed.get("power"),
                beam_angle=parsed.get("beam_angle"),
                has_rgb=parsed.get("has_rgb", False),
                has_color_wheel=parsed.get("has_color_wheel", False),
                source="gdtf",
            )
            db.add(fixture)
            db.flush()

            for mode_data in modes_data:
                channels_data = mode_data.pop("channels", [])
                mode = FixtureMode(
                    fixture_id=fixture.id,
                    name=mode_data["name"],
                    channel_count=mode_data["channel_count"],
                )
                db.add(mode)
                db.flush()

                for ch_data in channels_data:
                    ch = FixtureChannel(
                        mode_id=mode.id,
                        channel_number=ch_data["channel_number"],
                        channel_type=ChannelType(ch_data.get("channel_type", "other")),
                        name=ch_data.get("name", f"Ch {ch_data['channel_number']}"),
                        default_value=ch_data.get("default_value", 0),
                        is_fine=ch_data.get("is_fine", False),
                    )
                    db.add(ch)

            fixture_map[parsed.get("model", "")] = fixture.id
        else:
            fixture_map[parsed.get("model", "")] = existing.id

    # Create rig
    stage = mvr_data.get("stage", {})
    rig = Rig(
        name=f"MVR Import - {file.filename}",
        stage_width=stage.get("width", 10.0),
        stage_depth=stage.get("depth", 8.0),
        stage_height=stage.get("height", 6.0),
        source_format="mvr",
        source_file=file.filename,
        is_active=True,
    )
    db.add(rig)
    db.flush()

    # Create fixtures
    for i, fix_data in enumerate(mvr_data.get("fixtures", [])):
        gdtf_spec = fix_data.get("gdtf_spec", "")
        fixture_id = fixture_map.get(gdtf_spec)

        if not fixture_id:
            # Try to find by model name
            fixture_id = next(
                (fid for name, fid in fixture_map.items() if name in gdtf_spec),
                None
            )

        if not fixture_id:
            continue

        rf = RigFixture(
            rig_id=rig.id,
            fixture_id=fixture_id,
            name=fix_data.get("name", f"Fixture {i + 1}"),
            fixture_number=i + 1,
            universe=fix_data.get("universe", 0),
            dmx_address=fix_data.get("dmx_address", 1),
            position_x=fix_data.get("position_x", 0.0),
            position_y=fix_data.get("position_y", 0.0),
            position_z=fix_data.get("position_z", 0.0),
            is_active=True,
        )
        db.add(rf)

    db.commit()

    return {
        "rig_id": rig.id,
        "rig_name": rig.name,
        "fixtures_imported": len(mvr_data.get("fixtures", [])),
        "gdtf_fixtures_parsed": len(mvr_data.get("gdtf_parsed", [])),
    }


@router.post("/rigs/import/console-patch")
async def import_console_patch(
    file: UploadFile = File(...),
    format: str = Query(default="auto"),
    rig_name: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Import a rig from a console patch export file (grandMA, Hog, Eos)."""
    content = (await file.read()).decode("utf-8", errors="replace")
    format_hint = None if format == "auto" else format

    fixtures_data = detect_and_parse(content, format_hint)
    if not fixtures_data:
        raise HTTPException(status_code=400, detail="No fixtures found in patch file")

    # Create rig
    rig = Rig(
        name=rig_name or f"Console Import - {file.filename}",
        source_format="console",
        source_file=file.filename,
        is_active=True,
    )
    db.add(rig)
    db.flush()

    # Create generic fixtures and rig placements
    for i, fix_data in enumerate(fixtures_data):
        # Try to find matching fixture in library
        matched = None
        if fix_data.get("manufacturer") and fix_data.get("model"):
            matched = db.query(Fixture).filter(
                Fixture.manufacturer.ilike(f"%{fix_data['manufacturer']}%"),
                Fixture.model.ilike(f"%{fix_data['model']}%"),
            ).first()

        if not matched:
            # Create generic fixture
            matched = Fixture(
                manufacturer=fix_data.get("manufacturer") or "Generic",
                model=fix_data.get("model") or f"Fixture Type {i + 1}",
                fixture_type=FixtureType.OTHER,
                source="console",
            )
            db.add(matched)
            db.flush()

        rf = RigFixture(
            rig_id=rig.id,
            fixture_id=matched.id,
            name=fix_data.get("name", f"Fixture {i + 1}"),
            fixture_number=i + 1,
            universe=fix_data.get("universe", 0),
            dmx_address=fix_data.get("dmx_address", 1),
            is_active=True,
        )
        db.add(rf)

    db.commit()

    return {
        "rig_id": rig.id,
        "rig_name": rig.name,
        "fixtures_imported": len(fixtures_data),
    }


@router.get("/rigs/{rig_id}/export/json")
async def export_rig_json(rig_id: int, db: Session = Depends(get_db)):
    """Export rig as JSON."""
    rig = db.query(Rig).filter(Rig.id == rig_id).first()
    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")

    fixtures = (
        db.query(RigFixture)
        .filter(RigFixture.rig_id == rig_id)
        .options(
            joinedload(RigFixture.fixture),
            joinedload(RigFixture.mode).joinedload(FixtureMode.channels),
        )
        .all()
    )

    export_data = {
        "name": rig.name,
        "venue": rig.venue,
        "stage_width": rig.stage_width,
        "stage_depth": rig.stage_depth,
        "stage_height": rig.stage_height,
        "fixtures": [
            {
                "name": rf.name,
                "manufacturer": rf.fixture.manufacturer if rf.fixture else None,
                "model": rf.fixture.model if rf.fixture else None,
                "fixture_type": rf.fixture.fixture_type.value if rf.fixture and rf.fixture.fixture_type else None,
                "universe": rf.universe,
                "dmx_address": rf.dmx_address,
                "mode": rf.mode.name if rf.mode else None,
                "channel_count": rf.mode.channel_count if rf.mode else None,
                "position": {"x": rf.position_x, "y": rf.position_y, "z": rf.position_z},
                "rotation": {"x": rf.rotation_x, "y": rf.rotation_y, "z": rf.rotation_z},
                "group": rf.group_name,
            }
            for rf in fixtures
        ],
    }

    return export_data


@router.get("/rigs/{rig_id}/export/csv")
async def export_rig_csv(rig_id: int, db: Session = Depends(get_db)):
    """Export rig patch sheet as CSV."""
    rig = db.query(Rig).filter(Rig.id == rig_id).first()
    if not rig:
        raise HTTPException(status_code=404, detail="Rig not found")

    fixtures = (
        db.query(RigFixture)
        .filter(RigFixture.rig_id == rig_id)
        .options(joinedload(RigFixture.fixture), joinedload(RigFixture.mode))
        .order_by(RigFixture.universe, RigFixture.dmx_address)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Number", "Name", "Manufacturer", "Model", "Type",
        "Universe", "Address", "Mode", "Channels",
        "Position X", "Position Y", "Position Z", "Group",
    ])

    for rf in fixtures:
        writer.writerow([
            rf.fixture_number,
            rf.name or "",
            rf.fixture.manufacturer if rf.fixture else "",
            rf.fixture.model if rf.fixture else "",
            rf.fixture.fixture_type.value if rf.fixture and rf.fixture.fixture_type else "",
            rf.universe,
            rf.dmx_address,
            rf.mode.name if rf.mode else "",
            rf.mode.channel_count if rf.mode else "",
            rf.position_x,
            rf.position_y,
            rf.position_z,
            rf.group_name or "",
        ])

    csv_content = output.getvalue()
    return StreamingResponse(
        io.BytesIO(csv_content.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=rig_{rig_id}_patch.csv"},
    )
