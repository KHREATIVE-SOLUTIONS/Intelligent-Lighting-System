"""
Overhead lines, deleted raised areas and checks when a room is scanned again (keep_edits.py, slice 33)
======================================================================================================

What has to hold. An overhead line or ring that a person named, or set the
hanging height of, and that matches one of the new reading (the same
`best_match` raised areas are matched by, over a line's strip or a ring's
disc) gives it that name and that height; where it is and how long it is stay
the scan's, and `hanging_bands` still counts every line and ring. One added by
hand is kept as it is where the new reading has nothing, crossing trusses
included, and replaced and reported where the reading has one in its place. A
scanned raised area a person deleted leaves a record in the room, and a
reading that has it again leaves it out, reports it and carries the record
on. A kept height above the new ceiling, and something added by hand outside
the new walls, are kept and flagged. With none of these the reading comes
back as the same object. docs/ROOM_SCAN.md.

Slice 34: a scanned line or ring a person deleted leaves the same record and
is left out the same way, and a line or ring of the reading hanging more than
1.0 m from where the scan read the stored one is not it, so two trusses hung
one above the other keep their own names and trims.
"""

import copy

import pytest

from app.services.room_scan.edit import (
    DELETED_KEY, HEIGHT_BY_HAND, KIND_BY_HAND, NAME_BY_HAND, RESIZED_BY_HAND, SCAN_HEIGHT_KEY, add_item, delete_item,
    edit_item, tombstone,
)
from app.services.room_scan.keep_edits import CROSSING, LOST_HEIGHT, LOST_RECORD, hand_edits, keep_hand_edits
from app.services.room_scan.keep_mark import HANG_MATCH_M, LINE_STRIP_M, MATCH_IOU, best_match, footprint_overlap
from tests.unit.test_room_scan_edit import shell

LINES, RINGS = "truss_lines", "truss_rings"
# Clear of every truss of shell(): along the downstage wall.
PIPE = {"name": "Front pipe", "center_x": 2.5, "center_z": -4.0, "length": 3.0, "height": 4.2}
HALO = {"name": "Halo", "center_x": -4.0, "center_z": 3.0, "radius": 0.8, "height": 3.0}


def moved(found, where, index, /, **changes):
    """The room as a scan reads it again with one item read a little differently."""
    again = copy.deepcopy(found)
    again[where][index].update(changes)
    return again


def bands_add_up(room):
    bands = room["hanging_bands"]
    assert sum(band.get("lines", 0) for band in bands) == len(room[LINES])
    assert sum(band.get("rings", 0) for band in bands) == len(room[RINGS])
    assert all(band.get("lines", 0) + band.get("rings", 0) > 0 for band in bands)


class TestTheFootprintOfALineAndARing:

    def test_a_line_is_the_strip_along_it_and_one_read_to_the_side_shares_part(self):
        line = shell()[LINES][0]
        assert footprint_overlap(line, line) == pytest.approx(1.0)
        # Read d to one side: (W - d) / (W + d) of the two strips together.
        aside = {**line, "z1": -1.9, "z2": -1.9}
        assert footprint_overlap(line, aside) == pytest.approx((LINE_STRIP_M - 0.1) / (LINE_STRIP_M + 0.1))
        # The next truss along shares nothing, and neither does a line with no length or no ends.
        assert footprint_overlap(line, {**line, "z1": -1.3, "z2": -1.3}) < MATCH_IOU
        assert footprint_overlap(line, {**line, "z1": -1.4, "z2": -1.4}) == pytest.approx(0.0)
        assert footprint_overlap(line, {**line, "x2": -4.0}) == 0.0
        assert footprint_overlap(line, {"x1": 0.0}) == 0.0

    def test_an_angled_line_is_compared_as_it_runs_whichever_end_is_first(self):
        angled = shell()[LINES][1]
        swapped = {**angled, "x1": angled["x2"], "z1": angled["z2"], "x2": angled["x1"], "z2": angled["z1"]}
        assert footprint_overlap(angled, swapped) == pytest.approx(1.0)

    def test_a_truss_wider_than_the_strip_is_as_wide_as_it_is(self):
        wide = {**shell()[LINES][0], "across": 1.2}
        assert footprint_overlap(wide, {**wide, "z1": -1.6, "z2": -1.6}) == pytest.approx(0.8 / 1.6)

    def test_a_ring_is_its_disc(self):
        ring = shell()[RINGS][0]
        assert footprint_overlap(ring, ring) == pytest.approx(1.0)
        assert footprint_overlap(ring, {**ring, "center_x": 3.2}) > MATCH_IOU
        assert footprint_overlap(ring, {**ring, "center_x": 6.5}) == 0.0
        assert footprint_overlap(ring, {**ring, "radius": 0}) == 0.0

    def test_the_one_rule_picks_the_line_and_the_ring(self):
        found = shell()
        assert best_match(found[LINES][2], found[LINES]) == (2, pytest.approx(1.0))
        assert best_match(found[RINGS][0], found[RINGS]) == (0, pytest.approx(1.0))
        assert best_match({**found[LINES][0], "z1": 3.0, "z2": 3.0}, found[LINES]) == (None, 0.0)


