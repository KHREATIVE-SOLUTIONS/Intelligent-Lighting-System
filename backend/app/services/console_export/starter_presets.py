"""
grandMA2 starter presets
========================

A preset pack a programmer can busk with on day one, built from the same
ExportRig the patch and groups come from and from each fixture's profile
channels (RigFixture rows with `mode.channels` loaded, as the focus table reads
them):

- Dimmer, Preset 1.1 to 1.5: Full, 75, 50, 25, Out.
- Colour, Preset 4.1 to 4.13: a fixed palette (PALETTE). Each fixture gets the
  colour the way its profile makes colour: RGB mixing (with white and amber
  taken out of the mix where the fixture has them), CMY (subtractive), or the
  nearest named slot on a colour wheel.
- Beam, Preset 5.1 to 5.5: Shutter Open, Strobe Slow, Strobe Fast, Zoom Narrow,
  Zoom Wide, only for fixtures whose profile has the channel and, for strobe,
  names a strobe range. No strobe range is invented.

Every preset keeps its slot whether or not anything is stored in it, so "Red"
is Preset 4.3 on every rig. A fixture left out of a preset is listed with why.

`build_starter_presets` gives the plain table (preset -> fixture -> attribute
values), which is what the tests read; `starter_presets_script` writes it as
grandMA2 command-line text in the style of the focus presets. A database rig
only: a demo preset carries no channel lists. Not run on a desk:
docs/CONSOLE_EXPORT.md says what is unverified.
"""

import colorsys
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.dmx.channel_ranges import channel_type_name, resolve_channel_ranges

from .ma2 import _label, _number, selection
from .model import ExportRig

DIMMER_POOL = 1
COLOUR_POOL = 4
BEAM_POOL = 5

# The attribute each value is written to. One table, so a desk that names them
# otherwise is one edit. Not checked against a desk's fixture types.
MA2_ATTRIBUTES: Dict[str, str] = {
    "dimmer": "Dim",
    "red": "ColorRGB1", "green": "ColorRGB2", "blue": "ColorRGB3",
    "white": "ColorRGB5", "amber": "ColorRGB4", "uv": "ColorUV",
    "cyan": "ColorMixC", "magenta": "ColorMixM", "yellow": "ColorMixY",
    "color_wheel": "Color1",
    "shutter": "Shutter", "strobe": "Shutter",
    "zoom": "Zoom",
}

ADDITIVE = ("red", "green", "blue", "white", "amber", "uv")
SUBTRACTIVE = ("cyan", "magenta", "yellow")

DIMMER_PRESETS: Tuple[Tuple[str, float], ...] = (
    ("Full", 100.0), ("75", 75.0), ("50", 50.0), ("25", 25.0), ("Out", 0.0),
)
BEAM_PRESETS = ("Shutter Open", "Strobe Slow", "Strobe Fast", "Zoom Narrow", "Zoom Wide")
# Where in the profile's strobe range slow and fast sit, 0 slowest to 1 fastest.
STROBE_SLOW, STROBE_FAST = 0.1, 0.9

# A wheel slot counts as the colour when its hue is this close.
WHEEL_HUE_TOLERANCE_DEG = 18.0


@dataclass(frozen=True)
class PaletteColour:
    name: str
    rgb: Tuple[float, float, float]
    # "white" and "warm" are matched on a wheel by slot name, not hue.
    kind: str = "hue"
    uv: float = 0.0

    @property
    def hue(self) -> float:
        return colorsys.rgb_to_hsv(*self.rgb)[0] * 360.0


PALETTE: Tuple[PaletteColour, ...] = (
    PaletteColour("White", (1.0, 1.0, 1.0), kind="white"),
    PaletteColour("Warm White", (1.0, 0.78, 0.5), kind="warm"),
    PaletteColour("Red", (1.0, 0.0, 0.0)),
    PaletteColour("Orange", (1.0, 0.5, 0.0)),
    PaletteColour("Amber", (1.0, 0.75, 0.0)),
    PaletteColour("Yellow", (1.0, 1.0, 0.0)),
    PaletteColour("Green", (0.0, 1.0, 0.0)),
    PaletteColour("Cyan", (0.0, 1.0, 1.0)),
    PaletteColour("Light Blue", (0.4, 0.7, 1.0)),
    PaletteColour("Blue", (0.0, 0.0, 1.0)),
    PaletteColour("Congo", (0.3, 0.0, 1.0), uv=1.0),
    PaletteColour("Magenta", (1.0, 0.0, 1.0)),
    PaletteColour("Pink", (1.0, 0.4, 0.7)),
)

