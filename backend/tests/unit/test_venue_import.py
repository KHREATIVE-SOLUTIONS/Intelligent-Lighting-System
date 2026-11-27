"""
Venue import: the readers and the plan
======================================

Each reader (CSV patch list, GDTF, MVR, grandMA2 XML) is checked for the things
a wrong answer would put on stage: which universe and channel an address means,
millimetres against metres, which way a fixture is turned, a fixture the file
never placed, a type nothing matches, and two fixtures on the same channels.

The bundled samples have no clashes, no turned fixtures and no unplaced MVR or
grandMA2 fixture, so those inputs are written out here.
"""

import io
import zipfile
from pathlib import Path

import pytest

from app.services.demo import import_samples
from app.services.fixture_library import stage_axes
from app.services.fixture_library.console_parsers import parse_grandma_export
from app.services.fixture_library.mvr_parser import parse_matrix, parse_scene_xml
from app.services.venue_import import (
    ImportedFixture,
    ParsedVenue,
    VenueImportError,
    build_preview,
    detect_format,
    read_venue_file,
)
from app.services.venue_import.csv_patch import parse_csv_patch, read_address
from app.services.venue_import.model import split_absolute_address
from app.services.venue_import.preview import plan_import

SAMPLES = Path(__file__).resolve().parent.parent / "fixtures" / "import"

# Invented, so no library a test database happens to hold can match it.
UNKNOWN_TYPE = "Nonesuch Blinder 9000"

LIBRARY = [{
    "id": 7,
    "manufacturer": "Acme",
    "model": "Zed 300",
    "fixture_type": "spot",
    "gdtf_id": None,
    "source": "manual",
    "modes": [{"id": 70, "name": "16ch", "channel_count": 16}],
}]


def sample(name: str) -> bytes:
    return (SAMPLES / name).read_bytes()


def by_name(parsed: ParsedVenue) -> dict:
    return {f.name: f for f in parsed.fixtures}


def rows_by_name(preview: dict) -> dict:
    return {row["name"]: row for row in preview["fixtures"]}


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("absolute, expected", [
    (1, (0, 1)),
    (512, (0, 512)),
    (513, (1, 1)),
    (613, (1, 101)),
    (1049, (2, 25)),
    (0, None),
])
def test_absolute_address_becomes_universe_and_channel(absolute, expected):
    assert split_absolute_address(absolute) == expected


@pytest.mark.parametrize("text, universe, expected", [
    ("2.101", None, (1, 101)),
    ("2/101", None, (1, 101)),
    ("2:101", None, (1, 101)),
    ("613", None, (1, 101)),
    ("613.0", None, (1, 101)),     # a spreadsheet's idea of a whole number
    ("101", None, (0, 101)),
    ("101", 3, (3, 101)),
    ("512", None, (0, 512)),
    ("", 2, (2, None)),
    ("0", None, (None, None)),
])
def test_csv_address_cell(text, universe, expected):
    assert read_address(text, universe, []) == expected


def test_csv_address_that_cannot_be_read_says_so():
    notes = []
    assert read_address("stage left", None, notes) == (None, None)
    assert notes and "could not be read" in notes[0]

    notes = []
    assert read_address("2.600", None, notes)[1] is None
    assert notes


def test_csv_combined_address_outranks_the_universe_column():
    notes = []
    assert read_address("2.101", 4, notes) == (1, 101)
    assert notes and "the address was believed" in notes[0]


def test_csv_sample_reads_all_three_address_forms_into_one_universe():
    parsed = parse_csv_patch(sample("liv_approx_subset_patch.csv"), "patch.csv")
    assert len(parsed.fixtures) == 20
    fixtures = by_name(parsed)
    assert (fixtures["Dome Rim 1"].universe, fixtures["Dome Rim 1"].dmx_address) == (2, 1)     # 3.1
    assert (fixtures["Dome Rim 2"].universe, fixtures["Dome Rim 2"].dmx_address) == (2, 13)    # 3/13
    assert (fixtures["Dome Rim 3"].universe, fixtures["Dome Rim 3"].dmx_address) == (2, 25)    # 1049
    assert [f.dmx_address for f in parsed.fixtures] == [1 + 12 * i for i in range(20)]
    assert {f.universe for f in parsed.fixtures} == {2}


