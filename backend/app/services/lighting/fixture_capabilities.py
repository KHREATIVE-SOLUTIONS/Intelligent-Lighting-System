"""
Fixture Capability Profiles
===========================

Capability descriptors used by look/cue engines and visualizers.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.schemas.lighting_look import FixtureCapabilityProfile


DEFAULT_PAN_RANGE = 540.0
DEFAULT_TILT_RANGE = 270.0


DEFAULT_CAPABILITY_PROFILES: dict[str, FixtureCapabilityProfile] = {
    "beam": FixtureCapabilityProfile(
        role="beam",
        supports_gobo=True,
        supports_prism=True,
        supports_frost=True,
        supports_zoom=False,
        supports_focus=True,
        supports_iris=False,
        movement_speed_class="fast",
    ),
    "spot": FixtureCapabilityProfile(
        role="spot",
        supports_gobo=True,
        supports_prism=False,
        supports_frost=True,
        supports_zoom=True,
        supports_focus=True,
        supports_iris=True,
        movement_speed_class="slow",
    ),
    "effect": FixtureCapabilityProfile(
        role="effect",
        supports_gobo=False,
        supports_prism=False,
        supports_frost=False,
        supports_zoom=False,
        supports_focus=False,
        supports_iris=False,
        movement_speed_class="static",
    ),
    "wash": FixtureCapabilityProfile(
        role="wash",
        supports_gobo=False,
        supports_prism=False,
        supports_frost=True,
        supports_zoom=True,
        supports_focus=False,
        supports_iris=False,
        movement_speed_class="slow",
    ),
}


FIXTURE_TYPE_TO_ROLE: dict[str, str] = {
    "beam": "beam",
    "moving_head": "beam",
    "mover": "beam",
    "spot": "spot",
    "profile": "spot",
    "wash": "wash",
    "led_par": "wash",
    "par": "wash",
    "led_bar": "wash",
    "bar": "wash",
    "strobe": "effect",
    "laser": "effect",
    "effect": "effect",
}


# Channel types that answer one capability question between them. Keyed on the
# ChannelType *values* the engine uses as channel names, so a type this build
# does not know about yet costs nothing here.
GOBO_CHANNELS = frozenset({"gobo", "gobo2"})
GOBO_ROTATION_CHANNELS = frozenset({"gobo_rotation", "gobo2_rotation"})
RGB_CHANNELS = frozenset({"red", "green", "blue"})
CMY_CHANNELS = frozenset({"cyan", "magenta", "yellow"})
EMITTER_CHANNELS = RGB_CHANNELS | CMY_CHANNELS | frozenset(
    {"white", "amber", "uv", "lime", "indigo"}
)


@dataclass(frozen=True)
class FixtureCapabilities:
    """What a fixture can actually do, read from the channels it declares."""

    role: str
    movement_speed_class: str
    supports_dimmer: bool = False
    supports_shutter: bool = False
    supports_strobe: bool = False
    supports_rgb: bool = False
    supports_cmy: bool = False
    supports_white: bool = False
    supports_amber: bool = False
    supports_uv: bool = False
    supports_color_wheel: bool = False
    supports_gobo: bool = False
    supports_gobo_rotation: bool = False
    supports_prism: bool = False
    supports_zoom: bool = False
    supports_focus: bool = False
    supports_iris: bool = False
    supports_frost: bool = False
    supports_16bit_pan: bool = False
    supports_16bit_tilt: bool = False
    pan_range: float = 0.0
    tilt_range: float = 0.0

    @property
    def supports_movement(self) -> bool:
        return self.pan_range > 0.0 or self.tilt_range > 0.0

    def to_profile(self) -> FixtureCapabilityProfile:
        """Narrow to the capability profile the look spec carries."""
        return FixtureCapabilityProfile(
            role=self.role,
            supports_gobo=self.supports_gobo,
            supports_prism=self.supports_prism,
            supports_frost=self.supports_frost,
            supports_zoom=self.supports_zoom,
            supports_focus=self.supports_focus,
            supports_iris=self.supports_iris,
            movement_speed_class=self.movement_speed_class,
        )


def _canonical_channel_name(name: str) -> str:
    """The channel type a repeated-channel alias ("gobo_2") stands for."""
    base, _, suffix = name.rpartition("_")
    return base if base and suffix.isdigit() else name


def _channel_rows(source: Any) -> Any:
    """The channel container a source carries.

    The library ORM hangs channels off modes, so a `app.models.fixture.Fixture`
    has no `channels` of its own; its capability is the union across its modes.
    """
    channels = getattr(source, "channels", None)
    if channels is not None:
        return channels

    modes = getattr(source, "modes", None)
    if modes is not None:
        rows: list[Any] = []
        for mode in modes or []:
            rows.extend(getattr(mode, "channels", None) or [])
        return rows

    return source


def _channel_names(source: Any) -> set[str]:
    """Channel type names declared by a fixture, a channel map, a mode or a name list."""
    channels = _channel_rows(source)

    if isinstance(channels, Mapping):
        raw: Iterable[Any] = list(channels.keys())
    elif isinstance(channels, (str, bytes)):
        raw = []
    elif isinstance(channels, Iterable):
        raw = list(channels)
    else:
        raw = []

    names: set[str] = set()
    for entry in raw:
        value = getattr(entry, "channel_type", entry)
        value = getattr(value, "value", value)
        if not isinstance(value, str):
            continue
        name = _canonical_channel_name(value.strip().lower())
        if not name:
            continue
        names.add(name)
        # A profile may type a fine channel as a second channel of the coarse type.
        # The engine's channel map renames those; a raw channel row does not.
        if getattr(entry, "is_fine", False) and not name.endswith("_fine"):
            names.add(f"{name}_fine")
    return names


def _travel(source: Any, attribute: str, default: float) -> float:
    """Declared degrees of travel. 0 means the fixture cannot move that axis."""
    value = getattr(source, attribute, None)
    if value is None:
        # A FixtureMode carries no travel of its own; it lives on the profile.
        value = getattr(getattr(source, "fixture", None), attribute, None)
    if value is None:
        return default
    try:
        travel = float(value)
    except (TypeError, ValueError):
        return default
    return travel if travel > 0.0 else 0.0


def _known_type(fixture_type: str | None, role_hint: str | None) -> bool:
    """Whether the type table recognises this fixture rather than defaulting it."""
    if (role_hint or "").strip().lower() in DEFAULT_CAPABILITY_PROFILES:
        return True
    return (fixture_type or "").strip().lower() in FIXTURE_TYPE_TO_ROLE


def _infer_role(attributes: set[str]) -> str:
    if "pan" in attributes or "tilt" in attributes:
        return "spot" if attributes & GOBO_CHANNELS else "beam"
    return "wash" if attributes & EMITTER_CHANNELS else "effect"


def get_capability_profile_for_fixture(
    fixture_type: str | None,
    role_hint: str | None = None,
) -> FixtureCapabilityProfile:
    """
    Resolve a fixture capability profile from fixture metadata.

    Priority:
    1) Explicit role hint
    2) Fixture type mapping
    3) Beam default profile
    """
    role_key = (role_hint or "").strip().lower()
    if role_key in DEFAULT_CAPABILITY_PROFILES:
        return FixtureCapabilityProfile.model_validate(
            DEFAULT_CAPABILITY_PROFILES[role_key].model_dump()
        )

    fixture_key = (fixture_type or "").strip().lower()
    mapped_role = FIXTURE_TYPE_TO_ROLE.get(fixture_key, "beam")

    return FixtureCapabilityProfile.model_validate(
        DEFAULT_CAPABILITY_PROFILES[mapped_role].model_dump()
    )


def derive_fixture_capabilities(
    source: Any,
    fixture_type: str | None = None,
    role_hint: str | None = None,
) -> FixtureCapabilities:
    """
    Read what a fixture can do from the channels its profile declares.

    `source` may be an engine Fixture, its channel map, a FixtureMode, or any
    iterable of channel type names or channel rows. A source that declares no
    channels falls back to the fixture-type table, which is a guess by
    construction.
    """
    declared_type = fixture_type
    if declared_type is None:
        declared_type = getattr(source, "fixture_type", None)
        if not isinstance(declared_type, str):
            declared_type = getattr(declared_type, "value", None)

    profile = get_capability_profile_for_fixture(declared_type, role_hint)
    names = _channel_names(source)

    if not names:
        movable = profile.role != "effect"
        return FixtureCapabilities(
            role=profile.role,
            movement_speed_class=profile.movement_speed_class,
            supports_gobo=profile.supports_gobo,
            supports_prism=profile.supports_prism,
            supports_frost=profile.supports_frost,
            supports_zoom=profile.supports_zoom,
            supports_focus=profile.supports_focus,
            supports_iris=profile.supports_iris,
            pan_range=_travel(source, "pan_range", DEFAULT_PAN_RANGE) if movable else 0.0,
            tilt_range=_travel(source, "tilt_range", DEFAULT_TILT_RANGE) if movable else 0.0,
        )

    # A fine channel is the low byte of the attribute its coarse channel names,
    # so it answers "is this 16-bit", never "does this attribute exist".
    attributes = {
        name[:-5] if name.endswith("_fine") else name
        for name in names
    }

    has_pan = "pan" in attributes
    has_tilt = "tilt" in attributes

    role = profile.role if _known_type(declared_type, role_hint) else _infer_role(attributes)
    if has_pan or has_tilt:
        speed_class = DEFAULT_CAPABILITY_PROFILES[role].movement_speed_class
    else:
        speed_class = "static"

    return FixtureCapabilities(
        role=role,
        movement_speed_class=speed_class,
        supports_dimmer="dimmer" in attributes,
        supports_shutter="shutter" in attributes,
        supports_strobe="shutter" in attributes or "strobe" in attributes,
        supports_rgb=RGB_CHANNELS <= attributes,
        supports_cmy=CMY_CHANNELS <= attributes,
        supports_white="white" in attributes,
        supports_amber="amber" in attributes,
        supports_uv="uv" in attributes,
        supports_color_wheel="color_wheel" in attributes,
        supports_gobo=bool(attributes & GOBO_CHANNELS),
        supports_gobo_rotation=bool(attributes & GOBO_ROTATION_CHANNELS),
        supports_prism="prism" in attributes,
        supports_zoom="zoom" in attributes,
        supports_focus="focus" in attributes,
        supports_iris="iris" in attributes,
        supports_frost="frost" in attributes,
        supports_16bit_pan=has_pan and "pan_fine" in names,
        supports_16bit_tilt=has_tilt and "tilt_fine" in names,
        pan_range=_travel(source, "pan_range", DEFAULT_PAN_RANGE) if has_pan else 0.0,
        tilt_range=_travel(source, "tilt_range", DEFAULT_TILT_RANGE) if has_tilt else 0.0,
    )
