"""
Rig Loader
==========

Turns a patched rig in the database into a FixtureGroupManager the effects
engine can drive: RigFixture + fixture profile -> engine Fixture -> DMX.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.fixture import (
    ChannelType,
    Fixture as FixtureProfile,
    FixtureMode,
    FixtureType,
)
from app.models.rig import Rig, RigFixture
from app.services.effects.fixture_groups import Fixture, FixtureGroupManager

logger = logging.getLogger(__name__)

DMX_UNIVERSE_SIZE = 512
DEFAULT_PAN_RANGE = 540.0
DEFAULT_TILT_RANGE = 270.0

# Profile fixture type -> the engine's grouping vocabulary. The engine treats
# "mover"/"wash" as motion capable, excludes "bar" from move-in-black, and
# leaves "strobe" out of every movement path.
ENGINE_FIXTURE_TYPES: Dict[FixtureType, str] = {
    FixtureType.MOVING_HEAD: "mover",
    FixtureType.SPOT: "mover",
    FixtureType.BEAM: "mover",
    FixtureType.WASH: "wash",
    FixtureType.LED_PAR: "wash",
    FixtureType.DIMMER: "wash",
    FixtureType.LED_BAR: "bar",
    FixtureType.STROBE: "strobe",
    FixtureType.LASER: "effect",
    FixtureType.EFFECT: "effect",
    FixtureType.OTHER: "effect",
}
DEFAULT_ENGINE_TYPE = "effect"

# Used when a profile carries no mode at all: every offset here is a guess.
# Only a moving head has a layout conventional enough to guess pan/tilt from;
# for anything else the guess stays inside intensity and colour, because writing
# movement to a fixture that cannot move latches it against its end stop.
GENERIC_CHANNEL_MAPS: Dict[str, Dict[str, int]] = {
    "mover": {
        'pan': 0, 'pan_fine': 1, 'tilt': 2, 'tilt_fine': 3,
        'speed': 4, 'dimmer': 5, 'shutter': 6,
        'red': 7, 'green': 8, 'blue': 9, 'white': 10,
        'color_wheel': 11, 'gobo': 12, 'gobo_rotation': 13,
        'prism': 14, 'focus': 15,
    },
    "wash": {
        'dimmer': 5, 'shutter': 6,
        'red': 7, 'green': 8, 'blue': 9, 'white': 10,
        'zoom': 11,
    },
    "bar": {
        'dimmer': 0, 'strobe': 1,
        'red': 2, 'green': 3, 'blue': 4, 'white': 5,
        'amber': 6, 'uv': 7, 'macro': 8, 'speed': 9,
    },
    "strobe": {
        'dimmer': 0, 'strobe': 1,
    },
    "effect": {
        'dimmer': 0,
    },
}
GENERIC_CHANNEL_SPANS: Dict[str, int] = {
    "mover": 16,
    "wash": 14,
    "bar": 12,
    "strobe": 4,
    "effect": 1,
}

TYPE_GROUP_NAMES: Dict[str, str] = {
    "mover": "movers",
    "wash": "washes",
    "bar": "bars",
    "strobe": "strobes",
    "effect": "effects",
}


@dataclass
class RigLoadDiagnostics:
    """What the loader made of a rig, for the boot path to log."""

    rig_id: Optional[int] = None
    rig_name: Optional[str] = None
    fixture_count: int = 0
    universes: Dict[int, int] = field(default_factory=dict)
    groups: Dict[str, int] = field(default_factory=dict)
    skipped: List[Dict[str, Any]] = field(default_factory=list)
    modes_guessed: List[Dict[str, Any]] = field(default_factory=list)
    generic_maps: List[Dict[str, Any]] = field(default_factory=list)
    channel_aliases: List[Dict[str, Any]] = field(default_factory=list)
    truncated: List[Dict[str, Any]] = field(default_factory=list)
    group_conflicts: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def alias_count(self) -> int:
        return sum(int(entry.get("count", 0)) for entry in self.channel_aliases)

    def summary(self) -> str:
        universes = ", ".join(
            f"u{universe}={count}" for universe, count in sorted(self.universes.items())
        ) or "none"
        return (
            f"rig {self.rig_id} '{self.rig_name}': {self.fixture_count} fixtures "
            f"({universes}); {len(self.skipped)} skipped, "
            f"{len(self.modes_guessed)} modes guessed, "
            f"{len(self.generic_maps)} generic maps, "
            f"{self.alias_count} aliased channels"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rig_id": self.rig_id,
            "rig_name": self.rig_name,
            "fixture_count": self.fixture_count,
            "universes": dict(self.universes),
            "groups": dict(self.groups),
            "skipped": list(self.skipped),
            "modes_guessed": list(self.modes_guessed),
            "generic_maps": list(self.generic_maps),
            "channel_aliases": list(self.channel_aliases),
            "truncated": list(self.truncated),
            "group_conflicts": list(self.group_conflicts),
            "errors": list(self.errors),
        }


def get_rig_diagnostics(manager: Optional[FixtureGroupManager]) -> Optional[RigLoadDiagnostics]:
    """Diagnostics recorded on a manager built by this module."""
    return getattr(manager, "rig_diagnostics", None) if manager is not None else None


def _rig_query(rig_id: Optional[int] = None):
    """Select rigs with every relationship the loader touches already loaded."""
    query = select(Rig).options(
        selectinload(Rig.fixtures)
        .selectinload(RigFixture.fixture)
        .selectinload(FixtureProfile.modes)
        .selectinload(FixtureMode.channels),
        selectinload(Rig.fixtures)
        .selectinload(RigFixture.mode)
        .selectinload(FixtureMode.channels),
    )
    if rig_id is not None:
        query = query.where(Rig.id == rig_id)
    return query


def _engine_fixture_type(profile: FixtureProfile) -> str:
    raw = getattr(profile, "fixture_type", None)
    if raw is None:
        return DEFAULT_ENGINE_TYPE
    if isinstance(raw, FixtureType):
        return ENGINE_FIXTURE_TYPES.get(raw, DEFAULT_ENGINE_TYPE)
    try:
        return ENGINE_FIXTURE_TYPES.get(FixtureType(str(raw)), DEFAULT_ENGINE_TYPE)
    except ValueError:
        return DEFAULT_ENGINE_TYPE


def _as_int(value: Any, default: int = 0) -> int:
    """SQLite does not enforce Integer affinity and importers write untyped dicts."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _travel_range(value: Any, default: float) -> float:
    """Degrees of travel. 0 means the fixture cannot move and must stay 0."""
    if value is None:
        return default
    try:
        travel = float(value)
    except (TypeError, ValueError):
        return default
    return travel if travel > 0.0 else 0.0


