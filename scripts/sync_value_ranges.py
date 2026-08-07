#!/usr/bin/env python3
"""
Sync `value_ranges` onto the bundled fixture corpus from the Open Fixture Library
================================================================================

A fixture profile is a factual claim about real hardware. A wrong gobo slot puts
the wrong gobo on stage and the DMX byte still looks perfectly valid, so nothing
downstream catches it. This script therefore only ever writes ranges it can point
at a source for, and every decision it makes - both the matches and the refusals -
is spelled out in the tables below rather than inferred by a fuzzy matcher.

How it works
------------
`MATCHES` is the authority. Each entry names one bundled profile, the exact OFL
fixture key it may take data from, and an explicit channel-by-channel mapping from
our channel *name* to OFL's channel *name*. Nothing is matched by DMX position:
our layouts and OFL's frequently disagree (the RUSH PAR 2's eighth slot is
`Control/Reset` here and `Color Presets` at OFL - mapping by position would have
put colour presets on a reset channel).

`UNMATCHED` records why each of the other profiles gets nothing. That list is a
deliverable, not a failure.

Before writing, the script re-verifies that the OFL fixture still carries the name
we matched on and that every mapped channel still exists with capabilities that
fit in one 8-bit DMX byte. If any of that has drifted, it refuses rather than
guesses.

Idempotence
-----------
A channel that already carries a non-empty `value_ranges` is left exactly as it
is. Re-running after OFL adds detail therefore requires clearing the channel
first - deliberately, so a refresh can never silently replace curated data with
something weaker.

Usage
-----
    python scripts/sync_value_ranges.py --check     # byte-identity round trip only
    python scripts/sync_value_ranges.py --dry-run   # report, write nothing
    python scripts/sync_value_ranges.py             # write ranges + provenance
    python scripts/sync_value_ranges.py --audit     # what was left on the table

Fetched OFL definitions are cached (see --cache) so a re-run does not re-download.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLED_DIR = REPO_ROOT / "data" / "fixtures" / "bundled"
PROVENANCE = BUNDLED_DIR / "VALUE_RANGES_PROVENANCE.md"

OFL_BASE = "https://open-fixture-library.org"
USER_AGENT = "intelligent-lighting-system/value-ranges-sync (bundled fixture corpus)"
REQUEST_DELAY_S = 1.2

# Channel types the contract asks us to prioritise: the ones where a DMX byte
# selects a discrete thing rather than sliding along a continuum.
PRIORITY_TYPES = {
    "gobo", "gobo2", "gobo_rotation", "gobo2_rotation", "color_wheel",
    "shutter", "strobe", "prism", "macro", "effect", "animation", "other",
    "frost", "iris", "framing",
}


# --------------------------------------------------------------------------
# The authority: what may take data from what
# --------------------------------------------------------------------------

class Match:
    """One bundled profile cleared to take data from one OFL fixture."""

    def __init__(
        self,
        ofl_key: str,
        ofl_name: str,
        rationale: str,
        channels: Dict[str, str],
        skipped: Optional[Dict[str, str]] = None,
    ) -> None:
        self.ofl_key = ofl_key
        self.ofl_name = ofl_name          # re-checked at run time; drift = refuse
        self.rationale = rationale        # why rules 1-3 are satisfied
        self.channels = channels          # our channel name -> OFL channel name
        self.skipped = skipped or {}      # our channel name -> why it gets nothing


MATCHES: Dict[str, Match] = {

    "adj_dotz_par": Match(
        ofl_key="american-dj/dotz-par",
        ofl_name="Dotz Par",
        rationale="ADJ -> american-dj; model name identical; both an LED par "
                  "(OFL categories Blinder/Color Changer, ours led_par); neither "
                  "carries a gobo or colour wheel.",
        channels={
            "Strobe": "Strobe",
            "Color Macro": "Color Macros",
            "Program": "Programs",
        },
        skipped={
            "Strobe/Speed": "our 7-channel mode folds strobe and program speed onto "
                            "one channel; OFL keeps them on two, so no single OFL "
                            "channel describes it",
        },
    ),

    "adj_mega_tripar_profile": Match(
        ofl_key="american-dj/mega-tripar-profile-plus",
        ofl_name="Mega TRIPAR Profile Plus",
        rationale="ADJ -> american-dj; 'Mega TriPar Profile Plus' vs 'Mega TRIPAR "
                  "Profile Plus' differs only in capitalisation; both an LED par. "
                  "Distinct from the sibling 'Mega TRIPAR Profile' (no Plus), which "
                  "is a separate OFL entry.",
        channels={
            "Strobe": "Shutter/Strobe",
            "Color Macro": "Color Macros",
        },
        skipped={
            "Program": "OFL splits program selection across three mode-dependent "
                       "channels (Color Change / Color Fade / Sound Active Programs) "
                       "chosen by a fourth; our single 'Program' channel cannot be "
                       "resolved to one of them",
            "Strobe/Program Speed": "combined strobe+speed channel with no OFL "
                                    "counterpart",
        },
    ),

    "adj_ultra_hex_bar_12": Match(
        ofl_key="american-dj/ultra-hex-bar-12",
        ofl_name="Ultra Hex Bar 12",
        rationale="ADJ -> american-dj; model name identical; both a 12-cell HEX "
                  "pixel bar (OFL Pixel Bar, ours led_bar).",
        channels={
            "Strobe": "Strobe",
            "Color Macro": "Color Macros",
            "Program": "Programs",
            # OFL calls it 'Dimmer Mode'; its capabilities are literally the
            # dimming curves Standard/Stage/TV/Architectural/Theatre, which is
            # what our channel is named for.
            "Dimmer Curve": "Dimmer Mode",
        },
    ),

    "chauvet_rogue_r2_wash": Match(
        ofl_key="chauvet-professional/rogue-r2-wash",
        ofl_name="Rogue R2 Wash",
        rationale="Chauvet Professional -> chauvet-professional; model name "
                  "identical; both a moving-head wash. Explicitly NOT the source "
                  "for our Rogue R2 Spot: the Wash has no gobo wheel.",
        channels={
            "Shutter/Strobe": "Shutter",
            # Type 'macro' here, but it is the fixture's colour-preset channel -
            # matched on meaning, per rule 4.
            "Color Macro": "Color",
            "Control/Reset": "Control",
        },
    ),

    "chauvet_slimpar_pro_h": Match(
        ofl_key="chauvet-dj/slimpar-pro-h-usb",
        ofl_name="SlimPAR Pro H USB",
        rationale="Chauvet DJ -> chauvet-dj; model name identical including the USB "
                  "suffix; both a 6-in-1 HEX LED par.",
        channels={
            "Strobe": "Strobe",
            "Color Macro": "Color Macros",
        },
        skipped={
            "Dimmer Curve": "the only candidate, OFL's 'Dimmer Speed', describes "
                            "dimmer response speed (off/fast/50%/slow), not a "
                            "dimming curve - the content contradicts our channel's "
                            "stated function, so it is not the same thing",
            "Auto Speed": "continuous program-speed travel; OFL defines no slots on it",
        },
    ),

    "elation_sixpar_200": Match(
        ofl_key="elation/sixpar-200",
        ofl_name="SIXPAR 200",
        rationale="Elation -> elation; base model matched exactly, deliberately not "
                  "the sibling entries sixpar-200-ip or sixpar-200-wmg; both a "
                  "6-in-1 LED par.",
        channels={
            "Strobe": "Strobe",
            "Color Macro": "Color Macros",
            # OFL 'Dimming Modes' = Standard/Stage/TV/Architectural/Theater, i.e.
            # the dimming curve our channel names.
            "Dimmer Curve": "Dimming Modes",
        },
    ),

    "etc_colorsource_par": Match(
        ofl_key="etc/colorsource-par",
        ofl_name="ColorSource PAR",
        rationale="ETC -> etc; model name identical; both an RGB-L LED par. Not the "
                  "sibling 'ColorSource PAR Deep Blue', a different emitter set.",
        channels={
            "Strobe": "Strobe",
        },
        skipped={
            "Fan Control": "the ColorSource PAR has no fan-control channel at OFL; "
                           "the channel exists only in our 7-channel mode",
        },
    ),

    "etc_source_four_led_s2": Match(
        ofl_key="etc/source-four-led-series-2-lustr",
        ofl_name="Source Four LED Series 2 Lustr",
        rationale="ETC -> etc; model name identical including the Lustr variant; "
                  "both an LED ellipsoidal engine.",
        channels={},
        skipped={
            "Hue": "continuous; OFL models it as a single full-range capability",
            "Saturation": "continuous; OFL models it as a single full-range capability",
            "Cyan": "an additive emitter, continuous intensity - no slots",
        },
    ),

    "martin_rush_par_2_rgbw": Match(
        ofl_key="martin/rush-par-2-rgbw-zoom",
        ofl_name="Rush PAR 2 RGBW Zoom",
        rationale="Martin -> martin; model name identical; both an RGBW zoom par.",
        channels={
            "Strobe": "Shutter / Strobe",
        },
        skipped={
            "Control/Reset": "the RUSH PAR 2 has no control/reset channel at OFL. "
                             "OFL's ninth slot is 'Color Presets' - mapping by "
                             "position would have written colour presets onto a "
                             "reset channel",
        },
    ),

    "robe_robin_600_ledwash": Match(
        ofl_key="robe/robin-ledwash-600",
        ofl_name="Robin LEDWash 600",
        rationale="Robe -> robe; word-order variant of the same product - the token "
                  "set {robin, ledwash, 600} is unique in Robe's 11-fixture OFL "
                  "catalogue and matches no other entry. Corroborated structurally: "
                  "both are three-zone moving-head RGBW washes (OFL's matrix is an "
                  "inner/middle/outer ring, ours is Zone 1/2/3), both put the "
                  "special-functions channel at slot 6, and both carry CTC + virtual "
                  "colour wheel + zoom. CAVEAT for auditors: the physical metadata "
                  "disagrees - we say 9.8kg / 540deg pan / 280deg tilt, OFL says "
                  "10.6kg / 450deg / 300deg. Those fields were left untouched; only "
                  "the DMX semantics were taken.",
        channels={
            "Shutter/Strobe": "Shutter / Strobe",
            "Color Macro": "Virtual Color Wheel",
            # Robe's manual calls channel 6 'Special functions'; our profile calls
            # the same channel 'Control/Reset'. Same slot in both layouts, same job.
            "Control/Reset": "Special Functions",
        },
        skipped={
            "CTC": "continuous colour-temperature travel (15500K->2700K), not slot data",
            "FX1 Select": "OFL does not model the 29-channel mode's FX engine",
            "FX2 Select": "OFL does not model the 29-channel mode's FX engine",
        },
    ),

    "robe_robin_t1_profile": Match(
        ofl_key="robe/robin-t1-profile",
        ofl_name="Robin T1 Profile",
        rationale="Robe -> robe; model name identical; both a CMY moving-head "
                  "profile with framing, prism, frost and iris.",
        channels={
            "Shutter/Strobe": "Shutter / Strobe",
            # The T1 has no mechanical colour wheel; its colour-preset channel is
            # the virtual one, which is what our color_wheel channel drives.
            "Color Wheel": "Virtual Color wheel",
            "Prism": "Prism",
            "Prism Rotation": "Prism Rotation",
            "Frost": "Frost",
            "Iris": "Iris",
        },
        skipped={
            # This is the important refusal in the whole corpus.
            "Gobo Wheel 1": "our profile declares two gobo wheels; the real T1 "
                            "Profile has one ('Rotating Gobo Wheel', 8 slots). We "
                            "cannot tell which of our two channels that is, and the "
                            "phantom second wheel discredits the gobo layout. A "
                            "misplaced gobo slot reaches a venue silently",
            "Gobo Wheel 2": "the T1 Profile has no second gobo wheel",
            "Gobo 1 Rotation": "OFL exposes two gobo-rotation channels ('Rotating "
                               "Gobo Indexing' and 'Rotating Gobo Rotation'); our "
                               "single channel cannot be resolved to one",
            "Control/Reset": "the T1 spreads control across Power/Special Functions, "
                             "Color Functions, Color Mix Mode, LED Frequency and "
                             "Effect wheel animations; our one channel cannot be "
                             "resolved to one of them",
        },
    ),
}


UNMATCHED: Dict[str, str] = {
    "adj_focus_spot_5z": "OFL's american-dj catalogue (43 fixtures) has no Focus Spot in any size.",
    "adj_hydro_wash_x7": "No Hydro series in OFL's american-dj catalogue.",
    "adj_hyper_gem_led": "No Hyper Gem in OFL's american-dj catalogue.",
    "adj_mega_go_par": "OFL has 'Mega Par Profile Plus' and 'Mega Hex Par'; the battery-powered Mega Go PAR Plus is a different product (rule 2).",
    "adj_vizi_beam_12rx": "OFL has 'Vizi Q Wash7' and 'Vizi Spot LED Pro'. A beam must not take a wash's or a spot's data (rule 3).",
    "ayrton_cobra": "OFL's ayrton catalogue holds only Diablo-S, Diablo-TC and MagicBlade FX.",
    "ayrton_ghibli": "OFL's ayrton catalogue holds only Diablo-S, Diablo-TC and MagicBlade FX.",
    "ayrton_mistral_tc": "Diablo-TC shares the '-TC' suffix but is a different fixture; near-miss rejected under rule 2.",
    "ayrton_perseo_profile": "OFL's ayrton catalogue holds only Diablo-S, Diablo-TC and MagicBlade FX.",
    "chauvet_colorado_pxl_bar_16": "OFL's chauvet-professional catalogue (7 fixtures) has no COLORado PXL Bar.",
    "chauvet_colorband_pix_m": "OFL has 'COLORband PiX' and 'COLORband PiX IP'; the PiX-M USB is a distinct model (rule 2).",
    "chauvet_freedom_par_quad_4": "OFL's chauvet-dj catalogue has only 'Freedom H1' from the Freedom line.",
    "chauvet_intimidator_spot_375z": "OFL has Intimidator Spot 110/160/260; the 375Z IRC is a larger, different fixture (rule 2).",
    "chauvet_maverick_mk2_spot": "No Maverick line in OFL's chauvet-professional catalogue.",
    "chauvet_rogue_r2_spot": "OFL carries Rogue R1 Wash and Rogue R2 Wash only. Taking the R2 Wash's data is exactly the error rule 3 exists to stop: the Wash has neither gobo nor colour wheel, so a spot would inherit nothing true.",
    "chauvet_rogue_r3_wash": "OFL's Rogue line stops at R2; R3 is a different fixture (rule 2).",
    "chauvet_strike_array_4": "No Strike series in OFL's chauvet-professional catalogue.",
    "elation_colour_pendant": "Not present in OFL's elation catalogue (20 fixtures).",
    "elation_fuze_wash_500": "OFL has 'FUZE PAR Z60IP'. A moving wash must not take a par's data (rule 3).",
    "elation_platinum_fwd": "OFL has Platinum HFX, Platinum Seven and Platinum Spot 15R Pro; the FWD is a different fixture (rule 2).",
    "elation_rayzor_760": "Not present in OFL's elation catalogue.",
    "elation_smarty_hybrid": "OFL has 'Proteus Hybrid', a different (IP65) hybrid fixture (rule 2).",
    "etc_colorsource_linear_4": "OFL's etc catalogue has ColorSource PAR and Spot but no Linear batten.",
    "etc_colorsource_spot_jr": "OFL has 'ColorSource Spot' (and Deep Blue); the Spot jr is a separate, smaller model (rule 2).",
    "etc_desire_d22_studio": "No Desire series in OFL's etc catalogue.",
    "etc_source_four_ce_led": "OFL has Source Four LED Series 2/3 and Source 4WRD Color II; the CE LED is a different product (rule 2).",
    "martin_era_600_profile": "No ERA series in OFL's martin catalogue (24 fixtures).",
    "martin_mac_aura_xb": "OFL has the original 'MAC Aura'. The Aura XB is a different fixture with a different channel layout (rule 2).",
    "martin_mac_encore_wash": "OFL has 'MAC Encore Performance', a profile. A wash must not take a profile's data (rules 2 and 3).",
    "martin_mac_quantum_profile": "Not present in OFL's martin catalogue.",
    "martin_rush_mh6_wash": "OFL has RUSH MH 2 Wash, MH 3 Beam, MH 5 Profile and MH 7 Hybrid; there is no MH 6 (rule 2).",
    "martin_rush_strobe_cw": "Not present in OFL's martin catalogue.",
    "martin_thrill_mini_profile": "The Thrill line is not in OFL's martin catalogue.",
    "robe_robin_bmfl_spot": "Not present in OFL's robe catalogue (11 fixtures).",
    "robe_robin_dl4s_profile": "Not present in OFL's robe catalogue.",
    "robe_robin_megapointe": "Not present in OFL's robe catalogue.",
    "robe_robin_patt_2013": "Not present in OFL's robe catalogue.",
    "robe_robin_pointe": "Not present in OFL's robe catalogue.",
    "robe_robin_spikie": "Not present in OFL's robe catalogue.",
}


# --------------------------------------------------------------------------
# Fetching (cached, polite)
# --------------------------------------------------------------------------

def default_cache_dir() -> Path:
    override = os.environ.get("OFL_CACHE_DIR")
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "ofl_fixture_cache"


class OflFetcher:
    def __init__(self, cache_dir: Path, offline: bool = False) -> None:
        self.cache_dir = cache_dir
        self.offline = offline
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_request = 0.0

    def fixture(self, key: str) -> Dict[str, Any]:
        path = self.cache_dir / (key.replace("/", "__") + ".json")
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                return json.load(handle)
        if self.offline:
            raise RuntimeError(f"{key} is not cached and --offline was given")

        elapsed = time.monotonic() - self._last_request
        if elapsed < REQUEST_DELAY_S:
            time.sleep(REQUEST_DELAY_S - elapsed)
        request = urllib.request.Request(
            f"{OFL_BASE}/{key}.json", headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self._last_request = time.monotonic()

        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=1)
        return payload


# --------------------------------------------------------------------------
# Naming a range
# --------------------------------------------------------------------------

_ASCII_SUBS = {
    "–": "-", "—": "-", "→": "->", "°": "deg",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "×": "x", "…": "...", "±": "+/-",
}


def _ascii(text: str) -> str:
    """The bundled corpus is pure ASCII; keep it that way."""
    for source, target in _ASCII_SUBS.items():
        text = text.replace(source, target)
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii")


def _pretty(token: str) -> str:
    """'RampUpDown' -> 'Ramp up down'; leave already-spaced text alone."""
    if not token or " " in token:
        return token
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", token)
    if spaced == token:
        return token
    return spaced[0].upper() + spaced[1:].lower()


_SPAN_PAIRS = (
    ("speedStart", "speedEnd"),
    ("colorTemperatureStart", "colorTemperatureEnd"),
    ("frostIntensityStart", "frostIntensityEnd"),
    ("openPercentStart", "openPercentEnd"),
    ("angleStart", "angleEnd"),
    ("brightnessStart", "brightnessEnd"),
)

_SCALARS = (
    "speed", "parameter", "frostIntensity", "openPercent", "angle",
    "colorTemperature", "brightness",
)


def derive_name(capability: Dict[str, Any]) -> str:
    """A short, operator-facing name for one OFL capability.

    Preference order follows the contract: the most specific thing OFL states.
    Where a capability carries *both* an effect and a comment, the effect leads
    and the comment trails in parentheses - "Closed (Lamp power = 180W)" reads
    the way an operator thinks, and no information is dropped.
    """
    comment = _ascii((capability.get("comment") or "").strip())
    effect = capability.get("shutterEffect") or capability.get("effectName") or ""
    effect = _ascii(_pretty(effect))

    trailer = ""
    if effect:
        base = effect
        if comment and effect.lower() not in comment.lower():
            trailer = comment
    elif comment:
        base = comment
    else:
        slot = capability.get("wheelSlot") or capability.get("slotNumber")
        if isinstance(slot, list):
            slot = slot[0] if slot else None
        cap_type = capability.get("type", "")
        if slot is not None:
            base = f"Slot {slot}"
        elif cap_type == "NoFunction":
            base = "No function"
        elif capability.get("colors"):
            base = f"{_pretty(cap_type)} {' '.join(capability['colors'])}"
        else:
            base = _pretty(cap_type) or "Range"

    for start_key, end_key in _SPAN_PAIRS:
        start, end = capability.get(start_key), capability.get(end_key)
        if start is not None and end is not None:
            base = f"{base} {_ascii(str(start))}->{_ascii(str(end))}"
            break
    else:
        for key in _SCALARS:
            value = capability.get(key)
            if value is not None:
                value = _ascii(str(value))
                if value.lower() not in base.lower():
                    base = f"{base} {value}"
                break

    if capability.get("randomTiming"):
        base += " (random)"
    if trailer:
        base = f"{base} ({trailer})"

    return " ".join(base.split())


# --------------------------------------------------------------------------
# Turning an OFL channel into value_ranges
# --------------------------------------------------------------------------

class Refusal(Exception):
    """Raised when a mapped channel cannot be converted safely."""


def ranges_for(ofl_channel: Dict[str, Any], channel_label: str) -> List[Dict[str, Any]]:
    capabilities = ofl_channel.get("capabilities")
    if capabilities is None:
        raise Refusal(
            f"{channel_label}: OFL models this as a single continuous capability, "
            "so there are no slots to name"
        )

    resolution = ofl_channel.get("dmxValueResolution")
    if resolution not in (None, "8bit"):
        raise Refusal(
            f"{channel_label}: OFL declares dmxValueResolution={resolution!r}; the "
            "bundled schema stores ranges on the coarse byte only, and clamping "
            "would invent boundaries"
        )

    rows: List[Dict[str, Any]] = []
    for capability in capabilities:
        dmx_range = capability.get("dmxRange")
        if not (isinstance(dmx_range, list) and len(dmx_range) == 2):
            raise Refusal(f"{channel_label}: capability without a usable dmxRange")
        low, high = dmx_range
        if not all(isinstance(v, int) for v in (low, high)):
            raise Refusal(f"{channel_label}: non-integer dmxRange {dmx_range!r}")
        if not (0 <= low <= high <= 255):
            raise Refusal(
                f"{channel_label}: dmxRange {dmx_range!r} does not fit one 8-bit "
                "byte; refusing to clamp"
            )
        name = derive_name(capability)
        if not name:
            raise Refusal(f"{channel_label}: capability {dmx_range!r} yields no name")
        rows.append({"name": name, "min_value": low, "max_value": high})

    rows.sort(key=lambda row: row["min_value"])

    # Adjacent capabilities that derive the same name (long NoFunction runs, for
    # instance) collapse into one range. Lossless: each part already claimed the
    # same meaning, so their union claims it too.
    merged: List[Dict[str, Any]] = []
    for row in rows:
        if merged and merged[-1]["name"] == row["name"] and merged[-1]["max_value"] + 1 == row["min_value"]:
            merged[-1]["max_value"] = row["max_value"]
        else:
            merged.append(row)
    return merged


def validate(rows: Sequence[Dict[str, Any]], channel: Dict[str, Any], label: str) -> None:
    floor = channel.get("min_value", 0)
    ceiling = channel.get("max_value", 255)
    previous = None
    for row in rows:
        low, high = row["min_value"], row["max_value"]
        if not (0 <= low <= high <= 255):
            raise Refusal(f"{label}: range {row!r} outside 0..255")
        if low < floor or high > ceiling:
            raise Refusal(
                f"{label}: range {row!r} falls outside the channel's own "
                f"{floor}..{ceiling}"
            )
        if previous is not None and low <= previous:
            raise Refusal(f"{label}: range {row!r} overlaps the one before it")
        previous = high
        if not row["name"].strip():
            raise Refusal(f"{label}: empty range name")


def pydantic_check(rows: Sequence[Dict[str, Any]]) -> Optional[str]:
    """Validate through the app's own schema when it is importable."""
    backend = REPO_ROOT / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    try:
        from app.schemas.fixture import ChannelValueRange  # type: ignore
    except Exception as exc:  # pragma: no cover - standalone use
        return f"ChannelValueRange not importable ({exc}); skipped schema check"
    for row in rows:
        ChannelValueRange(**row)
    return None