def test_csv_universe_column_counts_from_one_unless_it_holds_a_zero():
    console = b"Name,Type,Universe,Address\nA,Par,1,101\nB,Par,2,5\n"
    parsed = parse_csv_patch(console)
    assert [(f.universe, f.dmx_address) for f in parsed.fixtures] == [(0, 101), (1, 5)]
    assert any("counting from 1" in a for a in parsed.assumptions)

    own = b"Name,Type,Universe,Address\nA,Par,0,101\nB,Par,1,5\n"
    parsed = parse_csv_patch(own)
    assert [(f.universe, f.dmx_address) for f in parsed.fixtures] == [(0, 101), (1, 5)]
    assert any("counting from 0" in a for a in parsed.assumptions)

    asked = parse_csv_patch(console, universe_base="0")
    assert [(f.universe, f.dmx_address) for f in asked.fixtures] == [(1, 101), (2, 5)]


def test_csv_semicolon_file_and_other_header_spellings():
    parsed = parse_csv_patch(b"Label;Fixture Type;DMX Address;Footprint\nKey;Par;2.101;7\n")
    fixture = parsed.fixtures[0]
    assert (fixture.name, fixture.type_name, fixture.channel_count) == ("Key", "Par", 7)
    assert (fixture.universe, fixture.dmx_address) == (1, 101)


def test_csv_without_a_header_is_refused():
    with pytest.raises(VenueImportError):
        parse_csv_patch(b"just some words\nand some more\n")


# ---------------------------------------------------------------------------
# CSV positions
# ---------------------------------------------------------------------------

def test_csv_positions_are_metres_and_keep_their_source():
    text = (
        "Name,Type,Patch,X,Y,Z,Rot Y\n"
        "Placed,Par,1.1,1.5 m,6,-2,90\n"
        "Half,Par,1.11,1.5,,-2,\n"
        "Nowhere,Par,1.21,,,,\n"
    )
    fixtures = by_name(parse_csv_patch(text.encode()))

    placed = fixtures["Placed"]
    assert placed.position == (1.5, 6.0, -2.0)
    assert placed.rotation == (0.0, 90.0, 0.0)
    assert placed.position_source == "csv"

    # Two of three coordinates is not a position, and none is made up.
    half = fixtures["Half"]
    assert half.position is None and half.position_source == "none" and half.unplaced
    assert any("only part of a position" in note for note in half.notes)

    nowhere = fixtures["Nowhere"]
    assert nowhere.position is None and nowhere.rotation is None
    assert nowhere.position_source == "none"


def test_csv_z_up_sheet_is_turned_into_stage_axes():
    text = "Name,Type,Patch,X,Y,Z,Rot Z\nA,Par,1.1,1,2,3,90\n"
    fixture = parse_csv_patch(text.encode(), up_axis="z").fixtures[0]
    assert fixture.position == (1.0, 3.0, -2.0)
    assert fixture.rotation == (0.0, 90.0, 0.0)


def test_csv_position_column_holding_coordinates_places_the_fixture():
    text = 'Name,Type,Patch,Position\nA,Par,1.1,"(1, 2.5, -3)"\nB,Par,1.11,Truss 2\n'
    fixtures = by_name(parse_csv_patch(text.encode()))
    assert fixtures["A"].position == (1.0, 2.5, -3.0)
    assert fixtures["B"].position is None
    assert fixtures["B"].position_label == "Truss 2"


