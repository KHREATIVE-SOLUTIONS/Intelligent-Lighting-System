"""
A scan applied again says by name what it kept, left out and lost (keep_edits.py, slice 35)
===========================================================================================

What has to hold. Beside the counts and the sentence, the answer lists what
was done one thing at a time (`items`): what it is ("raised area", "line",
"ring"), its name, and which of four things happened, worded the same in a
preview and after Apply. And nothing is lost without a word: a line or ring
whose name or trim was set by hand, and that matched nothing only because the
scan read a truss there more than 1.0 m higher or lower, or read it sharing
less than half of the plan, is named in `warnings` with what the scan read;
so is the record of a deleted raised area, line or ring that the reading has
nothing for and that is dropped. A truss the scan no longer reads at all, the
other truss of a stack and a truss that only crosses say nothing, as before.
docs/ROOM_SCAN.md.
"""

import copy

import pytest

from app.services.room_scan.edit import DELETED_KEY, SCAN_HEIGHT_KEY, add_item, delete_item, edit_item
from app.services.room_scan.keep_edits import (
    ADDED_KEPT, KEPT, LEFT_OUT, LOST_BESIDE, LOST_HEIGHT, LOST_RECORD, REPLACED, keep_hand_edits,
)
from app.services.room_scan.keep_mark import HANG_MATCH_M, MATCH_IOU
from tests.unit.test_room_scan_edit import shell
from tests.unit.test_room_scan_keep_overhead import HALO, LINES, PIPE, RINGS, moved, stacked

AREAS = "risers"
# What an answer has with nothing but raised areas kept: the keys of slice 32.
BARE = {"areas", "kept", "added_kept", "added_replaced", "message"}


def one(kind, name, outcome):
    return {"kind": kind, "name": name, "outcome": outcome}


def everything():
    """A room with one of each thing a scan applied again acts on, and what is expected said of each."""
    old = edit_item(shell(), AREAS, 1, name="The bar")[0]
    old = edit_item(old, LINES, 0, name="Front truss")[0]
    old = edit_item(old, RINGS, 0, height=3.4)[0]
    old = add_item(old, LINES, **PIPE)[0]
    old = add_item(old, RINGS, **HALO)[0]
    # Over a quarter of the booth: not the booth, and in its place.
    old = add_item(old, AREAS, name="Bar top", center_x=4.9, center_z=3.0, width=1.0, depth=1.0, height=1.2)[0]
    # 0.3 m beside the first truss, as long as it is.
    old = add_item(old, LINES, name="Side pipe", center_x=0.0, center_z=-1.7, length=8.0, height=4.2)[0]
    old = delete_item(old, AREAS, 0)[0]
    old = delete_item(old, LINES, 2)[0]
    return old, [
        one("raised area", "Stage", LEFT_OUT),
        one("line", "Overhead line 3", LEFT_OUT),
        one("raised area", "The bar", KEPT),
        one("line", "Front truss", KEPT),
        one("ring", "Overhead ring 1", KEPT),
        one("line", "Front pipe", ADDED_KEPT),
        one("ring", "Halo", ADDED_KEPT),
        one("raised area", "Bar top", REPLACED),
        one("line", "Side pipe", REPLACED),
    ]


