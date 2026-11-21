"""
LIV Miami approximate recreation
================================

The default demo rig. It imitates a real room from public press, so it has to
say everywhere it is read that it is not that room's patch; and it is the rig
looks are judged on, so it has to be mirrored, inside its universes, and hung
where the 3D view will hang it rather than stand it on the floor.
"""

from pathlib import Path

from app.api.endpoints import demo as demo_endpoints
from app.main import DEMO_VENUE_PRESET
from app.services.demo.patch_sheet import channel_count, patch_sheet_csv
from app.services.demo.venue_presets import LIV_DISCLAIMER, VENUE_PRESETS, create_venue_rig
from app.services.lighting.key_lighting import PerformerZone

NAME = "liv_miami_approx"
REPO_ROOT = Path(__file__).resolve().parents[3]
PATCH_SHEET = REPO_ROOT / "docs" / "venues" / "liv_miami_approx_patch.csv"
NOTES = REPO_ROOT / "docs" / "venues" / "LIV_MIAMI_APPROX_NOTES.md"


def _preset():
    return VENUE_PRESETS[NAME]


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
    assert len(_preset().fixtures) == 102
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
    assert sorted({f.universe for f in _preset().fixtures}) == [0, 1, 2]


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
            assert (f.x ** 2 + f.z ** 2) ** 0.5 <= 13.4 + 1e-6, f.id
            assert f.y > _preset().stage.height


def test_the_key_zones_name_real_zones_and_real_fixtures():
    ids = {f.id for f in _preset().fixtures}
    for zone in _preset().key_zones:
        PerformerZone(zone.zone)
        assert set(zone.fixture_ids) <= ids


def test_the_engine_rig_carries_every_fixture_and_only_movers_move():
    manager, preset = create_venue_rig(NAME)
    assert len(manager.fixtures) == len(preset.fixtures) == 102
    moving = [f for f in manager.fixtures.values() if f.pan_range > 0]
    assert len(moving) == 34
    assert len(manager.groups["movers"].fixture_ids) == 26
    assert len(manager.groups["washes"].fixture_ids) == 28
    assert len(manager.groups["bars"].fixture_ids) == 40
    assert len(manager.groups["strobes"].fixture_ids) == 8


def test_the_committed_patch_sheet_is_the_one_the_preset_generates():
    committed = PATCH_SHEET.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == patch_sheet_csv(_preset()), (
        "docs/venues/liv_miami_approx_patch.csv is stale - run scripts/export_demo_patch_sheet.py"
    )
