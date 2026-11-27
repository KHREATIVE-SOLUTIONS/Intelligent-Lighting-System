"""
A scan applied again says every loss, and which new item each points at (keep_edits.py, slice 36)
=================================================================================================

What has to hold. Three things that went without a word are said in
`hand_edits.warnings`, and listed in `items` with the outcome "lost": a raised
area with a name, a height or a base height set by hand that the scan reads
to one side (sharing some floor, less than the half a match needs), named
with the new area; a line or ring with a name or a trim set by hand that the
scan no longer reads at all; and, of two stored items that pick the same new
one, the one that does not have it, named with the one that does. Every
warning with an item of the new room behind it (those, and slice 35's two) is
also in `carry_over`, in the form POST .../room-scan/carry-over takes: the
list, the old name, the old trim or height, the place and name of the new
item, and why. Nothing is written for any of it. docs/ROOM_SCAN.md.
"""

import copy

import pytest

from app.services.room_scan.edit import NAME_BY_HAND, add_item, delete_item, edit_item
from app.services.room_scan.keep_edits import (
    KEPT, LOST, LOST_BESIDE, LOST_GONE, LOST_HEIGHT, LOST_OTHER, LOST_RECORD, keep_hand_edits,
)
from tests.unit.test_room_scan_edit import shell
from tests.unit.test_room_scan_keep_edits import RISER, SCAN, stored
from tests.unit.test_room_scan_keep_mark import area
from tests.unit.test_room_scan_keep_named import AREAS, BARE, one
from tests.unit.test_room_scan_keep_overhead import HALO, LINES, PIPE, RINGS, moved


