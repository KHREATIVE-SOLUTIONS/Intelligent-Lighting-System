"""
Remembered Audio Capture Choice
===============================

The operator picks the capture device once, from the dashboard. That choice
used to live only in memory, so after a power cut or a reboot the show came
back with no audio until someone picked the device again, which on an
unattended install means a dead night.

This keeps the choice in a small JSON file next to the database: the device's
name (indices move between boots, names do not) and whether capture was left
running. Boot starts it again from here. A missing or unreadable file means
nothing was chosen, never an error.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

FILENAME = "audio_capture.json"


def settings_path(data_dir: Optional[Path] = None) -> Path:
    if data_dir is None:
        from app.core.config import settings

        data_dir = settings.data_dir
    return Path(data_dir) / FILENAME


def load(data_dir: Optional[Path] = None) -> dict:
    """The remembered choice: {"device_name": str|None, "running": bool}."""
    path = settings_path(data_dir)
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return {"device_name": None, "running": False}
    except Exception as e:
        logger.warning("Ignoring unreadable audio capture settings at %s: %s", path, e)
        return {"device_name": None, "running": False}
    name = raw.get("device_name") if isinstance(raw, dict) else None
    choice = {
        "device_name": name if isinstance(name, str) and name.strip() else None,
        "running": bool(raw.get("running")) if isinstance(raw, dict) else False,
    }
    # Present only when one was remembered: Windows lists the same input once
    # per host API, and this says which of those entries was picked.
    hostapi = raw.get("hostapi") if isinstance(raw, dict) else None
    if choice["device_name"] and isinstance(hostapi, str) and hostapi.strip():
        choice["hostapi"] = hostapi
    return choice


def save(
    device_name: Optional[str],
    running: bool,
    data_dir: Optional[Path] = None,
    hostapi: Optional[str] = None,
) -> None:
    """Remember the choice. Best effort: a read-only disk must not stop the show."""
    path = settings_path(data_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        record = {"device_name": device_name, "running": bool(running)}
        if device_name and hostapi:
            record["hostapi"] = hostapi
        tmp.write_text(json.dumps(record))
        os.replace(tmp, path)
    except Exception as e:
        logger.warning("Could not save audio capture settings to %s: %s", path, e)


def set_running(running: bool, data_dir: Optional[Path] = None) -> None:
    """Keep the remembered device, change only whether capture should run."""
    remembered = load(data_dir)
    save(remembered["device_name"], running, data_dir, hostapi=remembered.get("hostapi"))
