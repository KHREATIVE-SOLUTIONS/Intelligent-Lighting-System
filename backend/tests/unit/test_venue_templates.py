"""
Bundled Venue Templates
=======================

The gallery is the shortest path from a box of lights to a working show, so a
template that ships wrong ships to everybody who takes that path.

Three ways it can be wrong and still look fine:
- a group patched onto a profile mode nothing can raise, so the fixture holds an
  address, appears on the plan and never lights;
- a placement whose coordinates were quietly defaulted to the stage origin;
- a template whose "overhead wash" is hung further downstage than the front
  truss, which is the exact defect contract section 2 named.
"""

import pytest

from app.db import venue_templates
from app.db.venue_templates import (
    FALLBACK_CHANNEL_COUNTS,
    VENUE_TEMPLATES,
    build_template_payload,
    template_stats,
)
from app.services.lighting.key_lighting import ZONE_VALUES
from app.services.rig.fixture_choice import choose_mode, mode_makes_light
from app.services.rig.wizard_service import MOUNTING_POSITIONS, WizardService


CHANNEL_COUNTS = dict(FALLBACK_CHANNEL_COUNTS)


def _payload(definition):
    return build_template_payload(definition, CHANNEL_COUNTS)


ALL_PAYLOADS = [(d["venue_type"], _payload(d)) for d in VENUE_TEMPLATES]
VENUE_TYPES = [venue_type for venue_type, _ in ALL_PAYLOADS]


def _positions(payload):
    for slot in payload["fixture_slots"]:
        for position in slot["positions"]:
            yield slot, position


# ---------------------------------------------------------------------------
# The gallery is not empty and the venues are the ones the contract asked for
# ---------------------------------------------------------------------------

def test_the_gallery_ships_the_eight_to_ten_venues_the_contract_asks_for():
    assert 8 <= len(VENUE_TEMPLATES) <= 10
    assert len(set(VENUE_TYPES)) == len(VENUE_TYPES), "two templates share a venue_type"
    for wanted in ("small_bar", "nightclub", "church", "band_stage",
                   "mobile_dj", "theater", "function_room", "festival_stage"):
        assert wanted in VENUE_TYPES, f"the gallery has no {wanted} template"


@pytest.mark.parametrize("venue_type,payload", ALL_PAYLOADS)
def test_every_group_declares_a_mounting_position_the_placement_call_knows(
    venue_type, payload
):
    for slot in payload["fixture_slots"]:
        assert slot["mounting"] in MOUNTING_POSITIONS, (
            f"{venue_type}: '{slot['group_name']}' is mounted {slot['mounting']!r}"
        )
        assert len(slot["positions"]) == slot["count"]


# ---------------------------------------------------------------------------
# Geometry - the same rules the wizard's own placements are held to
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("venue_type,payload", ALL_PAYLOADS)
def test_no_template_places_a_fixture_off_the_stage(venue_type, payload):
    half_width = payload["stage_width"] / 2 + 0.01
    half_depth = payload["stage_depth"] / 2 + 0.01
    trim = payload["stage_height"] + 0.01

    for slot, position in _positions(payload):
        assert -half_width <= position["x"] <= half_width, (
            f"{venue_type}: '{slot['group_name']}' at x={position['x']}"
        )
        assert -half_depth <= position["z"] <= half_depth, (
            f"{venue_type}: '{slot['group_name']}' at z={position['z']} - past "
            f"+{half_depth} is the audience"
        )
        assert -0.01 <= position["y"] <= trim, (
            f"{venue_type}: '{slot['group_name']}' at y={position['y']}"
        )


@pytest.mark.parametrize("venue_type,payload", ALL_PAYLOADS)
def test_no_template_hangs_two_fixtures_in_the_same_place(venue_type, payload):
    seen = {}
    for slot, position in _positions(payload):
        point = (position["x"], position["y"], position["z"])
        assert point not in seen, (
            f"{venue_type}: '{slot['group_name']}' sits on top of "
            f"'{seen[point]}' at {point}"
        )
        seen[point] = slot["group_name"]


@pytest.mark.parametrize("venue_type,payload", ALL_PAYLOADS)
def test_an_overhead_wash_is_not_hung_out_past_the_front_truss(venue_type, payload):
    """Contract section 2 named theater's 'Stage Wash' landing at the front edge
    rather than overhead. Changing how the mounting is chosen did not fix that on
    its own - the ceiling line itself has to be overhead."""
    ceilings = [p["z"] for s, p in _positions(payload) if s["mounting"] == "ceiling"]
    fronts = [p["z"] for s, p in _positions(payload) if s["mounting"] == "front_truss"]
    if not ceilings or not fronts:
        pytest.skip("this venue has no ceiling and front truss to compare")

    assert max(ceilings) < min(fronts), (
        f"{venue_type}: the ceiling groups sit at z={max(ceilings)}, downstage of "
        f"the front truss at z={min(fronts)} - the wash the description calls "
        f"overhead is hung out past the lip of the stage"
    )


@pytest.mark.parametrize("venue_type,payload", ALL_PAYLOADS)
def test_every_template_aims_its_fixtures(venue_type, payload):
    yaws = {p["rotation_y"] for _, p in _positions(payload)}
    assert yaws != {0.0}, (
        f"{venue_type}: every fixture has rotation_y 0, so nothing is aimed at "
        f"the performance area"
    )