# --------------------------------------------------------------------------
# Writing, without reformatting anything else
# --------------------------------------------------------------------------

CHANNEL_START = '{"channel_number"'


def rewrite(path: Path, additions: Dict[Tuple[int, int], List[Dict[str, Any]]]) -> str:
    """Insert value_ranges into specific channel entries, touching nothing else.

    `additions` is keyed by (mode index, channel index). A channel entry starts on
    a line beginning `{"channel_number"` and runs until that text parses as JSON -
    one line in a pristine profile, several once it carries ranges, so the script
    can read its own output. Every entry is parsed back and compared against the
    document `json` produced before a single byte is rewritten; a layout the
    scanner misreads aborts instead of corrupting the file. Untouched entries are
    re-emitted verbatim, which is what makes the round-trip byte-identical.
    """
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    document = json.loads(raw)

    expected: List[Tuple[Tuple[int, int], Dict[str, Any]]] = []
    for mode_index, mode in enumerate(document.get("modes", [])):
        for channel_index, channel in enumerate(mode.get("channels", [])):
            expected.append(((mode_index, channel_index), channel))

    lines = raw.split(newline)
    out: List[str] = []
    cursor = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.lstrip()
        if not stripped.startswith(CHANNEL_START):
            out.append(line)
            index += 1
            continue

        indent = line[: len(line) - len(stripped)]
        last = index
        while True:
            text = newline.join(lines[index:last + 1]).strip()
            comma = ""
            if text.endswith(","):
                comma, text = ",", text[:-1]
            try:
                parsed = json.loads(text)
                break
            except json.JSONDecodeError:
                last += 1
                if last >= len(lines):
                    raise Refusal(
                        f"{path.name}: channel entry starting at line {index + 1} "
                        "never closes"
                    )

        if cursor >= len(expected):
            raise Refusal(f"{path.name}: more channel entries than parsed channels")
        key, channel = expected[cursor]
        if parsed != channel:
            raise Refusal(
                f"{path.name}: the channel entry at line {index + 1} does not match "
                "the parsed document; refusing to edit by text"
            )
        cursor += 1

        rows = additions.get(key)
        if not rows:
            out.extend(lines[index:last + 1])
            index = last + 1
            continue
        if last != index:
            raise Refusal(
                f"{path.name}: the channel at line {index + 1} already spans several "
                "lines; refusing to rewrite it"
            )

        out.append(f'{indent}{text[:-1].rstrip()}, "value_ranges": [')
        for position, row in enumerate(rows):
            tail = "," if position < len(rows) - 1 else ""
            out.append(f"{indent}  {json.dumps(row)}{tail}")
        out.append(f"{indent}]}}{comma}")
        index = last + 1

    if cursor != len(expected):
        raise Refusal(
            f"{path.name}: read {cursor} channel entries but the document has "
            f"{len(expected)}"
        )
    return newline.join(out)


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def profile_paths() -> List[Path]:
    return sorted(BUNDLED_DIR.glob("*.json"))


