"""
Picking a fixture profile that can actually make light
=====================================================

The template gallery and the wizard both patch a fixture *type* rather than a
specific profile, so something has to choose which bundled profile and which of
its modes to use. "First fixture of the type, first mode" is not good enough:
the only bundled ``effect`` profile is the ADJ Hyper Gem, whose first mode is
2-Channel = macro + speed. Nothing in app/services/lighting renders a macro
channel, so a fixture patched on that mode occupies DMX addresses, appears in
the patch and on the plan, and can never be turned on - the exact symptom the
flash-to-identify walkthrough exists to diagnose.

A mode is usable when some renderer can raise its output: an intensity channel
or a colour channel it can drive.
"""

from typing import Any, Iterable, List, Optional, Sequence

# Channel types the lighting renderers actually write a level to. Shutter and
# strobe are excluded on purpose: they gate light that a dimmer or a colour has
# to provide first, so a mode carrying only those still never lights.
LIGHT_CHANNEL_TYPES = frozenset({
    "dimmer",
    "red", "green", "blue", "white", "amber", "uv", "lime", "indigo",
    "cyan", "magenta", "yellow",
})


def channel_type_name(channel: Any) -> str:
    """The channel's type as a plain lowercase string.

    Channels arrive as ORM rows carrying a ChannelType enum, as bare enums, and
    as strings depending on the caller, and a mismatch here silently reports a
    perfectly good profile as undrivable.
    """
    value = getattr(channel, "channel_type", channel)
    value = getattr(value, "value", value)
    return str(value).strip().lower()


def mode_makes_light(channels: Iterable[Any]) -> bool:
    """True when this mode has a channel a renderer can raise."""
    return any(channel_type_name(c) in LIGHT_CHANNEL_TYPES for c in channels)


def choose_mode(modes: Sequence[Any]) -> Optional[Any]:
    """The first mode that can make light, else the first mode, else None.

    Falling back to the first mode keeps a profile patchable rather than
    dropping the group; the caller reports the gap.
    """
    usable = [m for m in modes if mode_makes_light(getattr(m, "channels", []) or [])]
    if usable:
        return usable[0]
    return modes[0] if modes else None


def undrivable_modes(modes: Sequence[Any]) -> List[Any]:
    """Modes in this profile that no renderer could turn on."""
    return [m for m in modes if not mode_makes_light(getattr(m, "channels", []) or [])]


# What a mode lets the show do, by channel type. A mode is worth more the more of
# these it reaches; repeating one (a pixel mode's eight RGB cells) adds nothing,
# because the renderer mirrors one value onto every cell anyway.
MODE_FEATURES = {
    "dimmer": "dimmer",
    "red": "red", "green": "green", "blue": "blue", "white": "white",
    "amber": "amber", "uv": "UV", "lime": "lime", "indigo": "indigo",
    "cyan": "cyan", "magenta": "magenta", "yellow": "yellow",
    "cto": "CTO", "ctb": "CTB",
    "color_wheel": "colour wheel",
    "pan": "pan", "tilt": "tilt",
    "pan_fine": "fine pan", "tilt_fine": "fine tilt",
    "strobe": "strobe", "shutter": "strobe",
    "gobo": "gobo", "gobo_rotation": "gobo rotation",
    "gobo2": "second gobo",
    "prism": "prism", "zoom": "zoom", "focus": "focus",
    "frost": "frost", "iris": "iris",
}


def _channels_of(mode: Any) -> List[Any]:
    if isinstance(mode, dict):
        return list(mode.get("channels") or [])
    return list(getattr(mode, "channels", None) or [])


def _type_of(channel: Any) -> str:
    if isinstance(channel, dict):
        value = channel.get("channel_type", "other")
        return str(getattr(value, "value", value)).strip().lower()
    return channel_type_name(channel)


def _channel_count(mode: Any) -> int:
    raw = mode.get("channel_count") if isinstance(mode, dict) else getattr(mode, "channel_count", None)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return len(_channels_of(mode))


def mode_features(mode: Any) -> List[str]:
    """Plain names of what this mode can do, in a stable order, without repeats."""
    seen: List[str] = []
    for channel in _channels_of(mode):
        feature = MODE_FEATURES.get(_type_of(channel))
        if feature and feature not in seen:
            seen.append(feature)
    return seen


def recommend_mode(modes: Sequence[Any]) -> Optional[Any]:
    """The mode a programmer would patch for an automatic show.

    The one reaching the most features wins, and among equals the one using the
    fewest DMX channels: a moving head's 16-bit mode beats its 8-bit one because
    fine pan and tilt make movement smooth, but an LED bar's 4-channel RGBW+dimmer
    mode beats its 40-channel pixel mode because the show drives every cell the
    same. Modes that cannot make light are only chosen when nothing else can.
    """
    candidates = [m for m in modes if mode_makes_light_any(m)] or list(modes)
    if not candidates:
        return None
    ranked = sorted(
        enumerate(candidates),
        key=lambda item: (-_feature_score(item[1]), _channel_count(item[1]), item[0]),
    )
    return ranked[0][1]


# On a fixture that mixes colour from LEDs, a "colour wheel" channel is a macro
# table: the show mixes its own colours, and a macro left at a non-zero value
# overrides them. It earns that mode nothing.
_MIXING_FEATURES = frozenset({"red", "green", "blue", "cyan", "magenta", "yellow"})


def _feature_score(mode: Any) -> int:
    features = set(mode_features(mode))
    if features & _MIXING_FEATURES:
        features.discard("colour wheel")
    return len(features)


def mode_makes_light_any(mode: Any) -> bool:
    """mode_makes_light for an ORM mode or a converted mode dict."""
    return any(_type_of(c) in LIGHT_CHANNEL_TYPES for c in _channels_of(mode))