class TestTheListOfWhatWasDone:

    def test_the_four_outcomes_are_worded_as_the_dialog_shows_them(self):
        assert (KEPT, LEFT_OUT, REPLACED, ADDED_KEPT) == (
            "kept your edits", "left out (you deleted it)", "replaced (a scanned item overlaps it)",
            "added by hand, kept",
        )

    def test_each_thing_is_listed_by_name_with_what_it_is_and_what_happened(self):
        old, expected = everything()
        got = keep_hand_edits(old, shell())

        assert got.report()["items"] == expected
        assert got.lost == [] and "warnings" not in got.report()

    def test_the_list_is_the_same_before_apply_and_after_it(self):
        got = keep_hand_edits(everything()[0], shell())
        before, after = got.report(), got.report(applied=True)
        assert before["items"] == after["items"]
        assert before["message"] != after["message"]

    def test_the_counts_and_the_sentence_are_what_they_were(self):
        got = keep_hand_edits(everything()[0], shell())
        said = got.report(applied=True)
        assert set(said) == BARE | {
            "overhead_kept", "overhead_added_kept", "overhead_added_replaced", "deleted_left_out", "items",
        }
        assert said["areas"] == 1 and [entry["name"] for entry in said["kept"]] == ["The bar"]
        assert said["added_kept"] == []
        assert [(entry["name"], entry["by"]) for entry in said["added_replaced"]] == [("Bar top", "The bar")]
        assert [entry["name"] for entry in said["overhead_kept"]] == ["Front truss", "Overhead ring 1"]
        assert [entry["name"] for entry in said["overhead_added_kept"]] == ["Front pipe", "Halo"]
        assert [entry["name"] for entry in said["overhead_added_replaced"]] == ["Side pipe"]
        assert [entry["name"] for entry in said["deleted_left_out"]] == ["Stage", "Overhead line 3"]
        assert said["message"] == (
            "Left out 1 raised area you deleted: Stage. "
            "Left out 1 overhead line you deleted: Overhead line 3. "
            "Kept your edits on 1 raised area: The bar (name). "
            "Kept your edits on 1 overhead line: Front truss (name). "
            "Kept your edits on 1 overhead ring: Overhead ring 1 (hanging height). "
            "1 overhead line you added was kept as it is: Front pipe. "
            "1 overhead ring you added was kept as it is: Halo. "
            "Bar top, which you added, was replaced by the scan's The bar: the scan has a raised area there now. "
            "Side pipe, which you added, was replaced by the scan's Front truss: the scan has an overhead line there now."
        )

    def test_a_name_the_dj_booth_mark_gives_afterwards_is_the_one_listed(self):
        got = keep_hand_edits(edit_item(shell(), AREAS, 1, height=1.2)[0], shell())
        stored = copy.deepcopy(got.shell)
        stored[AREAS][1]["name"] = "DJ"
        assert got.report(stored)["items"] == [one("raised area", "DJ", KEPT)]

    def test_there_is_no_list_where_nothing_was_done(self):
        assert keep_hand_edits(shell(), shell()).report() is None
        # Only a warning: nothing was kept, left out or replaced, so there is nothing to list.
        gone = {**shell(), AREAS: shell()[AREAS][:1]}
        assert "items" not in keep_hand_edits(delete_item(shell(), AREAS, 1)[0], gone).report()