def _select_mode(
    rf: RigFixture,
    profile: FixtureProfile,
    diagnostics: RigLoadDiagnostics,
) -> Optional[FixtureMode]:
    """Resolve the mode this patched fixture is addressed in."""
    modes = list(profile.modes or [])
    mode = rf.mode
    if mode is not None and mode.fixture_id == profile.id:
        return mode

    if mode is not None:
        diagnostics.errors.append(
            f"rig fixture {rf.id}: mode {mode.id} belongs to profile {mode.fixture_id}, "
            f"not {profile.id}"
        )

    if not modes:
        return None

    modes.sort(key=lambda m: (m.id or 0))
    chosen = modes[0]
    diagnostics.modes_guessed.append({
        "rig_fixture_id": rf.id,
        "fixture": f"{profile.manufacturer} {profile.model}",
        "mode": chosen.name,
        "channel_count": chosen.channel_count,
        "reason": "no mode_id on the patch" if rf.mode_id is None else "mode_id not on this profile",
    })
    return chosen


def _build_channel_map(
    mode: FixtureMode,
    rf: RigFixture,
    profile: FixtureProfile,
    diagnostics: RigLoadDiagnostics,
) -> Tuple[Dict[str, int], Dict[str, tuple], int]:
    """Map a mode's channels to engine channel names and 0-based offsets.

    channel_number is 1-based. A channel type that appears more than once in a
    mode keeps the lowest channel_number under its canonical name; the rest are
    exposed as "<type>_2", "<type>_3", ... so nothing silently collides. The
    renderer mirrors the canonical value onto those aliases, which is right for
    per-cell duplicates ("Cell 1".."Cell 4") and wrong for a fine channel, so a
    fine duplicate is aliased under a name the renderer never emits instead.
    """
    channels: Dict[str, int] = {}
    limits: Dict[str, tuple] = {}
    seen: Dict[str, int] = {}
    aliases = 0
    span = 0

    ordered = sorted(
        (ch for ch in (mode.channels or []) if ch.channel_number is not None),
        key=lambda ch: (int(ch.channel_number), int(ch.id or 0)),
    )

    for channel in ordered:
        try:
            number = int(channel.channel_number)
        except (TypeError, ValueError):
            continue
        if number < 1:
            continue

        raw_type = channel.channel_type
        name = raw_type.value if isinstance(raw_type, ChannelType) else str(raw_type or ChannelType.OTHER.value)

        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            is_fine = bool(getattr(channel, "is_fine", False)) or getattr(channel, "coarse_channel", None) is not None
            if is_fine and not name.endswith("_fine"):
                name = f"{name}_fine_{seen[name]}"
            else:
                name = f"{name}_{seen[name]}"
            aliases += 1

        channels[name] = number - 1
        span = max(span, number)

        low = 0 if channel.min_value is None else int(channel.min_value)
        high = 255 if channel.max_value is None else int(channel.max_value)
        if (low, high) != (0, 255):
            limits[name] = (max(0, min(255, low)), max(0, min(255, high)))

    if aliases:
        diagnostics.channel_aliases.append({
            "rig_fixture_id": rf.id,
            "fixture": f"{profile.manufacturer} {profile.model}",
            "mode": mode.name,
            "count": aliases,
        })

    return channels, limits, max(span, int(mode.channel_count or 0))