class TestWhatSaysALineWasSetByHand:

    def test_the_marks_edit_room_writes_on_a_line_and_a_ring(self):
        found = shell()
        for kind in (LINES, RINGS):
            assert hand_edits(found[kind][0], kind) == ()
            named = edit_item(found, kind, 0, name="Front truss")[1]
            assert hand_edits(named, kind) == ("name",)
            assert named["suggested"] is True and named["basis"].count(NAME_BY_HAND) == 1
            hung = edit_item(found, kind, 0, height=3.5)[1]
            assert hand_edits(hung, kind) == ("height",)
            assert hung["suggested"] is False
            assert hung["basis"].count(HEIGHT_BY_HAND) == 1 and hung["basis"].count(RESIZED_BY_HAND) == 1
            both = edit_item(found, kind, 0, name="Front truss", height=3.5)[1]
            assert hand_edits(both, kind) == ("name", "height")

    def test_a_length_a_move_a_turn_and_a_radius_are_not_among_them(self):
        found = shell()
        assert hand_edits(edit_item(found, LINES, 0, length=6.0)[1], LINES) == ()
        assert hand_edits(edit_item(found, LINES, 0, center_z=-1.0)[1], LINES) == ()
        assert hand_edits(edit_item(found, LINES, 0, heading_deg=20)[1], LINES) == ()
        assert hand_edits(edit_item(found, RINGS, 0, radius=2.0)[1], RINGS) == ()
        # The same height again is not a change, and says nothing.
        assert hand_edits(edit_item(found, LINES, 0, height=4.2, length=6.0)[1], LINES) == ()

    def test_one_added_by_hand_is_a_persons_but_for_the_name_it_was_given_for_want_of_one(self):
        assert hand_edits(add_item(shell(), LINES, **PIPE)[1], LINES) == ("name", "height")
        assert hand_edits(add_item(shell(), RINGS, **HALO)[1], RINGS) == ("name", "height")
        unnamed = add_item(shell(), LINES, **{**PIPE, "name": None})[1]
        assert unnamed["name"] == "Overhead line 4" and hand_edits(unnamed, LINES) == ("height",)


class TestALineNamedOrHungByHand:

    def test_a_name_set_by_hand_is_kept_on_the_line_read_a_little_off(self):
        old = edit_item(shell(), LINES, 0, name="Front truss")[0]
        new = moved(shell(), LINES, 0, z1=-1.9, z2=-1.9, x2=4.1, length=8.1)
        read = new[LINES][0]

        got = keep_hand_edits(old, new)

        # Where and as long as the scan reads it; the name, and that it is a person's.
        assert got.shell[LINES][0] == {**read, "name": "Front truss", "basis": f"scan: a bar. {NAME_BY_HAND}"}
        assert got.shell[LINES][1:] == new[LINES][1:] and got.shell["hanging_bands"] == new["hanging_bands"]
        assert [(e["kind"], e["index"], e["edits"]) for e in got.overhead_kept] == [(LINES, 0, ["name"])]
        assert MATCH_IOU <= got.overhead_kept[0]["overlap"] < 1.0
        assert got.kept == [] and got.added_kept == [] and got.warnings == []

    def test_a_hanging_height_set_by_hand_is_kept_and_the_bands_still_add_up(self):
        old = edit_item(shell(), LINES, 0, height=3.0)[0]
        new = moved(shell(), LINES, 0, x1=-4.2, x2=3.8, height=4.22, top=4.5)

        got = keep_hand_edits(old, new)

        line = got.shell[LINES][0]
        # The trim is the person's, and the truss as deep as the scan reads it; the place is the scan's.
        assert (line["height"], line["top"]) == (3.0, 3.28)
        assert (line["x1"], line["x2"], line["length"]) == (-4.2, 3.8, 8.0)
        assert line["suggested"] is False
        assert line["basis"].count(HEIGHT_BY_HAND) == 1 and line["basis"].count(RESIZED_BY_HAND) == 1
        bands_add_up(got.shell)
        assert [(b["height"], b["lines"], b["rings"]) for b in got.shell["hanging_bands"]] == [
            (3.0, 1, 0), (4.2, 1, 1), (5.5, 1, 0),
        ]
        assert got.overhead_kept == [{"kind": LINES, "index": 0, "edits": ["height"], "overlap": pytest.approx(1.0, abs=0.1)}]

    def test_it_holds_at_the_reading_after_and_each_mark_is_written_once(self):
        old = edit_item(shell(), LINES, 2, name="Back truss", height=5.0)[0]

        first = keep_hand_edits(old, shell())
        second = keep_hand_edits(first.shell, shell())

        for got in (first, second):
            line = got.shell[LINES][2]
            assert (line["name"], line["height"], line["top"]) == ("Back truss", 5.0, 5.3)
            for mark in (NAME_BY_HAND, HEIGHT_BY_HAND, RESIZED_BY_HAND):
                assert line["basis"].count(mark) == 1
            assert got.overhead_kept[0]["edits"] == ["name", "height"]
            bands_add_up(got.shell)
        assert second.shell == first.shell

    def test_a_ring_keeps_its_name_and_its_hanging_height(self):
        old = edit_item(shell(), RINGS, 0, name="Mirror ball ring", height=3.4)[0]
        new = moved(shell(), RINGS, 0, center_x=3.1, radius=1.55)

        got = keep_hand_edits(old, new)

        ring = got.shell[RINGS][0]
        assert (ring["name"], ring["height"], ring["top"]) == ("Mirror ball ring", 3.4, 3.7)
        assert (ring["center_x"], ring["radius"]) == (3.1, 1.55)
        assert got.overhead_kept[0]["kind"] == RINGS and got.overhead_kept[0]["edits"] == ["name", "height"]
        bands_add_up(got.shell)

    def test_the_next_truss_along_and_a_line_no_longer_read_keep_nothing(self):
        old = edit_item(shell(), LINES, 0, name="Front truss", height=3.0)[0]
        for new in (moved(shell(), LINES, 0, z1=-1.3, z2=-1.3), {**shell(), LINES: shell()[LINES][1:]}):
            got = keep_hand_edits(old, new)
            # Slice 36: nothing is kept, as before, and it is now said that the scan no longer reads it.
            assert got.shell is new and got.overhead_kept == []
            assert [(entry["name"], entry["reason"]) for entry in got.lost] == [("Front truss", "no longer read")]

    def test_a_line_only_moved_or_made_longer_carries_nothing(self):
        old = edit_item(shell(), LINES, 0, center_z=-1.8, length=7.0)[0]
        new = shell()
        got = keep_hand_edits(old, new)
        assert got.shell is new and not got.any

    def test_neither_room_given_is_changed(self):
        old = add_item(edit_item(shell(), LINES, 0, name="Front truss", height=3.0)[0], LINES, **PIPE)[0]
        new = shell()
        old_was, new_was = copy.deepcopy(old), copy.deepcopy(new)
        got = keep_hand_edits(old, new)
        assert old == old_was and new == new_was and got.shell is not new


