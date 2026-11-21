"""
Channel Value Ranges
====================

What a fixture profile says the bytes on its shutter, strobe and dimmer
channels mean, in the three terms every writer needs: the value that lets
light through without flashing (open), the value that blocks it (closed), and
the span that rates the fixture's own strobe.

A profile states this as `value_ranges`, a list of {name, min_value,
max_value}. Without it a writer can only assume 255 opens a shutter and 0
rests a strobe channel, which is wrong often enough to matter: several pars
name 0 on their strobe channel "Closed", so the assumed resting value blacks
them out.

Nothing here decides whether a strobe may fire or how fast. That stays with
the engine's rate caps and the output stage; this only says which byte means
what once that decision is made.
"""

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Tuple

SHUTTER = "shutter"
STROBE = "strobe"
DIMMER = "dimmer"
RANGED_CHANNEL_TYPES = (SHUTTER, STROBE, DIMMER)

# What every writer sent before profiles carried ranges, and still sends for a
# channel whose profile names nothing usable.
FALLBACK_SHUTTER_OPEN = 255
FALLBACK_STROBE_IDLE = 0
FALLBACK_CLOSED = 0

# A range entered without a manual to point at says so in its name.
ASSUMED_MARK = "(assumed)"

# A range that flashes in some way other than a plain, steady strobe. The
# engine asks for a rate; these answer with a pattern.
_STROBE_VARIANTS = (
    "random", "puls", "ramp", "zone", "sound", "effect", "burst", "lightning",
    "spike", "sync", "music",
)
_OPEN_WORD = re.compile(r"\bopen\b")
_CLOSED_WORDS = ("closed", "blackout", "black out")
_IDLE_WORDS = ("no function", "no func", "no strobe", "strobe off")
_DIMMER_WORDS = ("dimmer", "intensity", "brightness", "master")
_HZ_SPAN = re.compile(r"(\d+(?:\.\d+)?)\s*hz\s*-+>\s*(\d+(?:\.\d+)?)\s*hz")
_FAST_TO_SLOW = re.compile(r"fast\s*-+>\s*slow")


def _byte(value: Any) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if 0 <= number <= 255 else None


def _unit(value: Any) -> float:
    """A 0-1 level. NaN and garbage read as 0: no strobe, no light."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, min(1.0, number))


def _entries(value_ranges: Any) -> List[Tuple[str, int, int]]:
    """(lowercased name, min, max) for every entry that is a real byte span."""
    if not isinstance(value_ranges, (list, tuple)):
        return []
    entries: List[Tuple[str, int, int]] = []
    for entry in value_ranges:
        if not isinstance(entry, dict):
            continue
        low = _byte(entry.get("min_value"))
        high = _byte(entry.get("max_value"))
        if low is None or high is None:
            continue
        if low > high:
            low, high = high, low
        name = str(entry.get("name") or "").lower().replace(ASSUMED_MARK, "").strip()
        entries.append((name, low, high))
    return entries


def _is_strobe(name: str) -> bool:
    return "strob" in name and not any(word in name for word in _IDLE_WORDS)


def _is_variant(name: str) -> bool:
    return any(word in name for word in _STROBE_VARIANTS)


def _is_open(name: str) -> bool:
    return bool(_OPEN_WORD.search(name)) and not _is_strobe(name) and not _is_variant(name)


def _is_closed(name: str) -> bool:
    if _is_strobe(name) or _is_variant(name):
        return False
    return any(word in name for word in _CLOSED_WORDS) or name in ("close", "off", "shut")


def _is_idle(name: str) -> bool:
    return any(word in name for word in _IDLE_WORDS)


def _pick(spans: Iterable[Tuple[int, int]], preferred: int) -> Optional[int]:
    """A byte inside one of `spans`: `preferred` when it qualifies, else the
    middle of the first span, which is the value furthest from either
    neighbour's boundary."""
    spans = list(spans)
    if not spans:
        return None
    for low, high in spans:
        if low <= preferred <= high:
            return preferred
    low, high = spans[0]
    return (low + high) // 2


def _strobe_span(entries: List[Tuple[str, int, int]]) -> Optional[Tuple[int, int]]:
    """(slowest byte, fastest byte) of the plain strobe range, if there is one."""
    plain = [entry for entry in entries if _is_strobe(entry[0]) and not _is_variant(entry[0])]
    if not plain:
        return None
    # A qualifier in brackets narrows the range to part of the fixture or to
    # one of several modes; the unqualified range is the fixture's strobe.
    unqualified = [entry for entry in plain if "(" not in entry[0]]
    name, low, high = (unqualified or plain)[0]

    reversed_span = bool(_FAST_TO_SLOW.search(name))
    hz = _HZ_SPAN.search(name)
    if hz:
        reversed_span = float(hz.group(1)) > float(hz.group(2))
    return (high, low) if reversed_span else (low, high)