def test_csv_sample_flags_the_two_fixtures_it_does_not_place():
    parsed = read_venue_file("liv_approx_subset_patch.csv", sample("liv_approx_subset_patch.csv"))
    unplaced = [f for f in parsed.fixtures if f.unplaced]
    assert [f.name for f in unplaced] == ["Tri Par 7", "Tri Par 8"]
    assert all(f.position_source == "none" and f.position_label == "Staircase Pars" for f in unplaced)

    preview = build_preview(parsed, [])
    assert preview["summary"]["placed"] == 18
    assert preview["summary"]["unplaced"] == 2
    assert preview["summary"]["position_sources"] == {"csv": 18, "none": 2}
    row = rows_by_name(preview)["Tri Par 7"]
    assert row["unplaced"] is True and row["position"] is None


# ---------------------------------------------------------------------------
# MVR
# ---------------------------------------------------------------------------

IDENTITY = "{1,0,0}{0,1,0}{0,0,1}"
QUARTER_TURN = "{0,1,0}{-1,0,0}{0,0,1}"   # +90 degrees about the drawing's Z (up)


def mvr_fixture(name: str, address: str = "", matrix: str = "", spec: str = "Acme@Zed 300.gdtf") -> str:
    return (
        f'<Fixture name="{name}" uuid="{name}">'
        + (f"<Matrix>{matrix}</Matrix>" if matrix else "")
        + f"<GDTFSpec>{spec}</GDTFSpec><GDTFMode>16ch</GDTFMode><FixtureID>{name}</FixtureID>"
        + (f'<Addresses><Address break="0">{address}</Address></Addresses>' if address else "")
        + "</Fixture>"
    )


def mvr_scene(*children: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<GeneralSceneDescription verMajor="1" verMinor="6"><Scene><Layers>'
        '<Layer name="Rig" uuid="layer"><ChildList>' + "".join(children) + "</ChildList></Layer>"
        "</Layers></Scene></GeneralSceneDescription>"
    ).encode()


def mvr_archive(scene: bytes, *members) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("GeneralSceneDescription.xml", scene)
        for name, data in members:
            zf.writestr(name, data)
    return buffer.getvalue()


@pytest.mark.parametrize("address, expected", [
    ("1", (0, 1)),
    ("512", (0, 512)),
    ("513", (1, 1)),
    ("613", (1, 101)),
    ("2.101", (1, 101)),
    ("2/101", (1, 101)),
])
def test_mvr_address_forms(address, expected):
    data = parse_scene_xml(mvr_scene(mvr_fixture("A", address, IDENTITY + "{0,0,0}")))
    fixture = data["fixtures"][0]
    assert fixture["patched"] is True
    assert (fixture["universe"], fixture["dmx_address"]) == expected
    assert data["warnings"] == []


def test_mvr_zero_address_is_unpatched_and_a_bad_one_is_reported():
    data = parse_scene_xml(mvr_scene(
        mvr_fixture("Unpatched", "0", IDENTITY + "{0,0,0}"),
        mvr_fixture("Broken", "seven", IDENTITY + "{0,0,0}"),
    ))
    assert [f["patched"] for f in data["fixtures"]] == [False, False]
    assert len(data["warnings"]) == 1 and "Broken" in data["warnings"][0]

    parsed = read_venue_file("scene.xml", mvr_scene(mvr_fixture("Unpatched", "0", IDENTITY + "{0,0,0}")))
    fixture = parsed.fixtures[0]
    assert fixture.universe is None and fixture.dmx_address is None
    row = build_preview(parsed, [])["fixtures"][0]
    assert row["importable"] is False and row["refusal"] == "no DMX address"


def test_mvr_millimetres_become_metres_in_stage_axes():
    parsed = read_venue_file("scene.xml", mvr_scene(mvr_fixture("A", "1", IDENTITY + "{1000,2000,3000}")))
    fixture = parsed.fixtures[0]
    # Drawing: 1 m across, 2 m upstage, 3 m up. Stage: X across, Y up, -Z upstage.
    assert fixture.position == (1.0, 3.0, -2.0)
    assert fixture.rotation == (0.0, 0.0, 0.0)
    assert fixture.position_source == "mvr"
    assert any("millimetres" in a for a in parsed.assumptions)


