"""
Auto-placement Geometry
=======================

Where the wizard puts a fixture the owner never positioned.

Under the canonical convention - X across the stage in [-width/2, +width/2],
Z from -depth/2 (upstage) to +depth/2 (downstage), Y above the deck - a
placement outside that footprint is a fixture standing in the audience, and two
placements at one point are two fixtures hung inside each other. Both are
invisible in a list of DMX addresses and obvious the moment the owner looks at
the floor plan.

Placement is driven by the mounting position the operator declares, never by the
free text they typed as a group name.
"""

import math

import pytest

from app.services.rig.wizard_service import VENUE_PRESETS, WizardService


PRESET_KEYS = [
    "small_club",
    "medium_venue",
    "church",
    "theater",
    "festival_stage",
    "large_venue",
    "nightclub",
    "outdoor",
]

# Contract section 2: the wizard asks for this, and nothing is inferred from the
# group name.
MOUNTING_KEY = "mounting_position"
MOUNTING_POSITIONS = [
    "front_truss",
    "mid_truss",
    "back_truss",
    "floor",
    "side_left",
    "side_right",
    "ceiling",
]

# Placements are published rounded to centimetres, so a fixture hung exactly on
# the edge may land half a rounding step outside it and nothing more.
EDGE_TOLERANCE = 0.005 + 1e-9

STAGE = {"stage_width": 12.0, "stage_depth": 8.0, "stage_height": 6.0}


def _place_preset(key):
    preset = VENUE_PRESETS[key]
    return WizardService.compute_placement(
        stage_width=preset["stage_width"],
        stage_depth=preset["stage_depth"],
        stage_height=preset["stage_height"],
        fixtures=[dict(group) for group in preset["suggested_fixtures"]],
    )


def _place_groups(groups, **stage):
    dimensions = {**STAGE, **stage}
    return WizardService.compute_placement(
        stage_width=dimensions["stage_width"],
        stage_depth=dimensions["stage_depth"],
        stage_height=dimensions["stage_height"],
        fixtures=[dict(group) for group in groups],
    )


def _group(name="Row", count=4, mounting="front_truss", fixture_type="led_par"):
    return {
        "fixture_type": fixture_type,
        "count": count,
        "group_name": name,
        MOUNTING_KEY: mounting,
    }


def _xyz(placement):
    return (
        round(placement["position_x"], 3),
        round(placement["position_y"], 3),
        round(placement["position_z"], 3),
    )


def _describe(placement):
    return f"{placement.get('name')} ({placement.get('group_name')})"


# --- the mounting position is the input, and it has to be there ---------------

def test_the_preset_catalogue_is_the_eight_venues_the_wizard_offers():
    assert sorted(VENUE_PRESETS) == sorted(PRESET_KEYS)


@pytest.mark.parametrize("key", PRESET_KEYS)
def test_every_preset_group_declares_a_mounting_position(key):
    """Placement cannot stop guessing from names until every group carries one."""
    for group in VENUE_PRESETS[key]["suggested_fixtures"]:
        mounting = group.get(MOUNTING_KEY)
        assert mounting is not None, (
            f"{key} group '{group.get('group_name')}' declares no {MOUNTING_KEY}, "
            f"so it can only be placed by guessing from its name"
        )
        assert mounting in MOUNTING_POSITIONS, (
            f"{key} group '{group.get('group_name')}' declares {MOUNTING_KEY}="
            f"{mounting!r}, which is not one of {MOUNTING_POSITIONS}"
        )


# --- nothing lands in the audience -------------------------------------------

@pytest.mark.parametrize("key", PRESET_KEYS)
def test_every_preset_places_every_fixture_inside_the_stage_footprint(key):
    preset = VENUE_PRESETS[key]
    half_width = preset["stage_width"] / 2.0
    half_depth = preset["stage_depth"] / 2.0

    placements = _place_preset(key)

    expected = sum(g.get("count", 1) for g in preset["suggested_fixtures"])
    assert len(placements) == expected

    for placement in placements:
        x = placement["position_x"]
        z = placement["position_z"]
        assert -half_width - EDGE_TOLERANCE <= x <= half_width + EDGE_TOLERANCE, (
            f"{key}: {_describe(placement)} sits at x={x}, outside "
            f"[{-half_width}, {half_width}]"
        )
        assert -half_depth - EDGE_TOLERANCE <= z <= half_depth + EDGE_TOLERANCE, (
            f"{key}: {_describe(placement)} sits at z={z}, outside "
            f"[{-half_depth}, {half_depth}] - positive Z past the edge is the "
            f"audience"
        )


