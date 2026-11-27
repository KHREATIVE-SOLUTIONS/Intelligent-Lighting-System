"""
Patch sheets: the generated layout
==================================

A patch sheet with no positions is laid out on a stage template. What is held
here is what the rest of the system leans on: a row is found from address
order, a row is spread evenly and mirrored about the centre line, a position
the sheet gave is left alone, and every position this code made up says so.
"""

from pathlib import Path

import pytest

from app.services.demo import patch_sheet_samples
from app.services.patch_sheet import read_patch_sheet
from app.services.patch_sheet.layout import (
    POSITION_SOURCE,
    find_rows,
    fixture_kind,
    generate_layout,
    pick_template,
)
from app.services.patch_sheet.positions import BOOTH, FLOOR, FOH, OVERHEAD, RISER, TOWER, classify_position
from app.services.patch_sheet.templates import (
    TEMPLATES,
    Line,
    Pair,
    Ring,
    build_template,
    club_ring,
    festival_main_stage,
    small_stage,
)
from app.services.venue_import.apply import TAG_UNCONFIRMED, TAG_UNPLACED, fixture_tags, stage_size
from app.services.venue_import.csv_patch import parse_csv_patch
from app.services.venue_import.preview import RESERVED_GROUP_NAMES, plan_import, render_preview

SAMPLES = Path(__file__).resolve().parent.parent / "fixtures" / "import"

LIBRARY = [{
    "id": 7, "manufacturer": "Acme", "model": "Zed 300", "fixture_type": "moving_head",
    "gdtf_id": None, "source": "manual",
    "modes": [{"id": 70, "name": "16ch", "channel_count": 16}],
}]


def plan(csv_text: str, library=()):
    parsed = parse_csv_patch(csv_text.encode())
    plans, clashes, warnings = plan_import(parsed, list(library))
    return parsed, plans


def festival_plans():
    parsed = read_patch_sheet(patch_sheet_samples.FESTIVAL_FILE, patch_sheet_samples.festival_csv().encode())
    plans, clashes, _ = plan_import(parsed, [])
    assert clashes == []
    return parsed, plans


def is_mirrored(points) -> bool:
    """Every point has its mirror image about the centre line (X = 0) in the set."""
    return all((-x + 0.0, y, z) in {(px + 0.0, py, pz) for px, py, pz in points} for x, y, z in points)


def row_names(rows):
    return [[p.name for p in row.plans] for row in rows]


# ---------------------------------------------------------------------------
# The sample
# ---------------------------------------------------------------------------

def test_the_committed_festival_sheet_is_the_one_the_generator_writes():
    committed = (SAMPLES / patch_sheet_samples.FESTIVAL_FILE).read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == patch_sheet_samples.festival_csv(), (
        "tests/fixtures/import/demo_festival_patch_no_positions.csv is out of date. "
        "Run scripts/build_venue_import_samples.py."
    )


def test_the_festival_sheet_is_labelled_example_data_and_places_nothing():
    text = patch_sheet_samples.festival_csv()
    assert "EXAMPLE DATA" in text.splitlines()[1]
    parsed, plans = festival_plans()
    assert len(parsed.fixtures) == 84
    assert all(f.position is None and not f.position_label and not f.group_name for f in parsed.fixtures)
    assert all(p.importable for p in plans)
    assert sorted({f.universe for f in parsed.fixtures}) == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# Rows from address order
# ---------------------------------------------------------------------------

def test_consecutive_addresses_of_one_type_are_one_row_in_address_order():
    # Written out of order on purpose: the row is in address order, not sheet order.
    _, plans = plan(
        "Name,Type,Footprint,Patch\n"
        "C,Acme Beam,16,1.33\n"
        "A,Acme Beam,16,1.1\n"
        "B,Acme Beam,16,1.17\n"
        "W1,Acme Wash,14,1.49\n"
        "W2,Acme Wash,14,1.63\n"
    )
    assert row_names(find_rows(plans)) == [["A", "B", "C"], ["W1", "W2"]]


