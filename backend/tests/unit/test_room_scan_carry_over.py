"""
A real `carry_over` entry put back onto the room it was made against (docs/ROOM_SCAN.md, slice 36)
=================================================================================================

Each entry keep_edits.py gives, for a raised area, a line and a ring, read
beside, at another height or lost to another stored item, is fed as it is to
carry_over.py with the room the scan left. None is stale (the name the answer
gives the new item is the name carry_over reads), the markers are on, and the
same reading applied again keeps what was carried and has nothing to carry.
"""

import pytest

from app.services.room_scan.carry_over import carry_over
from app.services.room_scan.edit import (
    BASE_BY_HAND, HEIGHT_BY_HAND, NAME_BY_HAND, RESIZED_BY_HAND, ShellEditError, edit_item,
)
from app.services.room_scan.keep_edits import LOST_BESIDE, LOST_HEIGHT, LOST_OTHER, keep_hand_edits
from tests.unit.test_room_scan_edit import shell
from tests.unit.test_room_scan_keep_edits import stored
from tests.unit.test_room_scan_keep_lost import two_named
from tests.unit.test_room_scan_keep_mark import area
from tests.unit.test_room_scan_keep_named import AREAS
from tests.unit.test_room_scan_keep_overhead import LINES, RINGS, moved


def round_trip(old, new):
    """(the entry, the room with it carried over, the item, what was done, the same reading applied again)."""
    got = keep_hand_edits(old, new)
    [entry] = got.report(applied=True)["carry_over"]
    carried, item, done = carry_over(got.shell, entry)
    return entry, carried, item, done, keep_hand_edits(carried, new)


class TestEachKindRoundTrips:

    def test_a_raised_area_read_beside_gets_its_name_height_and_base_height_back(self):
        old = edit_item(shell(), AREAS, 1, name="The bar", height=1.2, base_height=0.5)[0]
        entry, carried, item, done, again = round_trip(old, moved(shell(), AREAS, 1, center_x=5.0))
        assert entry["reason"] == LOST_BESIDE and entry["edits"] == ["name", "height", "base_height"]
        assert (item["name"], item["height"], item["base_height"]) == ("The bar", 1.2, 0.5)
        for mark in (NAME_BY_HAND, HEIGHT_BY_HAND, BASE_BY_HAND, RESIZED_BY_HAND):
            assert mark in item["basis"]
        assert item["suggested"] is False and carried[AREAS][1] == item
        assert done == f"{entry['new_name']} given the name, height and base height of The bar"
        kept = again.shell[AREAS][1]
        assert (kept["name"], kept["height"], kept["base_height"]) == ("The bar", 1.2, 0.5)
        assert "carry_over" not in again.report()

    def test_a_ring_trim_alone_keeps_the_scans_name_unmarked(self):
        old = edit_item(shell(), RINGS, 0, height=3.4)[0]
        entry, _, item, done, again = round_trip(old, moved(shell(), RINGS, 0, center_x=4.5))
        assert entry["edits"] == ["height"] and item["name"] == entry["new_name"]
        assert item["height"] == 3.4 and HEIGHT_BY_HAND in item["basis"] and NAME_BY_HAND not in item["basis"]
        assert done.endswith("given the trim of Overhead ring 1")
        assert again.shell[RINGS][0]["height"] == 3.4 and "carry_over" not in again.report()

    def test_a_line_read_at_another_height_keeps_the_reading_as_its_scan_height(self):
        old = edit_item(shell(), LINES, 0, name="Front truss", height=3.0)[0]
        new = moved(shell(), LINES, 0, height=5.3, top=5.6)
        entry, _, item, _, again = round_trip(old, new)
        assert entry["reason"] == LOST_HEIGHT
        assert (item["name"], item["height"], item["scan_height"]) == ("Front truss", 3.0, 5.3)
        assert again.shell[LINES][0]["name"] == "Front truss" and "carry_over" not in again.report()


class TestTheOneLostToAnother:

    def test_carried_over_it_takes_the_place_of_the_raised_area_that_had_it(self):
        near, nearer = two_named()
        new = stored(area("riser", -3.8, 0.0, 2.0, 1.0))
        entry, _, item, done, again = round_trip(stored(near, nearer), new)
        assert (entry["reason"], entry["new_name"]) == (LOST_OTHER, "Nearer")
        # The operator chose it: the one that had the new area gives it up.
        assert item["name"] == "Near" and done == "Nearer given the name of Near"
        assert again.shell[AREAS][0]["name"] == "Near" and not again.lost

    def test_carried_over_a_truss_takes_the_name_and_trim_of_the_other(self):
        both = shell()
        both[LINES][2].update({"z1": -2.0, "z2": -2.0, "height": 4.6, "top": 4.9})
        old = edit_item(edit_item(both, LINES, 0, name="Lower")[0], LINES, 2, name="Upper", height=4.8)[0]
        new = {**shell(), LINES: shell()[LINES][:2]}
        entry, _, item, _, again = round_trip(old, new)
        assert entry["new_name"] == "Lower"
        assert (item["name"], item["height"]) == ("Upper", 4.8)
        assert (again.shell[LINES][0]["name"], again.shell[LINES][0]["height"]) == ("Upper", 4.8)


class TestWhatIsRefused:

    def test_an_entry_already_carried_is_stale_and_the_room_given_is_not_changed(self):
        old = edit_item(shell(), LINES, 0, name="Front truss", height=3.0)[0]
        got = keep_hand_edits(old, moved(shell(), LINES, 0, height=5.3, top=5.6))
        [entry] = got.report(applied=True)["carry_over"]
        before = repr(got.shell)
        carried, _, _ = carry_over(got.shell, entry)
        assert repr(got.shell) == before
        with pytest.raises(ShellEditError) as e:
            carry_over(carried, entry)
        assert e.value.status == 409

    def test_no_room_is_a_404(self):
        with pytest.raises(ShellEditError) as e:
            carry_over(None, {"kind": LINES})
        assert e.value.status == 404