class TestATrussReadAtAnotherHeight:

    def test_a_name_lost_to_the_height_is_said_with_both_heights(self):
        old = edit_item(shell(), LINES, 0, name="Front truss")[0]
        new = moved(shell(), LINES, 0, height=5.3, top=5.6)

        got = keep_hand_edits(old, new)

        # Nothing is written: the room is the reading, the same object.
        assert got.shell is new and got.any and got.overhead_kept == [] and got.warnings == []
        fact = {
            "kind": LINES, "name": "Front truss", "edits": ["name"], "reason": LOST_HEIGHT,
            "read_height": 5.3, "trim": 4.2, "scan_height": 4.2,
        }
        assert got.lost == [fact]
        before, after = got.report(), got.report(applied=True)
        assert after["warnings"] == [{**fact, "message": (
            "The scan read a truss at 5.3 m where Front truss was, against its trim of 4.2 m: "
            "more than 1 m from where the scan read it before, so its name was not kept."
        )}]
        assert before["warnings"][0]["message"].endswith("so its name will not be kept.")
        assert after["message"] == after["warnings"][0]["message"]
        assert set(after) == BARE | {"warnings"}
        assert (after["areas"], after["kept"], after["added_kept"], after["added_replaced"]) == (0, [], [], [])

    def test_a_trim_set_by_hand_is_said_beside_where_the_scan_read_it_before(self):
        old = edit_item(shell(), LINES, 0, name="Front truss", height=3.0)[0]
        assert old[LINES][0][SCAN_HEIGHT_KEY] == 4.2
        new = moved(shell(), LINES, 0, height=5.3, top=5.6)

        got = keep_hand_edits(old, new)

        assert got.shell is new
        assert got.report(applied=True)["message"] == (
            "The scan read a truss at 5.3 m where Front truss was, against its trim of 3 m "
            "(the scan read it at 4.2 m before): more than 1 m from where the scan read it before, "
            "so its name and trim were not kept."
        )
        assert got.report()["message"].endswith("so its name and trim will not be kept.")

    def test_a_trim_alone_is_said_as_the_trim(self):
        old = edit_item(shell(), LINES, 0, height=3.0)[0]
        got = keep_hand_edits(old, moved(shell(), LINES, 0, height=5.3, top=5.6))
        assert got.lost[0]["name"] == "Overhead line 1" and got.lost[0]["edits"] == ["height"]
        assert got.report(applied=True)["message"].endswith("so its trim was not kept.")

    def test_a_trim_far_from_the_reading_is_no_loss_while_the_scan_reads_the_truss_where_it_did(self):
        old = edit_item(shell(), LINES, 0, name="Front truss", height=3.0)[0]
        got = keep_hand_edits(old, shell())
        assert got.lost == [] and got.shell[LINES][0]["height"] == 3.0 and "warnings" not in got.report()

    def test_inside_the_tolerance_nothing_is_lost(self):
        old = edit_item(shell(), LINES, 0, name="Front truss")[0]
        got = keep_hand_edits(old, moved(shell(), LINES, 0, height=4.2 + HANG_MATCH_M - 0.1, top=5.4))
        assert got.lost == [] and got.shell[LINES][0]["name"] == "Front truss"

    def test_a_ring_is_said_as_a_ring(self):
        old = edit_item(shell(), RINGS, 0, name="Mirror ball ring")[0]
        got = keep_hand_edits(old, moved(shell(), RINGS, 0, height=5.5, top=5.8))
        assert [(e["kind"], e["name"], e["reason"]) for e in got.lost] == [(RINGS, "Mirror ball ring", LOST_HEIGHT)]
        assert got.report(applied=True)["message"].startswith("The scan read a ring at 5.5 m where Mirror ball ring was")

    def test_the_other_truss_of_a_stack_is_itself_and_not_this_one_read_higher(self):
        # The lower one is named and no longer read; the upper one, over the same floor, still is.
        old = edit_item(stacked(), LINES, 0, name="Low truss")[0]
        new = {**stacked(), LINES: stacked()[LINES][1:]}
        got = keep_hand_edits(old, new)
        assert got.shell is new and not got.any and got.report() is None

    def test_a_truss_no_longer_read_and_one_nobody_edited_say_nothing(self):
        old = edit_item(shell(), LINES, 0, name="Front truss", height=3.0)[0]
        gone = {**shell(), LINES: shell()[LINES][1:]}
        assert not keep_hand_edits(old, gone).any
        # Read 1.1 m higher, but nothing on it was a person's: there is nothing to lose.
        assert not keep_hand_edits(shell(), moved(shell(), LINES, 0, height=5.3, top=5.6)).any

    def test_one_added_by_hand_is_spoken_of_as_kept_or_replaced_and_never_here(self):
        over = {**PIPE, "center_x": 0.0, "center_z": -1.7, "length": 8.0, "height": 2.5}
        got = keep_hand_edits(add_item(shell(), LINES, **over)[0], shell())
        assert got.lost == [] and [entry["name"] for entry in got.overhead_added_replaced] == ["Front pipe"]