class TestALineAddedByHand:

    def test_one_the_reading_has_nothing_in_the_place_of_is_kept_as_it_is(self):
        old, pipe, at = add_item(shell(), LINES, **PIPE)
        ringed, halo, ring_at = add_item(old, RINGS, **HALO)
        new = shell()

        got = keep_hand_edits(ringed, new)

        # After the scan's own, so every place the scan gave is what it was; and counted where it hangs.
        assert got.shell[LINES] == [*new[LINES], pipe] and got.shell[RINGS] == [*new[RINGS], halo]
        assert got.overhead_added_kept == [{"kind": LINES, "index": at}, {"kind": RINGS, "index": ring_at}]
        assert got.overhead_kept == [] and got.overhead_added_replaced == [] and got.warnings == []
        bands_add_up(got.shell)
        # And again at the reading after.
        again = keep_hand_edits(got.shell, shell())
        assert again.shell == got.shell

    def test_one_that_only_crosses_a_truss_of_the_reading_is_kept(self):
        old, cross, at = add_item(shell(), LINES, name="Cross pipe", center_x=3.0, center_z=-2.0, length=3.0,
                                  height=4.2, heading_deg=90)
        assert 0 < footprint_overlap(cross, shell()[LINES][0]) < CROSSING

        got = keep_hand_edits(old, shell())

        assert got.shell[LINES][at] == cross and got.overhead_added_kept == [{"kind": LINES, "index": at}]

    def test_one_the_reading_has_a_truss_in_the_place_of_is_replaced_and_reported(self):
        beside = {**PIPE, "center_x": 0.0, "center_z": -1.7, "length": 8.0}
        old = add_item(shell(), LINES, **beside)[0]
        new = shell()

        got = keep_hand_edits(old, new)

        # The room is the reading as it came, the same object.
        assert got.shell is new
        assert got.overhead_added_replaced == [{"kind": LINES, "name": "Front pipe", "by_index": 0}]
        said = got.report(applied=True)
        assert said["overhead_added_replaced"] == [
            {"kind": LINES, "name": "Front pipe", "by_index": 0, "by": "Overhead line 1"},
        ]
        assert said["message"] == (
            "Front pipe, which you added, was replaced by the scan's Overhead line 1: "
            "the scan has an overhead line there now."
        )
        assert (said["areas"], said["kept"], said["added_kept"], said["added_replaced"]) == (0, [], [], [])

    def test_one_added_exactly_over_the_scans_own_does_not_take_its_name(self):
        over = {**PIPE, "center_x": 0.0, "center_z": -2.0, "length": 8.0}
        got = keep_hand_edits(add_item(shell(), LINES, **over)[0], shell())
        assert got.shell[LINES][0]["name"] == "Overhead line 1"
        assert [entry["name"] for entry in got.overhead_added_replaced] == ["Front pipe"]

    def test_one_the_scan_now_reads_gives_it_its_name_and_height_and_is_the_scans(self):
        old, pipe, at = add_item(shell(), LINES, **PIPE)
        new = shell()
        new[LINES].append({
            "name": "Overhead line 4", "x1": 1.0, "z1": -3.95, "x2": 4.1, "z2": -3.95, "height": 4.3, "top": 4.6,
            "length": 3.1, "across": 0.3, "axis": "x", "heading_deg": 0.0, "suggested": True, "basis": "scan: a bar.",
        })
        new["hanging_bands"][0]["lines"] = 3

        got = keep_hand_edits(old, new)

        line = got.shell[LINES][3]
        assert (line["name"], line["height"], line["top"]) == ("Front pipe", 4.2, 4.5)
        assert (line["x1"], line["x2"], line["z1"]) == (1.0, 4.1, -3.95) and "added_by_hand" not in line
        assert len(got.shell[LINES]) == 4 and got.overhead_added_kept == []
        assert got.overhead_kept[0]["edits"] == ["name", "height"]
        bands_add_up(got.shell)


