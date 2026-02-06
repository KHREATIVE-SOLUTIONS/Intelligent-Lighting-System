"""
Shows API Endpoints
===================

CRUD operations for lighting shows.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.models.show import Show, ShowCue, ShowTrack, ShowStatus
from app.schemas.show import (
    ShowCreate, ShowUpdate, ShowResponse, ShowListResponse,
    CueCreate, CueUpdate, CueResponse,
    TrackCreate, TrackUpdate, TrackResponse,
)

router = APIRouter()


# Show CRUD
@router.get("/", response_model=ShowListResponse)
async def list_shows(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[ShowStatus] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all shows with pagination and filtering."""
    query = select(Show).options(
        selectinload(Show.tracks).selectinload(ShowTrack.cues),
        selectinload(Show.cues),
    )

    if status:
        query = query.where(Show.status == status)
    if search:
        query = query.where(Show.name.ilike(f"%{search}%"))

    # Count total
    count_query = select(func.count()).select_from(Show)
    if status:
        count_query = count_query.where(Show.status == status)
    if search:
        count_query = count_query.where(Show.name.ilike(f"%{search}%"))

    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    query = query.offset((page - 1) * size).limit(size).order_by(Show.updated_at.desc())
    result = await db.execute(query)
    shows = result.scalars().all()

    return ShowListResponse(
        items=shows,
        total=total,
        page=page,
        size=size,
        pages=(total + size - 1) // size,
    )


