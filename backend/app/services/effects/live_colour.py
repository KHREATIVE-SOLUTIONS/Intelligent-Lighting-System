"""
Live colour: saturated palette hues, changed on the phrase
==========================================================

The live renderer used to blend its base colour every frame toward a mood
colour made by averaging four corner colours, then mix up to 40 % white into
it on bass hits, then average r, g and b together in the breakdown. On dense
music that is a pale mauve, and the breakdown is grey.

This module is the replacement, as pure functions the engine calls:

* a short, ordered list of saturated **anchor hues** for each song palette,
  taken from the same hue ranges `ColorMapper` uses;
* the **next hue**, stepped deterministically on a phrase or section change
  and always at least `min_step_deg` from the one it replaces;
* the **saturation** for a section (never below the floor);
* a **crossfade** made along the short way round the hue wheel at constant
  saturation, so a fade between distant hues never passes through grey the
  way an RGB blend does;
* the largest **white accent** a colour can take and stay above the floor.

Brightness is the dimmer's job, so colours are made at full value.
"""

from __future__ import annotations

import colorsys
from typing import Dict, Optional, Sequence, Tuple

from .color_mapper import ColorPalette

# Ordered so that consecutive steps alternate the palette's two families.
PALETTE_HUES: Dict[ColorPalette, Tuple[float, ...]] = {
    ColorPalette.EDM: (200.0, 305.0, 240.0, 330.0, 265.0, 185.0),
    ColorPalette.ROCK: (0.0, 220.0, 25.0, 240.0),
    ColorPalette.AMBIENT: (190.0, 110.0, 210.0, 135.0),
    ColorPalette.HIP_HOP: (280.0, 45.0, 300.0, 5.0),
    ColorPalette.POP: (0.0, 180.0, 60.0, 240.0, 120.0, 300.0),
    ColorPalette.TECHNO: (210.0, 125.0, 235.0, 160.0),
    ColorPalette.HOUSE: (30.0, 330.0, 50.0, 10.0),
    ColorPalette.DUBSTEP: (280.0, 120.0, 295.0, 135.0),
}
DEFAULT_HUES = PALETTE_HUES[ColorPalette.EDM]

# A breakdown takes the palette's coolest hue when it has one in this band.
_COOL_BAND = (170.0, 300.0)


def hue_distance(a: float, b: float) -> float:
    """Degrees between two hues the short way round (0-180)."""
    d = abs((float(a) - float(b)) % 360.0)
    return min(d, 360.0 - d)


def anchors(palette: Optional[ColorPalette]) -> Tuple[float, ...]:
    return PALETTE_HUES.get(palette, DEFAULT_HUES) if palette is not None else DEFAULT_HUES


def next_hue(
    palette_hues: Sequence[float],
    step: int,
    previous: Optional[float],
    section: str,
    min_step_deg: float = 40.0,
) -> float:
    """The hue for the `step`-th recolour.

    Walks the palette's anchors in order, skipping any within `min_step_deg`
    of the hue being replaced, so every phrase change is a visible change. A
    breakdown prefers a cool anchor. Deterministic: the same music gives the
    same colours.
    """
    hues = [float(h) % 360.0 for h in palette_hues] or list(DEFAULT_HUES)
    n = len(hues)
    order = [hues[(int(step) + k) % n] for k in range(n)]
    if str(section or "").lower() == "breakdown":
        cool = [h for h in order if _COOL_BAND[0] <= h <= _COOL_BAND[1]]
        order = cool + [h for h in order if h not in cool]
    if previous is None:
        return order[0]
    for h in order:
        if hue_distance(h, previous) >= float(min_step_deg):
            return h
    # Every anchor is close to the last one: take the farthest.
    return max(order, key=lambda h: hue_distance(h, previous))


def saturation_for(section: str, saturation: float, breakdown_saturation: float, floor: float) -> float:
    """Saturation of the base colour in a section, never below the floor."""
    s = breakdown_saturation if str(section or "").lower() in ("breakdown", "bridge") else saturation
    return max(float(floor), min(1.0, float(s)))


def _smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def faded_hue(start_hue: float, end_hue: float, progress: float) -> float:
    """The hue `progress` (0-1) of the way from one hue to another, the short way round."""
    delta = ((float(end_hue) - float(start_hue) + 180.0) % 360.0) - 180.0
    return (float(start_hue) + delta * _smoothstep(progress)) % 360.0


def colour(hue_deg: float, saturation: float, value: float = 1.0) -> Tuple[float, float, float]:
    return colorsys.hsv_to_rgb((float(hue_deg) % 360.0) / 360.0, max(0.0, min(1.0, saturation)),
                               max(0.0, min(1.0, value)))


def white_accent_cap(saturation: float, floor: float) -> float:
    """The most white a colour of this saturation can take and keep `floor`.

    At full value, mixing a share `w` of white gives saturation `s·(1 - w)`.
    """
    s = float(saturation)
    if s <= 0.0:
        return 0.0
    return max(0.0, 1.0 - float(floor) / s)


class HueFade:
    """The base hue, crossfading on the hue wheel after each change."""

    def __init__(self) -> None:
        self.start: Optional[float] = None
        self.end: Optional[float] = None
        self.since: float = 0.0
        self.seconds: float = 1.0
        self.steps: int = 0

    @property
    def ready(self) -> bool:
        return self.end is not None

    def change(self, hue: float, now: float, seconds: float) -> None:
        """Begin a fade to `hue` from wherever the fade is now (no fade the first time)."""
        current = self.at(now)
        self.start = float(hue) if current is None else current
        self.end = float(hue) % 360.0
        self.since = float(now)
        self.seconds = max(0.0, float(seconds))
        self.steps += 1

    def at(self, now: float) -> Optional[float]:
        if self.end is None:
            return None
        if self.start is None or self.seconds <= 0.0:
            return self.end
        return faded_hue(self.start, self.end, (float(now) - self.since) / self.seconds)

    def reset(self) -> None:
        self.__init__()
