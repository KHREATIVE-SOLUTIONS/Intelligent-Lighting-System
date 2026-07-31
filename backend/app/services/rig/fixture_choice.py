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