def round_trip_check() -> List[str]:
    """Prove the serialiser reproduces every file byte for byte before it edits one."""
    failures = []
    for path in profile_paths():
        original = path.read_bytes()
        try:
            produced = rewrite(path, {}).encode("utf-8")
        except Refusal as exc:
            failures.append(str(exc))
            continue
        if produced != original:
            failures.append(f"{path.name}: round trip is not byte-identical")
    return failures


def run(dry_run: bool, offline: bool, cache_dir: Path) -> Dict[str, Any]:
    fetcher = OflFetcher(cache_dir, offline=offline)
    report: Dict[str, Any] = {
        "date": date.today().isoformat(),
        "profiles": {},
        "totals": {},
    }

    for path in profile_paths():
        stem = path.stem
        with path.open(encoding="utf-8") as handle:
            document = json.load(handle)

        entry: Dict[str, Any] = {
            "manufacturer": document["manufacturer"],
            "model": document["model"],
            "fixture_type": document.get("fixture_type", "other"),
            "ofl_key": None,
            "rationale": None,
            "written": [],
            "skipped": [],
            "channels_touched": 0,
        }

        match = MATCHES.get(stem)
        if match is None:
            entry["skipped"].append(("<whole profile>", UNMATCHED.get(stem, "no reason recorded")))
            report["profiles"][stem] = entry
            continue

        payload = fetcher.fixture(match.ofl_key)
        if payload.get("name") != match.ofl_name:
            raise Refusal(
                f"{stem}: OFL fixture {match.ofl_key} is now named "
                f"{payload.get('name')!r}, not {match.ofl_name!r}; the match was "
                "cleared against the old name and must be re-checked by a human"
            )
        entry["ofl_key"] = match.ofl_key
        entry["ofl_name"] = match.ofl_name
        entry["rationale"] = match.rationale
        available = payload.get("availableChannels", {})

        for our_name, why in sorted(match.skipped.items()):
            entry["skipped"].append((our_name, why))

        # our channel name -> the ranges it should carry
        resolved: Dict[str, List[Dict[str, Any]]] = {}
        caveats: Dict[str, List[str]] = {}
        for our_name, ofl_name in sorted(match.channels.items()):
            label = f"{stem}:{our_name} <- {match.ofl_key}:{ofl_name}"
            if ofl_name not in available:
                raise Refusal(
                    f"{label}: OFL no longer defines a channel named {ofl_name!r}"
                )
            resolved[our_name] = ranges_for(available[ofl_name], label)
            # OFL flags its own uncertainty. The DMX boundaries are still the
            # manual's; what is doubted is usually a colour identity. Surface it
            # rather than quietly inheriting the doubt.
            asked = sorted({
                cap["helpWanted"]
                for cap in available[ofl_name].get("capabilities", [])
                if cap.get("helpWanted")
            })
            if asked:
                caveats[our_name] = [_ascii(a) for a in asked]
        entry["caveats"] = caveats

        additions: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        for mode_index, mode in enumerate(document.get("modes", [])):
            for channel_index, channel in enumerate(mode.get("channels", [])):
                rows = resolved.get(channel.get("name"))
                if not rows:
                    continue
                if channel.get("is_fine"):
                    continue  # fine bytes carry no slots, same as the GDTF parser
                label = f"{stem}:{mode['name']}:{channel['name']}"
                validate(rows, channel, label)
                note = pydantic_check(rows)
                if note and "schema-check-note" not in entry:
                    entry["schema-check-note"] = note

                # Idempotent: a channel that already carries ranges keeps them,
                # untouched. It still belongs in the manifest, which describes
                # the corpus rather than this one run - so a re-run regenerates
                # the same document.
                existing = channel.get("value_ranges")
                if not existing:
                    additions[(mode_index, channel_index)] = rows
                entry["written"].append(
                    (mode["name"], channel["channel_number"], channel["name"],
                     channel["channel_type"], match.channels[channel["name"]],
                     len(existing or rows))
                )

        entry["channels_touched"] = len(additions)
        if additions and not dry_run:
            path.write_bytes(rewrite(path, additions).encode("utf-8"))
            json.loads(path.read_text(encoding="utf-8"))  # must still parse

        report["profiles"][stem] = entry

    return report


