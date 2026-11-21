"""
The look library, on the live renderer
======================================

`look_library` holds 67 designed looks - "predrop_freeze", "drop_fast_chase",
"moonlight_drift" - each tagged with the sections, moods, energy and kinds of
audio it suits, and a selector that picks among the ones that fit by weighted
random while avoiding the last few it used. That is what keeps a night from
repeating itself without ever picking something wrong for the moment.

It was written for an earlier engine and named movements, dimmer effects and
strobe modes this engine does not have, so it sat unused. This module is the
join. It asks the library's own selector for a look, using what this engine
can honestly say about the music, and translates the part of the look this
renderer can perform today.

**Performed now:** which look, its movement (mapped onto `live_looks`), and its
speed and size.

**Not performed yet, and deliberately:** the look's dimmer effect, chase,
bump, base level, strobe mode, blinder, colour treatment and fixture-group
isolation. Those change brightness and flashing, which is where the safety
limits and the drop contract live, so each will come in on its own with the
bench watching. Until then a look's name promises more than it delivers:
"drop_strobe_eighth" moves like itself but does not strobe on eighth notes,
and should not until the accent governor is the one doing it.

**What the selector is told about the music:**

* section - the engine's own.
* energy - the look library thinks on a 0-1 scale where a drop is 0.6-1.0 and
  a breakdown 0-0.3. The engine's raw energy follows playback level, so this
  uses the section's place on that scale, moved up or down by how loud the
  moment is against the track's own running level.
* mood - from valence and arousal. They are rough, and mood is only a bonus.
* audio character - only the tags this engine can stand behind (heavy bass,
  sparse, full, percussive, an impact). The library also knows vocal-heavy,
  synth-lead, drum-breakdown and others; nothing here can detect those
  reliably yet, so they are never claimed.
* the musical fingerprint - not supplied. The modules that produced it were
  measured in August 2026 and could not tell the things they described apart.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from . import live_looks
from .look_library import LOOK_LIBRARY, LookPreset, LookSelector

# The library's fifteen movements, as positions and motions.
MOVEMENT_TO_LOOK: Dict[str, str] = {
    "fly_out": "centre_fly_fan",
    "center_burst": "columns_fly_fan",
    "slow_breathe": "centre_tilt_unison",
    "tilt_wave": "columns_tilt_ripple",
    "cascade": "columns_tilt_rows",
    "audience_scan": "columns_sweep_ripple",
    "sync_sweep": "columns_sweep_unison",
    "mirror_sweep": "fan_sweep_unison",
    "stagger_sweep": "fan_sweep_rows",
    "symmetric_fan": "fan_tilt_unison",
    "symmetric_circle": "columns_circle_unison",
    "figure_eight_wide": "fan_circle_ripple",
    "cross_tilt": "cross_tilt_unison",
    "ballyhoo": "cross_circle_rows",
    "snap_look": "cross_hold",
}

# Where each section sits on the library's energy scale.
SECTION_ENERGY: Dict[str, float] = {
    "breakdown": 0.15, "verse": 0.40, "buildup": 0.60, "chorus": 0.75, "drop": 0.85,
}
DEFAULT_SECTION_ENERGY = 0.40
# How far a loud or quiet moment moves it. Programme level 0.5 is "as loud as
# this track's own running level".
LEVEL_SWING = 0.5

# How much likelier a club style makes the looks that move its way. A weight,
# not a filter: every look that fits the moment stays in the running, so a
# style never shrinks the choice and the night still does not repeat itself.
STYLE_LEAN = 2.5

_BY_NAME: Dict[str, LookPreset] = {look.name: look for look in LOOK_LIBRARY}


def movement_of(look: Optional[LookPreset]) -> Tuple[str, float, float]:
    """(movement, speed, size) for a library look, in `live_looks` terms."""
    if look is None:
        return live_looks.DEFAULT_LOOK, 1.0, 1.0
    name = MOVEMENT_TO_LOOK.get(look.movement_pattern, live_looks.DEFAULT_LOOK)
    return name, float(look.speed_factor), float(look.amplitude_factor)


def look_energy(section: str, programme_level: Optional[float]) -> float:
    """The moment's energy on the library's scale."""
    base = SECTION_ENERGY.get(str(section or "").lower(), DEFAULT_SECTION_ENERGY)
    if programme_level is None:
        return base
    return max(0.0, min(1.0, base + (float(programme_level) - 0.5) * LEVEL_SWING))


def mood_of(valence: float, arousal: float) -> str:
    """One of the library's eight moods, from valence and arousal (0-1)."""
    bright = float(valence) >= 0.5
    a = float(arousal)
    if a < 0.25:
        return "ethereal" if bright else "ambient"
    if a < 0.45:
        return "chill" if bright else "dark"
    if a < 0.70:
        return "party" if bright else "driving"
    return "euphoric" if bright else "aggressive"


def audio_characters(
    *,
    energy: float,
    bass: float,
    flux: float,
    section: str,
    programme_level: Optional[float],
    impact: bool,
) -> List[str]:
    """The library's audio tags this engine can stand behind right now."""
    tags: List[str] = []
    if bass >= 0.62:
        tags.append("heavy_bass")
    if energy < 0.2:
        tags.append("sparse_ambient")
    if programme_level is not None and programme_level >= 0.6 and section in ("chorus", "drop"):
        tags.append("full_wall")
    if flux >= 0.6:
        tags.append("fast_transients")
    elif flux >= 0.4:
        tags.append("percussive")
    if impact:
        tags.append("impact")
    return tags


class LibraryChooser:
    """Asks the look library for the next look, and never hands back the one running."""

    def __init__(self, seed: Optional[int] = None):
        self._selector = LookSelector(seed=seed)
        self._current: Optional[LookPreset] = None

    @property
    def current(self) -> Optional[LookPreset]:
        return self._current

    def choose(
        self,
        *,
        section: str,
        energy: float,
        mood: str,
        characters: Sequence[str] = (),
        bar: int = 0,
        style_movements: Optional[Sequence[str]] = None,
    ) -> Optional[LookPreset]:
        """The next look for this moment, or None if the library has none for the section.

        `style_movements` is a club style's lean: looks that move in one of
        those ways are `STYLE_LEAN` times likelier. Nothing is ruled out.
        """
        section = str(section or "").lower()
        wanted = set(style_movements or ())

        def style_weight(look: LookPreset) -> float:
            return STYLE_LEAN if MOVEMENT_TO_LOOK.get(look.movement_pattern) in wanted else 1.0

        lean = style_weight if wanted else None

        running = self._current.name if self._current is not None else None
        pick = None
        # The selector avoids its last four looks, but its last resort does
        # not. Ask again rather than hand back the look already running.
        for _ in range(6):
            pick = self._selector.select_look(
                section, float(energy), mood, int(bar), force_new=True,
                audio_characters=list(characters), lean=lean,
            )
            if pick is None or pick.name != running:
                break
        if pick is not None and pick.name == running:
            # Still the running look after asking again: take another one
            # tagged for the section, whatever its energy. Only reachable when
            # almost nothing fits the moment.
            others = [look for look in LOOK_LIBRARY if section in look.sections and look.name != running]
            if others:
                pick = others[int(bar) % len(others)]
        if pick is not None:
            self._current = pick
        return pick


def look_named(name: str) -> Optional[LookPreset]:
    return _BY_NAME.get(name)
