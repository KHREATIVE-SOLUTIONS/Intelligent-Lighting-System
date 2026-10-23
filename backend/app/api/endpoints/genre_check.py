"""
Genre Night Check API
=====================

Start a real-night check of the club genre model, mark what is actually
playing, and score the night afterwards. See services/ml/genre_night_check.py.

Starting a check loads the model if it is not already running. Unless
GENRE_MODEL_ENABLED is set it only listens: the show ignores what it says.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...core.config import settings
from ...services.ml.club_genre import ClubGenreModel
from ...services.ml.genre_night_check import (
    MARKS,
    MAX_BACKDATE_S,
    GenreNightCheck,
    list_nights,
    score_night,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/genre-check", tags=["genre-check"])


class MarkRequest(BaseModel):
    style: str = Field(..., description="What is playing: a club style, 'other' or 'not_music'")
    since_s: float = Field(0.0, ge=0.0, le=MAX_BACKDATE_S, description="It started this many seconds ago")


def _analyzer(request: Request):
    analyzer = getattr(request.app.state, "audio_analyzer", None)
    if analyzer is None:
        raise HTTPException(status_code=503, detail="Audio analysis is not running")
    return analyzer


def _check(request: Request) -> GenreNightCheck:
    check = getattr(request.app.state, "genre_night_check", None)
    if check is None:
        check = GenreNightCheck()
        request.app.state.genre_night_check = check
    return check


def _status(request: Request) -> dict:
    check = _check(request)
    analyzer = getattr(request.app.state, "audio_analyzer", None)
    classifier = getattr(analyzer, "_genre_classifier", None) if analyzer else None
    status = check.status()
    status["model_running"] = isinstance(classifier, ClubGenreModel) and classifier.loaded
    status["weights_present"] = ClubGenreModel(settings.GENRE_MODEL_PATH).weights_path.is_file()
    return status


@router.get("/status")
async def get_status(request: Request):
    """Whether a check is running, the model's latest guess and the current mark."""
    return _status(request)


@router.post("/start")
async def start_check(request: Request):
    """Start logging tonight. Loads the model to listen if it is not running."""
    analyzer = _analyzer(request)
    check = _check(request)
    classifier = getattr(analyzer, "_genre_classifier", None)
    if not (isinstance(classifier, ClubGenreModel) and classifier.loaded):
        model = ClubGenreModel(settings.GENRE_MODEL_PATH, device=settings.GENRE_MODEL_DEVICE)
        if not model.weights_path.is_file():
            raise HTTPException(
                status_code=409,
                detail="The genre model isn't downloaded yet. Run scripts/download_genre_model.py on the box.",
            )
        try:
            await model.load()
        except Exception as e:
            logger.warning("Genre night check could not load the model: %s", e)
            raise HTTPException(status_code=500, detail="The genre model failed to load") from e
        model.steers = bool(settings.GENRE_MODEL_ENABLED)
        # Put back whatever was there when the check stops.
        request.app.state.genre_check_previous_classifier = classifier
        analyzer.set_ml_models(
            mert_model=analyzer._mert_model,
            structure_analyzer=analyzer._structure_analyzer,
            genre_classifier=model,
        )
        classifier = model
    check.start(steering=getattr(classifier, "steers", False))
    analyzer.night_check = check
    return _status(request)


@router.post("/stop")
async def stop_check(request: Request):
    """Stop logging and return the night's score."""
    check = _check(request)
    night = check.stop()
    analyzer = getattr(request.app.state, "audio_analyzer", None)
    if analyzer is not None:
        analyzer.night_check = None
        state = request.app.state
        if hasattr(state, "genre_check_previous_classifier"):
            # The model was loaded only to listen: hand the slot back.
            analyzer.set_ml_models(
                mert_model=analyzer._mert_model,
                structure_analyzer=analyzer._structure_analyzer,
                genre_classifier=state.genre_check_previous_classifier,
            )
            del state.genre_check_previous_classifier
    status = _status(request)
    status["report"] = score_night(night) if night else None
    return status


@router.post("/mark")
async def mark_style(body: MarkRequest, request: Request):
    """Say what is playing now (or since a moment ago)."""
    if body.style not in MARKS:
        raise HTTPException(status_code=422, detail=f"style must be one of: {', '.join(MARKS)}")
    check = _check(request)
    if not check.active:
        raise HTTPException(status_code=409, detail="Start a night check first")
    check.mark(body.style, since_s=body.since_s)
    return _status(request)


@router.get("/nights")
async def get_nights():
    """Nights that have a log, oldest first."""
    return {"nights": list_nights()}


@router.get("/report")
async def get_report(night: Optional[str] = None):
    """Score a night (the latest one by default)."""
    nights = list_nights()
    if not nights:
        raise HTTPException(status_code=404, detail="No night checks yet")
    if night is None:
        night = nights[-1]
    elif night not in nights:
        raise HTTPException(status_code=404, detail="No such night")
    return score_night(night)