class TestARaisedAreaReadToOneSide:

    def test_a_name_and_a_height_lost_to_it_are_said_with_the_new_area(self):
        old = edit_item(shell(), AREAS, 1, name="The bar", height=1.2)[0]
        # The booth is 2 m wide: read 1 m along, it shares a third of the two footprints.
        new = moved(shell(), AREAS, 1, center_x=5.0)

        got = keep_hand_edits(old, new)

        # Nothing is written: the room is the reading, the same object.
        assert got.shell is new and got.kept == [] and got.warnings == []
        fact = {
            "kind": AREAS, "name": "The bar", "edits": ["name", "height"], "reason": LOST_BESIDE,
            "offset": 1.0, "overlap": 0.333, "by_index": 1,
        }
        assert got.lost == [fact]
        before, after = got.report(), got.report(applied=True)
        assert after["warnings"] == [{**fact, "by": "Booth or counter", "message": (
            "The scan read Booth or counter 1 m from where The bar was, sharing 33% of the plan with it "
            "where half is needed, so its name and height were not kept."
        ), "id": "lost-0"}]
        assert before["warnings"][0]["message"].endswith("so its name and height will not be kept.")
        assert after["message"] == after["warnings"][0]["message"]
        assert after["items"] == before["items"] == [one("raised area", "The bar", LOST)]
        assert set(after) == BARE | {"warnings", "items", "carry_over"}
        assert (after["areas"], after["kept"], after["added_kept"], after["added_replaced"]) == (0, [], [], [])

    def test_a_base_height_alone_is_said_as_that(self):
        old = edit_item(shell(), AREAS, 1, base_height=0.5)[0]
        got = keep_hand_edits(old, moved(shell(), AREAS, 1, center_x=5.0))
        assert got.lost[0]["edits"] == ["base_height"] and got.lost[0]["name"] == "Booth or counter"
        assert got.report(applied=True)["message"].endswith("so its base height was not kept.")
        assert got.report(applied=True)["carry_over"] == [{
            "kind": AREAS, "old_name": "Booth or counter", "old_trim_or_height": None, "old_base_height": 0.5,
            "edits": ["base_height"], "new_index": 1, "new_name": "Booth or counter", "reason": LOST_BESIDE,
            "warning": 0, "warning_id": "lost-0",
        }]

    def test_all_three_are_said_in_order(self):
        old = edit_item(shell(), AREAS, 1, name="The bar", height=1.2, base_height=0.5)[0]
        got = keep_hand_edits(old, moved(shell(), AREAS, 1, center_x=5.0))
        assert got.report()["message"].endswith("so its name, height and base height will not be kept.")

    def test_what_kind_the_new_area_is_read_as_is_not_looked_at(self):
        old = edit_item(shell(), AREAS, 1, name="The bar")[0]
        got = keep_hand_edits(old, moved(shell(), AREAS, 1, center_x=5.0, kind="riser", name="Riser"))
        assert [(entry["reason"], entry["by_index"]) for entry in got.lost] == [(LOST_BESIDE, 1)]
        assert got.report()["warnings"][0]["message"].startswith("The scan read Riser 1 m from where The bar was")

    def test_one_read_a_little_off_is_kept_and_says_nothing(self):
        old = edit_item(shell(), AREAS, 1, name="The bar")[0]
        got = keep_hand_edits(old, moved(shell(), AREAS, 1, center_x=4.3))
        assert got.lost == [] and got.shell[AREAS][1]["name"] == "The bar"

    def test_one_no_longer_read_or_read_as_another_kind_where_it_stood_still_says_nothing(self):
        # Slice 36 leaves these two: there is no warning for them.
        old = edit_item(shell(), AREAS, 1, name="The bar")[0]
        assert not keep_hand_edits(old, {**shell(), AREAS: shell()[AREAS][:1]}).any
        assert not keep_hand_edits(old, moved(shell(), AREAS, 1, kind="riser", name="Riser")).any
        # Clear of where it was: no floor is shared.
        assert not keep_hand_edits(old, moved(shell(), AREAS, 1, center_x=0.0, center_z=3.0)).any

    def test_a_new_area_that_another_stored_one_is_is_itself_and_not_this_one_read_beside(self):
        along = {**shell()[AREAS][1], "center_x": 5.0, "name": "Counter"}
        both = shell()
        both[AREAS].append(along)
        old = edit_item(both, AREAS, 1, name="The bar")[0]
        new = {**shell(), AREAS: [shell()[AREAS][0], copy.deepcopy(along)]}
        got = keep_hand_edits(old, new)
        assert got.shell is new and not got.any

    def test_of_several_the_one_that_shares_the_most_is_pointed_at(self):
        old = edit_item(shell(), AREAS, 1, name="The bar")[0]
        new = moved(shell(), AREAS, 1, center_x=5.4)
        new[AREAS].append({**shell()[AREAS][1], "center_x": 3.2, "name": "Counter"})
        got = keep_hand_edits(old, new)
        assert [(entry["by_index"], entry["offset"]) for entry in got.lost] == [(2, 0.8)]

    def test_one_added_by_hand_is_spoken_of_as_replaced_and_never_here(self):
        old = add_item(shell(), AREAS, name="Bar top", center_x=4.9, center_z=3.0, width=1.0, depth=1.0, height=1.2)[0]
        got = keep_hand_edits(old, shell())
        assert got.lost == [] and [entry["name"] for entry in got.added_replaced] == ["Bar top"]