def summarise(report: Dict[str, Any]) -> Dict[str, Any]:
    total_channels = 0
    populated = 0
    by_type: Dict[str, List[int]] = {}
    for path in profile_paths():
        with path.open(encoding="utf-8") as handle:
            document = json.load(handle)
        for mode in document.get("modes", []):
            for channel in mode.get("channels", []):
                total_channels += 1
                kind = channel.get("channel_type", "other")
                bucket = by_type.setdefault(kind, [0, 0])
                bucket[0] += 1
                if channel.get("value_ranges"):
                    populated += 1
                    bucket[1] += 1
    matched = sum(1 for e in report["profiles"].values() if e["ofl_key"])
    with_data = sum(1 for e in report["profiles"].values() if e["written"])

    # What this run resolved, independent of what is already on disk - so a
    # --dry-run against a pristine corpus reports the plan, not the empty state.
    planned = 0
    planned_by_type: Dict[str, int] = {}
    for entry in report["profiles"].values():
        for _mode, _number, _name, kind, _ofl, _count in entry["written"]:
            planned += 1
            planned_by_type[kind] = planned_by_type.get(kind, 0) + 1
    new_channels = sum(e["channels_touched"] for e in report["profiles"].values())

    report["totals"] = {
        "profiles": len(report["profiles"]),
        "matched": matched,
        "with_data": with_data,
        "channels": total_channels,
        "populated": populated,
        "by_type": by_type,
        "planned": planned,
        "planned_by_type": planned_by_type,
        "new_channels": new_channels,
    }
    return report["totals"]