def test_a_gap_a_whole_fixture_would_fit_in_starts_a_new_row():
    _, plans = plan(
        "Name,Type,Footprint,Patch\n"
        "A,Acme Beam,16,1.1\n"
        "B,Acme Beam,16,1.17\n"
        "C,Acme Beam,16,1.101\n"
        "D,Acme Beam,16,1.117\n"
    )
    assert row_names(find_rows(plans)) == [["A", "B"], ["C", "D"]]


def test_padding_smaller_than_a_fixture_does_not_break_a_row():
    # 16-channel fixtures patched every 20: the same row.
    _, plans = plan(
        "Name,Type,Footprint,Patch\nA,Acme Beam,16,1.1\nB,Acme Beam,16,1.21\nC,Acme Beam,16,1.41\n"
    )
    assert row_names(find_rows(plans)) == [["A", "B", "C"]]


def test_a_jump_in_fixture_ids_starts_a_new_row_even_on_consecutive_addresses():
    _, plans = plan(
        "FID,Name,Type,Footprint,Patch\n"
        "107,A,Acme Beam,16,1.1\n"
        "108,B,Acme Beam,16,1.17\n"
        "201,C,Acme Beam,16,1.33\n"
        "202,D,Acme Beam,16,1.49\n"
    )
    assert row_names(find_rows(plans)) == [["A", "B"], ["C", "D"]]


def test_a_jump_in_fixture_ids_after_a_single_fixture_starts_a_new_row():
    _, plans = plan(
        "FID,Name,Type,Footprint,Patch\n"
        "108,A,Acme Beam,16,1.1\n"
        "201,B,Acme Beam,16,1.17\n"
        "202,C,Acme Beam,16,1.33\n"
    )
    assert row_names(find_rows(plans)) == [["A"], ["B", "C"]]


def test_a_change_of_universe_starts_a_new_row():
    _, plans = plan(
        "Name,Type,Footprint,Patch\n"
        "A,Acme Beam,16,1.1\nB,Acme Beam,16,1.17\nC,Acme Beam,16,2.1\nD,Acme Beam,16,2.17\n"
    )
    assert row_names(find_rows(plans)) == [["A", "B"], ["C", "D"]]


def test_a_row_that_runs_off_the_end_of_a_universe_carries_on_in_the_next():
    _, plans = plan(
        "Name,Type,Footprint,Patch\n"
        "A,Acme Beam,16,1.481\nB,Acme Beam,16,1.497\nC,Acme Beam,16,2.1\nD,Acme Beam,16,2.17\n"
    )
    rows = find_rows(plans)
    assert row_names(rows) == [["A", "B", "C", "D"]]
    assert sorted({p.fixture.universe for p in rows[0].plans}) == [0, 1]


def test_rows_are_found_without_footprints_from_an_even_stride():
    # No Footprint column and no profile: the stride is all there is.
    _, plans = plan(
        "Name,Type,Patch\n"
        "A,Acme Beam,1.1\nB,Acme Beam,1.17\nC,Acme Beam,1.33\n"
        "D,Acme Beam,1.101\nE,Acme Beam,1.117\n"
    )
    assert not plans[0].footprint_known
    assert row_names(find_rows(plans)) == [["A", "B", "C"], ["D", "E"]]


def test_a_matched_profile_gives_the_footprint_a_row_is_found_by():
    _, plans = plan(
        "Name,Type,Patch\nA,Acme Zed 300,1.1\nB,Acme Zed 300,1.17\nC,Acme Zed 300,1.200\n", LIBRARY,
    )
    assert plans[0].footprint == 16 and plans[0].footprint_known
    assert row_names(find_rows(plans)) == [["A", "B"], ["C"]]


def test_a_position_name_or_a_sheet_group_splits_a_run():
    _, plans = plan(
        "Name,Type,Footprint,Patch,Position,Group\n"
        "A,Acme Beam,16,1.1,US Truss,\n"
        "B,Acme Beam,16,1.17,US Truss,\n"
        "C,Acme Beam,16,1.33,DS Truss,\n"
        "D,Acme Beam,16,1.49,DS Truss,Keys\n"
    )
    assert row_names(find_rows(plans)) == [["A", "B"], ["C"], ["D"]]