# Words a wheel slot is named with, and the hue each stands for.
_SLOT_HUES: Tuple[Tuple[str, float], ...] = (
    ("light blue", 205.0), ("lightblue", 205.0), ("lt blue", 205.0), ("sky", 205.0),
    ("congo blue", 262.0), ("congo", 262.0), ("uv", 262.0), ("lavender", 262.0), ("violet", 262.0), ("purple", 280.0),
    ("magenta", 300.0), ("pink", 330.0), ("rose", 330.0),
    ("red", 0.0), ("orange", 30.0), ("amber", 40.0), ("yellow", 60.0),
    ("lime", 90.0), ("green", 120.0), ("cyan", 180.0), ("blue", 240.0),
)
_SLOT_SKIP_WORDS = ("rotat", "rainbow", "scroll", "spin", "split", "half", "shake", "random", "cw")
_WARM_WORDS = ("cto", "warm", "3200", "2700", "3000")


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------

@dataclass
class StarterPreset:
    pool: int
    slot: int
    name: str
    # Fixture number -> attribute -> value, as written: percent, except a
    # wheel, shutter, strobe or zoom value, which is that percent of the DMX
    # range (`dmx` holds the byte).
    values: Dict[int, Dict[str, float]] = field(default_factory=dict)
    dmx: Dict[int, Dict[str, int]] = field(default_factory=dict)
    # Fixture number -> why it is not in this preset.
    skipped: Dict[int, str] = field(default_factory=dict)
    # Fixture number -> something taken on trust (no range names it).
    assumed: Dict[int, str] = field(default_factory=dict)

    @property
    def number(self) -> str:
        return f"{self.pool}.{self.slot}"


@dataclass
class StarterPresets:
    presets: List[StarterPreset]
    # Fixtures in no colour preset at all, and why.
    no_colour: List[Dict[str, Any]] = field(default_factory=list)

    def preset(self, name: str) -> StarterPreset:
        return next(p for p in self.presets if p.name == name)

    def table(self) -> Dict[str, Dict[int, Dict[str, float]]]:
        """Preset name -> fixture number -> attribute -> value."""
        return {p.name: {n: dict(v) for n, v in p.values.items()} for p in self.presets}


def _percent(byte: int) -> float:
    return round(byte * 100.0 / 255.0, 1)


def _mix(value: float) -> float:
    return float(round(max(0.0, min(1.0, value)) * 100.0))


@dataclass
class _Profile:
    """One fixture's coarse channels by type; None when no channel list is known."""

    channels: Optional[Dict[str, Any]]


def _profile(rf: Any) -> _Profile:
    mode = getattr(rf, "mode", None)
    channels = list(getattr(mode, "channels", None) or []) if mode is not None else []
    if not channels:
        return _Profile(None)
    by_type: Dict[str, Any] = {}
    for channel in sorted(channels, key=lambda c: int(getattr(c, "channel_number", 0) or 0)):
        if getattr(channel, "is_fine", False):
            continue
        by_type.setdefault(channel_type_name(getattr(channel, "channel_type", None)), channel)
    return _Profile(by_type)


NO_MODE = "no DMX mode is set, so its channels are not known"


# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------

def additive_mix(colour: PaletteColour, have: Sequence[str]) -> Dict[str, float]:
    """Percent per additive channel the fixture has. White and amber, where the
    fixture has them, take over the part of the mix they can make; UV is used
    for Congo only. Every channel it has is written, so a preset never leaves
    an old value behind."""
    r, g, b = colour.rgb
    w = a = 0.0
    if "white" in have:
        w = min(r, g, b)
        r, g, b = r - w, g - w, b - w
    if "amber" in have:
        # Amber is about full red and three quarters green.
        a = max(0.0, min(r, g / 0.75))
        r, g = r - a, g - 0.75 * a
    levels = {"red": r, "green": g, "blue": b, "white": w, "amber": a, "uv": colour.uv}
    return {name: _mix(levels[name]) for name in ADDITIVE if name in have}