class TestALineOrRingTheScanNoLongerReads:

    def test_a_named_and_trimmed_truss_is_said_to_go_with_its_name_and_trim(self):
        old = edit_item(shell(), LINES, 0, name="Front truss", height=3.0)[0]
        new = {**shell(), LINES: shell()[LINES][1:]}

        got = keep_hand_edits(old, new)

        assert got.shell is new and got.overhead_kept == [] and got.carry == []
        fact = {"kind": LINES, "name": "Front truss", "edits": ["name", "height"], "reason": LOST_GONE}
        assert got.lost == [fact]
        before, after = got.report(), got.report(applied=True)
        assert before["warnings"] == [{**fact, "message": (
            "The scan no longer reads Front truss; its name and trim go with it."
        )}]
        assert after["warnings"] == [{**fact, "message": (
            "The scan no longer reads Front truss; its name and trim went with it."
        )}]
        assert after["message"] == after["warnings"][0]["message"]
        assert after["items"] == before["items"] == [one("line", "Front truss", LOST)]
        # There is no item of the new room to put them onto.
        assert set(after) == BARE | {"warnings", "items"}

    def test_a_name_alone_a_trim_alone_and_a_ring(self):
        named = keep_hand_edits(edit_item(shell(), LINES, 0, name="Front truss")[0], {**shell(), LINES: []})
        assert named.report(applied=True)["message"] == "The scan no longer reads Front truss; its name went with it."
        hung = keep_hand_edits(edit_item(shell(), LINES, 0, height=3.0)[0], {**shell(), LINES: []})
        # One thing goes; two go (the test above).
        assert hung.report()["message"] == "The scan no longer reads Overhead line 1; its trim goes with it."
        ring = keep_hand_edits(edit_item(shell(), RINGS, 0, name="Mirror ball ring")[0], {**shell(), RINGS: []})
        assert ring.lost == [{"kind": RINGS, "name": "Mirror ball ring", "edits": ["name"], "reason": LOST_GONE}]
        assert ring.report()["items"] == [one("ring", "Mirror ball ring", LOST)]

    def test_a_reading_with_no_list_of_rings_has_none(self):
        new = shell()
        del new[RINGS]
        got = keep_hand_edits(edit_item(shell(), RINGS, 0, name="Mirror ball ring")[0], new)
        assert [entry["reason"] for entry in got.lost] == [LOST_GONE] and got.shell is new

    def test_one_read_at_another_height_or_beside_is_said_as_that_and_not_as_gone(self):
        old = edit_item(shell(), LINES, 0, name="Front truss")[0]
        assert [e["reason"] for e in keep_hand_edits(old, moved(shell(), LINES, 0, height=5.3, top=5.6)).lost] == [LOST_HEIGHT]
        assert [e["reason"] for e in keep_hand_edits(old, moved(shell(), LINES, 0, z1=-1.7, z2=-1.7)).lost] == [LOST_BESIDE]
        # And slice 35's two are warnings only, as they were: not in the list.
        assert "items" not in keep_hand_edits(old, moved(shell(), LINES, 0, height=5.3, top=5.6)).report()

    def test_one_nobody_edited_and_one_added_by_hand_are_not_lost(self):
        assert not keep_hand_edits(shell(), {**shell(), LINES: shell()[LINES][1:]}).any
        got = keep_hand_edits(add_item(shell(), LINES, **PIPE)[0], {**shell(), LINES: []})
        assert got.lost == [] and [entry["index"] for entry in got.overhead_added_kept] == [0]

    def test_it_is_said_once(self):
        old = edit_item(shell(), LINES, 0, name="Front truss")[0]
        new = {**shell(), LINES: shell()[LINES][1:]}
        assert not keep_hand_edits(keep_hand_edits(old, new).shell, new).any


def two_named(first="Near", second="Nearer"):
    near = {**RISER, "name": first, "basis": f"{SCAN} {NAME_BY_HAND}"}
    nearer = {**area("riser", -3.9, 0.0, 2.0, 1.0), "name": second, "basis": f"{SCAN} {NAME_BY_HAND}"}
    return near, nearer


