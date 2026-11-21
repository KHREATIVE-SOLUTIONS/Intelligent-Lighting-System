"""
A look's strobe mode, on the live renderer
==========================================

The look library gives some looks a strobe mode: a flash on the beat, on the
eighth notes, locked to the kick. The live renderer has one strobe of its own,
at the front of a drop, and until now every look got that one.

**What a mode may do, and it is very little, on purpose.** It names a rate,
in flashes per second, for the renderer's own drop strobe to run at instead
of its usual one. That is all.

* It never opens a window. The strobe runs when the renderer says so (the
  first moments of a drop the detector named, strobing switched on by the
  accent governor and the venue's policy), and at no other time.
* It never asks for more. The rate it names is used only if it is lower than
  the renderer's own. (A lower rate is not always fewer flashes in a window
  by count: where the grid falls when the window opens can add or lose one.
  The number in any one second is the venue's limit either way.)
* It never passes the limit by. The rate it names is handed to the same clamp
  as the renderer's own (`EffectsEngine._strobe_grid_hz`, the venue's
  `strobe_hz_cap`), and that clamp decides. This module does not read or
  write the cap, the duty, or whether strobing is on.

So a mode can make a drop's strobe slower and musical - once a beat instead
of as fast as the venue allows - and can do nothing else.

**The speed limit.** A rate that the venue's limit leaves no room for is
halved until it fits: eighth notes become beats, beats become every other
beat. It stays a division of the tempo instead of being clipped to a number
that has nothing to do with the music.

**What is not performed.**

* ``kick_locked``, ``snare_locked`` and ``drum_hits`` were written to follow
  real drum hits. The drum detector was measured and cannot separate drums,
  so they run at the rate those hits would have on a four-on-the-floor grid:
  every beat, every other beat, every beat.
* The rate is the beat's; the flashes are not placed on the beat. The
  renderer's strobe runs on the engine's clock, and that was left alone:
  placing flashes by the beat clock would let a jump in the tempo estimate
  add flashes.
* ``fast_synth``, ``random_burst`` and ``none`` are the renderer's own strobe,
  unchanged.
* ``buildup_accel``, the blinder modes, and any mode on a look outside the
  drop need a strobe window where the renderer has none. Not performed.
"""

from __future__ import annotations

from typing import Optional

# Flashes per beat, for the modes that name a musical rate.
FLASHES_PER_BEAT = {
    "beat_pulse": 1.0,
    "eighth_note": 2.0,
    "kick_locked": 1.0,
    "snare_locked": 0.5,
    "drum_hits": 1.0,
}

# A mode is never slowed past one flash every this many beats; if the venue's
# limit leaves no room even for that, the mode is not performed.
SLOWEST_BEATS_PER_FLASH = 8.0


def mode_of(look) -> str:
    """A library look's strobe mode. No look, or nothing set, is ``none``."""
    return str(getattr(look, "strobe_mode", "") or "none").lower()


def mode_hz(mode: str, bpm: float, allowed_hz: float) -> Optional[float]:
    """The rate a mode asks the drop strobe to run at, or None to leave it alone.

    `allowed_hz` is the most the venue's limit will let through, as the
    renderer's own clamp reports it. A rate above it is halved until it is
    not. None when the mode names no musical rate, the tempo is unknown, or
    the limit leaves no room.
    """
    per_beat = FLASHES_PER_BEAT.get(str(mode or "").lower())
    try:
        beats_per_s = float(bpm) / 60.0
        allowed = float(allowed_hz)
    except (TypeError, ValueError):
        return None
    if per_beat is None or not (0.0 < beats_per_s < 100.0) or not (0.0 < allowed < 1.0e6):
        return None
    slowest = 1.0 / SLOWEST_BEATS_PER_FLASH
    while per_beat * beats_per_s > allowed:
        per_beat /= 2.0
        if per_beat < slowest:
            return None
    return per_beat * beats_per_s