def subtractive_mix(colour: PaletteColour) -> Dict[str, float]:
    r, g, b = colour.rgb
    return {"cyan": _mix(1.0 - r), "magenta": _mix(1.0 - g), "yellow": _mix(1.0 - b)}


@dataclass(frozen=True)
class WheelSlot:
    name: str
    dmx: int
    kind: str            # "hue", "white" or "warm"
    hue: Optional[float] = None


def wheel_slots(value_ranges: Any) -> List[WheelSlot]:
    """The single-colour slots a wheel's ranges name, at the middle of each range."""
    out: List[WheelSlot] = []
    for entry in value_ranges or []:
        if not isinstance(entry, dict):
            continue
        try:
            low, high = sorted((int(entry.get("min_value")), int(entry.get("max_value"))))
        except (TypeError, ValueError):
            continue
        name = str(entry.get("name") or "").strip()
        text = name.lower()
        if not text or any(word in text for word in _SLOT_SKIP_WORDS):
            continue
        dmx = (low + high) // 2
        if any(word in text for word in _WARM_WORDS):
            out.append(WheelSlot(name, dmx, "warm"))
            continue
        if re.search(r"\b(open|white|no colou?r)\b", text):
            out.append(WheelSlot(name, dmx, "white"))
            continue
        hues = set()
        rest = text
        for word, hue in _SLOT_HUES:
            if word in rest:
                hues.add(hue)
                rest = rest.replace(word, " ")
        if len(hues) == 1:
            out.append(WheelSlot(name, dmx, "hue", hues.pop()))
        # Two colours in one name is a split slot; no colour word is a slot
        # nothing here can read. Both are left out.
    return out


def _hue_distance(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def nearest_slot(colour: PaletteColour, slots: Sequence[WheelSlot]) -> Tuple[Optional[WheelSlot], str]:
    """The slot for this colour, or None and why."""
    if not slots:
        return None, "its colour wheel names no colour slots"
    if colour.kind in ("white", "warm"):
        match = next((s for s in slots if s.kind == colour.kind), None)
        if match is None:
            return None, "no " + ("open or white" if colour.kind == "white" else "CTO or warm white") + " slot"
        return match, ""
    best: Optional[WheelSlot] = None
    best_d = 360.0
    for slot in slots:
        if slot.kind != "hue" or slot.hue is None:
            continue
        d = _hue_distance(colour.hue, slot.hue)
        if d < best_d:
            best, best_d = slot, d
    if best is None or best_d > WHEEL_HUE_TOLERANCE_DEG:
        near = f" (nearest is {best.name}, {best_d:.0f} degrees of hue away)" if best else ""
        return None, f"no wheel slot is close to {colour.name}{near}"
    return best, ""


def _colour_values(colour: PaletteColour, prof: _Profile) -> Tuple[Optional[Dict[str, float]], Dict[str, int], str]:
    """(attribute values, DMX bytes, why not) for one fixture and colour."""
    if prof.channels is None:
        return None, {}, NO_MODE
    have = [t for t in ADDITIVE if t in prof.channels]
    if {"red", "green", "blue"} <= set(have):
        return additive_mix(colour, have), {}, ""
    if all(t in prof.channels for t in SUBTRACTIVE):
        return subtractive_mix(colour), {}, ""
    wheel = prof.channels.get("color_wheel")
    if wheel is not None:
        slot, why = nearest_slot(colour, wheel_slots(getattr(wheel, "value_ranges", None)))
        if slot is None:
            return None, {}, why
        return {"color_wheel": _percent(slot.dmx)}, {"color_wheel": slot.dmx}, ""
    if have or any(t in prof.channels for t in SUBTRACTIVE):
        return None, {}, "it has part of a colour mix only (" + ", ".join(
            t for t in ADDITIVE + SUBTRACTIVE if t in prof.channels) + ")"
    return None, {}, "it has no colour control"


# ---------------------------------------------------------------------------
# Beam
# ---------------------------------------------------------------------------

def _strobe_channel(prof: _Profile) -> Tuple[Optional[Any], Any]:
    """The channel and its ranges that name a plain strobe range, shutter first."""
    for kind in ("shutter", "strobe"):
        channel = prof.channels.get(kind) if prof.channels else None
        if channel is None:
            continue
        ranges = resolve_channel_ranges(kind, getattr(channel, "value_ranges", None))
        if ranges is not None and ranges.strobe is not None:
            return channel, ranges
    return None, None


def _zoom_bytes(channel: Any) -> Tuple[int, int, bool]:
    """(narrow byte, wide byte, assumed) from the zoom channel's range names."""
    narrow = wide = None
    for entry in getattr(channel, "value_ranges", None) or []:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("name") or "").lower()
        try:
            low, high = sorted((int(entry.get("min_value")), int(entry.get("max_value"))))
        except (TypeError, ValueError):
            continue
        if narrow is None and re.search(r"\b(narrow|spot|tight)\b", text):
            narrow = low if "wide" in text or "flood" in text else (low + high) // 2
        if wide is None and re.search(r"\b(wide|flood)\b", text):
            wide = high if "narrow" in text or "spot" in text else (low + high) // 2
    if narrow is not None and wide is not None and narrow != wide:
        return narrow, wide, False
    return 0, 255, True


