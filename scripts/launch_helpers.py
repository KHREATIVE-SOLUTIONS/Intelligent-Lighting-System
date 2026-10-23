"""
Launch Helpers
==============

Small, dependency-free pieces shared by start.py and the capture scripts, kept
apart so they can be tested without an audio stack.

A venue box is started by a script nobody watches, so each of these replaces
something that used to need a person: a typed device number, a rig id that
was only right on the developer's database, and a login the launcher could not
do for itself.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional
from urllib.parse import quote


def rig_id_from_env(value: Optional[str] = None) -> Optional[int]:
    """The rig to drive from ILS_RIG_ID, or None to drive the live (active) rig.

    Rig 5 used to be hardcoded. On any database but the one it was written on,
    that is someone else's rig or none at all.
    """
    raw = os.getenv("ILS_RIG_ID", "") if value is None else value
    raw = str(raw).strip()
    if not raw:
        return None
    try:
        rig_id = int(raw)
    except ValueError:
        print(f"Ignoring ILS_RIG_ID={raw!r}: not a number; driving the active rig")
        return None
    return rig_id if rig_id > 0 else None


def reactive_on_message(rig_id: Optional[int]) -> str:
    """The reactive_on message; without a rig id the backend drives the active rig."""
    message = {"type": "reactive_on"}
    if rig_id is not None:
        message["rig_id"] = rig_id
    return json.dumps(message)


def backend_ws_url(base: str, path: str, token: Optional[str]) -> str:
    """A websocket URL for the backend, carrying the operator token when there is one."""
    url = base.replace("http://", "ws://").replace("https://", "wss://").rstrip("/") + path
    if token:
        url += f"?token={quote(token)}"
    return url


def backend_answers(url: str, timeout: float = 2.0,
                    opener: Callable = urllib.request.urlopen) -> bool:
    """True when the backend answers at all.

    /health returns 503 while a service is degraded (no database, models still
    loading); that is a backend that is up, so the launcher must not wait out
    its whole timeout on it.
    """
    try:
        opener(url, timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def mint_local_token(python: str, backend_dir: Path, lifetime_seconds: int = 24 * 3600) -> Optional[str]:
    """Issue an operator token with this box's own signing key.

    The launcher runs on the box the backend runs on and can read the same
    key, so it signs its own capture session in rather than leaving the audio
    feed refused when login is on. Returns None when it cannot.
    """
    code = (
        "from app.core.security import issue_token; "
        f"print(issue_token(lifetime_seconds={int(lifetime_seconds)}))"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", code], cwd=str(backend_dir),
            capture_output=True, text=True, timeout=60,
        )
    except Exception as exc:
        print(f"  Could not issue a capture token: {exc}")
        return None
    token = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if result.returncode != 0 or token.count(".") != 1:
        print(f"  Could not issue a capture token: {result.stderr.strip()[-300:]}")
        return None
    return token


def pick_device(devices: List[dict], recommended: dict, choice: Optional[str] = None,
                interactive: Optional[bool] = None,
                ask: Callable[[], str] = input) -> Optional[dict]:
    """Choose the capture device without blocking an unattended start.

    `choice` (from --device or ILS_AUDIO_DEVICE) is a device index or part of
    its name. With no choice, a person at a terminal is asked; anything else
    takes the recommended device instead of waiting for ever on a prompt.
    """
    if not devices:
        return None
    if choice is not None and str(choice).strip():
        wanted = str(choice).strip()
        for dev in devices:
            if wanted.isdigit() and dev["index"] == int(wanted):
                return dev
        for dev in devices:
            if wanted.lower() in dev["name"].lower():
                return dev
        print(f"  Audio device {wanted!r} not found, using recommended")
        return recommended

    if interactive is None:
        interactive = sys.stdin is not None and sys.stdin.isatty()
    if not interactive:
        return recommended

    print("\nEnter device number (or press Enter for recommended): ", end="", flush=True)
    try:
        answer = ask().strip()
    except (EOFError, KeyboardInterrupt):
        return recommended
    if not answer:
        return recommended
    return pick_device(devices, recommended, choice=answer, interactive=False)
