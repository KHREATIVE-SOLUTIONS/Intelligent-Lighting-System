"""
Room Scan from a Walkthrough Video
==================================

A phone video of the room, turned into a point cloud by free tools on this
machine (ffmpeg and COLMAP), then handed to the room scan reader like any
other scan. docs/ROOM_SCAN.md.

    GET    /api/room-scan/video/tools                       what is installed
    POST   /api/rigs/{rig_id}/room-scan/video               start a job (the body is the video)
    GET    /api/rigs/{rig_id}/room-scan/video/{job_id}      how it is doing
    GET    /api/rigs/{rig_id}/room-scan/video/{job_id}/cloud.ply   the result, scaled
    DELETE /api/rigs/{rig_id}/room-scan/video/{job_id}      stop it, or forget it

The work runs on a thread of its own; no request here waits for it. The result
is a PLY the client downloads and sends to POST /rigs/{rig_id}/room-scan, so
preview and apply are exactly the ones every other scan goes through, and this
module never writes to a rig.

The video is the request body itself, not a multipart form: a form is read
whole before the handler runs, and the size limit has to act while it arrives.
"""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path, PurePath
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.database import get_db
from app.models.rig import Rig
from app.services.room_scan import RoomScanError
from app.services.room_scan.video import (
    REFERENCE_KINDS, VIDEO_SUFFIXES, Reference, VideoTools, cloud_ply, find_tools,
)
from app.services.room_scan.video_jobs import DONE, JobBusy, VideoJob, jobs

logger = logging.getLogger(__name__)
router = APIRouter()

DOC = "docs/ROOM_SCAN.md"


def max_upload_bytes() -> int:
    return max(1, int(settings.ROOM_VIDEO_MAX_MB)) * 1024 * 1024


def installed_tools() -> VideoTools:
    return find_tools(settings.COLMAP_PATH, settings.OPENMVS_PATH)


def _tools_answer(tools: VideoTools) -> dict:
    return {
        **tools.to_dict(),
        "max_upload_mb": max_upload_bytes() // (1024 * 1024),
        "video_types": list(VIDEO_SUFFIXES),
        "reference_kinds": list(REFERENCE_KINDS),
        "operator_guide": DOC,
    }


async def _rig_exists(db: AsyncSession, rig_id: int) -> None:
    if (await db.execute(select(Rig.id).where(Rig.id == rig_id))).scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Rig not found")


def _job_for(rig_id: int, job_id: str) -> VideoJob:
    """The job, only when it belongs to this rig."""
    job = jobs.get(job_id)
    if job is None or job.rig_id != rig_id:
        raise HTTPException(
            status_code=404,
            detail="No such video job. Results are kept for two hours and do not survive a restart: "
                   "send the video again.",
        )
    return job


def _too_large() -> HTTPException:
    return HTTPException(
        status_code=413,
        detail=f"The video is larger than {max_upload_bytes() // (1024 * 1024)} MB. Film at 1080p rather "
               "than 4K, or trim it: one to two minutes round the room is enough.",
    )


@router.get("/room-scan/video/tools")
async def room_video_tools():
    """Which free tools are installed here, and what to install when a video cannot be read."""
    return _tools_answer(await asyncio.to_thread(installed_tools))