class TestOfTwoStoredItemsThatPickTheSameNewOne:

    def test_the_raised_area_that_does_not_have_it_is_named_with_the_one_that_does(self):
        near, nearer = two_named()
        new = stored(area("riser", -3.8, 0.0, 2.0, 1.0))
        for old in (stored(near, nearer), stored(nearer, near)):
            got = keep_hand_edits(old, new)

            assert got.shell[AREAS][0]["name"] == "Nearer"
            fact = {
                "kind": AREAS, "name": "Near", "edits": ["name"], "reason": LOST_OTHER,
                "kept": "Nearer", "read": "Riser", "by_index": 0,
            }
            assert got.lost == [fact]
            before, after = got.report(), got.report(applied=True)
            # `by` is what the new area is called in the room as stored: it has the other's name now.
            assert after["warnings"] == [{**fact, "by": "Nearer", "message": (
                "Near and Nearer both stand where the scan reads Riser: Nearer has it, "
                "so the name of Near was not kept."
            ), "id": "lost-0"}]
            assert before["warnings"][0]["message"] == (
                "Near and Nearer both stand where the scan reads Riser: Nearer will have it, "
                "so the name of Near will not be kept."
            )
            assert after["items"] == [one("raised area", "Nearer", KEPT), one("raised area", "Near", LOST)]
            assert after["carry_over"] == [{
                "kind": AREAS, "old_name": "Near", "old_trim_or_height": None, "old_base_height": None,
                "edits": ["name"], "new_index": 0, "new_name": "Nearer", "reason": LOST_OTHER, "warning": 0,
                "warning_id": "lost-0",
            }]

    def test_two_trusses_less_than_a_metre_apart_on_one_footprint(self):
        # Hung 0.4 m apart over the same floor: height does not tell them apart, and the scan now reads one.
        both = shell()
        both[LINES][2].update({"z1": -2.0, "z2": -2.0, "height": 4.6, "top": 4.9})
        old = edit_item(edit_item(both, LINES, 0, name="Lower")[0], LINES, 2, name="Upper", height=4.8)[0]
        new = {**shell(), LINES: shell()[LINES][:2]}

        got = keep_hand_edits(old, new)

        # Equal overlap: the earlier has it.
        assert got.shell[LINES][0]["name"] == "Lower"
        assert got.lost == [{
            "kind": LINES, "name": "Upper", "edits": ["name", "height"], "reason": LOST_OTHER,
            "kept": "Lower", "read": "Overhead line 1", "by_index": 0,
        }]
        said = got.report(applied=True)
        assert said["warnings"][0]["message"] == (
            "Upper and Lower both stand where the scan reads Overhead line 1: Lower has it, "
            "so the name and trim of Upper were not kept."
        )
        assert said["items"] == [one("line", "Lower", KEPT), one("line", "Upper", LOST)]
        assert said["carry_over"] == [{
            "kind": LINES, "old_name": "Upper", "old_trim_or_height": 4.8, "edits": ["name", "height"],
            "new_index": 0, "new_name": "Lower", "reason": LOST_OTHER, "warning": 0, "warning_id": "lost-0",
        }]

    def test_the_one_that_has_it_may_have_nothing_set_by_hand(self):
        near, _ = two_named()
        got = keep_hand_edits(stored(area("riser", -3.9, 0.0, 2.0, 1.0), near), stored(area("riser", -3.8, 0.0, 2.0, 1.0)))
        assert got.kept == [] and got.shell[AREAS][0]["name"] == "Riser"
        assert [(entry["name"], entry["kept"], entry["read"]) for entry in got.lost] == [("Near", "Riser", "Riser")]

    def test_one_with_nothing_set_by_hand_loses_nothing_and_one_added_by_hand_is_replaced(self):
        _, nearer = two_named()
        got = keep_hand_edits(stored(RISER, nearer), stored(area("riser", -3.8, 0.0, 2.0, 1.0)))
        assert got.lost == [] and [entry["index"] for entry in got.kept] == [0]
        old = add_item(shell(), AREAS, name="Bar top", center_x=4.0, center_z=3.0, width=2.0, depth=1.0, height=1.2)[0]
        again = keep_hand_edits(old, shell())
        assert again.lost == [] and [entry["name"] for entry in again.added_replaced] == ["Bar top"]