def _build_fixture(
    rf: RigFixture,
    diagnostics: RigLoadDiagnostics,
) -> Optional[Fixture]:
    """Build one engine fixture, or None when the patch is not drivable."""
    profile = rf.fixture
    if profile is None:
        diagnostics.skipped.append({
            "rig_fixture_id": rf.id,
            "name": rf.name,
            "reason": "no fixture profile",
        })
        return None

    address = rf.dmx_address
    try:
        address = int(address)
    except (TypeError, ValueError):
        address = 0
    if address < 1 or address > DMX_UNIVERSE_SIZE:
        diagnostics.skipped.append({
            "rig_fixture_id": rf.id,
            "name": rf.name,
            "reason": f"dmx address {rf.dmx_address} outside 1-{DMX_UNIVERSE_SIZE}",
        })
        return None

    try:
        universe = int(rf.universe or 0)
    except (TypeError, ValueError):
        universe = 0
    if universe < 0:
        universe = 0

    engine_type = _engine_fixture_type(profile)
    mode = _select_mode(rf, profile, diagnostics)

    if mode is not None:
        channels, limits, span = _build_channel_map(mode, rf, profile, diagnostics)
    else:
        channels = dict(GENERIC_CHANNEL_MAPS.get(engine_type, GENERIC_CHANNEL_MAPS["effect"]))
        limits = {}
        span = GENERIC_CHANNEL_SPANS.get(engine_type, len(channels))
        diagnostics.generic_maps.append({
            "rig_fixture_id": rf.id,
            "fixture": f"{profile.manufacturer} {profile.model}",
            "engine_type": engine_type,
            "reason": "profile has no modes",
        })

    if not channels:
        diagnostics.skipped.append({
            "rig_fixture_id": rf.id,
            "name": rf.name,
            "reason": f"mode '{mode.name if mode else '?'}' declares no channels",
        })
        return None

    if address + span - 1 > DMX_UNIVERSE_SIZE:
        diagnostics.truncated.append({
            "rig_fixture_id": rf.id,
            "name": rf.name,
            "universe": universe,
            "dmx_address": address,
            "channel_count": span,
        })

    fixture = Fixture(
        id=f"rf{rf.id}",
        name=rf.name or profile.model or f"Fixture {rf.id}",
        dmx_address=address,
        universe=universe,
        channels=channels,
        x=float(rf.position_x or 0.0),
        y=float(rf.position_y or 0.0),
        z=float(rf.position_z or 0.0),
        fixture_type=engine_type,
    )
    # Travel a fixture has no channel for is travel it does not have, whatever
    # the profile row claims: the model default is 540/270 for every row that
    # never set one.
    fixture.pan_range = _travel_range(profile.pan_range, DEFAULT_PAN_RANGE) if 'pan' in channels else 0.0
    fixture.tilt_range = _travel_range(profile.tilt_range, DEFAULT_TILT_RANGE) if 'tilt' in channels else 0.0
    fixture.channel_limits = limits
    return fixture


