"""The compact level / tempo block a UI meter reads.

One builder for both places it is published: the websocket analysis payload
(main.py `_broadcast_lighting_state`, as `meter`) and
GET /api/audio/capture/status (also as `meter`). Existing payload fields are
left exactly as they were; this only adds a key.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def build_meter_block(capture: Any = None, engine: Any = None) -> Dict[str, Optional[Any]]:
    block: Dict[str, Optional[Any]] = {
        "rms": 0.0, "peak": 0.0, "rms_dbfs": -120.0, "peak_dbfs": -120.0,
        "running": False, "silent": False, "device_name": None, "capture_method": None,
        "block_age_s": None,
        "bpm": None, "beat_count": 0, "seconds_since_beat": None, "beat_phase": None,
        "clock_locked": False, "pulse_level": 0.0, "pulse_count": 0, "makeup_gain": 1.0,
    }
    level = getattr(capture, "level_meter", None)
    if callable(level):
        try:
            block.update(level())
        except Exception:
            pass
    beat = getattr(engine, "beat_meter", None)
    if callable(beat):
        try:
            block.update(beat())
        except Exception:
            pass
    return block