@pytest.mark.parametrize("key", PRESET_KEYS)
def test_every_preset_keeps_every_fixture_between_the_deck_and_the_trim(key):
    preset = VENUE_PRESETS[key]
    trim = preset["stage_height"]

    for placement in _place_preset(key):
        y = placement["position_y"]
        assert -EDGE_TOLERANCE <= y <= trim + EDGE_TOLERANCE, (
            f"{key}: {_describe(placement)} sits at y={y}, outside "
            f"[0, {trim}] - Y is height above the deck"
        )


# --- no two fixtures in the same place ----------------------------------------

@pytest.mark.parametrize("key", PRESET_KEYS)
def test_no_two_fixtures_in_a_preset_share_a_position(key):
    placements = _place_preset(key)

    seen = {}
    collisions = []
    for placement in placements:
        point = _xyz(placement)
        if point in seen:
            collisions.append(f"{_describe(seen[point])} and {_describe(placement)} at {point}")
        seen[point] = placement

    assert not collisions, f"{key} hangs fixtures on top of each other: " + "; ".join(collisions)


def test_two_groups_on_the_same_mounting_position_do_not_overlap():
    """Contract section 2: stagger depth or interleave, but do not stack."""
    placements = _place_groups([
        _group(name="Moving Heads", count=6, mounting="mid_truss", fixture_type="moving_head"),
        _group(name="Beams", count=6, mounting="mid_truss", fixture_type="beam"),
    ])

    first = {_xyz(p) for p in placements if p["group_name"] == "Moving Heads"}
    second = {_xyz(p) for p in placements if p["group_name"] == "Beams"}

    assert len(first) == 6 and len(second) == 6
    assert not (first & second), (
        f"two groups on mid_truss land on the same points: {sorted(first & second)}"
    )


# --- the group name is a label, the mounting position is the geometry ----------

@pytest.mark.parametrize("renamed", ["Downstage", "Cyc Blast", "Side Fill", "Anything"])
def test_renaming_a_group_does_not_move_its_fixtures(renamed):
    original = _place_groups([_group(name="Front Wash", mounting="front_truss")])
    after = _place_groups([_group(name=renamed, mounting="front_truss")])

    assert [_xyz(p) for p in after] == [_xyz(p) for p in original], (
        f"renaming 'Front Wash' to {renamed!r} moved the fixtures; placement is "
        f"still reading the group name"
    )
    assert [p["rotation_y"] for p in after] == [p["rotation_y"] for p in original]


def test_changing_the_mounting_position_moves_the_fixtures():
    name = "Movers"
    front = _place_groups([_group(name=name, mounting="front_truss")])
    back = _place_groups([_group(name=name, mounting="back_truss")])
    floor = _place_groups([_group(name=name, mounting="floor")])

    assert {_xyz(p) for p in front}.isdisjoint({_xyz(p) for p in back}), (
        "front_truss and back_truss place the same group identically"
    )
    assert {p["position_z"] for p in front} != {p["position_z"] for p in back}, (
        "front and back must differ in depth"
    )
    assert {p["position_y"] for p in floor} != {p["position_y"] for p in front}, (
        "a floor fixture and a front truss fixture must differ in height"
    )


def test_all_seven_mounting_positions_place_fixtures_somewhere_different():
    """Two options that resolve to one line make the other a dead control."""
    placed = {
        mounting: {_xyz(p) for p in _place_groups([_group(name="Group", mounting=mounting)])}
        for mounting in MOUNTING_POSITIONS
    }

    duplicates = []
    for i, first in enumerate(MOUNTING_POSITIONS):
        for second in MOUNTING_POSITIONS[i + 1:]:
            if placed[first] & placed[second]:
                duplicates.append(f"{first}/{second}")

    assert not duplicates, (
        "these mounting positions place fixtures on shared points: " + ", ".join(duplicates)
    )


def test_placement_is_deterministic():
    """The floor plan is saved once; a jittered placement would move the rig on
    every reload."""
    groups = [_group(name="Movers", count=5, mounting="mid_truss")]
    first = _place_groups(groups)
    second = _place_groups(groups)

    assert [_xyz(p) for p in first] == [_xyz(p) for p in second]
    assert [p["rotation_y"] for p in first] == [p["rotation_y"] for p in second]


# --- rotation_y is aim, not a leftover zero -----------------------------------