def _build_groups(
    manager: FixtureGroupManager,
    fixtures: List[Fixture],
    group_names: Dict[str, List[str]],
    diagnostics: RigLoadDiagnostics,
) -> None:
    """Recreate the demo rig's type groups plus one group per rig group_name."""
    by_type: Dict[str, List[str]] = {name: [] for name in TYPE_GROUP_NAMES}
    for fixture in fixtures:
        by_type.setdefault(fixture.fixture_type, []).append(fixture.id)

    for engine_type, group_name in TYPE_GROUP_NAMES.items():
        manager.create_custom_group(group_name, list(by_type.get(engine_type, [])))

    manager.create_custom_group(
        "movers_washes",
        list(by_type.get("mover", [])) + list(by_type.get("wash", [])),
    )

    # A rig group_name that lands on one of these would replace the group the
    # engine looks up for every effect.
    reserved = set(manager.groups)

    for raw_name, ids in group_names.items():
        name = raw_name.strip()
        if not name or not ids:
            continue
        if name in reserved:
            diagnostics.group_conflicts.append({
                "group_name": raw_name,
                "fixture_count": len(ids),
                "reason": "name is reserved by the engine's own groups",
            })
            continue
        manager.create_custom_group(name, list(ids))

    diagnostics.groups = {
        name: len(group.fixture_ids) for name, group in manager.groups.items()
    }


def _build_manager(rig: Rig, diagnostics: RigLoadDiagnostics) -> FixtureGroupManager:
    manager = FixtureGroupManager()

    patches = []
    for rf in (rig.fixtures or []):
        if rf.is_active is False:
            diagnostics.skipped.append({
                "rig_fixture_id": rf.id,
                "name": rf.name,
                "reason": "fixture is not active",
            })
            continue
        patches.append(rf)

    patches.sort(key=lambda rf: (_as_int(rf.universe), _as_int(rf.dmx_address), _as_int(rf.id)))

    fixtures: List[Fixture] = []
    group_names: Dict[str, List[str]] = {}

    for rf in patches:
        try:
            fixture = _build_fixture(rf, diagnostics)
        except Exception as e:
            diagnostics.skipped.append({
                "rig_fixture_id": getattr(rf, "id", None),
                "name": getattr(rf, "name", None),
                "reason": f"unreadable patch: {e}",
            })
            logger.warning("Skipping rig fixture %s: %s", getattr(rf, "id", None), e, exc_info=True)
            continue

        if fixture is None:
            continue

        fixtures.append(fixture)
        if rf.group_name:
            group_names.setdefault(rf.group_name, []).append(fixture.id)

    manager.add_fixtures(fixtures)
    _build_groups(manager, fixtures, group_names, diagnostics)

    diagnostics.fixture_count = len(fixtures)
    for fixture in fixtures:
        diagnostics.universes[fixture.universe] = diagnostics.universes.get(fixture.universe, 0) + 1

    return manager