def test_mvr_matrix_accepts_the_four_by_four_form():
    three = parse_matrix(IDENTITY + "{1000,2000,3000}")
    four = parse_matrix("{1,0,0,0}{0,1,0,0}{0,0,1,0}{1000,2000,3000,1}")
    assert three == four
    assert three[1] == (1000.0, 2000.0, 3000.0)
    assert parse_matrix("") is None and parse_matrix("{1,2}") is None


def test_mvr_fixture_inside_a_group_is_placed_through_the_group():
    scene = mvr_scene(
        '<GroupObject name="Chord A" uuid="g"><Matrix>' + IDENTITY + "{1000,0,0}</Matrix><ChildList>"
        + mvr_fixture("Inner", "17", IDENTITY + "{500,0,2000}")
        + "</ChildList></GroupObject>"
    )
    fixture = read_venue_file("scene.xml", scene).fixtures[0]
    assert fixture.position == (1.5, 2.0, 0.0)
    assert fixture.group_name == "Chord A"


def test_mvr_turned_group_turns_what_hangs_in_it():
    scene = mvr_scene(
        '<GroupObject name="Turned" uuid="g"><Matrix>' + QUARTER_TURN + "{0,0,0}</Matrix><ChildList>"
        + mvr_fixture("Inner", "17", IDENTITY + "{1000,0,0}")
        + "</ChildList></GroupObject>"
    )
    fixture = read_venue_file("scene.xml", scene).fixtures[0]
    # One metre along the group's X is one metre along the drawing's Y: upstage.
    assert fixture.position == (0.0, 0.0, -1.0)
    assert fixture.rotation == (0.0, 90.0, 0.0)


def test_mvr_rotation_about_the_vertical_is_the_heading():
    fixture = read_venue_file(
        "scene.xml", mvr_scene(mvr_fixture("A", "1", QUARTER_TURN + "{0,0,4000}"))
    ).fixtures[0]
    assert fixture.position == (0.0, 4.0, 0.0)
    assert fixture.rotation == (0.0, 90.0, 0.0)


def test_mvr_fixture_with_no_matrix_is_unplaced_not_put_at_the_origin():
    parsed = read_venue_file("scene.xml", mvr_scene(
        mvr_fixture("Placed", "1", IDENTITY + "{1000,0,3000}"),
        mvr_fixture("Loose", "17"),
        mvr_fixture("Unreadable", "33", "{1,0}{garbage}"),
    ))
    fixtures = by_name(parsed)
    assert fixtures["Placed"].position_source == "mvr"
    for name in ("Loose", "Unreadable"):
        assert fixtures[name].position is None
        assert fixtures[name].rotation is None
        assert fixtures[name].position_source == "none"
    assert any("Unreadable" in w for w in parsed.warnings)

    preview = build_preview(parsed, [])
    assert preview["summary"]["position_sources"] == {"mvr": 1, "none": 2}
    assert rows_by_name(preview)["Loose"]["importable"] is True   # patched, just not placed


def test_mvr_names_a_gdtf_the_archive_does_not_hold():
    scene = mvr_scene(
        mvr_fixture("Known", "1", IDENTITY + "{0,0,0}", spec=f"{import_samples.MAKER}@Demo Spot 16ch.gdtf"),
        mvr_fixture("Stranger", "101", IDENTITY + "{1000,0,0}", spec="Nonesuch@Blinder 9000.gdtf"),
    )
    archive = mvr_archive(scene, (f"{import_samples.MAKER}@Demo Spot 16ch.gdtf", import_samples.gdtf_bytes()))
    assert detect_format("rig.mvr", archive) == "mvr"

    parsed = read_venue_file("rig.mvr", archive)
    assert len(parsed.profiles) == 1
    preview = build_preview(parsed, [])
    rows = rows_by_name(preview)

    assert rows["Known"]["profile"]["status"] == "embedded"
    assert rows["Known"]["channel_count"] == 16 and rows["Known"]["active"] is True

    stranger = rows["Stranger"]
    assert stranger["profile"]["status"] == "unmatched"
    assert stranger["active"] is False and stranger["channel_count_known"] is False
    assert any("not in the file" in issue for issue in stranger["issues"])
    assert [u["type_name"] for u in preview["unmatched_types"]] == [UNKNOWN_TYPE]
    assert preview["unmatched_types"][0]["names"] == ["Stranger"]