def test_the_festival_sheet_is_seven_rows_with_the_split_universe_kept_together():
    _, plans = festival_plans()
    rows = find_rows(plans)
    assert [len(row.plans) for row in rows] == [16, 12, 16, 8, 8, 12, 12]
    back_wash = rows[-1]
    assert [p.name for p in back_wash.plans] == [f"Back Wash {n}" for n in range(1, 13)]
    assert sorted({p.fixture.universe for p in back_wash.plans}) == [2, 3]
    assert [row.kind for row in rows] == ["mover", "wash", "mover", "strobe", "blinder", "bar", "wash"]


def test_fixtures_that_cannot_be_patched_or_already_have_a_position_are_not_in_a_row():
    _, plans = plan(
        "Name,Type,Footprint,Patch,X,Y,Z\n"
        "Placed,Acme Beam,16,1.1,1,5,-2\n"
        "Free,Acme Beam,16,1.17,,,\n"
        "No address,Acme Beam,16,,,,\n"
    )
    assert row_names(find_rows(plans)) == [["Free"]]


# ---------------------------------------------------------------------------
# Kinds and position names
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("type_name, kind", [
    ("Acme Beam 300", "mover"), ("Demo Spot 16ch", "mover"), ("MegaWash 7", "wash"),
    ("Demo Strobe 4ch", "strobe"), ("Demo Blinder 2ch", "blinder"), ("Demo LED Bar 8ch", "bar"),
    ("Slim Par 64", "par"), ("Hazer Pro", "atmosphere"), ("Nonesuch 9000", "other"),
])
def test_kind_of_fixture_from_its_type_name(type_name, kind):
    _, plans = plan(f"Name,Type,Patch\nX,{type_name},1.1\n")
    assert fixture_kind(plans[0]) == kind


def test_kind_prefers_the_matched_profile_over_the_words_in_the_name():
    _, plans = plan("Name,Type,Patch\nBar wash 1,Acme Zed 300,1.1\n", LIBRARY)
    assert fixture_kind(plans[0]) == "mover"


@pytest.mark.parametrize("label, family, depth, side", [
    ("US Truss", OVERHEAD, 0.0, ""),
    ("Upstage truss", OVERHEAD, 0.0, ""),
    ("MS Truss", OVERHEAD, 0.5, ""),
    ("DS Pipe", OVERHEAD, 1.0, ""),
    ("D/S truss", OVERHEAD, 1.0, ""),
    ("USL", OVERHEAD, 0.0, "sl"),
    ("LX 2", OVERHEAD, None, ""),
    ("Floor", FLOOR, None, ""),
    ("DS floor", FLOOR, 1.0, ""),
    ("SL Tower", TOWER, None, "sl"),
    ("Tower SR", TOWER, None, "sr"),
    ("Stage Left", TOWER, None, "sl"),
    ("House Left ladder", TOWER, None, "sr"),
    ("Side towers", TOWER, None, ""),
    ("Drum Riser", RISER, None, ""),
    ("DJ Booth", BOOTH, None, ""),
    ("FOH", FOH, None, ""),
])
def test_position_names(label, family, depth, side):
    hint = classify_position(label)
    assert (hint.family, hint.depth, hint.side) == (family, depth, side)


def test_position_names_that_say_nothing_are_not_guessed_at():
    assert classify_position("") is None
    assert classify_position("Dimmer room") is None
    assert classify_position("LX 2").number == 2
    assert classify_position("Ring").ring is True