def _empty_manager(diagnostics: RigLoadDiagnostics) -> FixtureGroupManager:
    manager = FixtureGroupManager()
    manager.rig_diagnostics = diagnostics
    return manager


def build_manager_from_rig(rig: Rig) -> FixtureGroupManager:
    """Build a FixtureGroupManager from an already eager-loaded rig.

    Pure and synchronous - it touches no session, so every relationship it walks
    (rig.fixtures -> rf.fixture -> .modes -> .channels, rf.mode -> .channels)
    must already be loaded. Never raises: a broken patch or an unreadable profile
    yields a partial manager with the reason in `get_rig_diagnostics(manager)`.
    """
    diagnostics = RigLoadDiagnostics(
        rig_id=getattr(rig, "id", None),
        rig_name=getattr(rig, "name", None),
    )
    manager = _build_manager(rig, diagnostics)
    manager.rig_diagnostics = diagnostics
    return manager


async def build_manager_for_rig_id(db: AsyncSession, rig_id: int) -> FixtureGroupManager:
    """Build a FixtureGroupManager from the rig patched under `rig_id`.

    Always returns a manager. A missing rig or an unreadable one yields an empty
    manager with the reason recorded in `get_rig_diagnostics(manager)` - the show
    must run either way.
    """
    try:
        result = await db.execute(_rig_query(rig_id))
        rig = result.scalar_one_or_none()
    except Exception as e:
        logger.error("Could not load rig %s: %s", rig_id, e, exc_info=True)
        return _empty_manager(RigLoadDiagnostics(
            rig_id=rig_id, errors=[f"could not load rig {rig_id}: {e}"]
        ))

    if rig is None:
        return _empty_manager(RigLoadDiagnostics(
            rig_id=rig_id, errors=[f"rig {rig_id} not found"]
        ))

    manager = build_manager_from_rig(rig)
    logger.info("Loaded %s", get_rig_diagnostics(manager).summary())
    return manager


async def load_active_rig(
    db: AsyncSession,
) -> Tuple[Optional[FixtureGroupManager], Optional[Rig]]:
    """Build a manager from the active rig.

    `Rig.is_active` is not unique, so the most recently updated active rig wins
    and the number of candidates is logged - two imports both stamping
    is_active=True must not make which rig boots depend on row order.

    Returns (None, None) when no rig is marked active, and (None, rig) when the
    active rig produced no drivable fixture - both mean the caller should fall
    back to its built-in rig rather than run a dark show.
    """
    try:
        candidate_count = int((await db.execute(
            select(func.count()).select_from(Rig).where(Rig.is_active == True)
        )).scalar() or 0)
        result = await db.execute(
            _rig_query()
            .where(Rig.is_active == True)
            .order_by(Rig.updated_at.desc(), Rig.id.desc())
            .limit(1)
        )
        rig = result.scalars().first()
    except Exception as e:
        logger.error("Could not query the active rig: %s", e, exc_info=True)
        return None, None

    if rig is None:
        logger.info("No active rig configured")
        return None, None

    logger.info(
        "Active rig: '%s' (id=%s) chosen from %d active candidate(s)",
        rig.name, rig.id, candidate_count,
    )

    manager = build_manager_from_rig(rig)
    diagnostics = get_rig_diagnostics(manager)

    if diagnostics.fixture_count == 0:
        logger.warning("Active %s - nothing drivable", diagnostics.summary())
        return None, rig

    logger.info("Active %s", diagnostics.summary())
    return manager, rig
