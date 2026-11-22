"""
Patch Sheet Import Endpoint
===========================

POST /api/import/patch-sheet takes a patch sheet - CSV, .xlsx, a text table, a
PDF, or a photo where local OCR is set up - and answers with a preview: the
fixtures it read, their addresses, the types it could not match, the address
clashes, and a 3D layout generated for every fixture the sheet does not place.
Nothing is written.

The layout is a first guess on a stage template (festival main stage, club
ring, small stage). Every generated position says so: position_source
"template" and position_confirmed false in the preview, the tag
position_unconfirmed on the rig fixture. A position the sheet gives is kept.

The same request with apply=true writes the preview as a NEW rig, which is not
active; activate=true asks for that as well, through the same path as the
Activate button. The file is sent again to apply: nothing is kept on the
server between the two requests.

A venue file that carries its own positions (MVR, GDTF, console XML) goes to
POST /api/import/venue instead.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.demo import patch_sheet_samples
from app.services.patch_sheet import read_patch_sheet
from app.services.patch_sheet.extract import ocr_available, pdf_reader_available
from app.services.patch_sheet.layout import generate_layout, pick_template
from app.services.patch_sheet.templates import TEMPLATES, build_template
from app.services.venue_import import VenueImportError
from app.services.venue_import.apply import apply_import, load_library
from app.services.venue_import.preview import plan_import, render_preview

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
TEMPLATE_PATTERN = "^(auto|" + "|".join(TEMPLATES) + ")$"


@router.get("/import/patch-sheet/templates")
async def list_templates():
    """The stage templates a layout can be generated on, and what this machine can read."""
    return {
        "templates": [builder().describe() for builder in TEMPLATES.values()],
        "default": "auto",
        "reads": {
            "csv": True,
            "xlsx": True,
            "text": True,
            "pdf": pdf_reader_available(),
            "image": ocr_available(),
        },
    }


@router.get("/import/patch-sheet/sample")
async def sample_patch_sheet():
    """The example festival patch sheet: fixtures and addresses, no positions.

    Made-up example data, for trying the importer without a venue's own sheet.
    """
    return Response(
        content=patch_sheet_samples.festival_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{patch_sheet_samples.FESTIVAL_FILE}"'},
    )


@router.post("/import/patch-sheet")
async def import_patch_sheet(
    request: Request,
    file: UploadFile = File(..., description="A patch sheet: .csv, .xlsx, .txt, .pdf or a photo"),
    apply: bool = Query(False, description="Write the preview as a new rig"),
    rig_name: Optional[str] = Query(None, max_length=255, description="Name for the new rig"),
    activate: bool = Query(False, description="With apply: also make the new rig the active one"),
    layout: bool = Query(True, description="Generate positions for the fixtures the sheet does not place"),
    template: str = Query(
        "auto", pattern=TEMPLATE_PATTERN,
        description="The stage template to lay the rig out on; auto picks one from the sheet",
    ),
    stage_width: Optional[float] = Query(None, gt=0, le=200, description="Template width in metres"),
    stage_depth: Optional[float] = Query(None, gt=0, le=200, description="Template depth in metres"),
    stage_height: Optional[float] = Query(None, gt=0, le=100, description="Template height in metres"),
    mirror: bool = Query(False, description="Put SL / stage left on the plan's right (+X) instead of its left"),
    universe_base: str = Query(
        "auto", pattern="^(auto|0|1)$",
        description="What a separate Universe column calls the first universe",
    ),
    up_axis: str = Query("y", pattern="^(y|z)$", description="Which of X/Y/Z is height, where the sheet has them"),
    db: AsyncSession = Depends(get_db),
):
    """Preview a patch sheet with a generated layout, or with apply=true create a new rig from it."""
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )
    filename = file.filename or ""

    # Unzipping, PDF text and OCR are CPU work; keep them off the loop the show runs on.
    try:
        parsed = await asyncio.to_thread(read_patch_sheet, filename, content, universe_base, up_axis)
    except VenueImportError as e:
        raise HTTPException(status_code=400, detail=str(e))

    library = await load_library(db)
    plans, clashes, plan_warnings = await asyncio.to_thread(plan_import, parsed, library)

    report = None
    stage = None
    if layout:
        if template == "auto":
            name, why = pick_template(plans)
            chosen_by = f"chosen because {why}"
        else:
            name, chosen_by = template, "asked for"
        stage_template = build_template(name, stage_width, stage_depth, stage_height)
        report = generate_layout(plans, stage_template, mirror=mirror, chosen_by=chosen_by)
        if report["generated"]:
            stage = stage_template.stage_size()
            parsed.assumptions.extend(report["assumptions"])
        parsed.warnings.extend(report["warnings"])

    preview = render_preview(parsed, library, plans, clashes, plan_warnings)
    preview["layout"] = report
    preview["applied"] = None

    if not apply:
        return preview

    if not any(p.importable for p in plans):
        reasons = sorted({p.refusal for p in plans if p.refusal})
        raise HTTPException(
            status_code=400,
            detail="Nothing in the sheet can be patched"
            + (": " + "; ".join(reasons[:5]) if reasons else " - it holds no fixtures") + ".",
        )

    applied = await apply_import(db, parsed, plans, rig_name=rig_name, stage=stage)
    applied["activated"] = False

    if activate:
        from app.api.endpoints.rigs import activate_rig

        await activate_rig(applied["rig_id"], request, db)
        applied["activated"] = True
        applied["is_active"] = True

    logger.info(
        "Patch sheet import: rig %s '%s' from %s (%s): %d fixtures, %d on generated positions, "
        "%d switched off, %d not imported",
        applied["rig_id"], applied["rig_name"], filename, parsed.format,
        applied["fixtures_created"], applied["unconfirmed_positions"],
        applied["fixtures_switched_off"], applied["fixtures_not_imported"],
    )
    preview["applied"] = applied
    return preview
