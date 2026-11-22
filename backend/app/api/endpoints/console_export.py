"""
Console export responses
========================

The downloads behind the rig and demo-preset export routes: a grandMA2 fixture
layer XML, a grandMA2 command-line script and an MVR. This module has no routes
of its own. rig_import_export serves a database rig through it and demo serves
a venue preset, so both hand back the same files for the same rig.

Every route is a GET that reads and writes nothing: no rig is changed and
nothing is sent to a console.
"""

from typing import Any, Dict

from fastapi import Query
from fastapi.responses import Response

from app.services.console_export.ma2 import ma2_script, ma2_xml
from app.services.console_export.model import ExportRig
from app.services.console_export.mvr import mvr_bytes

MARK_NAMES = Query(
    False,
    description="Also append ' (position unconfirmed)' to the name of each fixture whose "
                "position nobody has confirmed, so the mark shows on the desk",
)
FIRST_GROUP = Query(1, ge=1, le=9999, description="The group number the first group is stored at")
INCLUDE = Query("all", pattern="^(all|patch|groups)$", description="Which part of the script to write")
NOTES = Query(True, description="Write the '#' note lines. Off gives a file that is commands only")

DOC = "docs/CONSOLE_EXPORT.md"


def _download(content: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def ma2_xml_response(rig: ExportRig, mark_names: bool = False) -> Response:
    return _download(
        ma2_xml(rig, mark_names=mark_names).encode("utf-8"),
        "application/xml",
        f"{rig.file_stem()}_ma2.xml",
    )


def ma2_script_response(
    rig: ExportRig,
    first_group: int = 1,
    include: str = "all",
    notes: bool = True,
    mark_names: bool = False,
) -> Response:
    text = ma2_script(
        rig,
        first_group=first_group,
        include_patch=include in ("all", "patch"),
        include_groups=include in ("all", "groups"),
        notes=notes,
        mark_names=mark_names,
    )
    return _download(text.encode("utf-8"), "text/plain; charset=utf-8", f"{rig.file_stem()}_ma2_script.txt")


def mvr_response(rig: ExportRig, mark_names: bool = False) -> Response:
    return _download(mvr_bytes(rig, mark_names=mark_names), "application/octet-stream", f"{rig.file_stem()}.mvr")


def summary(rig: ExportRig) -> Dict[str, Any]:
    """What an export of this rig holds and leaves out, before anything is downloaded."""
    out = rig.summary()
    out["operator_guide"] = DOC
    return out