class TestATrussReadBesideWhereItWas:

    def test_a_name_lost_to_a_reading_to_one_side_is_said_with_how_far(self):
        old = edit_item(shell(), LINES, 0, name="Front truss", height=3.0)[0]
        new = moved(shell(), LINES, 0, z1=-1.7, z2=-1.7)

        got = keep_hand_edits(old, new)

        assert got.shell is new and got.overhead_kept == []
        # 0.3 m to one side: (0.6 - 0.3) / (0.6 + 0.3) of the two strips, under the half a match needs.
        fact = {
            "kind": LINES, "name": "Front truss", "edits": ["name", "height"], "reason": LOST_BESIDE,
            "offset": 0.3, "overlap": 0.333,
        }
        assert got.lost == [fact] and fact["overlap"] < MATCH_IOU
        after = got.report(applied=True)
        assert after["warnings"] == [{**fact, "message": (
            "The scan read a truss 0.3 m from where Front truss was, sharing 33% of the plan with it "
            "where half is needed, so its name and trim were not kept."
        )}]
        assert got.report()["message"].endswith("so its name and trim will not be kept.")
        assert set(after) == BARE | {"warnings"}

    def test_one_read_much_shorter_is_said_the_same_way(self):
        old = edit_item(shell(), LINES, 0, name="Front truss")[0]
        got = keep_hand_edits(old, moved(shell(), LINES, 0, x2=-1.0, length=3.0))
        assert [(e["reason"], e["offset"], e["overlap"]) for e in got.lost] == [(LOST_BESIDE, 2.5, 0.375)]

    def test_one_read_a_little_off_is_kept_and_one_read_clear_of_it_says_nothing(self):
        old = edit_item(shell(), LINES, 0, name="Front truss")[0]
        near = keep_hand_edits(old, moved(shell(), LINES, 0, z1=-1.9, z2=-1.9))
        assert near.lost == [] and near.shell[LINES][0]["name"] == "Front truss"
        # 0.7 m aside the strips share nothing: the next truss along, not this one.
        assert not keep_hand_edits(old, moved(shell(), LINES, 0, z1=-1.3, z2=-1.3)).any

    def test_a_truss_that_crosses_is_itself_and_not_this_one_read_beside(self):
        cross = {
            "name": "Overhead line 4", "x1": 3.0, "z1": -3.5, "x2": 3.0, "z2": -0.5, "height": 4.2, "top": 4.5,
            "length": 3.0, "across": 0.3, "axis": "z", "heading_deg": 90.0, "suggested": True, "basis": "scan: a bar.",
        }
        both = shell()
        both[LINES].append(cross)
        old = edit_item(both, LINES, 0, name="Front truss")[0]
        new = {**copy.deepcopy(both), LINES: copy.deepcopy(both[LINES][1:])}
        got = keep_hand_edits(old, new)
        assert got.shell is new and not got.any

    def test_a_ring_read_beside_is_said_as_a_ring(self):
        old = edit_item(shell(), RINGS, 0, name="Mirror ball ring")[0]
        got = keep_hand_edits(old, moved(shell(), RINGS, 0, center_x=4.5))
        assert [(e["reason"], e["offset"]) for e in got.lost] == [(LOST_BESIDE, 1.5)]
        assert 0.2 < got.lost[0]["overlap"] < 0.3
        assert got.report(applied=True)["message"].startswith("The scan read a ring 1.5 m from where Mirror ball ring was")

    def test_a_height_out_of_reach_comes_before_a_reading_beside(self):
        old = edit_item(shell(), LINES, 0, name="Front truss")[0]
        new = moved(shell(), LINES, 0, height=5.3, top=5.6)
        new[LINES].append({**shell()[LINES][0], "name": "Overhead line 4", "z1": -1.7, "z2": -1.7})
        got = keep_hand_edits(old, new)
        assert [entry["reason"] for entry in got.lost] == [LOST_HEIGHT]