@pytest.mark.parametrize("key", PRESET_KEYS)
def test_rotation_y_is_computed_rather_than_left_at_zero(key):
    placements = _place_preset(key)
    yaws = [p["rotation_y"] for p in placements]

    for placement, yaw in zip(placements, yaws):
        assert isinstance(yaw, (int, float)) and math.isfinite(yaw), (
            f"{key}: {_describe(placement)} has rotation_y={yaw!r}"
        )
        assert -360.0 <= yaw <= 360.0, (
            f"{key}: {_describe(placement)} has rotation_y={yaw}, not a heading in degrees"
        )

    assert any(yaw != 0.0 for yaw in yaws), (
        f"{key}: every fixture has rotation_y=0, so nothing is aimed at the stage"
    )


@pytest.mark.parametrize("key", PRESET_KEYS)
def test_a_preset_does_not_aim_every_fixture_the_same_way(key):
    yaws = {p["rotation_y"] for p in _place_preset(key)}

    assert len(yaws) > 1, (
        f"{key}: all {len(_place_preset(key))} fixtures share rotation_y={yaws.pop()}, "
        f"so they all face one direction regardless of where they hang"
    )


def test_the_left_and_right_side_positions_do_not_aim_the_same_way():
    """A boom on each side of the stage aiming the same heading means one of them
    is pointed offstage."""
    left = _place_groups([_group(name="Sides", mounting="side_left")])
    right = _place_groups([_group(name="Sides", mounting="side_right")])

    left_yaws = {p["rotation_y"] for p in left}
    right_yaws = {p["rotation_y"] for p in right}

    assert not (left_yaws & right_yaws), (
        f"side_left and side_right share headings {sorted(left_yaws & right_yaws)}"
    )


# --- where each mounting position is, not merely that they differ -------------
#
# "front and back differ" is satisfied by swapping them outright, by hanging the
# floor at trim height, and by putting side_left at +X. A plan that is a mirror
# of the room is worse than no plan: the owner drags every light to fix it and
# the numbers still disagree with the truss they are standing under.

def _line(mounting, **stage):
    """The single (x, y, z) line one group occupies on a mounting position."""
    placements = _place_groups([_group(name="Row", count=5, mounting=mounting)], **stage)
    return {
        "x": sorted({p["position_x"] for p in placements}),
        "y": sorted({p["position_y"] for p in placements}),
        "z": sorted({p["position_z"] for p in placements}),
    }


def test_the_front_truss_hangs_downstage_and_the_back_truss_upstage():
    front = _line("front_truss")
    back = _line("back_truss")

    assert len(front["z"]) == 1 and len(back["z"]) == 1

    assert front["z"][0] > 0.0, (
        f"front_truss sits at z={front['z'][0]}; +Z is downstage, toward the "
        f"audience, so a front truss at z<=0 is behind the performers"
    )
    assert back["z"][0] < 0.0, (
        f"back_truss sits at z={back['z'][0]}; -Z is upstage, so a back truss at "
        f"z>=0 is in front of the performers"
    )
    assert front["z"][0] > back["z"][0]


def test_the_mid_truss_sits_between_the_front_and_back_trusses():
    front = _line("front_truss")["z"][0]
    mid = _line("mid_truss")["z"][0]
    back = _line("back_truss")["z"][0]

    assert front > mid > back, (
        f"the three trusses run front={front}, mid={mid}, back={back}; they have "
        f"to run downstage to upstage in that order"
    )


def test_the_floor_line_stands_on_the_deck_upstage_of_centre():
    floor = _line("floor")
    trusses = [_line(m)["y"][0] for m in ("front_truss", "mid_truss", "back_truss", "ceiling")]

    assert floor["y"][0] < min(trusses), (
        f"the floor mount hangs at y={floor['y'][0]}, no lower than the trusses "
        f"{trusses}; 'standing on the floor' would be a dead control"
    )
    assert floor["y"][0] <= 0.5, f"a floor fixture at y={floor['y'][0]} is not on the deck"
    assert floor["z"][0] < 0.0, (
        f"the floor line sits at z={floor['z'][0]}, downstage of centre - "
        f"uplighters belong upstage, not in front of the performers"
    )


def test_the_ceiling_is_the_highest_line_and_is_not_hung_past_the_front_truss():
    ceiling = _line("ceiling")
    others = {
        m: _line(m)["y"][0]
        for m in ("front_truss", "mid_truss", "back_truss", "floor", "side_left")
    }

    assert ceiling["y"][0] > max(others.values()), (
        f"'fixed to the ceiling' hangs at y={ceiling['y'][0]}, no higher than "
        f"{others}"
    )
    assert ceiling["z"][0] < _line("front_truss")["z"][0], (
        f"the ceiling line sits at z={ceiling['z'][0]}, downstage of the front "
        f"truss - an 'overhead wash' hung past the lip of the stage"
    )


