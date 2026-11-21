"""
Remembered Output Target
========================

Where the show is sent - protocol, node IP, universe - is chosen once, at the
venue, and has to survive a reboot. Left only in memory, a power cut put the
box back on the settings default (Art-Net limited broadcast) instead of the
node it had been pointed at.

Kept the same way as the audio capture choice: a small JSON file next to the
database, written atomically, read tolerantly. A missing or unreadable file
means nothing was chosen, never an error.

The sACN CID lives in its own file beside it. E1.31 wants a source to keep one
CID for life, so changing the target must never be able to mint a new one.
"""

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from app.schemas.dmx import OutputTarget

logger = logging.getLogger(__name__)

FILENAME = "output_target.json"
CID_FILENAME = "sacn_cid"


def default_data_dir() -> Path:
    from app.core.config import settings

    return settings.data_dir


def settings_path(data_dir: Optional[Path] = None) -> Path:
    return Path(data_dir if data_dir is not None else default_data_dir()) / FILENAME


def cid_path(data_dir: Optional[Path] = None) -> Path:
    return Path(data_dir if data_dir is not None else default_data_dir()) / CID_FILENAME


def load(data_dir: Optional[Path] = None) -> Optional[OutputTarget]:
    """The remembered target, or None when nothing usable was saved."""
    path = settings_path(data_dir)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.warning("Ignoring unreadable output target at %s: %s", path, e)
        return None
    try:
        # Validated again on the way in: a hand-edited file must not be able to
        # put the show on broadcast without the same explicit flag the API needs.
        return OutputTarget.model_validate(raw)
    except Exception as e:
        logger.warning("Ignoring invalid output target at %s: %s", path, e)
        return None


def save(target: OutputTarget, data_dir: Optional[Path] = None) -> bool:
    """Remember the target. Best effort: a read-only disk must not stop the show."""
    path = settings_path(data_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(target.model_dump(), indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except Exception as e:
        logger.warning("Could not save output target to %s: %s", path, e)
        return False


def load_or_create_cid(data_dir: Optional[Path] = None) -> bytes:
    """This install's sACN component identifier, created on first use."""
    path = cid_path(data_dir)
    try:
        return uuid.UUID(path.read_text(encoding="utf-8").strip()).bytes
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("Replacing unreadable sACN CID at %s: %s", path, e)

    cid = uuid.uuid4()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(str(cid), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as e:
        logger.warning("Could not persist sACN CID to %s (it will change on restart): %s", path, e)
    return cid.bytes
