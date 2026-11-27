"""
LIV Miami approximate recreation
================================

The default demo rig. It imitates a real room from public press, so it has to
say everywhere it is read that it is not that room's patch; and it is the rig
looks are judged on, so it has to be mirrored, inside its universes, and hung
where the 3D view will hang it rather than stand it on the floor.
"""

from pathlib import Path

import pytest

from app.api.endpoints import demo as demo_endpoints
from app.main import DEMO_VENUE_PRESET
from app.services.demo.patch_sheet import (
    COLUMNS,
    channel_count,
    patch_sheet_csv,
    patch_sheet_markdown,
)
from app.services.demo.venue_presets import (
    ENGINE_TYPE_GROUP_NAMES,
    LIV_DISCLAIMER,
    LIV_DOME_RADIUS,
    VENUE_PRESETS,
    create_venue_rig,
)
from app.services.effects.fixture_groups import FixtureGroupManager
from app.services.lighting.key_lighting import PerformerZone

NAME = "liv_miami_approx"
REPO_ROOT = Path(__file__).resolve().parents[3]
PATCH_SHEET = REPO_ROOT / "docs" / "venues" / "liv_miami_approx_patch.csv"
PATCH_SHEET_MD = REPO_ROOT / "docs" / "venues" / "liv_miami_approx_patch.md"
NOTES = REPO_ROOT / "docs" / "venues" / "LIV_MIAMI_APPROX_NOTES.md"

BOOTH_UNIVERSE_IDS = ("ledwall_", "booth_wash_")


def _preset():
    return VENUE_PRESETS[NAME]


def _radius(f) -> float:
    return (f.x ** 2 + f.z ** 2) ** 0.5


def test_it_is_the_default_demo_rig_in_both_places():
    assert DEMO_VENUE_PRESET == NAME
    assert demo_endpoints.DEFAULT_DEMO_PRESET == NAME