def test_side_left_is_stage_left_and_side_right_is_stage_right():
    left = _line("side_left")
    right = _line("side_right")

    assert len(left["x"]) == 1 and len(right["x"]) == 1
    assert left["x"][0] < 0.0 < right["x"][0], (
        f"side_left is at x={left['x'][0]} and side_right at x={right['x'][0]}; "
        f"the module docstring and StageView2D both put side_left at -X"
    )
    # A side boom that spreads across the stage instead of down it is a truss.
    assert len(left["z"]) > 1 and len(right["z"]) > 1


def test_a_second_group_on_one_mounting_position_gets_its_own_line():
    """The 5 cm anti-overlap nudge alone satisfies "do not stack"; the contract
    asks for a stagger or an interleave, which is a different line."""
    placements = _place_groups([
        _group(name="First", count=4, mounting="front_truss"),
        _group(name="Second", count=4, mounting="front_truss"),
    ])
    first = {p["position_z"] for p in placements if p["group_name"] == "First"}
    second = {p["position_z"] for p in placements if p["group_name"] == "Second"}

    assert len(first) == 1 and len(second) == 1
    gap = abs(first.pop() - second.pop())
    assert gap > 0.1, (
        f"two groups on front_truss are only {gap} m apart in depth - that is the "
        f"collision nudge, not a stagger"
    )


def test_the_second_line_is_staggered_toward_stage_centre():
    placements = _place_groups([
        _group(name="First", count=4, mounting="front_truss"),
        _group(name="Second", count=4, mounting="front_truss"),
    ])
    first = {p["position_z"] for p in placements if p["group_name"] == "First"}.pop()
    second = {p["position_z"] for p in placements if p["group_name"] == "Second"}.pop()

    assert abs(second) < abs(first), (
        f"the second front_truss group sits at z={second}, further from stage "
        f"centre than the first at z={first} - staggering outward walks fixtures "
        f"off the deck and into the audience"
    )


# --- rotation_y is a heading toward the performers ----------------------------

def _distance_to_performance_strip(x, z, stage_width):
    """How far a point is from the central strip the rig is aimed at."""
    half = stage_width * 0.25
    dx = min(max(x, -half), half) - x
    return math.hypot(dx, -z)


def _forward(yaw_deg):
    """Unit vector the wizard's yaw names: 0 is +Z downstage, +90 is +X."""
    yaw = math.radians(yaw_deg)
    return math.sin(yaw), math.cos(yaw)


@pytest.mark.parametrize("key", PRESET_KEYS)
def test_every_fixture_is_aimed_toward_the_performance_area(key):
    """The only thing rotation_y is for. Finite, in range and not-all-equal are
    all true of a heading that points into the audience."""
    preset = VENUE_PRESETS[key]
    width = preset["stage_width"]
    step = 0.05

    for placement in _place_preset(key):
        x = placement["position_x"]
        z = placement["position_z"]
        before = _distance_to_performance_strip(x, z, width)
        if before < step:
            continue  # already standing in the strip; any heading is defensible

        dx, dz = _forward(placement["rotation_y"])
        after = _distance_to_performance_strip(x + dx * step, z + dz * step, width)

        assert after < before, (
            f"{key}: {_describe(placement)} at x={x} z={z} has rotation_y="
            f"{placement['rotation_y']}, a heading of ({dx:.3f}, {dz:.3f}) that "
            f"moves it from {before:.3f} m to {after:.3f} m from the performers - "
            f"it is pointed away from the stage"
        )


def test_a_front_truss_fixture_over_stage_centre_aims_upstage():
    """The concrete case: hung downstage on the centre line, it has to look back
    at the band, which is yaw 180 under this convention."""
    placement = _place_groups([_group(name="Centre", count=1, mounting="front_truss")])[0]

    assert placement["position_z"] > 0
    dx, dz = _forward(placement["rotation_y"])
    assert dz < -0.9, (
        f"a front-truss fixture at z={placement['position_z']} has rotation_y="
        f"{placement['rotation_y']}, heading ({dx:.3f}, {dz:.3f}) - it is aimed "
        f"downstage into the audience rather than upstage at the performers"
    )


def test_a_side_boom_aims_across_the_stage_rather_than_into_the_wing():
    for mounting, expected_sign in (("side_left", 1.0), ("side_right", -1.0)):
        for placement in _place_groups([_group(name="Boom", count=3, mounting=mounting)]):
            dx, _ = _forward(placement["rotation_y"])
            assert dx * expected_sign > 0, (
                f"{mounting} fixture at x={placement['position_x']} has "
                f"rotation_y={placement['rotation_y']}, aiming the wrong way "
                f"across the stage - off the deck into the wing"
            )