# ---------------------------------------------------------------------------
# Zones - the one place a non-expert could get them for free
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("venue_type,payload", ALL_PAYLOADS)
def test_every_template_names_at_least_one_zone(venue_type, payload):
    """The groups are already called "Key Light", "Drum Fill", "Booth Bars" - the
    zone vocabulary in English. A template-created rig with no zones still cannot
    say which light is on the singer."""
    zones = [slot.get("zone") for slot in payload["fixture_slots"] if slot.get("zone")]
    assert zones, f"{venue_type} carries no zone on any group"
    for zone in zones:
        assert zone in ZONE_VALUES, f"{venue_type} declares unknown zone {zone!r}"


# ---------------------------------------------------------------------------
# Addressing survives being applied
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("venue_type,payload", ALL_PAYLOADS)
def test_the_advertised_universe_count_matches_sequential_patching(venue_type, payload):
    stats = template_stats(payload)
    assert stats["fixtures"] == sum(s["count"] for s in payload["fixture_slots"])
    assert stats["universes"] >= 1
    assert stats["channels"] <= stats["universes"] * 512


# ---------------------------------------------------------------------------
# A placement that came back malformed is a broken template, not a placed one
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("missing_key", ["position_x", "position_y", "position_z", "rotation_y"])
def test_a_placement_missing_a_coordinate_refuses_to_seed(monkeypatch, missing_key):
    """Defaulting a missing key to 0.0 would seed ten venues whose every fixture
    is stacked on the stage origin, behind a single aggregated warning."""
    real = WizardService.compute_placement

    def drop_key(**kwargs):
        placements = real(**kwargs)
        for placement in placements:
            placement.pop(missing_key, None)
        return placements

    monkeypatch.setattr(WizardService, "compute_placement", staticmethod(drop_key))

    with pytest.raises(ValueError) as excinfo:
        build_template_payload(VENUE_TEMPLATES[0], CHANNEL_COUNTS)
    assert missing_key in str(excinfo.value)


def test_a_short_placement_result_refuses_to_seed(monkeypatch):
    real = WizardService.compute_placement
    monkeypatch.setattr(
        WizardService, "compute_placement",
        staticmethod(lambda **kwargs: real(**kwargs)[:-1]),
    )
    with pytest.raises(ValueError):
        build_template_payload(VENUE_TEMPLATES[0], CHANNEL_COUNTS)


# ---------------------------------------------------------------------------
# A fixture that can never light
# ---------------------------------------------------------------------------

class _Channel:
    def __init__(self, channel_type):
        self.channel_type = channel_type


class _Mode:
    def __init__(self, name, channel_types):
        self.name = name
        self.channel_count = len(channel_types)
        self.channels = [_Channel(t) for t in channel_types]


def test_a_macro_and_speed_mode_is_not_treated_as_drivable():
    """The only bundled `effect` profile's first mode is 2-Channel = macro,
    speed. No renderer writes a macro channel."""
    assert not mode_makes_light(_Mode("2-Channel", ["macro", "speed"]).channels)
    assert not mode_makes_light(_Mode("Shutter only", ["shutter", "strobe"]).channels)
    assert mode_makes_light(_Mode("5-Channel", ["red", "green", "blue", "strobe", "speed"]).channels)
    assert mode_makes_light(_Mode("4-Channel", ["dimmer", "dimmer", "dimmer", "dimmer"]).channels)


def test_choosing_a_mode_prefers_one_that_can_be_turned_on():
    modes = [
        _Mode("2-Channel", ["macro", "speed"]),
        _Mode("5-Channel", ["red", "green", "blue", "strobe", "speed"]),
    ]
    assert choose_mode(modes).name == "5-Channel", (
        "taking the first mode patches an effect fixture onto macro+speed, so it "
        "holds a DMX address and can never be turned on"
    )
    only_dark = [_Mode("2-Channel", ["macro", "speed"])]
    assert choose_mode(only_dark).name == "2-Channel", (
        "with nothing drivable available the slot still has to patch, so the gap "
        "is visible rather than the group silently vanishing"
    )
    assert choose_mode([]) is None


def test_the_bundled_library_can_drive_every_fixture_type_the_templates_use():
    """The end-to-end version of the same check, against the real bundled library
    a shipped box seeds its gallery from."""
    from pathlib import Path

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models.fixture import Fixture

    dev_db = Path(__file__).resolve().parents[2] / "lighting_dev.db"
    if not dev_db.exists():
        pytest.skip("no bundled fixture library on this machine")

    engine = create_engine(f"sqlite:///{dev_db.as_posix()}")
    session = sessionmaker(bind=engine)()
    try:
        wanted = sorted({
            group["fixture_type"]
            for definition in VENUE_TEMPLATES
            for group in definition["groups"]
        })
        if session.query(Fixture).count() == 0:
            pytest.skip("no fixture library in this database")

        dark = []
        for fixture_type in wanted:
            fixture, mode = venue_templates.pick_profile_sync(session, fixture_type)
            if fixture is None:
                continue  # reported separately as a library gap
            if mode is None or not mode_makes_light(mode.channels):
                dark.append(fixture_type)

        assert not dark, (
            f"every '{', '.join(dark)}' fixture these templates seed would patch, "
            f"occupy addresses, appear on the plan and never light"
        )
    finally:
        session.close()
        engine.dispose()