def test_mvr_sample_reads_whole():
    parsed = read_venue_file("liv_approx_subset.mvr", sample("liv_approx_subset.mvr"))
    assert parsed.format == "mvr"
    assert len(parsed.fixtures) == 36 and len(parsed.profiles) == 3
    assert all(f.position_source == "mvr" for f in parsed.fixtures)
    first = by_name(parsed)["Design Spot A1"]
    assert (first.universe, first.dmx_address) == (0, 1)
    assert first.position == (-6.0, 6.5, -7.5)
    assert first.position_label == "Chord A"
    assert parsed.positions and parsed.positions[0]["kind"] == "truss"

    preview = build_preview(parsed, [])
    assert preview["summary"]["address_clashes"] == 0
    assert preview["summary"]["unmatched_fixtures"] == 2


def test_not_a_zip_named_mvr_is_refused():
    with pytest.raises(VenueImportError):
        read_venue_file("rig.mvr", b"this is not an archive")
    with pytest.raises(VenueImportError):
        read_venue_file("rig.mvr", b"")


# ---------------------------------------------------------------------------
# grandMA2
# ---------------------------------------------------------------------------

MA_NAMESPACE = "http://schemas.malighting.de/grandma2/xml/MA"


def ma2_fixture(name: str, patch: str = "", position: str = "", type_name: str = "2 Acme Zed 300", fid: str = "1") -> str:
    return (
        f'<Fixture name="{name}" fixture_id="{fid}" channel_id="{fid}">'
        f'<FixtureType name="{type_name}"><No>2</No></FixtureType>'
        f'<SubFixture index="0">{patch}{position}</SubFixture></Fixture>'
    )


def ma2_export(*fixtures: str, layer: str = "Movers") -> bytes:
    return (
        f'<?xml version="1.0" encoding="utf-8"?><MA xmlns="{MA_NAMESPACE}">'
        f'<Layers><Layer name="{layer}">' + "".join(fixtures) + "</Layer></Layers></MA>"
    ).encode()


def ma2_position(location: str, rotation: str = "") -> str:
    return (
        f"<AbsolutePosition><Location {location}/>"
        + (f"<Rotation {rotation}/>" if rotation else "")
        + "</AbsolutePosition>"
    )


@pytest.mark.parametrize("patch, expected", [
    ("<Patch><Address>1</Address></Patch>", (0, 1)),
    ("<Patch><Address>512</Address></Patch>", (0, 512)),
    ("<Patch><Address>513</Address></Patch>", (1, 1)),
    ("<Patch><Address>613</Address></Patch>", (1, 101)),
    ("<Patch><Address>2.101</Address></Patch>", (1, 101)),
    ("<Patch><Address>2/101</Address></Patch>", (1, 101)),
    ('<Patch Universe="2" Address="101"/>', (1, 101)),
    ('<Patch Address="101"/>', (0, 101)),
    ('<Patch Address="1125"/>', (2, 101)),   # no universe beside it: absolute, not clamped to 512
])
def test_ma2_address_forms(patch, expected):
    data = parse_grandma_export(ma2_export(ma2_fixture("A", patch)))
    fixture = data["fixtures"][0]
    assert fixture["patched"] is True
    assert (fixture["universe"], fixture["dmx_address"]) == expected