class TestARaisedAreaDeletedByHand:

    def test_a_scanned_one_leaves_a_record_and_one_added_by_hand_none(self):
        found = shell()
        gone, removed = delete_item(found, "risers", 1)
        assert gone[DELETED_KEY] == [{
            "kind": "booth", "name": "Booth or counter", "center_x": 4.0, "center_z": 3.0, "width": 2.0, "depth": 1.0,
        }] == [tombstone(removed)]
        assert DELETED_KEY not in found
        # A second one is added to the list.
        assert [left["kind"] for left in delete_item(gone, "risers", 0)[0][DELETED_KEY]] == ["booth", "stage"]

        added, _, at = add_item(found, "risers", center_x=-4.0, center_z=3.0, width=1.0, depth=1.0, height=0.3)
        assert DELETED_KEY not in delete_item(added, "risers", at)[0]
        # (A scanned line or ring left none until slice 34: TestALineOrRingDeletedByHand.)
        assert tombstone({"kind": "riser", "center_x": 0.0}) is None and tombstone(None) is None

    def test_a_heading_and_a_kind_set_by_hand_are_remembered(self):
        turned = edit_item(shell(), "risers", 1, heading_deg=30, riser_kind="riser")[0]
        left = delete_item(turned, "risers", 1)[0][DELETED_KEY][0]
        assert left["heading_deg"] == 30.0 and left["basis"] == KIND_BY_HAND and left["kind"] == "riser"

    def test_the_reading_that_has_it_again_leaves_it_out_and_carries_the_record_on(self):
        old = delete_item(shell(), "risers", 1)[0]
        new = moved(shell(), "risers", 1, center_x=4.1, width=2.1)

        got = keep_hand_edits(old, new)

        assert got.shell["risers"] == [new["risers"][0]]
        assert got.left_out == [{"name": "Booth or counter", "kind": "booth", "overlap": got.left_out[0]["overlap"]}]
        assert MATCH_IOU <= got.left_out[0]["overlap"] < 1.0
        # The record stands where this reading has it, for the reading after.
        assert got.shell[DELETED_KEY] == [{
            "kind": "booth", "name": "Booth or counter", "center_x": 4.1, "center_z": 3.0, "width": 2.1, "depth": 1.0,
        }]
        assert {key: value for key, value in got.shell.items() if key not in ("risers", DELETED_KEY)} == {
            key: value for key, value in new.items() if key != "risers"
        }
        assert DELETED_KEY not in new and len(new["risers"]) == 2

        again = keep_hand_edits(got.shell, shell())
        assert len(again.shell["risers"]) == 1 and len(again.left_out) == 1 and len(again.shell[DELETED_KEY]) == 1

    def test_what_is_said_before_apply_and_after_it(self):
        got = keep_hand_edits(delete_item(shell(), "risers", 1)[0], shell())
        assert got.any
        before, after = got.report(), got.report(applied=True)
        assert before["message"] == "Will leave out 1 raised area you deleted: Booth or counter."
        assert after["message"] == "Left out 1 raised area you deleted: Booth or counter."
        assert after["deleted_left_out"] == [{"name": "Booth or counter", "kind": "booth", "overlap": 1.0}]
        # "items" since slice 35.
        assert set(after) == {"areas", "kept", "added_kept", "added_replaced", "message", "deleted_left_out", "items"}

    def test_a_record_the_reading_has_nothing_for_is_dropped_and_another_kind_is_not_it(self):
        old = delete_item(shell(), "risers", 1)[0]
        for new in (
            {**shell(), "risers": shell()["risers"][:1]},
            moved(shell(), "risers", 1, center_x=-4.0),
            moved(shell(), "risers", 1, kind="riser", name="Riser"),
        ):
            got = keep_hand_edits(old, new)
            assert got.shell is new and DELETED_KEY not in got.shell and not got.left_out
            # Slice 35: dropped, and said (until then nothing was: `not got.any`).
            assert got.lost == [{"kind": "risers", "name": "Booth or counter", "reason": LOST_RECORD}]

    def test_a_kind_set_by_hand_before_it_was_deleted_matches_what_the_scan_reads(self):
        old = delete_item(edit_item(shell(), "risers", 1, riser_kind="riser")[0], "risers", 1)[0]
        got = keep_hand_edits(old, shell())
        assert len(got.shell["risers"]) == 1 and got.left_out[0]["kind"] == "riser"
        assert got.shell[DELETED_KEY][0]["basis"] == KIND_BY_HAND

    def test_one_deleted_and_put_in_again_by_hand_is_kept_as_the_persons(self):
        gone = delete_item(shell(), "risers", 1)[0]
        old, bar, _ = add_item(gone, "risers", name="The bar", riser_kind="booth", center_x=4.0, center_z=3.0,
                               width=2.4, depth=1.0, height=1.1)

        got = keep_hand_edits(old, shell())

        # The scan's is left out first, so the person's overlaps nothing and is kept as it is.
        assert got.shell["risers"] == [shell()["risers"][0], bar]
        assert got.added_kept == [{"index": 1}] and len(got.left_out) == 1 and got.added_replaced == []
        assert got.report(applied=True)["message"] == (
            "Left out 1 raised area you deleted: Booth or counter. 1 raised area you added was kept as it is: The bar."
        )

    def test_an_edit_kept_beside_one_left_out_is_listed_at_its_place_in_the_new_room(self):
        old = delete_item(edit_item(shell(), "risers", 1, name="The bar")[0], "risers", 0)[0]
        got = keep_hand_edits(old, shell())
        assert [item["name"] for item in got.shell["risers"]] == ["The bar"]
        assert got.kept == [{"index": 0, "edits": ["name"], "overlap": 1.0}]
        assert got.report()["kept"][0]["name"] == "The bar"


