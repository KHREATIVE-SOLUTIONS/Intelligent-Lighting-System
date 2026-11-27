"""
Venue Import Endpoint
=====================

POST /api/import/venue takes what a venue already has - a CSV patch list, a
GDTF, an MVR or a grandMA2 XML export - and answers with a preview: the
fixtures it read, their groups, the types it could not match to a profile, the
address clashes, and what it had to assume. Nothing is written.

The same request with apply=true writes that preview as a NEW rig. The new rig
is not active, so the rig on stage is untouched; activate=true asks for it to
be made the active rig as well, through the same path as the Activate button.

The file is sent again to apply. Nothing is kept on the server between the two
requests, so a preview can never be applied against a different file.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.venue_import import VenueImportError, read_venue_file
from app.services.venue_import.apply import apply_import, load_library, store_profiles
from app.services.venue_import.preview import plan_import, render_preview

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_BYTES = 100 * 1024 * 1024


@router.post("/import/venue")
async def import_venue(
    request: Request,
    file: UploadFile = File(..., description="A .csv patch list, .gdtf, .mvr or grandMA2 .xml export"),
    apply: bool = Query(False, description="Write the preview as a new rig"),
    rig_name: Optional[str] = Query(None, max_length=255, description="Name for the new rig"),
    activate: bool = Query(False, description="With apply: also make the new rig the active one"),
    universe_base: str = Query(
        "auto", pattern="^(auto|0|1)$",
        description="CSV only: what a separate Universe column calls the first universe",
    ),
    up_axis: str = Query("y", pattern="^(y|z)$", description="CSV only: which of X/Y/Z is height"),
    db: AsyncSession = Depends(get_db),
):
    """Preview a venue file, or with apply=true create a new rig from it."""
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )
    filename = file.filename or ""

    # Unzipping and parsing is CPU work; keep it off the loop the show runs on.
    try:
        parsed = await asyncio.to_thread(
            read_venue_file, filename, content, universe_base, up_axis
        )
    except VenueImportError as e:
        raise HTTPException(status_code=400, detail=str(e))

    library = await load_library(db)
    plans, clashes, plan_warnings = await asyncio.to_thread(plan_import, parsed, library)
    preview = render_preview(parsed, library, plans, clashes, plan_warnings)
    preview["applied"] = None

    if not apply:
        return preview

    if parsed.format == "gdtf":
        # A fixture profile on its own patches nothing: it goes to the library.
        created = await store_profiles(db, parsed, library)
        preview["applied"] = {
            "rig_id": None,
            "profiles_created": created,
            "message": (
                "The profile was added to the fixture library." if created
                else "The profile is already in the fixture library; nothing was written."
            ),
        }
        return preview

    if not any(p.importable for p in plans):
        reasons = sorted({p.refusal for p in plans if p.refusal})
        raise HTTPException(
            status_code=400,
            detail="Nothing in the file can be patched"
            + (": " + "; ".join(reasons[:5]) if reasons else " - it holds no fixtures") + ".",
        )

    applied = await apply_import(db, parsed, plans, rig_name=rig_name)
    applied["activated"] = False

    if activate:
        from app.api.endpoints.rigs import activate_rig

        await activate_rig(applied["rig_id"], request, db)
        applied["activated"] = True
        applied["is_active"] = True

    logger.info(
        "Venue import: rig %s '%s' from %s (%s): %d fixtures, %d switched off, %d not imported",
        applied["rig_id"], applied["rig_name"], filename, parsed.format,
        applied["fixtures_created"], applied["fixtures_switched_off"], applied["fixtures_not_imported"],
    )
    preview["applied"] = applied
    return preview
