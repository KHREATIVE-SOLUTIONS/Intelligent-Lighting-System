"""
The rig, as an export sees it
=============================

One neutral description of a rig that every writer reads. It is built from the
two places a rig lives:

- a database rig (Rig and its RigFixture rows): the same rows the layout view
  edits, the 3D view draws and rig_loader hands to the engine;
- a demo venue preset (VenuePreset): the same FixtureSpec list /api/demo/rig
  serves to the 3D view and create_venue_rig hands to the engine.

Conventions are this system's own, unchanged: universe 0-based, address 1-512,
positions in metres in stage axes (X across, Y up, -Z upstage), rotations in
degrees about X, Y and Z. Turning those into a console's is each writer's job.

Order is universe, then address, then id, so the same rig always exports the
same bytes.
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.services.demo import import_samples
from app.services.demo.patch_sheet import channel_count
from app.services.demo.venue_presets import VenuePreset
from app.services.venue_import.apply import TAG_UNCONFIRMED, TAG_UNPLACED

Vector = Tuple[float, float, float]

DMX_UNIVERSE_SIZE = 512

# Every UUID an export writes is derived from this and the rig's own ids.
_NAMESPACE = uuid.UUID("3b0d4c52-7a1e-4f0b-9c7e-2f6a8d1e5b90")

GROUP_TAG_PREFIX = "group:"

# The group the command-line script gathers unconfirmed positions in.
UNCONFIRMED_GROUP = "Position unconfirmed"
# Appended to a fixture's name when the caller asks for the mark to be visible.
UNCONFIRMED_SUFFIX = " (position unconfirmed)"
# The layer a fixture with no group goes in. A console needs one.
UNGROUPED_LAYER = "Ungrouped"

# Demo preset fixture type -> (GDTF spec, mode). The first three are the demo
# GDTFs this system can write itself; the last two have no GDTF anywhere, so an
# MVR names them and embeds nothing.
_LED_SPEC = (f"{import_samples.MAKER}@Demo LED 12ch.gdtf", "Standard 12ch")
_STROBE_SPEC = (f"{import_samples.MAKER}@Demo Strobe 4ch.gdtf", "Standard 4ch")
PRESET_SPECS: Dict[str, Tuple[str, str]] = {
    **import_samples.MVR_SPECS,
    "bar": _LED_SPEC,
    "par": _LED_SPEC,
    "strobe": _STROBE_SPEC,
}


def stable_uuid(*parts: Any) -> str:
    """The same UUID for the same parts, on every run and every machine."""
    return str(uuid.uuid5(_NAMESPACE, "/".join(str(p) for p in parts))).upper()


@dataclass(frozen=True)
class ExportFixture:
    """One patched fixture."""

    # Stable within its rig: "fixture-<row id>" or the preset's own fixture id.
    key: str
    # The console's fixture id. Unique within the rig, counted from 1.
    number: int
    name: str
    manufacturer: str
    model: str
    mode_name: str
    channel_count: Optional[int]
    universe: int
    address: int
    # None when the rig never placed it. An export then writes no position at
    # all: 0,0,0 would read back as a real place.
    position: Optional[Vector]
    rotation: Vector
    # The position is a generated guess nobody has checked against the room.
    unconfirmed: bool
    # The one group a person reads on the patch sheet. May be empty.
    layer: str
    # Every group it is in, the layer first.
    groups: Tuple[str, ...]
    # The GDTF file name an MVR names for it.
    gdtf_spec: str
    active: bool = True

    @property
    def type_name(self) -> str:
        """Maker and model as one string, the way a console lists a fixture type."""
        words: List[str] = []
        for word in f"{self.manufacturer} {self.model}".split():
            # "ILS Demo" + "Demo Spot 16ch" is "ILS Demo Spot 16ch".
            if not words or words[-1].lower() != word.lower():
                words.append(word)
        return " ".join(words) or "Unknown"

    @property
    def absolute_address(self) -> int:
        """Counted from 1 across universes: universe 1 (0-based) address 1 is 513."""
        return self.universe * DMX_UNIVERSE_SIZE + self.address

    @property
    def layer_name(self) -> str:
        return self.layer or UNGROUPED_LAYER


@dataclass(frozen=True)
class ExportGroup:
    name: str
    # Fixture numbers, in patch order.
    numbers: Tuple[int, ...]


@dataclass
class ExportRig:
    """A rig, read once, ready to be written in any format."""

    # Stable: "rig-<id>" or "preset-<name>". Every UUID is derived from it.
    key: str
    name: str
    fixtures: List[ExportFixture] = field(default_factory=list)
    # GDTF files to put in an MVR, by the name fixtures refer to them under.
    gdtf_files: Dict[str, bytes] = field(default_factory=dict)
    # Printed at the head of every file, for a preset modelled on a real room.
    disclaimer: str = ""
    # What the export had to decide or leave out. For the operator.
    notes: List[str] = field(default_factory=list)

    @property
    def groups(self) -> List[ExportGroup]:
        """Every group, in the order the patch first names it."""
        members: Dict[str, List[int]] = {}
        for fixture in self.fixtures:
            for name in fixture.groups:
                members.setdefault(name, []).append(fixture.number)
        return [ExportGroup(name, tuple(numbers)) for name, numbers in members.items()]

    @property
    def unconfirmed(self) -> List[ExportFixture]:
        return [f for f in self.fixtures if f.unconfirmed]

    @property
    def missing_gdtf(self) -> List[str]:
        """GDTF specs fixtures name that no file is embedded for."""
        return sorted({f.gdtf_spec for f in self.fixtures if f.gdtf_spec not in self.gdtf_files})

    def file_stem(self) -> str:
        """A file name for a download: letters, digits, dash and underscore."""
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", self.name).strip("_")
        return stem[:60] or self.key

    def summary(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "fixtures": len(self.fixtures),
            "universes": sorted({f.universe for f in self.fixtures}),
            "groups": [{"name": g.name, "fixtures": len(g.numbers)} for g in self.groups],
            "unplaced": sum(1 for f in self.fixtures if f.position is None),
            "position_unconfirmed": len(self.unconfirmed),
            "gdtf_embedded": sorted(self.gdtf_files),
            "gdtf_not_embedded": self.missing_gdtf,
            "disclaimer": self.disclaimer,
            "notes": list(self.notes),
        }


def assign_numbers(wanted: Sequence[Optional[int]]) -> List[int]:
    """A unique positive number for each fixture, keeping the ones it can.

    A console addresses a fixture by its id, so two fixtures cannot share one
    and none can go without. The first fixture to ask for a number keeps it;
    a fixture with no number, or with one already taken, gets the next number
    above every number that was kept.
    """
    taken = set()
    kept: List[Optional[int]] = []
    for number in wanted:
        if isinstance(number, int) and not isinstance(number, bool) and number > 0 and number not in taken:
            taken.add(number)
            kept.append(number)
        else:
            kept.append(None)
    following = max(taken, default=0)
    out = []
    for number in kept:
        if number is None:
            following += 1
            number = following
        out.append(number)
    return out


def _spec_leaf(text: Optional[str]) -> str:
    return (text or "").replace("\\", "/").rsplit("/", 1)[-1].strip()


def _spec_part(text: str) -> str:
    """A maker or model as it can stand in a GDTF file name."""
    return re.sub(r'[@/\\:*?"<>|]+', " ", text).strip() or "Unknown"


def _plain(value: Any) -> float:
    try:
        return float(value) + 0.0
    except (TypeError, ValueError):
        return 0.0


def _gdtf_notes(rig: ExportRig) -> None:
    missing = rig.missing_gdtf
    if rig.gdtf_files:
        rig.notes.append(
            f"MVR: {len(rig.gdtf_files)} GDTF file(s) are in the archive: "
            + ", ".join(sorted(rig.gdtf_files)) + "."
        )
    if missing:
        rig.notes.append(
            f"MVR: {len(missing)} fixture type(s) are named by GDTF spec only, with no file in "
            "the archive, because this system holds no GDTF for them: " + ", ".join(missing)
            + ". The visualiser needs its own profile for each."
        )


def _common_notes(rig: ExportRig) -> None:
    unplaced = sum(1 for f in rig.fixtures if f.position is None)
    if unplaced:
        rig.notes.append(
            f"{unplaced} fixture(s) have no position in this rig and are exported without one."
        )
    if rig.unconfirmed:
        rig.notes.append(
            f"{len(rig.unconfirmed)} fixture(s) have a position nobody has confirmed. They are "
            "exported where the rig has them, and marked."
        )
    _gdtf_notes(rig)


def from_rig(rig: Any, rig_fixtures: Iterable[Any]) -> ExportRig:
    """A database rig. `rig_fixtures` need their `fixture` and `mode` loaded.

    Reads the columns the layout view writes and the 3D view and rig_loader
    read: universe, dmx_address, position_x/y/z, rotation_x/y/z, group_name and
    tags. Fixtures that are switched off are exported too: the desk still has
    to know what sits on those channels.
    """
    rows = sorted(
        rig_fixtures,
        key=lambda rf: (int(rf.universe or 0), int(rf.dmx_address or 0), int(rf.id or 0)),
    )
    numbers = assign_numbers([rf.fixture_number for rf in rows])
    out = ExportRig(key=f"rig-{rig.id}", name=rig.name or f"Rig {rig.id}")

    for rf, number in zip(rows, numbers):
        tags = [t for t in (rf.tags or []) if isinstance(t, str)]
        profile = rf.fixture
        manufacturer = (getattr(profile, "manufacturer", "") or "").strip()
        model = (getattr(profile, "model", "") or "").strip()
        mode = rf.mode

        listed = _spec_leaf(getattr(profile, "gdtf_file", None))
        if listed.lower().endswith(".gdtf"):
            spec = listed
        else:
            spec = f"{_spec_part(manufacturer)}@{_spec_part(model)}.gdtf"
        # The library keeps a GDTF's name, not its bytes. The only ones that
        # can be put back in an archive are the demo profiles written here.
        if manufacturer == import_samples.MAKER and spec in import_samples.GDTF_PROFILES:
            out.gdtf_files.setdefault(spec, import_samples.gdtf_bytes(spec))

        layer = (rf.group_name or "").strip()
        groups = [layer] if layer else []
        for tag in tags:
            name = tag[len(GROUP_TAG_PREFIX):].strip() if tag.startswith(GROUP_TAG_PREFIX) else ""
            if name and name not in groups:
                groups.append(name)

        placed = TAG_UNPLACED not in tags
        out.fixtures.append(ExportFixture(
            key=f"fixture-{rf.id}",
            number=number,
            name=(rf.name or "").strip() or f"Fixture {number}",
            manufacturer=manufacturer,
            model=model,
            mode_name=(getattr(mode, "name", "") or "").strip(),
            channel_count=getattr(mode, "channel_count", None),
            universe=int(rf.universe or 0),
            address=int(rf.dmx_address or 1),
            position=(_plain(rf.position_x), _plain(rf.position_y), _plain(rf.position_z)) if placed else None,
            rotation=(_plain(rf.rotation_x), _plain(rf.rotation_y), _plain(rf.rotation_z)),
            unconfirmed=placed and TAG_UNCONFIRMED in tags,
            layer=layer,
            groups=tuple(groups),
            gdtf_spec=spec,
            active=rf.is_active is not False,
        ))

    renumbered = sum(1 for rf, number in zip(rows, numbers) if rf.fixture_number != number)
    if renumbered:
        out.notes.append(
            f"{renumbered} fixture(s) had no fixture number, or one another fixture already "
            "uses, and were given the next free numbers. A console needs each id once."
        )
    switched_off = sum(1 for f in out.fixtures if not f.active)
    if switched_off:
        out.notes.append(
            f"{switched_off} fixture(s) are switched off in this rig (an unmatched type or an "
            "address clash) and are exported all the same. Check them before patching."
        )
    _common_notes(out)
    return out


def from_preset(preset: VenuePreset) -> ExportRig:
    """A demo venue preset, numbered the way its patch sheet numbers it.

    A preset fixture is patched on this system's generic demo profile for its
    type, so that is the type an export names: the footprint on the desk then
    matches the addresses. The real fixture a preset stands in for (the patch
    sheet's Source Fixture column) is not exported as the type.
    """
    ordered = sorted(preset.fixtures, key=lambda f: (f.universe, f.dmx_address, f.id))
    out = ExportRig(
        key=f"preset-{preset.name}",
        name=preset.display_name,
        disclaimer=preset.disclaimer,
    )

    for number, spec in enumerate(ordered, start=1):
        gdtf, mode = PRESET_SPECS.get(spec.fixture_type, _LED_SPEC)
        if gdtf in import_samples.GDTF_PROFILES:
            out.gdtf_files.setdefault(gdtf, import_samples.gdtf_bytes(gdtf))
        layer = spec.group or spec.fixture_type
        groups = [layer] + [name for name in spec.groups if name != layer]
        out.fixtures.append(ExportFixture(
            key=spec.id,
            number=number,
            name=spec.name,
            manufacturer=import_samples.MAKER,
            model=gdtf.split("@", 1)[1][:-len(".gdtf")],
            mode_name=mode,
            channel_count=channel_count(spec.fixture_type),
            universe=spec.universe,
            address=spec.dmx_address,
            position=(_plain(spec.x), _plain(spec.y), _plain(spec.z)),
            rotation=tuple(_plain(v) for v in spec.rotation),  # type: ignore[arg-type]
            unconfirmed=False,
            layer=layer,
            groups=tuple(groups),
            gdtf_spec=gdtf,
        ))

    out.notes.append(
        "This is a demo preset. Every fixture is exported on this system's generic demo "
        "profile for its type, not on the real fixture the preset stands in for."
    )
    _common_notes(out)
    return out