def stacked():
    """shell() with its third truss (5.5 m) hung straight above its first (4.2 m): one footprint on the plan."""
    room = shell()
    room[LINES][2].update({"z1": -2.0, "z2": -2.0})
    return room


def turned_over(room):
    """The same room with its first and third lines read in the other order."""
    again = copy.deepcopy(room)
    again[LINES][0], again[LINES][2] = again[LINES][2], again[LINES][0]
    return again


class TestALineOrRingDeletedByHand:
    """Slice 34: the record slice 33 keeps for a raised area, kept for a scanned line and ring too."""

    def test_a_scanned_line_and_ring_leave_a_record_and_one_added_by_hand_none(self):
        found = shell()
        gone, removed = delete_item(found, LINES, 0)
        assert gone[DELETED_KEY] == [{
            "name": "Overhead line 1", "x1": -4.0, "z1": -2.0, "x2": 4.0, "z2": -2.0, "across": 0.3, "height": 4.2,
        }] == [tombstone(removed, LINES)]
        both = delete_item(gone, RINGS, 0)[0]
        assert both[DELETED_KEY][1] == {
            "name": "Overhead ring 1", "center_x": 3.0, "center_z": 2.0, "radius": 1.5, "height": 4.2,
        }
        # Neither stores a kind: a line and a ring of a reading have none to be the same as.
        assert all("kind" not in left for left in both[DELETED_KEY])
        assert DELETED_KEY not in found

        added, _, at = add_item(found, LINES, **PIPE)
        assert DELETED_KEY not in delete_item(added, LINES, at)[0]
        ringed, _, ring_at = add_item(found, RINGS, **HALO)
        assert DELETED_KEY not in delete_item(ringed, RINGS, ring_at)[0]
        assert tombstone({"x1": 0.0, "z1": 0.0, "x2": 0.0, "z2": 0.0}, LINES) is None
        assert tombstone({"center_x": 0.0, "center_z": 0.0, "radius": 0}, RINGS) is None

    def test_the_record_holds_the_height_the_scan_read_not_a_trim_set_by_hand(self):
        trimmed = edit_item(shell(), LINES, 0, height=3.0)[0]
        assert trimmed[LINES][0][SCAN_HEIGHT_KEY] == 4.2
        assert delete_item(trimmed, LINES, 0)[0][DELETED_KEY][0]["height"] == 4.2
        # A trim set before the scan's height was kept beside it: no height is remembered, and none compared.
        old = copy.deepcopy(trimmed)
        del old[LINES][0][SCAN_HEIGHT_KEY]
        left = delete_item(old, LINES, 0)[0][DELETED_KEY][0]
        assert "height" not in left and best_match(left, shell()[LINES]) == (0, pytest.approx(1.0))

    def test_the_reading_that_has_the_line_again_leaves_it_out_and_carries_the_record_on(self):
        old = delete_item(shell(), LINES, 0)[0]
        new = moved(shell(), LINES, 0, x1=-4.2, x2=3.8, height=4.22, top=4.5)

        got = keep_hand_edits(old, new)

        assert got.shell[LINES] == new[LINES][1:] and got.shell[RINGS] == new[RINGS]
        assert got.shell["risers"] == new["risers"]
        assert got.left_out == [{"name": "Overhead line 1", "kind": LINES, "overlap": got.left_out[0]["overlap"]}]
        assert MATCH_IOU <= got.left_out[0]["overlap"] < 1.0
        # No longer counted where it hung.
        bands_add_up(got.shell)
        assert [(b["height"], b["lines"], b["rings"]) for b in got.shell["hanging_bands"]] == [(4.2, 1, 1), (5.5, 1, 0)]
        # The record stands, and hangs, where this reading has the line, for the reading after.
        assert got.shell[DELETED_KEY] == [{
            "name": "Overhead line 1", "x1": -4.2, "z1": -2.0, "x2": 3.8, "z2": -2.0, "across": 0.3, "height": 4.22,
        }]
        assert DELETED_KEY not in new and len(new[LINES]) == 3 and new["hanging_bands"][0]["lines"] == 2

        again = keep_hand_edits(got.shell, shell())
        assert len(again.shell[LINES]) == 2 and len(again.left_out) == 1 and len(again.shell[DELETED_KEY]) == 1
        bands_add_up(again.shell)

    def test_the_reading_that_has_the_ring_again_leaves_it_out(self):
        old = delete_item(shell(), RINGS, 0)[0]
        new = moved(shell(), RINGS, 0, center_x=3.1, radius=1.55)

        got = keep_hand_edits(old, new)

        assert got.shell[RINGS] == [] and got.shell[LINES] == new[LINES]
        assert [(e["name"], e["kind"]) for e in got.left_out] == [("Overhead ring 1", RINGS)]
        bands_add_up(got.shell)
        assert got.shell[DELETED_KEY] == [{
            "name": "Overhead ring 1", "center_x": 3.1, "center_z": 2.0, "radius": 1.55, "height": 4.2,
        }]
        assert keep_hand_edits(got.shell, shell()).shell[RINGS] == []

    def test_the_only_line_of_a_room_left_out_leaves_no_bands(self):
        one = {**shell(), LINES: shell()[LINES][2:], RINGS: [], "hanging_bands": shell()["hanging_bands"][1:]}
        got = keep_hand_edits(delete_item(one, LINES, 0)[0], copy.deepcopy(one))
        assert got.shell[LINES] == [] and got.shell["hanging_bands"] == []

    def test_what_is_said_of_each_kind_and_which_keys_are_sent(self):
        old = delete_item(delete_item(delete_item(shell(), "risers", 1)[0], LINES, 0)[0], RINGS, 0)[0]
        got = keep_hand_edits(old, shell())
        before, after = got.report(), got.report(applied=True)
        assert before["message"] == (
            "Will leave out 1 raised area you deleted: Booth or counter. "
            "Will leave out 1 overhead line you deleted: Overhead line 1. "
            "Will leave out 1 overhead ring you deleted: Overhead ring 1."
        )
        assert after["message"] == before["message"].replace("Will leave", "Left")
        assert after["deleted_left_out"] == [
            {"name": "Booth or counter", "kind": "booth", "overlap": 1.0},
            {"name": "Overhead line 1", "kind": LINES, "overlap": 1.0},
            {"name": "Overhead ring 1", "kind": RINGS, "overlap": 1.0},
        ]
        # "items" since slice 35.
        assert set(after) == {"areas", "kept", "added_kept", "added_replaced", "message", "deleted_left_out", "items"}
        assert (after["areas"], after["kept"], after["added_kept"], after["added_replaced"]) == (0, [], [], [])

    def test_a_record_the_reading_has_nothing_for_is_dropped_and_a_line_hung_elsewhere_is_not_it(self):
        old = delete_item(shell(), LINES, 0)[0]
        for new in (
            {**shell(), LINES: shell()[LINES][1:]},
            moved(shell(), LINES, 0, z1=-1.3, z2=-1.3),
            # Over the same floor, but more than HANG_MATCH_M above where the deleted one hung.
            moved(shell(), LINES, 0, height=4.2 + HANG_MATCH_M + 0.1, top=5.6),
        ):
            got = keep_hand_edits(old, new)
            assert got.shell is new and DELETED_KEY not in got.shell and not got.left_out
            # Slice 35: dropped, and said (until then nothing was: `not got.any`).
            assert got.lost == [{"kind": LINES, "name": "Overhead line 1", "reason": LOST_RECORD}]

    def test_a_record_of_a_line_is_never_asked_of_raised_areas_or_rings(self):
        old = delete_item(shell(), LINES, 0)[0]
        new = {**shell(), LINES: []}
        got = keep_hand_edits(old, new)
        # Slice 35: nothing is left out, and the dropped record is said (until then: `not got.any`).
        assert got.shell is new and not got.left_out
        assert got.lost == [{"kind": LINES, "name": "Overhead line 1", "reason": LOST_RECORD}]

    def test_one_deleted_and_put_in_again_by_hand_is_kept_as_the_persons(self):
        gone = delete_item(shell(), LINES, 0)[0]
        old, pipe, _ = add_item(gone, LINES, name="My truss", center_x=0.0, center_z=-2.0, length=7.0, height=3.8)

        got = keep_hand_edits(old, shell())

        assert got.shell[LINES] == [*shell()[LINES][1:], pipe]
        assert len(got.left_out) == 1 and got.overhead_added_replaced == []
        assert got.overhead_added_kept == [{"kind": LINES, "index": 2}]
        bands_add_up(got.shell)


