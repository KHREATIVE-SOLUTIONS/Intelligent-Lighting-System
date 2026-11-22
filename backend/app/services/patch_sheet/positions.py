"""
Position Names
==============

A patch sheet that says anything about where a fixture hangs says it in a
word or two: "US Truss", "LX 2", "Floor", "SL Tower", "Drum Riser", "DJ Booth".
This reads such a name into the little it actually states - what kind of place,
how far upstage, which side - and nothing more. A name it cannot read is
returned as None and the fixture is placed by its type instead.

Depth is a fraction: 0 is the upstage edge, 1 the downstage edge.
Side is "sl", "sr" or "c" as the sheet wrote it. Which way round that is on the
plan is the layout generator's decision, not this module's.
"""

import re
from dataclasses import dataclass
from typing import Optional

OVERHEAD = "overhead"
FLOOR = "floor"
TOWER = "tower"
RISER = "riser"
BOOTH = "booth"
FOH = "foh"

_DEPTH = {
    "us": 0.0, "upstage": 0.0, "rear": 0.0, "back": 0.0,
    "ms": 0.5, "mid": 0.5, "midstage": 0.5, "middle": 0.5,
    "ds": 1.0, "downstage": 1.0, "front": 1.0,
}
# "USL" and the like: a depth and a side in one word.
_CORNER = {
    depth_word + side_letter: (depth, side)
    for depth_word, depth in (("us", 0.0), ("ms", 0.5), ("ds", 1.0))
    for side_letter, side in (("l", "sl"), ("r", "sr"), ("c", "c"))
}
_SIDE = {
    "sl": "sl", "left": "sl", "sr": "sr", "right": "sr",
    "centre": "c", "center": "c", "ctr": "c",
    # House left is the audience's left: the other side from stage left.
    "hl": "sr", "hr": "sl",
}
# Checked in this order: "DJ booth truss" is the booth, "floor SL" is the floor.
_FAMILY = (
    (BOOTH, ("dj", "booth", "desk")),
    (RISER, ("riser", "risers", "drum", "drums")),
    (TOWER, ("tower", "towers", "ladder", "ladders", "boom", "booms", "totem", "totems",
             "wing", "wings", "side", "sides", "goalpost", "stand", "stands", "tree", "trees")),
    (FLOOR, ("floor", "ground", "deck", "gnd")),
    (FOH, ("foh",)),
    (OVERHEAD, ("truss", "trusses", "tr", "lx", "electric", "electrics", "elec", "pipe", "pipes",
                "bar", "bars", "batten", "battens", "roof", "grid", "flown", "overhead", "oh",
                "ring", "circle", "bridge")),
)
_RING = ("ring", "circle")


@dataclass(frozen=True)
class HangHint:
    """What a position name states."""

    family: str
    depth: Optional[float] = None
    side: str = ""
    number: Optional[int] = None
    ring: bool = False


def classify_position(label: str) -> Optional[HangHint]:
    """What `label` says about where a fixture hangs, or None when it says nothing readable."""
    text = (label or "").lower()
    text = text.replace("u/s", "us").replace("d/s", "ds").replace("m/s", "ms")
    tokens = re.findall(r"[a-z]+|\d+", text)
    if not tokens:
        return None

    depth: Optional[float] = None
    side = ""
    number: Optional[int] = None
    for token in tokens:
        if token.isdigit():
            if number is None:
                number = int(token)
        elif token in _CORNER:
            depth, side = _CORNER[token]
        elif token in _DEPTH and depth is None:
            depth = _DEPTH[token]
        elif token in _SIDE and not side:
            side = _SIDE[token]
    if "house" in tokens and side in ("sl", "sr"):
        side = "sr" if side == "sl" else "sl"

    family = next((name for name, words in _FAMILY if any(t in words for t in tokens)), "")
    if not family:
        if depth is not None:
            family = OVERHEAD       # "US", "DSL": a truss is what is meant
        elif side in ("sl", "sr"):
            family = TOWER          # "SL" on its own: the side of the stage
        else:
            return None
    return HangHint(
        family=family, depth=depth, side=side, number=number,
        ring=any(t in _RING for t in tokens),
    )