def _beam_values(name: str, prof: _Profile) -> Tuple[Optional[int], str, str, str]:
    """(byte, channel type, why not, what was assumed) for one beam preset."""
    if prof.channels is None:
        return None, "", NO_MODE, ""
    if name == "Shutter Open":
        for kind in ("shutter", "strobe"):
            channel = prof.channels.get(kind)
            if channel is None:
                continue
            ranges = resolve_channel_ranges(kind, getattr(channel, "value_ranges", None))
            if ranges is not None and ranges.open is not None:
                return ranges.open, kind, "", ""
            if kind == "shutter" and not getattr(channel, "value_ranges", None):
                return 255, kind, "", "no range names open; 255 taken as open"
            if kind == "shutter":
                # Ranges that name no open value: 255 may well be a strobe.
                return None, "", "its shutter ranges name no open value", ""
        return None, "", "it has no shutter channel that names an open value", ""
    if name.startswith("Strobe"):
        channel, ranges = _strobe_channel(prof)
        if channel is None:
            return None, "", "its profile names no strobe range", ""
        kind = channel_type_name(channel.channel_type)
        return ranges.strobe_byte(STROBE_SLOW if name == "Strobe Slow" else STROBE_FAST), kind, "", ""
    channel = prof.channels.get("zoom")
    if channel is None:
        return None, "", "it has no zoom channel", ""
    narrow, wide, assumed = _zoom_bytes(channel)
    note = "no range names narrow and wide; 0 taken as narrow" if assumed else ""
    return (narrow if name == "Zoom Narrow" else wide), "zoom", "", note


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

def build_starter_presets(rows: Sequence[Any], export: ExportRig) -> StarterPresets:
    """The starter preset table for a database rig's fixtures, in fixture number order."""
    by_key = {f.key: f for f in export.fixtures}
    fixtures = []
    for rf in rows:
        exported = by_key.get(f"fixture-{rf.id}")
        if exported is not None:
            fixtures.append((exported, _profile(rf)))
    fixtures.sort(key=lambda item: item[0].number)

    presets: List[StarterPreset] = []
    for slot, (name, level) in enumerate(DIMMER_PRESETS, start=1):
        p = StarterPreset(DIMMER_POOL, slot, name)
        for fx, prof in fixtures:
            if prof.channels is not None and "dimmer" not in prof.channels:
                p.skipped[fx.number] = "it has no dimmer channel"
                continue
            p.values[fx.number] = {"dimmer": level}
            if prof.channels is None:
                p.assumed[fx.number] = NO_MODE + "; a dimmer is assumed"
        presets.append(p)

    coloured = set()
    for slot, colour in enumerate(PALETTE, start=1):
        p = StarterPreset(COLOUR_POOL, slot, colour.name)
        for fx, prof in fixtures:
            values, dmx, why = _colour_values(colour, prof)
            if values is None:
                p.skipped[fx.number] = why
                continue
            p.values[fx.number] = values
            if dmx:
                p.dmx[fx.number] = dmx
            coloured.add(fx.number)
        presets.append(p)

    for slot, name in enumerate(BEAM_PRESETS, start=1):
        p = StarterPreset(BEAM_POOL, slot, name)
        for fx, prof in fixtures:
            byte, kind, why, assumed = _beam_values(name, prof)
            if byte is None:
                p.skipped[fx.number] = why
                continue
            p.values[fx.number] = {kind: _percent(byte)}
            p.dmx[fx.number] = {kind: byte}
            if assumed:
                p.assumed[fx.number] = assumed
        presets.append(p)

    no_colour = []
    for fx, prof in fixtures:
        if fx.number in coloured:
            continue
        values, _, why = _colour_values(PALETTE[0], prof)
        no_colour.append({"fixture_id": fx.number, "name": fx.name,
                          "reason": why or "no palette colour could be made"})
    return StarterPresets(presets, no_colour)