class TestTrussesHungOneAboveTheOther:
    """Slice 34: a line or ring read more than HANG_MATCH_M from where the scan read the stored one is not it."""

    def test_the_two_share_all_of_the_plan(self):
        room = stacked()
        assert footprint_overlap(room[LINES][0], room[LINES][2]) == pytest.approx(1.0)
        assert abs(room[LINES][0]["height"] - room[LINES][2]["height"]) > HANG_MATCH_M
        assert best_match(room[LINES][0], turned_over(room)[LINES]) == (2, pytest.approx(1.0))
        assert best_match(room[LINES][2], turned_over(room)[LINES]) == (0, pytest.approx(1.0))

    def test_each_keeps_its_own_name_and_trim_whichever_is_read_first(self):
        old = edit_item(stacked(), LINES, 0, name="Low truss", height=3.9)[0]
        old = edit_item(old, LINES, 2, name="High truss", height=5.2)[0]
        new = turned_over(stacked())

        got = keep_hand_edits(old, new)

        high, low = got.shell[LINES][0], got.shell[LINES][2]
        assert (high["name"], high["height"], high["top"], high[SCAN_HEIGHT_KEY]) == ("High truss", 5.2, 5.5, 5.5)
        assert (low["name"], low["height"], low["top"], low[SCAN_HEIGHT_KEY]) == ("Low truss", 3.9, 4.2, 4.2)
        assert sorted((e["index"], tuple(e["edits"])) for e in got.overhead_kept) == [
            (0, ("name", "height")), (2, ("name", "height")),
        ]
        bands_add_up(got.shell)

        # And at the reading after, read the first way round again: matched by where the scan read them.
        again = keep_hand_edits(got.shell, stacked())
        assert [(line["name"], line["height"]) for line in again.shell[LINES]] == [
            ("Low truss", 3.9), ("Overhead line 2", 4.25), ("High truss", 5.2),
        ]

    def test_a_trim_set_onto_the_other_ones_height_is_still_this_ones(self):
        # The lower one is hung by hand at 5.4 m, beside where the scan reads the upper one.
        old = edit_item(stacked(), LINES, 0, name="Low truss", height=5.4)[0]
        got = keep_hand_edits(old, turned_over(stacked()))
        assert [(line["name"], line["height"]) for line in got.shell[LINES]] == [
            ("Overhead line 3", 5.5), ("Overhead line 2", 4.25), ("Low truss", 5.4),
        ]

    def test_a_deleted_one_takes_out_only_the_one_at_its_height(self):
        new = turned_over(stacked())
        low_gone = keep_hand_edits(delete_item(stacked(), LINES, 0)[0], new)
        assert [line["height"] for line in low_gone.shell[LINES]] == [5.5, 4.25]
        high_gone = keep_hand_edits(delete_item(stacked(), LINES, 2)[0], new)
        assert [line["height"] for line in high_gone.shell[LINES]] == [4.25, 4.2]
        for got in (low_gone, high_gone):
            assert len(got.left_out) == 1
            bands_add_up(got.shell)

    def test_one_read_within_the_tolerance_is_the_same_and_one_beyond_it_is_not(self):
        old = edit_item(shell(), LINES, 0, name="Front truss")[0]
        near = keep_hand_edits(old, moved(shell(), LINES, 0, height=4.2 + HANG_MATCH_M - 0.1, top=5.4))
        assert near.shell[LINES][0]["name"] == "Front truss"
        new = moved(shell(), LINES, 0, height=4.2 + HANG_MATCH_M + 0.1, top=5.6)
        far = keep_hand_edits(old, new)
        # Slice 35: nothing is kept, and that is said (until then nothing was: `not far.any`).
        assert far.shell is new and not far.overhead_kept
        assert [(entry["name"], entry["reason"]) for entry in far.lost] == [("Front truss", LOST_HEIGHT)]

    def test_a_ring_is_told_from_one_above_it_too(self):
        ring = shell()[RINGS][0]
        above = {**ring, "name": "Overhead ring 2", "height": 5.5, "top": 5.8}
        assert best_match(ring, [above, ring]) == (1, pytest.approx(1.0))
        assert best_match(ring, [above]) == (None, 0.0)

    def test_a_trim_set_before_the_scans_height_was_kept_is_matched_without_one(self):
        old = edit_item(shell(), LINES, 0, height=3.0)[0]
        del old[LINES][0][SCAN_HEIGHT_KEY]
        got = keep_hand_edits(old, shell())
        line = got.shell[LINES][0]
        # Kept as slice 33 kept it, and from here on the scan's height is beside it.
        assert (line["height"], line[SCAN_HEIGHT_KEY]) == (3.0, 4.2)

    def test_the_scans_height_is_written_once_and_not_for_a_line_added_by_hand(self):
        once = edit_item(shell(), LINES, 0, height=3.0)[0]
        twice = edit_item(once, LINES, 0, height=3.4)[0]
        assert twice[LINES][0][SCAN_HEIGHT_KEY] == 4.2
        assert SCAN_HEIGHT_KEY not in edit_item(shell(), LINES, 0, name="Front truss")[1]
        added, _, at = add_item(shell(), LINES, **PIPE)
        assert SCAN_HEIGHT_KEY not in edit_item(added, LINES, at, height=3.9)[1]
        assert SCAN_HEIGHT_KEY not in edit_item(shell(), "risers", 1, height=1.2)[1]

    def test_a_raised_areas_height_is_still_not_compared(self):
        old = edit_item(shell(), "risers", 1, name="The bar")[0]
        got = keep_hand_edits(old, moved(shell(), "risers", 1, height=2.9))
        assert got.shell["risers"][1]["name"] == "The bar"

    def test_a_stack_nobody_edited_comes_back_as_it_was_read(self):
        for new in (stacked(), turned_over(stacked())):
            got = keep_hand_edits(stacked(), new)
            assert got.shell is new and not got.any and got.report() is None