def test_ma2_positions_are_metres_turned_into_stage_axes():
    parsed = read_venue_file("patch.xml", ma2_export(ma2_fixture(
        "A", "<Patch><Address>613</Address></Patch>",
        ma2_position('x="1" y="2" z="3"', 'x="0" y="0" z="90"'),
    )))
    assert parsed.format == "ma2"
    fixture = parsed.fixtures[0]
    assert fixture.position == (1.0, 3.0, -2.0)      # metres already: not divided by 1000
    assert fixture.rotation == (0.0, 90.0, 0.0)      # the same heading an MVR quarter turn gives
    assert fixture.position_source == "ma2"
    assert (fixture.universe, fixture.dmx_address) == (1, 101)
    assert fixture.type_name == "Acme Zed 300"       # the console's type number is not the name
    assert fixture.group_name == "Movers" and fixture.layer == "Movers"
    assert fixture.fixture_number == 1


def test_ma2_and_mvr_agree_on_a_heading():
    assert stage_axes.z_up_euler_to_stage(0, 0, 90) == stage_axes.stage_rotation_degrees(
        stage_axes.z_up_rotation_to_stage(parse_matrix(QUARTER_TURN + "{0,0,0}")[0])
    )


def test_ma2_turn_about_two_axes_is_carried_over_with_a_warning():
    parsed = read_venue_file("patch.xml", ma2_export(ma2_fixture(
        "Tilted", "<Patch><Address>1</Address></Patch>",
        ma2_position('x="0" y="0" z="5"', 'x="30" y="0" z="90"'),
    )))
    assert parsed.fixtures[0].rotation == (30.0, 90.0, 0.0)
    assert any("Tilted" in w and "more than one axis" in w for w in parsed.warnings)


def test_ma2_fixture_without_a_position_or_a_patch():
    parsed = read_venue_file("patch.xml", ma2_export(
        ma2_fixture("Placed", "<Patch><Address>1</Address></Patch>", ma2_position('x="1" y="0" z="5"')),
        ma2_fixture("Loose", "<Patch><Address>17</Address></Patch>", fid="2"),
        ma2_fixture("Spare", "", fid="3"),
    ))
    fixtures = by_name(parsed)
    assert fixtures["Placed"].position == (1.0, 5.0, 0.0)
    assert fixtures["Loose"].position is None and fixtures["Loose"].position_source == "none"
    assert fixtures["Loose"].rotation is None
    assert fixtures["Spare"].universe is None and fixtures["Spare"].dmx_address is None

    preview = build_preview(parsed, [])
    rows = rows_by_name(preview)
    assert rows["Loose"]["unplaced"] is True and rows["Loose"]["importable"] is True
    assert rows["Spare"]["importable"] is False
    assert preview["not_importable"] == [{"index": 2, "name": "Spare", "reason": "no DMX address"}]
    assert preview["summary"]["position_sources"] == {"ma2": 1, "none": 2}


def test_ma2_unknown_type_is_listed_and_switched_off():
    parsed = read_venue_file("patch.xml", ma2_export(
        ma2_fixture("Known", "<Patch><Address>1</Address></Patch>"),
        ma2_fixture("Stranger", "<Patch><Address>101</Address></Patch>", type_name=UNKNOWN_TYPE, fid="2"),
    ))
    preview = build_preview(parsed, LIBRARY)
    rows = rows_by_name(preview)
    assert rows["Known"]["profile"]["status"] == "library"
    assert rows["Known"]["channel_count"] == 16 and rows["Known"]["active"] is True
    assert rows["Stranger"]["profile"]["status"] == "unmatched"
    assert rows["Stranger"]["active"] is False
    assert [u["type_name"] for u in preview["unmatched_types"]] == [UNKNOWN_TYPE]
    assert preview["summary"]["unmatched_fixtures"] == 1