# ---------------------------------------------------------------------------
# As grandMA2 command-line text
# ---------------------------------------------------------------------------

def _reasons(skipped: Dict[int, str]) -> List[Tuple[str, str]]:
    """(selection, reason), fixtures with the same reason together."""
    by_reason: Dict[str, List[int]] = {}
    for number in sorted(skipped):
        by_reason.setdefault(skipped[number], []).append(number)
    return [(selection(numbers), why) for why, numbers in by_reason.items()]


def starter_presets_script(rig: ExportRig, table: StarterPresets, notes: bool = True) -> str:
    """The starter presets as grandMA2 command-line text, one command a line.

        ClearAll
        ClearSelection
        Fixture 1 Thru 12
        Attribute "ColorRGB1" At 100
        ...
        Store Preset 4.3
        Label Preset 4.3 "Red"

    Fixtures given the same values are selected together. A preset already in
    a slot is asked about or replaced.
    """
    out: List[str] = []

    def note(text: str = "") -> None:
        if notes:
            out.append(f"# {text}".rstrip())

    note(f"{rig.name}: grandMA2 starter presets (dimmer, colour, beam)")
    note("Exported by the Intelligent Lighting System. Not run on a desk: read before you paste.")
    if rig.disclaimer:
        note(rig.disclaimer)
    note("Lines starting with # are notes, not commands. Run the patch script first:")
    note("these select fixtures by the fixture ids it patches.")
    note(f"Dimmer at Preset {DIMMER_POOL}.1-{len(DIMMER_PRESETS)}, colour at Preset {COLOUR_POOL}.1-"
         f"{len(PALETTE)}, beam at Preset {BEAM_POOL}.1-{len(BEAM_PRESETS)}. Each keeps its slot when empty.")
    note("Attribute names: " + ", ".join(f"{k} = {v}" for k, v in MA2_ATTRIBUTES.items())
         + ". Check them against your fixture types.")
    note("Dimmer and colour mix values are percent. Wheel, shutter, strobe and zoom values are the")
    note("profile's DMX byte as a percent of 255; how the desk reads them depends on its fixture type.")
    for item in table.no_colour:
        note(f"Fixture {item['fixture_id']} is in no colour preset: {item['reason']}.")

    stored = False
    for p in table.presets:
        note()
        if not p.values:
            note(f"Preset {p.number} {p.name}: not stored. No fixture can take it.")
        else:
            note(f"Preset {p.number} {p.name}: {len(p.values)} fixture(s).")
        for sel, why in _reasons(p.skipped):
            note(f"  fixture {sel} left out: {why}")
        for sel, what in _reasons(p.assumed):
            note(f"  fixture {sel}: {what}")
        if not p.values:
            continue
        out.append("ClearAll")
        stored = True
        same: Dict[Tuple[Tuple[str, float], ...], List[int]] = {}
        for number in sorted(p.values):
            # In the order the mix was built (red, green, blue, white...), not by name.
            same.setdefault(tuple(p.values[number].items()), []).append(number)
        for values, numbers in same.items():
            out += ["ClearSelection", f"Fixture {selection(numbers)}"]
            for kind, value in values:
                out.append(f'Attribute "{MA2_ATTRIBUTES[kind]}" At {_number(value)}')
        out += [f"Store Preset {p.number}", f'Label Preset {p.number} "{_label(p.name)}"']
    if stored:
        out.append("ClearAll")
    out.append("")
    return "\n".join(out)