# ---------------------------------------------------------------------------
# Templates: even and mirrored
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("count", [1, 2, 3, 4, 7, 12, 16, 25])
def test_a_line_is_spread_evenly_and_mirrored(count):
    line = festival_main_stage().overhead(0.0)
    points = line.points(count)
    assert len(points) == len(set(points)) == count
    assert is_mirrored(points)
    xs = [x for x, _, _ in points]
    assert xs == sorted(xs), "left to right"
    assert len({(y, z) for _, y, z in points}) == 1
    steps = [round(b - a, 2) for a, b in zip(xs, xs[1:])]
    assert max(steps, default=0) - min(steps, default=0) <= 0.011
    if count % 2:
        assert points[count // 2][0] == 0.0
    # Half a bay of margin at each end: never on the end of the truss.
    assert abs(xs[0]) < line.length / 2


@pytest.mark.parametrize("count", [1, 2, 5, 8, 12])
def test_a_ring_is_spread_evenly_and_mirrored(count):
    template = club_ring()
    ring = template.ring()
    points = ring.points(count)
    assert len(points) == len(set(points)) == count
    assert is_mirrored(points)
    assert all(y == template.trim for _, y, _ in points)
    for x, _, z in points:
        assert ((x ** 2 + (z - ring.centre_z) ** 2) ** 0.5) == pytest.approx(ring.radius, abs=0.02)


@pytest.mark.parametrize("count", [2, 4, 8])
def test_towers_carry_an_even_row_level_for_level(count):
    template = festival_main_stage()
    points = template.towers().points(count)
    assert is_mirrored(points)
    low = [p for p in points if p[0] < 0]
    high = [p for p in points if p[0] > 0]
    assert len(low) == len(high) == count // 2
    assert [y for _, y, _ in low] == sorted(y for _, y, _ in low), "bottom to top"
    assert all(template.tower_low < y < template.tower_high for _, y, _ in points)


def test_towers_with_an_odd_row_put_the_extra_one_on_the_first_tower():
    points = festival_main_stage().towers().points(5)
    assert sum(1 for x, _, _ in points if x < 0) == 3
    assert sum(1 for x, _, _ in points if x > 0) == 2


@pytest.mark.parametrize("name", list(TEMPLATES))
def test_every_template_keeps_its_places_inside_the_room_and_off_the_origin(name):
    template = build_template(name)
    places = [
        template.overhead(0.0), template.overhead(0.5), template.overhead(1.0),
        template.floor(0.0), template.floor(0.5), template.floor(1.0),
        template.towers(), template.riser(), template.booth(), template.foh(),
    ]
    if template.has_ring:
        places.append(template.ring())
    for place in places:
        for count in (1, 2, 3):
            for x, y, z in place.points(count):
                assert (x, y, z) != (0.0, 0.0, 0.0)
                assert 0.0 < y <= template.height
                assert abs(x) <= template.width / 2 + 2.5
                assert abs(z) <= template.depth / 2 + 2.0
    described = template.describe()
    assert described["name"] == name and described["places"]["upstage_truss"]["shape"] == "line"


def test_a_template_takes_the_size_it_is_given():
    wide = build_template("festival_main_stage", width=40, depth=20, height=16)
    assert (wide.width, wide.depth, wide.height) == (40, 20, 16)
    assert wide.truss_length == 38 and wide.trim == 14.5
    assert build_template("small_stage").width == small_stage().width
    with pytest.raises(KeyError):
        build_template("arena")


def test_rows_sharing_one_truss_sit_on_different_chords():
    line = festival_main_stage().overhead(0.0)
    assert isinstance(line, Line) and isinstance(club_ring().ring(), Ring)
    assert isinstance(festival_main_stage().towers(), Pair)
    depths = {line.shifted(nth).points(1)[0][2] for nth in range(4)}
    assert len(depths) == 4


# ---------------------------------------------------------------------------
# The layout
# ---------------------------------------------------------------------------

def test_the_festival_sheet_is_laid_out_whole_on_the_festival_stage():
    parsed, plans = festival_plans()
    name, why = pick_template(plans)
    assert name == "festival_main_stage" and "84" in why
    template = build_template(name)
    report = generate_layout(plans, template, chosen_by=why)

    assert report["generated"] == 84 and report["kept_from_sheet"] == 0
    assert report["position_confirmed"] is False
    assert [row["where"] for row in report["rows"]] == [
        "US Truss", "Truss C", "Truss B", "Truss E", "DS Truss", "US Floor", "Truss D",
    ]
    assert all(row["placed_by"] == "type" and row["position_confirmed"] is False for row in report["rows"])

    positions = [p.position for p in plans]
    assert None not in positions and (0.0, 0.0, 0.0) not in positions
    assert len(set(positions)) == 84, "no two fixtures share a point"

    # Each row is one straight line across the stage, left to right in address order.
    for row in report["rows"]:
        points = [plans[i].position for i in row["fixture_indexes"]]
        assert is_mirrored(points)
        assert len({(y, z) for _, y, z in points}) == 1
        assert [x for x, _, _ in points] == sorted(x for x, _, _ in points)
        addresses = [(plans[i].fixture.universe, plans[i].fixture.dmx_address) for i in row["fixture_indexes"]]
        assert addresses == sorted(addresses)

    by_group = {row["group"]: row for row in report["rows"]}
    assert by_group["US Truss ILS Demo Demo Spot 16ch"]["fixtures"] == 16
    assert by_group["US Floor ILS Demo Demo LED Bar 8ch"]["from"]["y"] == pytest.approx(0.1)
    # Movers upstage of washes, washes upstage of strobes and blinders.
    depth = {row["kind"]: [] for row in report["rows"]}
    for row in report["rows"]:
        depth[row["kind"]].append(row["from"]["z"])
    assert max(depth["mover"]) < min(depth["wash"]) < max(depth["wash"]) < depth["strobe"][0] < depth["blinder"][0]

    assert stage_size(plans, parsed, at_least=template.stage_size()) == {
        "stage_width": 24.0, "stage_depth": 14.0, "stage_height": 12.0,
    }


def test_every_generated_position_is_flagged_unconfirmed():
    parsed, plans = festival_plans()
    generate_layout(plans, festival_main_stage())
    for p in plans:
        assert p.position_source == POSITION_SOURCE == "template"
        assert p.position_confirmed is False
        tags = fixture_tags(p)
        assert TAG_UNCONFIRMED in tags and "position_source:template" in tags
        assert TAG_UNPLACED not in tags

    preview = render_preview(parsed, [], plans, [], [])
    assert all(row["position_confirmed"] is False and row["unplaced"] is False for row in preview["fixtures"])
    assert all(row["position_source"] == "template" for row in preview["fixtures"])
    summary = preview["summary"]
    assert (summary["placed"], summary["unplaced"], summary["unconfirmed_positions"]) == (84, 0, 84)
    assert summary["position_sources"] == {"template": 84}


def test_a_position_the_sheet_gives_is_kept_and_is_not_flagged():
    parsed, plans = plan(
        "Name,Type,Footprint,Patch,X,Y,Z\n"
        "Measured,Acme Beam,16,1.1,1.5,6,-2\n"
        "Guessed,Acme Beam,16,1.17,,,\n"
        "No address,Acme Beam,16,,,,\n"
    )
    report = generate_layout(plans, small_stage())
    measured, guessed, unpatched = plans
    assert measured.position == (1.5, 6.0, -2.0) and measured.position_source == "csv"
    assert measured.position_confirmed is True and TAG_UNCONFIRMED not in fixture_tags(measured)
    assert guessed.position is not None and guessed.position_confirmed is False
    assert unpatched.position is None and TAG_UNPLACED in fixture_tags(unpatched)
    assert (report["generated"], report["kept_from_sheet"]) == (1, 1)


def test_position_names_put_rows_where_they_say():
    _, plans = plan(
        "Name,Type,Footprint,Patch,Position\n"
        "U1,Acme Beam,16,1.1,US Truss\nU2,Acme Beam,16,1.17,US Truss\n"
        "D1,Acme Wash,14,1.101,DS Truss\nD2,Acme Wash,14,1.115,DS Truss\n"
        "L1,Acme Beam,16,1.201,SL Tower\nL2,Acme Beam,16,1.217,SL Tower\n"
        "R1,Acme Beam,16,1.301,SR Tower\nR2,Acme Beam,16,1.317,SR Tower\n"
        "F1,Slim Par,8,1.401,Floor\nF2,Slim Par,8,1.409,Floor\n"
        "K1,Acme Wash,14,2.1,Drum Riser\n"
        "B1,Acme Wash,14,2.101,DJ Booth\nB2,Acme Wash,14,2.115,DJ Booth\n"
    )
    template = festival_main_stage()
    report = generate_layout(plans, template)
    at = {p.name: p.position for p in plans}
    where = {row["position_label"]: row for row in report["rows"]}

    assert at["U1"][1:] == at["U2"][1:] == (template.trim, template.upstage_z)
    assert at["D1"][1:] == (template.trim, template.downstage_z)
    assert at["U1"][0] == -at["U2"][0] < 0

    # The two towers mirror each other, level for level, bottom to top.
    assert at["L1"][0] == at["L2"][0] == -template.tower_x
    assert at["R1"] == (-at["L1"][0], at["L1"][1], at["L1"][2])
    assert at["R2"] == (-at["L2"][0], at["L2"][1], at["L2"][2])
    assert at["L1"][1] < at["L2"][1]

    assert at["F1"][1] == pytest.approx(0.1) and at["F1"][0] == -at["F2"][0]
    assert at["K1"] == (0.0, template.riser_y, template.riser_z)
    assert at["B1"][1:] == (template.booth_y, round(template.booth_z, 2))
    assert where["US Truss"]["placed_by"] == "label" and where["US Truss"]["where"] == "US Truss"
    assert where["SL Tower"]["where"] == "SL Tower" and where["DJ Booth"]["where"] == "DJ Booth"
    # "Floor" names a kind of place and no depth, so the type decides which floor row.
    assert where["Floor"]["placed_by"] == "type"
    assert any("stage left" in a and "mirror=true" in a for a in report["assumptions"])


def test_mirror_swaps_which_side_stage_left_is():
    sheet = (
        "Name,Type,Footprint,Patch,Position\n"
        "L1,Acme Beam,16,1.1,SL Tower\nR1,Acme Beam,16,1.101,SR Tower\n"
    )
    _, plans = plan(sheet)
    generate_layout(plans, festival_main_stage())
    usual = {p.name: p.position[0] for p in plans}
    _, plans = plan(sheet)
    report = generate_layout(plans, festival_main_stage(), mirror=True)
    swapped = {p.name: p.position[0] for p in plans}
    assert usual["L1"] < 0 < usual["R1"]
    assert swapped["L1"] > 0 > swapped["R1"]
    assert any("as asked (mirror)" in a for a in report["assumptions"])


def test_towers_without_a_side_take_a_row_between_them_and_say_when_it_is_odd():
    _, plans = plan(
        "Name,Type,Footprint,Patch,Position\n"
        + "".join(f"T{n},Acme Beam,16,1.{1 + 16 * (n - 1)},Towers\n" for n in range(1, 6))
    )
    report = generate_layout(plans, festival_main_stage())
    xs = [p.position[0] for p in plans]
    assert [x < 0 for x in xs] == [True, True, True, False, False]
    assert any("odd number" in w for w in report["warnings"])


def test_numbered_trusses_run_from_downstage_to_upstage():
    _, plans = plan(
        "Name,Type,Footprint,Patch,Position\n"
        "A,Acme Beam,16,1.1,LX 1\nB,Acme Beam,16,1.101,LX 2\nC,Acme Beam,16,1.201,LX 3\n"
    )
    template = small_stage()
    report = generate_layout(plans, template)
    z = {p.name: p.position[2] for p in plans}
    assert z["A"] == template.downstage_z and z["C"] == template.upstage_z
    assert z["A"] > z["B"] > z["C"]
    assert any("Numbered overhead positions" in a for a in report["assumptions"])


def test_a_position_name_that_is_not_understood_is_reported_and_placed_by_type():
    _, plans = plan(
        "Name,Type,Footprint,Patch,Position\nA,Acme Beam,16,1.1,Dimmer room\nB,Acme Beam,16,1.17,Dimmer room\n"
    )
    report = generate_layout(plans, small_stage())
    assert report["rows"][0]["placed_by"] == "type"
    assert report["rows"][0]["group"] == "Dimmer room Acme Beam"
    assert any("'Dimmer room'" in w for w in report["warnings"])
    assert all(p.position is not None for p in plans)


def test_the_club_template_hangs_unlabelled_rows_on_rings():
    _, plans = festival_plans()
    template = club_ring()
    report = generate_layout(plans, template)
    rings = {row["where"]: row for row in report["rows"] if row["place"]["shape"] == "ring"}
    # Three rings, moving lights first; what is left hangs on trusses across the room.
    assert sorted(rings) == ["Ring", "Ring 2", "Ring 3"]
    assert [rings[name]["kind"] for name in ("Ring", "Ring 2", "Ring 3")] == ["mover", "mover", "wash"]
    assert rings["Ring"]["place"]["radius"] > rings["Ring 2"]["place"]["radius"] > rings["Ring 3"]["place"]["radius"]
    lines = [row for row in report["rows"] if row["kind"] in ("strobe", "blinder")]
    assert all(row["place"]["shape"] == "line" and row["from"]["y"] == template.trim for row in lines)
    for row in report["rows"]:
        assert is_mirrored([plans[i].position for i in row["fixture_indexes"]])
    assert len({p.position for p in plans}) == 84


def test_a_sheet_that_names_a_ring_picks_the_club_and_a_short_one_the_small_stage():
    _, plans = plan("Name,Type,Footprint,Patch,Position\nA,Acme Beam,16,1.1,Ring\n")
    assert pick_template(plans)[0] == "club_ring"
    _, plans = plan("Name,Type,Footprint,Patch\nA,Acme Beam,16,1.1\n")
    assert pick_template(plans)[0] == "small_stage"


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

def test_each_row_becomes_a_group_and_a_type_spanning_rows_is_tagged():
    parsed, plans = festival_plans()
    report = generate_layout(plans, festival_main_stage())

    groups = [row["group"] for row in report["rows"]]
    assert len(set(groups)) == 7
    assert all(0 < len(g) <= 100 and g.lower() not in RESERVED_GROUP_NAMES for g in groups)
    for row in report["rows"]:
        assert {plans[i].fixture.group_name for i in row["fixture_indexes"]} == {row["group"]}

    # The 14-channel wash is in two rows, so both carry the type as a tag.
    washes = [p for p in plans if "Wash 14ch" in p.fixture.type_name]
    assert len(washes) == 24 and len({p.fixture.group_name for p in washes}) == 2
    assert all(p.fixture.groups == ["ILS Demo Demo Wash 14ch"] for p in washes)
    assert all("group:ILS Demo Demo Wash 14ch" in fixture_tags(p) for p in washes)
    spots = [p for p in plans if p.fixture.type_name.endswith("Demo Spot 16ch")]
    assert all(p.fixture.groups == [] for p in spots)

    preview = render_preview(parsed, [], plans, [], [])
    listed = {g["name"]: g for g in preview["groups"]}
    assert listed["US Truss ILS Demo Demo Spot 16ch"] == {
        "name": "US Truss ILS Demo Demo Spot 16ch", "fixtures": 16, "role": "group",
        "reserved": False, "reaches_engine": True,
    }
    assert listed["ILS Demo Demo Wash 14ch"]["role"] == "tag"


def test_a_group_the_sheet_names_is_kept():
    _, plans = plan(
        "Name,Type,Footprint,Patch,Group\nA,Acme Beam,16,1.1,Keys\nB,Acme Beam,16,1.17,Keys\n"
    )
    report = generate_layout(plans, small_stage())
    assert report["rows"][0]["group"] == "Keys"
    assert {p.fixture.group_name for p in plans} == {"Keys"}


def test_two_rows_that_would_share_a_group_name_get_different_ones():
    _, plans = plan(
        "Name,Type,Footprint,Patch,Position\n"
        "A,Acme Beam,16,1.1,US Truss\nB,Acme Beam,16,1.17,US Truss\n"
        "C,Acme Beam,16,1.201,US Truss\nD,Acme Beam,16,1.217,US Truss\n"
    )
    report = generate_layout(plans, festival_main_stage())
    assert [row["group"] for row in report["rows"]] == ["US Truss Acme Beam", "US Truss Acme Beam (2)"]
    # Same truss, different chords: no fixture on top of another.
    assert len({p.position for p in plans}) == 4
    assert len({p.position[2] for p in plans}) == 2


def test_a_row_too_tight_for_its_truss_is_warned_about():
    sheet = "Name,Type,Footprint,Patch\n" + "".join(f"P{n},Acme Beam,1,1.{n}\n" for n in range(1, 41))
    _, plans = plan(sheet)
    report = generate_layout(plans, small_stage())
    assert any("apart on this template" in w for w in report["warnings"])
    assert len({p.position for p in plans}) == 40