def test_ma2_sample_reads_whole():
    parsed = read_venue_file("liv_approx_subset_ma2.xml", sample("liv_approx_subset_ma2.xml"))
    assert parsed.format == "ma2" and len(parsed.fixtures) == 20
    assert all(f.position_source == "ma2" for f in parsed.fixtures)
    last = by_name(parsed)["Atomic Strobe 8"]
    assert (last.universe, last.dmx_address) == (1, 509)
    assert last.position == (8.0, 6.5, 7.5)


def test_xml_with_no_fixtures_or_with_entities_is_refused():
    with pytest.raises(VenueImportError):
        read_venue_file("patch.xml", b"<MA><Layers/></MA>")
    with pytest.raises(VenueImportError):
        read_venue_file(
            "patch.xml",
            b'<!DOCTYPE x [<!ENTITY a "aaaa">]><MA><Fixture name="&a;"/></MA>',
        )


# ---------------------------------------------------------------------------
# GDTF
# ---------------------------------------------------------------------------

def test_gdtf_sample_is_a_profile_and_patches_nothing():
    content = sample("ils_demo_spot_16ch.gdtf")
    assert detect_format("ils_demo_spot_16ch.gdtf", content) == "gdtf"
    parsed = read_venue_file("ils_demo_spot_16ch.gdtf", content)
    assert parsed.format == "gdtf" and parsed.fixtures == []
    profile = parsed.profiles[0]
    assert (profile["manufacturer"], profile["model"]) == ("ILS Demo", "Demo Spot 16ch")
    assert 16 in [mode["channel_count"] for mode in profile["modes"]]

    preview = build_preview(parsed, [])
    assert preview["summary"]["fixtures"] == 0
    assert preview["summary"]["profiles_in_file"] == 1
    assert preview["profiles"][0]["model"] == "Demo Spot 16ch"


def test_spreadsheets_are_named_as_unsupported():
    with pytest.raises(VenueImportError):
        detect_format("patch.xlsx", b"anything")


# ---------------------------------------------------------------------------
# The plan: unknown types, clashes, the origin
# ---------------------------------------------------------------------------

def patched(name, universe, address, channels=None, type_name=UNKNOWN_TYPE, position=(1.0, 2.0, 3.0)) -> ImportedFixture:
    return ImportedFixture(
        name=name, type_name=type_name, channel_count=channels,
        universe=universe, dmx_address=address,
        position=position, position_source="csv" if position is not None else "none",
    )


def test_unknown_type_is_reported_once_with_the_fixtures_that_use_it():
    parsed = ParsedVenue(format="csv", fixtures=[
        patched("A", 0, 1, 16, type_name="Acme Zed 300"),
        patched("B", 0, 101, 8),
        patched("C", 0, 201, 8),
        patched("D", 0, 301, None, type_name=""),
    ])
    preview = build_preview(parsed, LIBRARY)
    rows = rows_by_name(preview)

    assert rows["A"]["profile"]["status"] == "library" and rows["A"]["active"] is True
    unmatched = {u["type_name"]: u for u in preview["unmatched_types"]}
    assert unmatched[UNKNOWN_TYPE]["fixtures"] == 2
    assert unmatched[UNKNOWN_TYPE]["names"] == ["B", "C"]
    assert unmatched[UNKNOWN_TYPE]["channel_counts"] == [8]
    assert len(unmatched) == 2          # the fixture with no type at all is its own line
    for name in ("B", "C", "D"):
        assert rows[name]["profile"]["status"] == "unmatched"
        assert rows[name]["importable"] is True and rows[name]["active"] is False
    assert preview["summary"]["switched_off"] == 3
    assert rows["D"]["channel_count_known"] is False