class TestARecordOfADeletedItemThatIsDropped:

    def test_a_raised_area_the_scan_no_longer_reads_is_named(self):
        old = delete_item(shell(), AREAS, 1)[0]
        new = {**shell(), AREAS: shell()[AREAS][:1]}

        got = keep_hand_edits(old, new)

        assert got.shell is new and DELETED_KEY not in got.shell and got.left_out == []
        fact = {"kind": AREAS, "name": "Booth or counter", "reason": LOST_RECORD}
        assert got.lost == [fact]
        before, after = got.report(), got.report(applied=True)
        assert after["warnings"] == [{**fact, "message": (
            "The scan did not see Booth or counter; the record that keeps it deleted was dropped, "
            "so it may come back on a later scan."
        )}]
        assert before["warnings"] == [{**fact, "message": (
            "The scan did not see Booth or counter; the record that keeps it deleted will be dropped, "
            "so it may come back on a later scan."
        )}]
        assert after["message"] == after["warnings"][0]["message"]
        assert set(after) == BARE | {"warnings"}

    def test_it_is_said_once_and_the_reading_after_brings_the_area_back(self):
        old = delete_item(shell(), AREAS, 1)[0]
        got = keep_hand_edits(old, {**shell(), AREAS: shell()[AREAS][:1]})
        again = keep_hand_edits(got.shell, shell())
        assert not again.any and len(again.shell[AREAS]) == 2

    def test_a_line_and_a_ring_are_named_beside_what_was_left_out(self):
        old = delete_item(delete_item(delete_item(shell(), AREAS, 1)[0], LINES, 0)[0], RINGS, 0)[0]
        new = {**shell(), RINGS: []}

        got = keep_hand_edits(old, new)

        assert [entry["name"] for entry in got.left_out] == ["Booth or counter", "Overhead line 1"]
        assert got.lost == [{"kind": RINGS, "name": "Overhead ring 1", "reason": LOST_RECORD}]
        # The two it has again go on; the one it does not is gone.
        assert [record["name"] for record in got.shell[DELETED_KEY]] == ["Booth or counter", "Overhead line 1"]
        said = got.report(applied=True)
        assert said["items"] == [
            one("raised area", "Booth or counter", LEFT_OUT), one("line", "Overhead line 1", LEFT_OUT),
        ]
        assert said["message"] == (
            "Left out 1 raised area you deleted: Booth or counter. "
            "Left out 1 overhead line you deleted: Overhead line 1. "
            "The scan did not see Overhead ring 1; the record that keeps it deleted was dropped, "
            "so it may come back on a later scan."
        )

    def test_a_line_read_at_another_height_or_clear_of_where_it_was_drops_the_record_and_says_so(self):
        old = delete_item(shell(), LINES, 0)[0]
        for new in (moved(shell(), LINES, 0, height=5.3, top=5.6), moved(shell(), LINES, 0, z1=-1.3, z2=-1.3)):
            got = keep_hand_edits(old, new)
            assert got.shell is new and len(got.shell[LINES]) == 3
            assert got.lost == [{"kind": LINES, "name": "Overhead line 1", "reason": LOST_RECORD}]

    def test_of_two_records_that_pick_one_area_the_one_that_does_not_have_it_is_named(self):
        old = delete_item(shell(), AREAS, 1)[0]
        old[DELETED_KEY].append({**old[DELETED_KEY][0], "name": "Flight case", "center_x": 4.2})
        got = keep_hand_edits(old, shell())
        assert [entry["name"] for entry in got.left_out] == ["Booth or counter"]
        assert got.lost == [{"kind": AREAS, "name": "Flight case", "reason": LOST_RECORD}]

    def test_a_record_with_no_name_is_called_what_it_was_and_one_that_is_no_record_is_passed_over(self):
        old = delete_item(shell(), LINES, 0)[0]
        del old[DELETED_KEY][0]["name"]
        old[DELETED_KEY].append("not a record")
        got = keep_hand_edits(old, {**shell(), LINES: []})
        assert got.lost == [{"kind": LINES, "name": "a deleted overhead line", "reason": LOST_RECORD}]

    def test_a_check_comes_before_what_was_lost(self):
        old = add_item(delete_item(shell(), AREAS, 1)[0], LINES, **{**PIPE, "center_x": 4.0})[0]
        new = {**shell(), AREAS: shell()[AREAS][:1]}
        new["room"] = {**new["room"], "width": 8.0}

        said = keep_hand_edits(old, new).report(applied=True)

        assert [(entry["name"], entry["reason"], "index" in entry) for entry in said["warnings"]] == [
            ("Front pipe", "partly outside the walls", True), ("Booth or counter", LOST_RECORD, False),
        ]
        assert "message" not in said["warnings"][0]
        assert said["message"] == (
            "1 overhead line you added was kept as it is: Front pipe. "
            "Check Front pipe: it is partly outside the walls of the room as this scan reads it. "
            "The scan did not see Booth or counter; the record that keeps it deleted was dropped, "
            "so it may come back on a later scan."
        )
        assert said["items"] == [one("line", "Front pipe", ADDED_KEPT)]


class TestNothingElseChanges:

    def test_neither_room_is_changed_by_a_warning(self):
        old = edit_item(delete_item(shell(), AREAS, 1)[0], LINES, 0, name="Front truss")[0]
        new = moved({**shell(), AREAS: shell()[AREAS][:1]}, LINES, 0, height=5.3, top=5.6)
        old_was, new_was = copy.deepcopy(old), copy.deepcopy(new)
        got = keep_hand_edits(old, new)
        assert old == old_was and new == new_was and got.shell is new
        assert [entry["reason"] for entry in got.lost] == [LOST_HEIGHT, LOST_RECORD]

    def test_what_is_lost_is_said_beside_what_is_kept(self):
        old = edit_item(edit_item(shell(), LINES, 0, name="Front truss")[0], LINES, 2, name="Back truss")[0]
        got = keep_hand_edits(old, moved(shell(), LINES, 0, height=5.3, top=5.6))
        said = got.report(applied=True)
        assert got.shell[LINES][2]["name"] == "Back truss" and got.shell[LINES][0]["name"] == "Overhead line 1"
        assert said["items"] == [one("line", "Back truss", KEPT)]
        assert [entry["name"] for entry in said["warnings"]] == ["Front truss"]

    def test_a_raised_area_read_beside_where_it_was_still_says_nothing(self):
        # Slice 35 speaks of lines and rings: a raised area's name lost to a reading to one side is as it was.
        old = edit_item(shell(), AREAS, 1, name="The bar")[0]
        assert not keep_hand_edits(old, moved(shell(), AREAS, 1, center_x=5.0)).any

    def test_the_tolerance_is_the_one_the_match_uses(self):
        assert HANG_MATCH_M == pytest.approx(1.0)