class TestWhatCanBePutBack:

    def test_a_truss_read_at_another_height_is_pointed_at_with_the_old_name_and_trim(self):
        old = edit_item(shell(), LINES, 0, name="Front truss", height=3.0)[0]
        got = keep_hand_edits(old, moved(shell(), LINES, 0, height=5.3, top=5.6))
        entry = {
            "kind": LINES, "old_name": "Front truss", "old_trim_or_height": 3.0, "edits": ["name", "height"],
            "new_index": 0, "new_name": "Overhead line 1", "reason": LOST_HEIGHT, "warning": 0,
            "warning_id": "lost-0",
        }
        # The same before Apply and after it: it is what a program acts on.
        assert got.report()["carry_over"] == got.report(applied=True)["carry_over"] == [entry]
        # The warning itself is what it was in slice 35: the place is only here.
        assert "new_index" not in got.report()["warnings"][0] and "by_index" not in got.report()["warnings"][0]

    def test_a_name_alone_carries_no_trim_and_a_trim_alone_the_scans_name(self):
        named = keep_hand_edits(edit_item(shell(), LINES, 0, name="Front truss")[0], moved(shell(), LINES, 0, z1=-1.7, z2=-1.7))
        assert [(e["old_name"], e["old_trim_or_height"], e["edits"], e["reason"]) for e in named.report()["carry_over"]] == [
            ("Front truss", None, ["name"], LOST_BESIDE),
        ]
        hung = keep_hand_edits(edit_item(shell(), RINGS, 0, height=3.4)[0], moved(shell(), RINGS, 0, center_x=4.5))
        assert [(e["kind"], e["old_name"], e["old_trim_or_height"], e["edits"]) for e in hung.report()["carry_over"]] == [
            (RINGS, "Overhead ring 1", 3.4, ["height"]),
        ]

    def test_what_has_no_new_item_behind_it_is_not_there(self):
        gone = keep_hand_edits(edit_item(shell(), LINES, 0, name="Front truss")[0], {**shell(), LINES: []})
        assert gone.carry == [] and "carry_over" not in gone.report()
        dropped = keep_hand_edits(delete_item(shell(), AREAS, 1)[0], {**shell(), AREAS: shell()[AREAS][:1]})
        assert [entry["reason"] for entry in dropped.lost] == [LOST_RECORD] and "carry_over" not in dropped.report()
        assert "carry_over" not in keep_hand_edits(edit_item(shell(), LINES, 0, name="Front truss")[0], shell()).report()

    def test_each_says_which_warning_is_its_own_after_the_checks(self):
        old = add_item(edit_item(shell(), LINES, 0, name="Front truss")[0], LINES, **{**PIPE, "center_x": 4.0})[0]
        old = edit_item(old, RINGS, 0, name="Mirror ball ring")[0]
        new = moved(moved(shell(), LINES, 0, height=5.3, top=5.6), RINGS, 0, center_x=4.5)
        new["room"] = {**new["room"], "width": 8.0}

        said = keep_hand_edits(old, new).report(applied=True)

        assert [(entry["name"], "index" in entry) for entry in said["warnings"]] == [
            ("Front pipe", True), ("Front truss", False), ("Mirror ball ring", False),
        ]
        assert [(entry["old_name"], entry["warning"]) for entry in said["carry_over"]] == [
            ("Front truss", 1), ("Mirror ball ring", 2),
        ]
        for entry in said["carry_over"]:
            assert said["warnings"][entry["warning"]]["name"] == entry["old_name"]

    def test_the_place_is_the_one_in_the_room_as_stored_with_an_earlier_item_left_out(self):
        # The first truss was deleted, so the scan's first truss is left out and the rest move up one.
        old = edit_item(delete_item(shell(), LINES, 0)[0], LINES, 1, name="Back truss")[0]
        new = moved(shell(), LINES, 2, height=4.3, top=4.6)

        got = keep_hand_edits(old, new)

        [entry] = got.report()["carry_over"]
        assert (entry["new_index"], entry["new_name"], entry["reason"]) == (1, "Overhead line 3", LOST_HEIGHT)
        there = got.shell[LINES][entry["new_index"]]
        assert (there["name"], there["z1"], there["height"]) == ("Overhead line 3", 0.0, 4.3)
        assert len(got.shell[LINES]) == 2

    def test_the_place_holds_with_one_added_by_hand_kept_after_the_scans(self):
        old = add_item(edit_item(shell(), RINGS, 0, name="Mirror ball ring")[0], RINGS, **HALO)[0]
        got = keep_hand_edits(old, moved(shell(), RINGS, 0, center_x=4.5))
        [entry] = got.report()["carry_over"]
        assert [ring["name"] for ring in got.shell[RINGS]] == ["Overhead ring 1", "Halo"]
        assert (entry["new_index"], entry["new_name"]) == (0, "Overhead ring 1")

    def test_neither_room_is_changed(self):
        old = edit_item(edit_item(shell(), AREAS, 1, name="The bar")[0], LINES, 0, name="Front truss")[0]
        new = moved({**shell(), LINES: shell()[LINES][1:]}, AREAS, 1, center_x=5.0)
        old_was, new_was = copy.deepcopy(old), copy.deepcopy(new)
        got = keep_hand_edits(old, new)
        assert old == old_was and new == new_was and got.shell is new
        # Raised areas first, then lines, then rings, then the records dropped.
        assert [entry["reason"] for entry in got.lost] == [LOST_BESIDE, LOST_GONE]


def test_the_outcome_and_the_reasons_are_worded_as_the_answer_sends_them():
    assert (LOST, LOST_GONE, LOST_OTHER) == ("lost", "no longer read", "another has it")
    assert pytest.approx(1.0 / 3.0, abs=0.001) == 0.333