def test_it_says_it_is_not_the_real_patch_wherever_it_is_named():
    preset = _preset()
    assert "approximate recreation" in preset.display_name.lower()
    assert "APPROXIMATE RECREATION" in preset.description
    assert "NOT LIV's real patch" in preset.description

    header = [line for line in PATCH_SHEET.read_text(encoding="utf-8").splitlines() if line.startswith("#")]
    assert any(LIV_DISCLAIMER in line for line in header)

    # In the Markdown sheet it is the first thing under the title.
    sheet = [line for line in PATCH_SHEET_MD.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert "approximate recreation" in sheet[0].lower()
    assert LIV_DISCLAIMER in sheet[1]

    assert "Not a survey of the venue" in preset.room.basis

    notes = NOTES.read_text(encoding="utf-8")
    assert "APPROXIMATE RECREATION" in notes.split("\n## ")[0]
    assert "NOT LIV's real patch" in notes


def test_the_sourced_counts_are_the_ones_the_press_gives():
    by_model = {}
    for f in _preset().fixtures:
        by_model[f.model] = by_model.get(f.model, 0) + 1
    assert by_model["Elation Design Spot 575E"] == 22
    assert by_model["Elation Design Spot 300E"] == 4
    assert by_model["Elation Impression RGB"] == 8
    assert len(_preset().fixtures) == 131
    assert all(f.model and f.basis and f.stands_for for f in _preset().fixtures)


def test_no_two_fixtures_share_a_channel_and_none_runs_off_its_universe():
    taken = set()
    for f in _preset().fixtures:
        width = channel_count(f.fixture_type)
        assert 1 <= f.dmx_address and f.dmx_address + width - 1 <= 512, f.id
        assert 0 <= f.universe <= 15
        for channel in range(f.dmx_address, f.dmx_address + width):
            assert (f.universe, channel) not in taken, f"{f.id} overlaps at {f.universe}/{channel}"
            taken.add((f.universe, channel))
    assert sorted({f.universe for f in _preset().fixtures}) == [0, 1, 2, 3]


def test_no_universe_carries_more_than_512_channels():
    used = {}
    for f in _preset().fixtures:
        used[f.universe] = used.get(f.universe, 0) + channel_count(f.fixture_type)
    assert all(total <= 512 for total in used.values()), used
    assert used == {0: 512, 1: 512, 2: 240, 3: 348}


def test_the_led_walls_and_booth_wash_have_a_universe_to_themselves():
    fixtures = _preset().fixtures
    booth = [f for f in fixtures if f.id.startswith(BOOTH_UNIVERSE_IDS)]
    assert len([f for f in booth if f.id.startswith("ledwall_")]) == 27
    assert len([f for f in booth if f.id.startswith("booth_wash_")]) == 2
    assert {f.universe for f in booth} == {3}
    assert [f.id for f in fixtures if f.universe == 3 and f not in booth] == []

    # End to end from channel 1, so no gap and no overlap.
    expected = 1
    for f in sorted(booth, key=lambda f: f.dmx_address):
        assert f.dmx_address == expected, f.id
        expected += channel_count(f.fixture_type)
    assert expected - 1 <= 512

    # A video wall is not a lighting fixture and the press names no make: the
    # sheet has to say these cells are a stand-in.
    assert all("assumed" in f.basis for f in booth)
    assert all("not reported" in f.model for f in booth if f.id.startswith("ledwall_"))


def test_the_led_walls_and_booth_wash_are_bracketed_to_the_upstage_wall():
    # previs/layout.ts puts the upstage wall on the stage box, or 0.15 m behind
    # the rearmost fixture, and brackets to it any fixture within 0.25 m that is
    # 0.6 m or more off the floor. Further out, each row of cells would get a
    # truss or a stand of its own.
    preset = _preset()
    back_wall = min(-preset.stage.depth / 2, min(f.z for f in preset.fixtures) - 0.15)
    assert back_wall == -preset.stage.depth / 2, "a fixture has pushed the upstage wall back"
    for f in preset.fixtures:
        if f.id.startswith(BOOTH_UNIVERSE_IDS):
            assert 0 <= f.z - back_wall <= 0.25, f.id
            assert f.y >= 0.6, f.id


def test_the_led_walls_hang_above_the_booth_and_the_dj_camera():
    # The view's DJ camera stands a metre behind the upstage wall at 2.6 m and
    # looks out through it; its speaker stacks and the DJ reach about 2.1 m. A
    # wall cell at that height would fill the camera's frame.
    for f in _preset().fixtures:
        if f.id.startswith(BOOTH_UNIVERSE_IDS):
            assert f.y >= 3.5, f.id
            assert f.y < _preset().stage.height, f.id


def test_no_fixture_sits_on_the_line_between_the_engines_left_centre_and_right():
    # The engine calls a fixture left or right when it is more than 0.5 m off
    # the mean x of the rig. The mean of a mirrored rig is zero give or take
    # float noise, so a fixture at exactly 0.5 could fall either side of it
    # and its mirror image the other way.
    manager, preset = create_venue_rig(NAME)
    for f in preset.fixtures:
        assert abs(abs(f.x) - 0.5) > 0.05, f.id
    assert len(manager.groups["left"].fixture_ids) == len(manager.groups["right"].fixture_ids)


def test_every_fixture_has_a_mirror_image_of_its_own_kind():
    fixtures = _preset().fixtures
    places = {(f.model, round(f.x, 2), round(f.y, 2), round(f.z, 2)) for f in fixtures}
    assert len(places) == len(fixtures), "two fixtures are patched in the same place"
    for f in fixtures:
        assert (f.model, round(-f.x, 2), round(f.y, 2), round(f.z, 2)) in places, f.id


def test_the_moving_heads_hang_in_rows_wide_enough_to_fan():
    rows = {}
    for f in _preset().fixtures:
        if f.fixture_type in ("mover", "wash", "spot"):
            rows.setdefault(f.z, []).append(f)
    assert len(rows) == 7
    assert all(len(row) >= 4 for row in rows.values())


def test_nothing_hung_is_low_enough_for_the_view_to_stand_it_on_the_floor():
    # previs/layout.ts stands any fixture below 0.45 x stage height on a stand,
    # unless it is on the floor (below 0.6 m) or bracketed to a wall or the booth.
    preset = _preset()
    stand_below = 0.45 * preset.stage.height
    for f in preset.fixtures:
        if f.fixture_type in ("mover", "wash", "spot", "strobe"):
            assert f.y >= stand_below, f.id
    washes = [f for f in preset.fixtures if f.fixture_type == "wash"]
    assert all(abs(f.y - 3.05) < 1e-6 for f in washes), "the washes trim at 10 ft"


def test_the_dome_stays_inside_the_dome():
    for f in _preset().fixtures:
        if f.id.startswith("dome_"):
            assert _radius(f) <= 13.4 + 1e-6, f.id
            assert f.y > _preset().stage.height


def test_the_key_zones_name_real_zones_and_real_fixtures():
    ids = {f.id for f in _preset().fixtures}
    for zone in _preset().key_zones:
        PerformerZone(zone.zone)
        assert set(zone.fixture_ids) <= ids


def test_the_engine_rig_carries_every_fixture_and_only_movers_move():
    manager, preset = create_venue_rig(NAME)
    assert len(manager.fixtures) == len(preset.fixtures) == 131
    moving = [f for f in manager.fixtures.values() if f.pan_range > 0]
    assert len(moving) == 34
    assert len(manager.groups["movers"].fixture_ids) == 26
    # To the engine the two booth wash pars are washes and the LED wall cells bars.
    assert len(manager.groups["washes"].fixture_ids) == 30
    assert len(manager.groups["bars"].fixture_ids) == 67
    assert len(manager.groups["strobes"].fixture_ids) == 8


# --- Groups ------------------------------------------------------------------

def test_every_fixture_is_in_a_group_and_every_group_names_real_fixtures():
    preset = _preset()
    ids = {f.id for f in preset.fixtures}
    grouped = {fid for members in preset.groups.values() for fid in members}
    assert grouped == ids, sorted(ids ^ grouped)
    assert all(f.groups for f in preset.fixtures)
    for name, members in preset.groups.items():
        assert members, name
        assert len(members) == len(set(members)), name


def test_the_groups_are_the_ones_a_look_would_ask_for():
    sizes = {name: len(members) for name, members in _preset().groups.items()}
    assert sizes == {
        "floor_spots": 22,
        "spots_chord_a": 5, "spots_chord_b": 6, "spots_chord_c": 6, "spots_chord_d": 5,
        "spots_left": 10, "spots_right": 10,
        "balcony_spots": 4,
        "centre_washes": 8,
        "truss_strobes": 8,
        "led_pars": 10, "wall_pars": 6, "staircase_pars": 2, "booth_wash": 2,
        "led_strips": 8, "booth_strips": 4, "skybox_strips": 4,
        "dome_pixels": 44, "dome_spokes": 32, "dome_spokes_inner": 16,
        "dome_spokes_outer": 16, "dome_rim": 12,
        "led_wall": 27, "led_wall_centre": 15, "led_wall_wings": 12,
        "dj_booth": 33,
    }


def test_the_left_and_right_spots_are_mirror_images():
    by_id = {f.id: f for f in _preset().fixtures}
    groups = _preset().groups
    left = sorted((round(-by_id[i].x, 2), by_id[i].z) for i in groups["spots_left"])
    right = sorted((round(by_id[i].x, 2), by_id[i].z) for i in groups["spots_right"])
    assert left == right
    assert all(by_id[i].x < 0 for i in groups["spots_left"])


def test_no_preset_group_takes_a_name_the_engine_owns():
    # A preset group called "washes" or "strobes" would replace the group every
    # effect looks up. create_venue_rig leaves such a group out; this holds the
    # preset to never asking for one.
    manager, preset = create_venue_rig(NAME)
    owned = set(FixtureGroupManager().groups) | set(ENGINE_TYPE_GROUP_NAMES.values()) | {"movers_washes"}
    assert {"all", "left", "right", "washes", "strobes"} <= owned
    assert not owned & set(preset.groups)
    for name, members in preset.groups.items():
        assert manager.groups[name].fixture_ids == members, name


# --- Room shell --------------------------------------------------------------

def test_the_room_shell_has_the_dome_floor_balcony_booth_and_rear_stage():
    room = _preset().room
    assert room is not None

    assert room.dome.diameter_ft == 88.0
    assert room.dome.radius == LIV_DOME_RADIUS
    assert abs(room.dome.radius * 2 - 88 * 0.3048) < 0.1
    assert room.dome.apex_height > room.dome.rim_height > _preset().stage.height
    assert abs(room.dome.height_at(0.0) - room.dome.apex_height) < 1e-9
    assert abs(room.dome.height_at(room.dome.radius) - room.dome.rim_height) < 1e-9

    assert 0 < room.dance_floor.radius < room.balcony.inner_radius < room.balcony.outer_radius
    assert room.balcony.outer_radius <= room.dome.radius
    assert room.balcony.deck_height > room.balcony.soffit_height
    assert room.dj_booth.center_z < 0 < room.rear_stage.center_z
    assert len(room.led_walls) == 3

    for part in (room.dome, room.dance_floor, room.balcony, room.dj_booth, room.rear_stage, *room.led_walls):
        assert part.basis, part


def test_the_fixtures_fit_the_room_shell_they_are_patched_in():
    preset = _preset()
    room = preset.room
    in_group = {name: [f for f in preset.fixtures if name in f.groups] for name in preset.groups}

    # Dome cells hang under the dome's surface, not through it.
    for f in in_group["dome_pixels"]:
        assert f.y < room.dome.height_at(_radius(f)), f.id

    # The mezzanine spots are on the balcony's soffit, inside its ring and arc.
    for f in in_group["balcony_spots"]:
        assert room.balcony.inner_radius <= _radius(f) <= room.balcony.outer_radius, f.id
        assert f.y == room.balcony.soffit_height
        assert f.z > 0, "the balcony is the rear half of the room"

    # The booth strips are on the booth's front face.
    booth_front = room.dj_booth.center_z + room.dj_booth.depth / 2
    for f in in_group["booth_strips"]:
        assert 0 <= f.z - booth_front <= 0.25, f.id
        assert abs(f.x) <= room.dj_booth.width / 2
        assert f.y <= room.dj_booth.height

    # Every wall cell lies on one of the wall panels.
    for f in in_group["led_wall"]:
        assert any(
            abs(f.x - wall.center_x) <= wall.width / 2
            and wall.base_height <= f.y <= wall.base_height + wall.height
            for wall in room.led_walls
        ), f.id

    # The rear riser does not bury the staircase pars beside it, or anything else.
    riser = room.rear_stage
    for f in preset.fixtures:
        inside = (
            abs(f.x - riser.center_x) < riser.width / 2
            and abs(f.z - riser.center_z) < riser.depth / 2
            and f.y < riser.height
        )
        assert not inside, f.id


@pytest.mark.asyncio
async def test_the_demo_rig_payload_carries_the_room_shell():
    rig = await demo_endpoints.get_demo_rig(NAME)
    shell = rig["room_shell"]
    assert set(shell) == {"basis", "dome", "dance_floor", "balcony", "dj_booth", "rear_stage", "led_walls"}
    assert shell["dome"]["diameter_ft"] == 88.0
    assert shell["rear_stage"]["name"] == "Rear stage riser"
    assert len(rig["fixtures"]) == 131

    # A preset that describes no room says so rather than leaving the key out.
    assert (await demo_endpoints.get_demo_rig("club_night"))["room_shell"] is None


# --- Patch sheets ------------------------------------------------------------

def test_the_committed_patch_sheet_is_the_one_the_preset_generates():
    committed = PATCH_SHEET.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == patch_sheet_csv(_preset()), (
        "docs/venues/liv_miami_approx_patch.csv is stale - run scripts/export_demo_patch_sheet.py"
    )


def test_the_committed_markdown_sheet_is_the_one_the_preset_generates():
    committed = PATCH_SHEET_MD.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == patch_sheet_markdown(_preset()), (
        "docs/venues/liv_miami_approx_patch.md is stale - run scripts/export_demo_patch_sheet.py"
    )


def test_the_markdown_sheet_lists_every_fixture_with_its_groups():
    preset = _preset()
    assert "Groups" in COLUMNS and "Fixture ID" in COLUMNS

    patch = patch_sheet_markdown(preset).split("## Patch")[1]
    rows = [line for line in patch.splitlines() if line.startswith("| ") and not line.startswith("| ---")]
    columns = [cell.strip() for cell in rows[0].strip("|").split("|")]
    assert columns == ["#", "Fixture ID", "Name", "Profile", "Mode", "Channels", "Universe",
                       "Address", "Group", "Groups", "X", "Y", "Z", "Rotation"]
    body = rows[1:]
    assert len(body) == len(preset.fixtures)

    by_id = {f.id: f for f in preset.fixtures}
    for line in body:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        # A stray bar in any cell would add a column to its row.
        assert len(cells) == len(columns), line
        f = by_id[cells[1].strip("`")]
        assert cells[9].split("; ") == list(f.groups)
        assert (int(cells[5]), int(cells[6]), int(cells[7])) == (
            channel_count(f.fixture_type), f.universe, f.dmx_address)
        assert (cells[10], cells[11], cells[12]) == (f"{f.x:.2f}", f"{f.y:.2f}", f"{f.z:.2f}")