@router.post("/rigs/{rig_id}/room-scan/video")
async def start_room_video(
    rig_id: int,
    request: Request,
    filename: str = Query(..., max_length=255, description="The video's name; its ending says what it is"),
    quality: str = Query("sparse", pattern="^(sparse|dense)$",
                         description="dense asks for a filled-in cloud where a tool for it is installed"),
    db: AsyncSession = Depends(get_db),
):
    """Start turning a walkthrough video into a room scan. The request body is the video file."""
    await _rig_exists(db, rig_id)
    suffix = PurePath(filename).suffix.lower()
    if suffix not in VIDEO_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"'{PurePath(filename).name}' is not a video this reads. Send {', '.join(VIDEO_SUFFIXES)}.",
        )
    limit = max_upload_bytes()
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise _too_large()

    tools = await asyncio.to_thread(installed_tools)
    if not tools.ready:
        # Not an error: the answer says what to install, or what to do instead.
        # The body is read and dropped first, so the answer is not lost to a
        # connection closed with the upload still arriving.
        dropped = 0
        async for chunk in request.stream():
            dropped += len(chunk)
            if dropped > limit:
                break
        return {"job_id": None, "rig_id": rig_id, "state": "unavailable", "error": tools.missing_message(),
                "tools": _tools_answer(tools)}

    busy = jobs.running()
    if busy is not None:
        raise HTTPException(
            status_code=409,
            detail="Another walkthrough video is already being processed. Wait for it, or stop it first.",
        )

    work = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="ils-room-video-"))
    video = work / f"video{suffix}"      # never the client's name: it is only ever a label
    try:
        received = 0
        with open(video, "wb") as out:
            async for chunk in request.stream():
                received += len(chunk)
                if received > limit:
                    raise _too_large()
                await asyncio.to_thread(out.write, chunk)
        if received == 0:
            raise HTTPException(status_code=400, detail="The video is empty.")
        job = jobs.start(
            rig_id, video, work, PurePath(filename).name, tools, quality=quality,
            timeout_s=max(1, int(settings.ROOM_VIDEO_TIMEOUT_MIN)) * 60.0,
        )
    except JobBusy:
        await asyncio.to_thread(shutil.rmtree, work, True)
        raise HTTPException(
            status_code=409,
            detail="Another walkthrough video is already being processed. Wait for it, or stop it first.",
        )
    except BaseException:
        await asyncio.to_thread(shutil.rmtree, work, True)
        raise
    logger.info("Room video %s started for rig %s: %s, %.1f MB", job.id, rig_id, job.filename, received / 1e6)
    return JSONResponse(status_code=202, content=job.to_dict())


@router.get("/rigs/{rig_id}/room-scan/video/{job_id}")
async def room_video_status(rig_id: int, job_id: str):
    """How a video job is doing. Poll this."""
    return _job_for(rig_id, job_id).to_dict()


@router.get("/rigs/{rig_id}/room-scan/video/{job_id}/cloud.ply")
async def room_video_cloud(
    rig_id: int,
    job_id: str,
    ceiling_height: Optional[float] = Query(None, description="Measured floor to ceiling, in metres"),
    longest_wall: Optional[float] = Query(None, description="Measured length of the longest wall, in metres"),
):
    """The finished cloud as a PLY in metres, to send to POST /rigs/{rig_id}/room-scan.

    A video has no scale. Give one measurement; with none the scale is assumed
    and the PLY says so, which the preview shows as a warning.
    """
    job = _job_for(rig_id, job_id)
    if job.state != DONE or job.cloud is None:
        raise HTTPException(status_code=409, detail="This video job has no result: it is " + job.state + ".")
    if ceiling_height is not None and longest_wall is not None:
        raise HTTPException(status_code=400, detail="Give one measurement: the ceiling height or the longest wall.")
    try:
        if ceiling_height is not None:
            reference = Reference("ceiling_height", ceiling_height)
        elif longest_wall is not None:
            reference = Reference("longest_wall", longest_wall)
        else:
            reference = Reference()
        content, info = await asyncio.to_thread(cloud_ply, job.cloud, reference)
    except RoomScanError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="walkthrough-{job.id}.ply"',
            "X-Room-Scale-Assumed": "true" if info["assumed"] else "false",
            "X-Room-Scale-Basis": str(info["basis"]),
        },
    )


@router.delete("/rigs/{rig_id}/room-scan/video/{job_id}")
async def stop_room_video(rig_id: int, job_id: str):
    """Stop a running job, or forget a finished one. Nothing on the rig is touched."""
    job = _job_for(rig_id, job_id)
    was_running = job.state not in ("done", "failed", "cancelled")
    jobs.cancel(job_id)
    jobs.forget(job_id)
    return {"job_id": job_id, "rig_id": rig_id, "stopping": was_running}