def write_provenance(report: Dict[str, Any]) -> None:
    totals = report["totals"]
    lines: List[str] = []
    add = lines.append

    add("# `value_ranges` provenance")
    add("")
    add(f"Generated by `scripts/sync_value_ranges.py` on {report['date']} from the")
    add("[Open Fixture Library](https://open-fixture-library.org). Re-running the script")
    add("regenerates this file.")
    add("")
    add("Every range below came from an OFL `availableChannels[*].capabilities` entry for")
    add("the fixture named in its row. Nothing was inferred from a channel name, borrowed")
    add("from a similar fixture, or filled in with a plausible default. Where a channel")
    add("could not be sourced it carries no `value_ranges` at all - an empty gap is a")
    add("known unknown, a guessed slot is a defect that reaches a venue.")
    add("")
    add("## Coverage")
    add("")
    add(f"- Profiles matched to an OFL fixture: **{totals['matched']} / {totals['profiles']}**")
    add(f"- Profiles that gained at least one range: **{totals['with_data']} / {totals['profiles']}**")
    add(f"- Channels carrying `value_ranges`: **{totals['populated']} / {totals['channels']}**")
    add("")
    add("By channel type:")
    add("")
    add("| channel_type | populated | total |")
    add("| --- | --- | --- |")
    for kind in sorted(totals["by_type"]):
        total, done = totals["by_type"][kind]
        if done or kind in PRIORITY_TYPES:
            add(f"| `{kind}` | {done} | {total} |")
    add("")
    add("## Derivation rules")
    add("")
    add("- A range's name takes the most specific thing OFL states: `comment`, else the")
    add("  wheel slot, else `shutterEffect`/`effectName`, else `colors` with the")
    add("  capability type, else the type alone. Speed, angle and intensity spans are")
    add("  appended as `start->end`; `randomTiming` appends `(random)`. Where a")
    add("  capability carries both an effect and a comment the effect leads and the")
    add("  comment trails in parentheses.")
    add("- Adjacent capabilities that derive the *same* name are merged into one range.")
    add("  This is lossless: each part already asserted that meaning.")
    add("- Names are folded to ASCII, matching the rest of the corpus.")
    add("- Fine channels never receive ranges, matching `gdtf_parser`.")
    add("- Channels OFL models as one continuous capability (pan, dimmer, a bare zoom)")
    add("  are skipped: there are no slots to name.")
    add("")
    add("If you audit a range against an OFL *web page* rather than its JSON, expect the")
    add("page to have more rows than we do where consecutive capabilities share a name")
    add("(we merged them), and fewer where a capability is pure \"no function\" (the page")
    add("hides those, the API returns them and we keep them, so the byte space stays")
    add("fully accounted for).")
    add("")
    add("## Matched profiles")
    add("")

    for stem in sorted(report["profiles"]):
        entry = report["profiles"][stem]
        if not entry["ofl_key"]:
            continue
        add(f"### `{stem}.json` - {entry['manufacturer']} {entry['model']} ({entry['fixture_type']})")
        add("")
        add(f"- **OFL fixture:** [`{entry['ofl_key']}`]({OFL_BASE}/{entry['ofl_key']}) - \"{entry['ofl_name']}\"")
        add(f"- **Retrieved:** {report['date']}")
        add(f"- **Why this fixture:** {entry['rationale']}")
        add("")
        if entry["written"]:
            add("| mode | ch | our channel | type | OFL channel | ranges |")
            add("| --- | --- | --- | --- | --- | --- |")
            for mode_name, number, name, kind, ofl_channel, count in entry["written"]:
                add(f"| {mode_name} | {number} | {name} | `{kind}` | {ofl_channel} | {count} |")
            add("")
        else:
            add("No channel on this profile could be sourced; see the refusals below.")
            add("")
        if entry.get("caveats"):
            add("OFL flags its own uncertainty on these channels. The DMX boundaries")
            add("still come from the manufacturer's manual; what is in doubt is noted:")
            add("")
            for name, asked in sorted(entry["caveats"].items()):
                for question in asked:
                    add(f"- **{name}** - OFL asks: {question}")
            add("")
        if entry["skipped"]:
            add("Refused on this profile:")
            add("")
            for name, why in entry["skipped"]:
                add(f"- **{name}** - {why}")
            add("")

    add("## Profiles with no OFL match")
    add("")
    add("Each of these was checked against the manufacturer's full OFL catalogue and the")
    add("search API. None gained any `value_ranges`.")
    add("")
    add("| profile | fixture | why not |")
    add("| --- | --- | --- |")
    for stem in sorted(report["profiles"]):
        entry = report["profiles"][stem]
        if entry["ofl_key"]:
            continue
        why = entry["skipped"][0][1] if entry["skipped"] else "no reason recorded"
        add(f"| `{stem}.json` | {entry['manufacturer']} {entry['model']} ({entry['fixture_type']}) | {why} |")
    add("")

    PROVENANCE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def audit(cache_dir: Path, offline: bool) -> None:
    """List what each matched fixture still leaves on the table, both sides."""
    fetcher = OflFetcher(cache_dir, offline=offline)
    for stem, match in sorted(MATCHES.items()):
        payload = fetcher.fixture(match.ofl_key)
        with (BUNDLED_DIR / f"{stem}.json").open(encoding="utf-8") as handle:
            document = json.load(handle)
        ours = {
            c["name"]: c["channel_type"]
            for mode in document["modes"] for c in mode["channels"]
            if not c.get("is_fine") and c["channel_type"] in PRIORITY_TYPES
        }
        unmapped_ours = sorted(set(ours) - set(match.channels) - set(match.skipped))
        theirs = {
            name for name, body in payload.get("availableChannels", {}).items()
            if body.get("capabilities")
        }
        unmapped_theirs = sorted(theirs - set(match.channels.values()))
        print(f"== {stem}  ({match.ofl_key})")
        print(f"   ours, priority type, unmapped and unexplained: {unmapped_ours or 'none'}")
        print(f"   OFL, has capabilities, unused: {unmapped_theirs or 'none'}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--check", action="store_true",
                        help="only prove the serialiser round-trips every file byte for byte")
    parser.add_argument("--audit", action="store_true",
                        help="list channels left unmapped on both sides")
    parser.add_argument("--offline", action="store_true",
                        help="use only cached OFL definitions")
    parser.add_argument("--cache", type=Path, default=default_cache_dir(),
                        help="directory for cached OFL fixture JSON")
    args = parser.parse_args(argv)

    failures = round_trip_check()
    if failures:
        print("Refusing to edit: the serialiser does not reproduce these files exactly:")
        for failure in failures:
            print(f"  - {failure}")
        return 2
    print(f"Round trip: all {len(profile_paths())} bundled files reproduce byte for byte.")
    if args.check:
        return 0

    if args.audit:
        audit(args.cache, args.offline)
        return 0

    try:
        report = run(dry_run=args.dry_run, offline=args.offline, cache_dir=args.cache)
    except Refusal as exc:
        print(f"Refused: {exc}")
        return 2

    totals = summarise(report)
    print(f"Profiles matched to an OFL fixture : {totals['matched']}/{totals['profiles']}")
    print(f"Profiles that gained ranges        : {totals['with_data']}/{totals['profiles']}")
    if args.dry_run:
        print(f"Channels this run would populate   : {totals['planned']}/{totals['channels']}")
        for kind in sorted(totals["planned_by_type"]):
            total = totals["by_type"][kind][0]
            print(f"    {kind:<14} {totals['planned_by_type'][kind]}/{total}")
    else:
        print(f"Channels carrying value_ranges     : {totals['populated']}/{totals['channels']}")
        for kind in sorted(totals["by_type"]):
            total, done = totals["by_type"][kind]
            if done:
                print(f"    {kind:<14} {done}/{total}")
        print(f"Newly written this run             : {totals['new_channels']}")

    if not args.dry_run:
        write_provenance(report)
        print(f"Wrote {PROVENANCE.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
