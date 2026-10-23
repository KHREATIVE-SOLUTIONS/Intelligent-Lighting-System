"""
Offline fixture library, mode choice and address planning
=========================================================

The venue patches at load-in, usually before the house network is up. These
tests hold the parts that make that work with no internet: the bundled OFL
snapshot finds club fixtures by the words a tech would type, every definition in
it converts, the mode we patch is the one a programmer would pick, and the
addresses we hand out never overlap or straddle a universe.
"""

import gzip
import json

import pytest

from app.services.fixture_library.ofl_snapshot import OFLSnapshot, get_snapshot
from app.services.rig.fixture_choice import mode_features, recommend_mode
from app.services.rig.patching_service import PatchPlanError, plan_addresses


@pytest.fixture(scope="module")
def snapshot():
    snap = get_snapshot()
    if not snap.available:
        pytest.fail("data/fixtures/ofl/ofl_snapshot.json.gz is missing - run scripts/update_ofl_snapshot.py")
    return snap


def test_the_whole_snapshot_converts(snapshot):
    entries = snapshot.entries()
    assert len(entries) == snapshot.info()["fixture_count"]
    assert len(entries) > 500
    assert all(e["modes"] for e in entries if e["fixture_type"] != "other")


@pytest.mark.parametrize("query, manufacturer, name", [
    ("intimidator 260", "Chauvet DJ", "Intimidator Spot 260"),
    ("rogue r2 wash", "Chauvet Professional", "Rogue R2 Wash"),
    ("sharpy", "Clay Paky", "Sharpy"),
    ("adj mega hex", "American DJ", "Mega Hex Par"),
])
def test_search_finds_club_fixtures_by_what_a_tech_types(snapshot, query, manufacturer, name):
    top = snapshot.search(query, limit=3)[0]
    assert (top["manufacturer"], top["name"]) == (manufacturer, name)


def test_search_filters_by_type_and_rejects_nonsense(snapshot):
    movers = snapshot.search("chauvet", fixture_type="moving_head", limit=50)
    assert movers and all(e["fixture_type"] == "moving_head" for e in movers)
    assert snapshot.search("zzqx nothing like this") == []


def test_manufacturer_names_come_from_ofl_not_the_key(snapshot):
    converted = snapshot.convert("chauvet-dj", "intimidator-spot-260")
    assert converted["manufacturer"] == "Chauvet DJ"
    assert converted["source_id"] == "chauvet-dj/intimidator-spot-260"


def test_redirects_resolve_to_the_renamed_fixture(tmp_path):
    path = tmp_path / "snap.json.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump({
            "manufacturers": {"acme": {"name": "ACME"}},
            "redirects": {"acme/old-par": "acme/new-par"},
            "fixtures": {"acme/new-par": {
                "name": "New Par", "categories": ["Color Changer"],
                "availableChannels": {"Dimmer": {"capability": {"type": "Intensity"}}},
                "modes": [{"name": "1ch", "channels": ["Dimmer"]}],
            }},
        }, fh)
    snap = OFLSnapshot(path)
    assert snap.resolve_key("acme", "old-par") == "acme/new-par"
    assert snap.convert("acme", "old-par")["model"] == "New Par"


def test_a_missing_snapshot_is_empty_not_fatal(tmp_path):
    snap = OFLSnapshot(tmp_path / "absent.json.gz")
    assert not snap.available
    assert snap.search("anything") == []
    assert snap.get("a", "b") is None


def _mode(name, *types):
    return {"name": name, "channel_count": len(types),
            "channels": [{"channel_type": t} for t in types]}


def test_movers_get_the_fine_pan_tilt_mode():
    basic = _mode("8ch", "pan", "tilt", "color_wheel", "gobo", "dimmer", "shutter", "speed", "macro")
    extended = _mode("12ch", "pan", "pan_fine", "tilt", "tilt_fine", "color_wheel", "gobo",
                     "dimmer", "shutter", "speed", "macro", "other", "other")
    assert recommend_mode([basic, extended]) is extended


def test_pixel_bars_get_the_compact_mode():
    compact = _mode("5ch", "dimmer", "red", "green", "blue", "strobe")
    pixel = _mode("26ch", "dimmer", "strobe", *(["red", "green", "blue"] * 8))
    assert recommend_mode([pixel, compact]) is compact


def test_colour_macros_do_not_win_over_mixing_on_an_led_par():
    eight = _mode("8ch", "red", "green", "blue", "white", "amber", "uv", "dimmer", "strobe")
    eleven = _mode("11ch", "red", "green", "blue", "white", "amber", "uv", "dimmer", "strobe",
                   "color_wheel", "macro", "speed")
    assert recommend_mode([eleven, eight]) is eight


def test_a_mode_that_cannot_make_light_is_a_last_resort():
    macro_only = _mode("2ch", "macro", "speed")
    usable = _mode("4ch", "dimmer", "red", "green", "blue")
    assert recommend_mode([macro_only, usable]) is usable
    assert recommend_mode([macro_only]) is macro_only
    assert mode_features(usable) == ["dimmer", "red", "green", "blue"]


def test_addresses_pack_into_gaps_without_overlap():
    occupied = {0: [(1, 16), (33, 40)]}
    assert plan_addresses(occupied, 16, 3) == [(0, 17), (0, 41), (0, 57)]


def test_a_full_universe_spills_into_the_next():
    occupied = {0: [(1, 500)]}
    assert plan_addresses(occupied, 16, 2) == [(1, 1), (1, 17)]


def test_never_straddles_a_universe_boundary():
    plan = plan_addresses({}, 100, 6)
    assert plan[:5] == [(0, 1), (0, 101), (0, 201), (0, 301), (0, 401)]
    assert plan[5] == (1, 1)


def test_a_start_address_is_honoured_or_refused():
    assert plan_addresses({0: [(1, 8)]}, 8, 2, start_address=9) == [(0, 9), (0, 17)]
    with pytest.raises(PatchPlanError, match="overlaps"):
        plan_addresses({0: [(20, 30)]}, 8, 2, start_address=9)
    with pytest.raises(PatchPlanError, match="past the end"):
        plan_addresses({}, 16, 2, start_address=500)