class TestWhatTheNewRoomDoesNotHold:

    def test_a_kept_height_above_the_new_ceiling_is_kept_and_flagged(self):
        old = edit_item(edit_item(shell(), "risers", 1, height=2.6)[0], LINES, 2, height=5.6)[0]
        new = shell()
        new["room"]["height"] = 5.0     # lower than the truss a person hung, but not than the riser

        got = keep_hand_edits(old, new)

        assert got.shell["risers"][1]["height"] == 2.6 and got.shell[LINES][2]["height"] == 5.6
        # Only what was kept is spoken of: the scan's own truss at 5.5 m... is this one, kept at 5.6 m.
        assert got.warnings == [{"kind": LINES, "index": 2, "reason": "above the ceiling"}]
        said = got.report()
        assert said["warnings"] == [
            {"kind": LINES, "index": 2, "reason": "above the ceiling", "name": "Overhead line 3"},
        ]
        assert said["message"].endswith(
            "Check Overhead line 3: it is above the ceiling of the room as this scan reads it."
        )

        new["room"]["height"] = 2.5
        low = keep_hand_edits(old, new)
        assert {(w["kind"], w["index"]) for w in low.warnings} == {("risers", 1), (LINES, 2)}

    def test_a_name_kept_on_something_the_scan_itself_reads_too_high_is_not_flagged(self):
        old = edit_item(shell(), LINES, 2, name="Back truss")[0]
        new = shell()
        new["room"]["height"] = 5.0
        got = keep_hand_edits(old, new)
        assert got.overhead_kept and got.warnings == [] and "warnings" not in got.report()

    def test_one_added_by_hand_outside_the_new_walls_is_kept_and_flagged(self):
        old = add_item(shell(), "risers", name="Podium", center_x=5.0, center_z=-4.0, width=1.0, depth=1.0, height=0.4)[0]
        old, pipe, at = add_item(old, LINES, **{**PIPE, "center_x": 4.0})
        new = shell()
        new["room"].update({"width": 8.0})      # the walls are now at 4 m either side

        got = keep_hand_edits(old, new)

        assert got.shell["risers"][2]["name"] == "Podium" and got.shell[LINES][at] == pipe
        assert got.warnings == [
            {"kind": "risers", "index": 2, "reason": "outside the walls"},
            {"kind": LINES, "index": at, "reason": "partly outside the walls"},
        ]
        assert got.report(applied=True)["message"] == (
            "1 raised area you added was kept as it is: Podium. "
            "1 overhead line you added was kept as it is: Front pipe. "
            "Check Podium: it is outside the walls of the room as this scan reads it. "
            "Check Front pipe: it is partly outside the walls of the room as this scan reads it."
        )

    def test_nothing_is_flagged_and_no_key_sent_where_the_room_holds_it_all(self):
        old = add_item(edit_item(shell(), LINES, 0, height=3.0)[0], LINES, **PIPE)[0]
        got = keep_hand_edits(old, shell())
        assert got.warnings == []
        assert set(got.report()) == {
            "areas", "kept", "added_kept", "added_replaced", "message", "overhead_kept", "overhead_added_kept",
            "items",    # since slice 35
        }


class TestNothingToCarry:

    def test_a_room_nobody_edited_comes_back_as_it_was_read(self):
        new = shell()
        for old in (shell(), None, {}, {"risers": None, LINES: "x", DELETED_KEY: "x"}):
            got = keep_hand_edits(old, new)
            assert got.shell is new and not got.any and got.report() is None

    def test_the_words_for_lines_and_rings_kept(self):
        old = edit_item(edit_item(shell(), LINES, 0, name="Front truss", height=3.0)[0], RINGS, 0, height=3.4)[0]
        got = keep_hand_edits(old, shell())
        assert got.report()["message"] == (
            "Will keep your edits on 1 overhead line: Front truss (name, hanging height). "
            "Will keep your edits on 1 overhead ring: Overhead ring 1 (hanging height)."
        )