@router.post("/", response_model=ShowResponse, status_code=201)
async def create_show(
    show_data: ShowCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new show."""
    show = Show(**show_data.model_dump())
    db.add(show)
    await db.flush()
    await db.refresh(show)
    return show


@router.get("/{show_id}", response_model=ShowResponse)
async def get_show(
    show_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific show by ID."""
    query = select(Show).where(Show.id == show_id).options(
        selectinload(Show.tracks).selectinload(ShowTrack.cues),
        selectinload(Show.cues),
    )
    result = await db.execute(query)
    show = result.scalar_one_or_none()

    if not show:
        raise HTTPException(status_code=404, detail="Show not found")

    return show


@router.put("/{show_id}", response_model=ShowResponse)
async def update_show(
    show_id: int,
    show_data: ShowUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a show."""
    query = select(Show).where(Show.id == show_id)
    result = await db.execute(query)
    show = result.scalar_one_or_none()

    if not show:
        raise HTTPException(status_code=404, detail="Show not found")

    update_data = show_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(show, field, value)

    await db.flush()
    await db.refresh(show)
    return show


@router.delete("/{show_id}", status_code=204)
async def delete_show(
    show_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a show."""
    query = select(Show).where(Show.id == show_id)
    result = await db.execute(query)
    show = result.scalar_one_or_none()

    if not show:
        raise HTTPException(status_code=404, detail="Show not found")

    await db.delete(show)


@router.post("/{show_id}/duplicate", response_model=ShowResponse, status_code=201)
async def duplicate_show(
    show_id: int,
    new_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Duplicate an existing show."""
    query = select(Show).where(Show.id == show_id).options(
        selectinload(Show.tracks).selectinload(ShowTrack.cues),
        selectinload(Show.cues),
    )
    result = await db.execute(query)
    original = result.scalar_one_or_none()

    if not original:
        raise HTTPException(status_code=404, detail="Show not found")

    # Create copy
    new_show = Show(
        name=new_name or f"{original.name} (Copy)",
        description=original.description,
        duration=original.duration,
        bpm=original.bpm,
        base_valence=original.base_valence,
        base_arousal=original.base_arousal,
        status=ShowStatus.DRAFT,
    )
    db.add(new_show)
    await db.flush()

    # Copy tracks and cues
    track_mapping = {}
    for track in original.tracks:
        new_track = ShowTrack(
            show_id=new_show.id,
            name=track.name,
            track_type=track.track_type,
            order=track.order,
            fixture_ids=track.fixture_ids,
        )
        db.add(new_track)
        await db.flush()
        track_mapping[track.id] = new_track.id

    for cue in original.cues:
        new_cue = ShowCue(
            show_id=new_show.id,
            track_id=track_mapping.get(cue.track_id) if cue.track_id else None,
            name=cue.name,
            cue_type=cue.cue_type,
            start_time=cue.start_time,
            duration=cue.duration,
            fade_in=cue.fade_in,
            fade_out=cue.fade_out,
            dmx_values=cue.dmx_values,
            effect_type=cue.effect_type,
            effect_params=cue.effect_params,
            audio_reactive=cue.audio_reactive,
            audio_trigger=cue.audio_trigger,
            audio_params=cue.audio_params,
            valence=cue.valence,
            arousal=cue.arousal,
        )
        db.add(new_cue)

    await db.refresh(new_show)
    return new_show


# Track CRUD
@router.get("/{show_id}/tracks", response_model=List[TrackResponse])
async def list_tracks(
    show_id: int,
    db: AsyncSession = Depends(get_db),
):
    """List all tracks in a show."""
    query = select(ShowTrack).where(ShowTrack.show_id == show_id).options(
        selectinload(ShowTrack.cues)
    ).order_by(ShowTrack.order)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{show_id}/tracks", response_model=TrackResponse, status_code=201)
async def create_track(
    show_id: int,
    track_data: TrackCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new track in a show."""
    # Verify show exists
    show_query = select(Show).where(Show.id == show_id)
    show_result = await db.execute(show_query)
    if not show_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Show not found")

    track = ShowTrack(show_id=show_id, **track_data.model_dump())
    db.add(track)
    await db.flush()
    await db.refresh(track)
    return track


@router.put("/{show_id}/tracks/{track_id}", response_model=TrackResponse)
async def update_track(
    show_id: int,
    track_id: int,
    track_data: TrackUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a track."""
    query = select(ShowTrack).where(
        ShowTrack.id == track_id,
        ShowTrack.show_id == show_id
    )
    result = await db.execute(query)
    track = result.scalar_one_or_none()

    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    update_data = track_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(track, field, value)

    await db.flush()
    await db.refresh(track)
    return track


@router.delete("/{show_id}/tracks/{track_id}", status_code=204)
async def delete_track(
    show_id: int,
    track_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a track."""
    query = select(ShowTrack).where(
        ShowTrack.id == track_id,
        ShowTrack.show_id == show_id
    )
    result = await db.execute(query)
    track = result.scalar_one_or_none()

    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    await db.delete(track)


# Cue CRUD
@router.get("/{show_id}/cues", response_model=List[CueResponse])
async def list_cues(
    show_id: int,
    track_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all cues in a show."""
    query = select(ShowCue).where(ShowCue.show_id == show_id)
    if track_id:
        query = query.where(ShowCue.track_id == track_id)
    query = query.order_by(ShowCue.start_time)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{show_id}/cues", response_model=CueResponse, status_code=201)
async def create_cue(
    show_id: int,
    cue_data: CueCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new cue in a show."""
    # Verify show exists
    show_query = select(Show).where(Show.id == show_id)
    show_result = await db.execute(show_query)
    if not show_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Show not found")

    cue = ShowCue(show_id=show_id, **cue_data.model_dump())
    db.add(cue)
    await db.flush()
    await db.refresh(cue)
    return cue


@router.put("/{show_id}/cues/{cue_id}", response_model=CueResponse)
async def update_cue(
    show_id: int,
    cue_id: int,
    cue_data: CueUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a cue."""
    query = select(ShowCue).where(
        ShowCue.id == cue_id,
        ShowCue.show_id == show_id
    )
    result = await db.execute(query)
    cue = result.scalar_one_or_none()

    if not cue:
        raise HTTPException(status_code=404, detail="Cue not found")

    update_data = cue_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(cue, field, value)

    await db.flush()
    await db.refresh(cue)
    return cue


@router.delete("/{show_id}/cues/{cue_id}", status_code=204)
async def delete_cue(
    show_id: int,
    cue_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a cue."""
    query = select(ShowCue).where(
        ShowCue.id == cue_id,
        ShowCue.show_id == show_id
    )
    result = await db.execute(query)
    cue = result.scalar_one_or_none()

    if not cue:
        raise HTTPException(status_code=404, detail="Cue not found")

    await db.delete(cue)
