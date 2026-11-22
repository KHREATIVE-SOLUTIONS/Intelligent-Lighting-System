"""
Import Preview
==============

Turns a parsed file into a plan - what each fixture would be patched as - and
the report an operator reads before anything is written: fixtures, groups,
unmatched types, address clashes, what cannot be imported and why.

Pure: it takes the library as plain dicts and returns plain data, so the same
code produces the preview and decides what apply writes.

What the plan refuses or holds back:

- A fixture with no address, on a universe past the last one this system
  drives, or whose footprint runs past channel 512 is reported and not imported.
- A fixture whose type matched nothing is imported switched off, on a
  placeholder profile that only occupies its channels. The rig loader would
  otherwise hand an unknown fixture a generic map and write a dimmer to it.
- Of two fixtures that share channels, the second is imported switched off.
- A fixture without a position is unplaced. Several fixtures sitting exactly on
  the origin are what an export looks like when nobody placed them, so they are
  unplaced too.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.services.lighting.key_lighting import ZONE_VALUES, parse_zone
from app.services.rig.patching_service import MAX_UNIVERSES

from .matching import match_type, normalise, pick_mode
from .model import DMX_UNIVERSE_SIZE, UNCONFIRMED_POSITION_SOURCES, ImportedFixture, ParsedVenue

# Group names the engine builds for itself (rig_loader.TYPE_GROUP_NAMES plus the
# combined one). A rig group of the same name is dropped at load.
RESERVED_GROUP_NAMES = ("movers", "washes", "bars", "strobes", "effects", "movers_washes")

NO_TYPE = "(no type given)"
MAX_NAMES_LISTED = 10


@dataclass
class PlannedFixture:
    """One fixture and what importing it would do."""

    index: int
    fixture: ImportedFixture
    # "library": an existing profile. "embedded": a profile the file carries,
    # written to the library on apply. "unmatched": neither.
    profile_status: str = "unmatched"
    library_entry: Optional[Dict[str, Any]] = None
    embedded_profile: Optional[Dict[str, Any]] = None
    mode: Optional[Dict[str, Any]] = None
    mode_how: str = ""
    match_how: str = ""
    suggestions: List[Dict[str, Any]] = field(default_factory=list)
    footprint: int = 1
    footprint_known: bool = False
    position: Optional[Tuple[float, float, float]] = None
    rotation: Optional[Tuple[float, float, float]] = None
    position_source: str = "none"
    zone: Optional[str] = None
    importable: bool = True
    refusal: str = ""
    clashes: bool = False
    issues: List[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.fixture.display_name(self.index)

    @property
    def last_address(self) -> Optional[int]:
        if self.fixture.dmx_address is None:
            return None
        return self.fixture.dmx_address + self.footprint - 1

    @property
    def switched_off(self) -> bool:
        """Imported, but not handed to the engine until someone has looked at it."""
        return self.profile_status == "unmatched" or self.clashes

    @property
    def type_label(self) -> str:
        return self.fixture.type_name or NO_TYPE

    @property
    def position_confirmed(self) -> bool:
        """The position is the file's own. False for a fixture with none, and
        for one whose position was generated from a stage template."""
        return self.position is not None and self.position_source not in UNCONFIRMED_POSITION_SOURCES


def _profile_key(name: str) -> str:
    leaf = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    if leaf.lower().endswith(".gdtf"):
        leaf = leaf[:-5]
    return normalise(leaf)


def _profile_name(profile: Dict[str, Any]) -> str:
    return f"{profile.get('manufacturer') or ''} {profile.get('model') or ''}".strip()


def _embedded_for(fixture: ImportedFixture, profiles: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The profile carried in the file that this fixture names, if there is one."""
    if fixture.gdtf_spec:
        wanted = _profile_key(fixture.gdtf_spec)
        for profile in profiles:
            if _profile_key(profile.get("_gdtf_filename", "")) == wanted:
                return profile
    wanted = normalise(fixture.type_name)
    if wanted:
        for profile in profiles:
            if normalise(_profile_name(profile)) == wanted:
                return profile
    return None