def test_address_clashes():
    parsed = ParsedVenue(format="csv", fixtures=[
        patched("First", 0, 1, 16),
        patched("Same", 0, 1, 16),
        patched("Overlap", 0, 10, 8),
        patched("Next", 0, 33, 4),
        patched("Adjacent", 0, 37, 4),
        patched("Unknown", 0, 36, None),
        patched("Elsewhere", 1, 1, 16),
        patched("Past", 0, 510, 8),
    ])
    plans, clashes, _ = plan_import(parsed, [])
    by = {p.name: p for p in plans}

    pairs = {(c["first"]["name"], c["second"]["name"]): c for c in clashes}
    assert set(pairs) == {
        ("First", "Same"), ("First", "Overlap"), ("Same", "Overlap"), ("Next", "Unknown"),
    }
    assert pairs[("First", "Same")]["kind"] == "same_address"
    assert pairs[("First", "Same")]["channels"] == [1, 16]
    assert pairs[("First", "Overlap")]["kind"] == "overlap"
    assert pairs[("First", "Overlap")]["channels"] == [10, 16]
    assert pairs[("Next", "Unknown")]["channels"] == [36, 36]
    assert pairs[("Next", "Unknown")]["footprints_known"] is False
    assert all(c["universe"] == 0 for c in clashes)

    # The later of each pair is the one marked; the first keeps its channels.
    assert {name for name, plan in by.items() if plan.clashes} == {"Same", "Overlap", "Unknown"}
    # Touching is not sharing, and another universe is another cable.
    assert not by["Adjacent"].clashes and not by["Elsewhere"].clashes

    assert by["Past"].importable is False and "run past channel 512" in by["Past"].refusal

    preview = build_preview(parsed, [])
    assert preview["summary"]["address_clashes"] == 4
    assert preview["summary"]["not_importable"] == 1


def test_clash_switches_off_a_fixture_whose_profile_matched():
    parsed = ParsedVenue(format="csv", fixtures=[
        patched("A", 0, 1, type_name="Acme Zed 300"),
        patched("B", 0, 9, type_name="Acme Zed 300"),
        patched("C", 0, 17, type_name="Acme Zed 300"),
    ])
    preview = build_preview(parsed, LIBRARY)
    rows = rows_by_name(preview)
    assert [rows[n]["active"] for n in ("A", "B", "C")] == [True, False, False]
    assert preview["summary"]["address_clashes"] == 2
    assert preview["unmatched_types"] == []


def test_out_of_range_patch_is_not_importable():
    parsed = ParsedVenue(format="csv", fixtures=[
        patched("NoAddress", None, None, 4),
        patched("TooHigh", 0, 600, 4),
        patched("FarUniverse", 99, 1, 4),
    ])
    plans, _, _ = plan_import(parsed, [])
    assert [p.importable for p in plans] == [False, False, False]
    assert plans[0].refusal == "no DMX address"
    assert "outside 1-512" in plans[1].refusal
    assert "universe 99" in plans[2].refusal


def test_several_fixtures_exactly_on_the_origin_are_left_unplaced():
    parsed = ParsedVenue(format="mvr", fixtures=[
        patched("A", 0, 1, 4, position=(0.0, 0.0, 0.0)),
        patched("B", 0, 5, 4, position=(0.0, 0.0, 0.0)),
        patched("C", 0, 9, 4, position=(1.0, 0.0, 0.0)),
    ])
    plans, _, warnings = plan_import(parsed, [])
    assert [p.position for p in plans] == [None, None, (1.0, 0.0, 0.0)]
    assert [p.position_source for p in plans] == ["none", "none", "csv"]
    assert any("origin" in w for w in warnings)

    # One fixture at the centre of the floor is a fixture at the centre of the floor.
    alone = ParsedVenue(format="mvr", fixtures=[patched("A", 0, 1, 4, position=(0.0, 0.0, 0.0))])
    assert plan_import(alone, [])[0][0].position == (0.0, 0.0, 0.0)


def test_repeated_fixture_ids_are_warned_about():
    first, second = patched("A", 0, 1, 4), patched("B", 0, 5, 4)
    first.fixture_id = second.fixture_id = "101"
    _, _, warnings = plan_import(ParsedVenue(format="csv", fixtures=[first, second]), [])
    assert any("101" in w for w in warnings)