def _dimmer_span(entries: List[Tuple[str, int, int]]) -> Optional[Tuple[int, int]]:
    for name, low, high in entries:
        if _is_strobe(name) or _is_variant(name):
            continue
        if any(word in name for word in _DIMMER_WORDS):
            return (low, high)
    return None


@dataclass(frozen=True)
class ChannelRangeValues:
    """One channel's profile ranges, reduced to the bytes a writer needs.

    `kind` is the channel type: "shutter", "strobe" or "dimmer". A field is
    None where the profile names no such range; the methods then answer with
    the value writers used before ranges existed.
    """

    kind: str
    open: Optional[int] = None
    closed: Optional[int] = None
    strobe: Optional[Tuple[int, int]] = None      # (slowest, fastest)
    dimmer: Optional[Tuple[int, int]] = None      # (0%, 100%)
    assumed: bool = False

    def open_byte(self) -> int:
        """Light through, no flashing. On a strobe channel: not strobing."""
        if self.open is not None:
            return self.open
        return FALLBACK_SHUTTER_OPEN if self.kind == SHUTTER else FALLBACK_STROBE_IDLE

    def closed_byte(self) -> int:
        """Light blocked. A channel that cannot block it rests instead."""
        if self.closed is not None:
            return self.closed
        if self.kind == STROBE and self.open is not None:
            # The profile names a resting value and no closed one: this
            # channel only rates a strobe, and dark is the dimmer's job.
            return self.open
        return FALLBACK_CLOSED

    def strobe_byte(self, rate: Any) -> int:
        """The byte for the fixture's own strobe at `rate`, 0-1 slow to fast.

        A rate of 0 is the open value. So is any rate on a channel whose
        profile names no plain strobe range: every other byte on it already
        means something else, and a steady light is the safe reading.
        """
        level = _unit(rate)
        if level <= 0.0 or self.strobe is None:
            return self.open_byte()
        slow, fast = self.strobe
        return max(0, min(255, slow + int(level * (fast - slow))))

    def dimmer_byte(self, level: Any) -> int:
        """The byte for an intensity of `level`, 0-1. Zero is always 0."""
        amount = _unit(level)
        if amount <= 0.0:
            return 0
        low, high = self.dimmer if self.dimmer is not None else (0, 255)
        return max(0, min(255, low + int(amount * (high - low))))


def channel_type_name(channel_type: Any) -> str:
    """A channel type as its plain string, whether enum member or text."""
    return str(getattr(channel_type, "value", channel_type) or "").strip().lower()


def resolve_channel_ranges(channel_type: Any, value_ranges: Any) -> Optional[ChannelRangeValues]:
    """What a channel's `value_ranges` say, or None when they say nothing usable.

    None is the answer for a channel type other than shutter, strobe and
    dimmer, for a channel with no ranges, and for ranges that name no open,
    closed, strobe or intensity span. The caller then keeps its fixed numbers.
    """
    kind = channel_type_name(channel_type)
    if kind not in RANGED_CHANNEL_TYPES:
        return None
    entries = _entries(value_ranges)
    if not entries:
        return None

    assumed = all(
        ASSUMED_MARK in str(entry.get("name") or "").lower()
        for entry in value_ranges if isinstance(entry, dict)
    )

    if kind == DIMMER:
        span = _dimmer_span(entries)
        if span is None:
            return None
        return ChannelRangeValues(kind=kind, dimmer=span, assumed=assumed)

    resting = FALLBACK_SHUTTER_OPEN if kind == SHUTTER else FALLBACK_STROBE_IDLE
    open_spans = [(low, high) for name, low, high in entries if _is_open(name)]
    idle_spans = [(low, high) for name, low, high in entries if _is_idle(name)]
    closed_spans = [(low, high) for name, low, high in entries if _is_closed(name)]

    # The value in use today stays in use wherever the profile agrees it is a
    # resting value, so a correct fixture sees no change on the wire.
    if any(low <= resting <= high for low, high in open_spans + idle_spans):
        open_value: Optional[int] = resting
    else:
        open_value = _pick(open_spans, resting)
        if open_value is None:
            open_value = _pick(idle_spans, resting)

    closed_value = _pick(closed_spans, FALLBACK_CLOSED)
    strobe_span = _strobe_span(entries)

    if open_value is None and closed_value is None and strobe_span is None:
        return None
    return ChannelRangeValues(
        kind=kind, open=open_value, closed=closed_value, strobe=strobe_span, assumed=assumed,
    )