def _library_for_profile(profile: Dict[str, Any], library: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The library row an embedded profile already is: the same GDTF id."""
    gdtf_id = profile.get("gdtf_id")
    if not gdtf_id:
        return None
    for entry in library:
        if entry.get("gdtf_id") == gdtf_id:
            return entry
    return None


def _resolve_profile(
    plan: PlannedFixture,
    parsed: ParsedVenue,
    library: List[Dict[str, Any]],
    chosen: Dict[str, Dict[str, Any]],
) -> None:
    fixture = plan.fixture
    modes: List[Dict[str, Any]] = []

    embedded = _embedded_for(fixture, parsed.profiles)
    picked = chosen.get(normalise(plan.type_label))
    if picked is not None:
        # The operator named the profile for this type. That outranks anything
        # the file or the matcher would say.
        plan.profile_status, plan.library_entry, plan.match_how = "library", picked, "chosen"
        modes = picked.get("modes") or []
    elif embedded is not None:
        existing = _library_for_profile(embedded, library)
        if existing is not None:
            plan.profile_status, plan.library_entry, plan.match_how = "library", existing, "gdtf_id"
            modes = existing.get("modes") or []
        else:
            plan.profile_status, plan.embedded_profile, plan.match_how = "embedded", embedded, "file"
            modes = embedded.get("modes") or []
    else:
        entry, how, suggestions = match_type(fixture.type_name, fixture.manufacturer, fixture.model, library)
        if entry is not None:
            plan.profile_status, plan.library_entry, plan.match_how = "library", entry, how
            modes = entry.get("modes") or []
        else:
            plan.suggestions = suggestions
            if fixture.gdtf_spec:
                plan.issues.append(f"names '{fixture.gdtf_spec}', which is not in the file")

    plan.mode, plan.mode_how = pick_mode(modes, fixture.mode_name, fixture.channel_count)
    stated = fixture.channel_count

    if plan.mode is not None:
        plan.footprint = max(1, int(plan.mode.get("channel_count") or 1))
        plan.footprint_known = True
        if plan.mode_how == "guessed":
            wanted = f"'{fixture.mode_name}', which the profile does not have" if fixture.mode_name else "no mode"
            plan.issues.append(
                f"the file names {wanted}; '{plan.mode.get('name')}' ({plan.footprint} channels) was assumed"
            )
        elif fixture.mode_name and plan.mode_how != "name":
            plan.issues.append(
                f"mode '{fixture.mode_name}' is not on the profile; '{plan.mode.get('name')}' was used"
            )
        if stated and stated != plan.footprint:
            plan.issues.append(
                f"the file says {stated} channels; the profile's '{plan.mode.get('name')}' mode has {plan.footprint}"
            )
    elif stated:
        plan.footprint, plan.footprint_known = max(1, int(stated)), True
        if plan.profile_status != "unmatched":
            plan.issues.append("the profile has no modes; the file's channel count was used")
    else:
        plan.footprint, plan.footprint_known = 1, False
        if plan.profile_status != "unmatched":
            plan.issues.append("the profile has no modes, so its footprint is unknown")


def _check_patch(plan: PlannedFixture) -> None:
    fixture = plan.fixture
    if fixture.dmx_address is None or fixture.universe is None:
        plan.importable, plan.refusal = False, "no DMX address"
        return
    if not 1 <= fixture.dmx_address <= DMX_UNIVERSE_SIZE:
        plan.importable, plan.refusal = False, f"address {fixture.dmx_address} is outside 1-512"
        return
    if not 0 <= fixture.universe < MAX_UNIVERSES:
        plan.importable = False
        plan.refusal = f"universe {fixture.universe} is past the last one this system drives ({MAX_UNIVERSES - 1})"
        return
    if plan.last_address > DMX_UNIVERSE_SIZE:
        plan.importable = False
        plan.refusal = (
            f"{plan.footprint} channels from {fixture.dmx_address} run past channel 512 "
            f"of universe {fixture.universe}"
        )


def _find_clashes(plans: List[PlannedFixture]) -> List[Dict[str, Any]]:
    """Every pair of importable fixtures that share a channel.

    The second of each pair, in address order, is marked: it is the one apply
    switches off.
    """
    clashes: List[Dict[str, Any]] = []
    by_universe: Dict[int, List[PlannedFixture]] = {}
    for plan in plans:
        if plan.importable:
            by_universe.setdefault(plan.fixture.universe, []).append(plan)

    for universe, members in sorted(by_universe.items()):
        members.sort(key=lambda p: (p.fixture.dmx_address, p.index))
        for i, first in enumerate(members):
            for second in members[i + 1:]:
                if second.fixture.dmx_address > first.last_address:
                    break
                second.clashes = True
                low = second.fixture.dmx_address
                high = min(first.last_address, second.last_address)
                clashes.append({
                    "universe": universe,
                    "kind": "same_address" if low == first.fixture.dmx_address else "overlap",
                    "channels": [low, high],
                    "first": _clash_side(first),
                    "second": _clash_side(second),
                    "footprints_known": first.footprint_known and second.footprint_known,
                })
    return clashes


def _clash_side(plan: PlannedFixture) -> Dict[str, Any]:
    return {
        "index": plan.index,
        "name": plan.name,
        "dmx_address": plan.fixture.dmx_address,
        "last_address": plan.last_address,
        "channel_count": plan.footprint,
    }


def plan_import(
    parsed: ParsedVenue,
    library: List[Dict[str, Any]],
    profile_map: Optional[Dict[str, int]] = None,
) -> Tuple[List[PlannedFixture], List[Dict[str, Any]], List[str]]:
    """(the plan for every fixture, the address clashes, warnings about the file as a whole).

    profile_map is the operator's answer to an unmatched list: a type name as
    the report prints it -> the id of the library profile to patch it on.
    """
    warnings: List[str] = []
    plans = [PlannedFixture(index=i, fixture=f) for i, f in enumerate(parsed.fixtures)]

    by_id = {entry.get("id"): entry for entry in library}
    type_names = {normalise(p.type_label) for p in plans}
    chosen: Dict[str, Dict[str, Any]] = {}
    for type_name, fixture_id in (profile_map or {}).items():
        entry = by_id.get(fixture_id)
        if entry is None:
            warnings.append(f"profile_map: there is no library profile {fixture_id} (for '{type_name}').")
        elif normalise(type_name) not in type_names:
            warnings.append(f"profile_map: the file has no fixture type '{type_name}'.")
        else:
            chosen[normalise(type_name)] = entry

    at_origin = [p for p in plans if p.fixture.position == (0.0, 0.0, 0.0)]
    stacked = {p.index for p in at_origin} if len(at_origin) > 1 else set()
    if stacked:
        warnings.append(
            f"{len(stacked)} fixtures sit exactly on the origin, which is what a file looks like "
            "when nobody placed them. They were left unplaced."
        )

    for plan in plans:
        fixture = plan.fixture
        plan.issues.extend(fixture.notes)
        if fixture.position is not None and plan.index not in stacked:
            plan.position = fixture.position
            plan.rotation = fixture.rotation
            plan.position_source = fixture.position_source
        if fixture.zone:
            zone = parse_zone(fixture.zone)
            if zone is None:
                plan.issues.append(
                    f"zone '{fixture.zone}' is not one of: {', '.join(ZONE_VALUES)}; it was dropped"
                )
            else:
                plan.zone = zone.value
        _resolve_profile(plan, parsed, library, chosen)
        _check_patch(plan)

    clashes = _find_clashes(plans)

    seen: Dict[str, int] = {}
    for plan in plans:
        if plan.fixture.fixture_id:
            seen[plan.fixture.fixture_id] = seen.get(plan.fixture.fixture_id, 0) + 1
    repeated = sorted(fid for fid, count in seen.items() if count > 1)
    if repeated:
        warnings.append(
            "Fixture IDs used more than once: " + ", ".join(repeated[:MAX_NAMES_LISTED])
            + ("..." if len(repeated) > MAX_NAMES_LISTED else "") + "."
        )
    return plans, clashes, warnings


def _xyz(value: Optional[Tuple[float, float, float]]) -> Optional[Dict[str, float]]:
    if value is None:
        return None
    return {"x": value[0], "y": value[1], "z": value[2]}


def _fixture_row(plan: PlannedFixture) -> Dict[str, Any]:
    fixture = plan.fixture
    profile: Dict[str, Any] = {"status": plan.profile_status, "matched_by": plan.match_how}
    if plan.library_entry is not None:
        profile.update(
            fixture_id=plan.library_entry.get("id"),
            manufacturer=plan.library_entry.get("manufacturer"),
            model=plan.library_entry.get("model"),
        )
    elif plan.embedded_profile is not None:
        profile.update(
            manufacturer=plan.embedded_profile.get("manufacturer"),
            model=plan.embedded_profile.get("model"),
            file=plan.embedded_profile.get("_gdtf_filename"),
        )
    if plan.mode is not None:
        profile.update(mode=plan.mode.get("name"), mode_chosen_by=plan.mode_how)

    return {
        "index": plan.index,
        "name": plan.name,
        "fixture_id": fixture.fixture_id,
        "fixture_number": fixture.fixture_number,
        "type_name": fixture.type_name,
        "category": fixture.category,
        "mode_name": fixture.mode_name,
        "universe": fixture.universe,
        "dmx_address": fixture.dmx_address,
        "last_address": plan.last_address,
        "channel_count": plan.footprint,
        "channel_count_known": plan.footprint_known,
        "position": _xyz(plan.position),
        "rotation": _xyz(plan.rotation),
        "position_source": plan.position_source,
        "unplaced": plan.position is None,
        "position_confirmed": plan.position_confirmed,
        "position_label": fixture.position_label,
        "group_name": fixture.group_name,
        "groups": list(fixture.groups),
        "layer": fixture.layer,
        "zone": plan.zone,
        "profile": profile,
        "importable": plan.importable,
        "refusal": plan.refusal,
        "active": plan.importable and not plan.switched_off,
        "issues": list(plan.issues),
    }


def _groups(plans: List[PlannedFixture]) -> List[Dict[str, Any]]:
    """Each group named in the file, and whether the engine will get it.

    A rig fixture carries one group_name, and that is what the engine builds a
    group from. Any further groups a file gives a fixture are kept on it as
    tags and listed here, but are not engine groups yet.
    """
    primary: Dict[str, int] = {}
    extra: Dict[str, int] = {}
    for plan in plans:
        if plan.fixture.group_name:
            primary[plan.fixture.group_name] = primary.get(plan.fixture.group_name, 0) + 1
        for name in plan.fixture.groups:
            extra[name] = extra.get(name, 0) + 1

    rows = []
    for name, count in primary.items():
        reserved = name.strip() in RESERVED_GROUP_NAMES
        rows.append({
            "name": name, "fixtures": count, "role": "group",
            "reserved": reserved, "reaches_engine": not reserved,
        })
    for name, count in extra.items():
        if name in primary:
            continue
        rows.append({
            "name": name, "fixtures": count, "role": "tag",
            "reserved": False, "reaches_engine": False,
        })
    return rows


def _unmatched(plans: List[PlannedFixture]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for plan in plans:
        if plan.profile_status != "unmatched":
            continue
        row = grouped.setdefault(plan.type_label, {
            "type_name": plan.type_label,
            "fixtures": 0,
            "names": [],
            "modes": [],
            "channel_counts": [],
            "suggestions": plan.suggestions,
            "imported_as": "a placeholder profile, switched off, until it is given a real one",
        })
        row["fixtures"] += 1
        if len(row["names"]) < MAX_NAMES_LISTED:
            row["names"].append(plan.name)
        if plan.fixture.mode_name and plan.fixture.mode_name not in row["modes"]:
            row["modes"].append(plan.fixture.mode_name)
        if plan.fixture.channel_count and plan.fixture.channel_count not in row["channel_counts"]:
            row["channel_counts"].append(plan.fixture.channel_count)
    return list(grouped.values())


def describe_profile(profile: Dict[str, Any], library: List[Dict[str, Any]], used_by: int) -> Dict[str, Any]:
    """A profile the file carries, as the report shows it."""
    unknown: List[str] = []
    modes = []
    for mode in profile.get("modes") or []:
        channels = []
        for channel in mode.get("channels") or []:
            known = bool(channel.get("attribute_known", True))
            attribute = channel.get("attribute") or channel.get("name") or ""
            if not known and not channel.get("is_fine") and attribute and attribute not in unknown:
                unknown.append(attribute)
            channels.append({
                "channel_number": channel.get("channel_number"),
                "name": channel.get("name"),
                "attribute": attribute,
                "channel_type": channel.get("channel_type"),
                "known": known,
                "is_fine": bool(channel.get("is_fine", False)),
            })
        modes.append({
            "name": mode.get("name"),
            "channel_count": mode.get("channel_count"),
            "channels": channels,
        })

    existing = _library_for_profile(profile, library)
    return {
        "manufacturer": profile.get("manufacturer"),
        "model": profile.get("model"),
        "short_name": profile.get("short_name") or "",
        "long_name": profile.get("long_name") or "",
        "fixture_type": profile.get("fixture_type"),
        "gdtf_id": profile.get("gdtf_id"),
        "file": profile.get("_gdtf_filename"),
        "pan_range": profile.get("pan_range"),
        "tilt_range": profile.get("tilt_range"),
        "modes": modes,
        "unknown_attributes": unknown,
        "in_library": existing.get("id") if existing is not None else None,
        "used_by": used_by,
    }


def build_preview(
    parsed: ParsedVenue,
    library: List[Dict[str, Any]],
    profile_map: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """The whole report for a parsed file, as plain data."""
    plans, clashes, plan_warnings = plan_import(parsed, library, profile_map)
    return render_preview(parsed, library, plans, clashes, plan_warnings)


def render_preview(
    parsed: ParsedVenue,
    library: List[Dict[str, Any]],
    plans: List[PlannedFixture],
    clashes: List[Dict[str, Any]],
    plan_warnings: List[str],
) -> Dict[str, Any]:
    warnings = list(parsed.warnings) + list(plan_warnings)

    groups = _groups(plans)
    for group in groups:
        if group["reserved"]:
            warnings.append(
                f"Group '{group['name']}' has a name the engine keeps for its own groups, "
                "so the engine will not build it. Rename it after import."
            )

    profiles = []
    for profile in parsed.profiles:
        used_by = sum(1 for p in plans if p.embedded_profile is profile or (
            p.library_entry is not None and p.match_how == "gdtf_id"
            and p.library_entry.get("gdtf_id") == profile.get("gdtf_id")
        ))
        described = describe_profile(profile, library, used_by)
        if described["unknown_attributes"]:
            warnings.append(
                f"{described['manufacturer']} {described['model']}: attributes this system has no "
                f"meaning for were kept and will not be driven: {', '.join(described['unknown_attributes'])}."
            )
        if not described["modes"]:
            warnings.append(f"{described['manufacturer']} {described['model']}: no usable DMX mode was read.")
        profiles.append(described)

    unmatched = _unmatched(plans)
    not_importable = [
        {"index": p.index, "name": p.name, "reason": p.refusal} for p in plans if not p.importable
    ]
    importable = [p for p in plans if p.importable]
    universes: Dict[int, int] = {}
    for plan in importable:
        universes[plan.fixture.universe] = universes.get(plan.fixture.universe, 0) + 1

    return {
        "format": parsed.format,
        "source_file": parsed.source_file,
        "summary": {
            "fixtures": len(plans),
            "importable": len(importable),
            "not_importable": len(not_importable),
            "placed": sum(1 for p in plans if p.position is not None),
            "unplaced": sum(1 for p in plans if p.position is None),
            "unconfirmed_positions": sum(
                1 for p in plans if p.position is not None and not p.position_confirmed
            ),
            "switched_off": sum(1 for p in importable if p.switched_off),
            "universes": [{"universe": u, "fixtures": n} for u, n in sorted(universes.items())],
            "groups": sum(1 for g in groups if g["role"] == "group"),
            "profiles_in_file": len(profiles),
            "unmatched_types": len(unmatched),
            "unmatched_fixtures": sum(row["fixtures"] for row in unmatched),
            "address_clashes": len(clashes),
            "position_sources": _count(p.position_source for p in plans),
        },
        "fixtures": [_fixture_row(p) for p in plans],
        "groups": groups,
        "profiles": profiles,
        "unmatched_types": unmatched,
        "address_clashes": clashes,
        "not_importable": not_importable,
        "positions": list(parsed.positions),
        "layers": list(parsed.layers),
        "assumptions": list(parsed.assumptions),
        "warnings": warnings,
    }


def _count(values) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts
