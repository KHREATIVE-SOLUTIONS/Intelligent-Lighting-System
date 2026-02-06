"""
Utility Helper Functions
========================

Common utility functions used across the application.
"""

import hashlib
import json
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import numpy as np


def generate_fingerprint_hash(data: bytes) -> str:
    """Generate a SHA-256 hash for fingerprint data."""
    return hashlib.sha256(data).hexdigest()


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max."""
    return max(min_val, min(max_val, value))


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between a and b."""
    return a + (b - a) * t


def ease_in_out(t: float) -> float:
    """Ease in/out curve for smooth transitions."""
    if t < 0.5:
        return 2 * t * t
    return 1 - (-2 * t + 2) ** 2 / 2


def dmx_to_percent(value: int) -> float:
    """Convert DMX value (0-255) to percentage (0-1)."""
    return value / 255.0


def percent_to_dmx(value: float) -> int:
    """Convert percentage (0-1) to DMX value (0-255)."""
    return int(clamp(value, 0.0, 1.0) * 255)


def degrees_to_dmx(degrees: float, max_degrees: float) -> int:
    """Convert degrees to DMX value based on max range."""
    return int((degrees / max_degrees) * 255)


def dmx_to_degrees(value: int, max_degrees: float) -> float:
    """Convert DMX value to degrees based on max range."""
    return (value / 255.0) * max_degrees


def rgb_to_dmx(r: int, g: int, b: int) -> Dict[str, int]:
    """Convert RGB values to DMX channel values."""
    return {
        'red': clamp(r, 0, 255),
        'green': clamp(g, 0, 255),
        'blue': clamp(b, 0, 255),
    }


def hsv_to_rgb_dmx(h: float, s: float, v: float) -> Dict[str, int]:
    """Convert HSV (0-1 ranges) to RGB DMX values."""
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return {
        'red': int(r * 255),
        'green': int(g * 255),
        'blue': int(b * 255),
    }


def calculate_bpm_from_intervals(intervals: List[float]) -> Optional[float]:
    """Calculate BPM from a list of beat intervals in seconds."""
    if not intervals:
        return None

    # Filter outliers (intervals outside typical range)
    valid = [i for i in intervals if 0.25 < i < 2.0]  # 30-240 BPM
    if not valid:
        return None

    avg_interval = sum(valid) / len(valid)
    return 60.0 / avg_interval


def smooth_value(
    current: float,
    target: float,
    smoothing: float = 0.1
) -> float:
    """Smooth a value towards a target (exponential moving average)."""
    return current + (target - current) * smoothing


def normalize_audio(audio: np.ndarray) -> np.ndarray:
    """Normalize audio to -1.0 to 1.0 range."""
    max_val = np.max(np.abs(audio))
    if max_val > 0:
        return audio / max_val
    return audio


def calculate_rms(audio: np.ndarray) -> float:
    """Calculate RMS (root mean square) energy of audio."""
    return float(np.sqrt(np.mean(audio ** 2)))


def db_to_linear(db: float) -> float:
    """Convert decibels to linear amplitude."""
    return 10 ** (db / 20)


def linear_to_db(amplitude: float) -> float:
    """Convert linear amplitude to decibels."""
    if amplitude <= 0:
        return -float('inf')
    return 20 * np.log10(amplitude)


def format_timecode(seconds: float, fps: int = 30) -> str:
    """Format seconds as timecode (HH:MM:SS:FF)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    frames = int((seconds % 1) * fps)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"


def parse_timecode(timecode: str, fps: int = 30) -> float:
    """Parse timecode string to seconds."""
    parts = timecode.split(':')
    if len(parts) == 4:
        hours, minutes, seconds, frames = map(int, parts)
        return hours * 3600 + minutes * 60 + seconds + frames / fps
    elif len(parts) == 3:
        hours, minutes, seconds = map(int, parts)
        return hours * 3600 + minutes * 60 + seconds
    return 0.0


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split a list into chunks of specified size."""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
