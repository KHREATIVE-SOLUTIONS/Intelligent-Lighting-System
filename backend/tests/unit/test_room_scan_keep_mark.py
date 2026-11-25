"""
The DJ booth mark kept when a room is scanned again (services/room_scan/keep_mark.py, slice 30)
===============================================================================================

A person marked one raised area as the DJ's booth; the scan is read again and
makes a new room whose raised areas carry no mark. What has to hold: the mark
is kept on the raised area of the new reading that is the same kind and
overlaps the marked one by an intersection over union of at least 0.5; of two
that do, the one that overlaps more, and of two that overlap as much, the
earlier; with none, the mark is dropped and that is said; a mark is never
given to another kind or to something that only stands near; a booth at a
heading is compared as it stands; at most one raised area is marked
afterwards; and neither shell given is changed. docs/ROOM_SCAN.md.
"""

import copy

import pytest

from app.services.room_scan.edit import DJ_BOOTH_KEY, KIND_BY_HAND, dj_booth_place
from app.services.room_scan.keep_mark import MATCH_IOU, footprint_overlap, keep_dj_booth, kind_set_by_hand


def area(kind, x, z, width, depth, heading=None, name=None, **more):
    item = {
        "center_x": x, "center_z": z, "width": width, "depth": depth, "height": 1.0, "base_height": 0.0,
        "name": name or {"stage": "Stage", "riser": "Riser", "booth": "Booth or counter"}[kind],
        "kind": kind, "suggested": True, "basis": "scan: a level area.",
    }
    if heading is not None:
        item["heading_deg"] = heading
    item.update(more)
    return item


def room(*risers):
    return {
        "source": "scan", "suggested": True,
        "room": {"width": 12.0, "depth": 10.0, "height": 6.0, "suggested": True},
        "risers": [copy.deepcopy(r) for r in risers],
        "truss_lines": [], "truss_rings": [], "hanging_bands": [],
        "scan": {"file": "club.obj", "format": "obj"},
    }


def marked(shell: dict) -> list:
    return [place for place, item in enumerate(shell["risers"]) if DJ_BOOTH_KEY in item]


STAGE = area("stage", 0.0, -3.5, 6.0, 3.0)
BAR = area("booth", 4.0, 3.0, 2.0, 1.0)
DJ = area("booth", -4.0, 0.0, 2.0, 1.0)


def old_room(booth=DJ):
    """The room as it was stored: a stage, the bar, and the DJ's booth, marked by hand."""
    return room(STAGE, BAR, {**booth, DJ_BOOTH_KEY: True, "name": "DJ"})


class TestOverlap:

    def test_the_same_footprint_is_one_and_one_apart_is_nothing(self):
        assert footprint_overlap(DJ, DJ) == pytest.approx(1.0)
        assert footprint_overlap(DJ, BAR) == 0.0
        # Touching along an edge shares no area.
        assert footprint_overlap(DJ, area("booth", -2.0, 0.0, 2.0, 1.0)) == pytest.approx(0.0)

    def test_a_shift_is_the_shared_part_over_the_two_together(self):
        # 2 x 1 moved 0.5 m along its width: 1.5 shared of 2.5 covered.
        assert footprint_overlap(DJ, area("booth", -3.5, 0.0, 2.0, 1.0)) == pytest.approx(1.5 / 2.5)
        # One inside the other: the small one's area over the big one's.
        assert footprint_overlap(STAGE, area("riser", 0.0, -3.5, 2.0, 2.0)) == pytest.approx(4.0 / 18.0)

    def test_the_same_rectangle_stored_a_quarter_turn_round_is_the_same_footprint(self):
        assert footprint_overlap(DJ, area("booth", -4.0, 0.0, 1.0, 2.0, heading=90.0)) == pytest.approx(1.0)
        assert footprint_overlap(DJ, area("booth", -4.0, 0.0, 1.0, 2.0, heading=-90.0)) == pytest.approx(1.0)

    def test_a_square_turned_an_eighth_is_the_octagon_they_share(self):
        # Two unit squares on one centre, 45 degrees apart: a regular octagon of area 2(sqrt 2 - 1).
        shared = 2.0 * (2.0 ** 0.5 - 1.0)
        one, other = area("booth", 1.0, 1.0, 1.0, 1.0), area("booth", 1.0, 1.0, 1.0, 1.0, heading=45.0)
        assert footprint_overlap(one, other) == pytest.approx(shared / (2.0 - shared))
        assert footprint_overlap(other, one) == pytest.approx(shared / (2.0 - shared))

    def test_which_way_a_heading_turns_is_told_apart(self):
        # A long thin area at +30 and the same at -30 cross like an X: they share only the middle.
        one, other = area("booth", 0.0, 0.0, 4.0, 0.5, heading=30.0), area("booth", 0.0, 0.0, 4.0, 0.5, heading=-30.0)
        assert footprint_overlap(one, one) == pytest.approx(1.0)
        assert footprint_overlap(one, other) < 0.2

    @pytest.mark.parametrize("broken", [
        None, "booth", {}, {**DJ, "width": 0.0}, {**DJ, "depth": -1.0}, {**DJ, "center_x": None},
        {**DJ, "center_z": float("nan")}, {**DJ, "width": True}, {k: v for k, v in DJ.items() if k != "depth"},
    ])
    def test_an_area_with_no_footprint_overlaps_nothing(self, broken):
        assert footprint_overlap(DJ, broken) == 0.0
        assert footprint_overlap(broken, DJ) == 0.0


class TestKeepingTheMark:

    def test_the_same_booth_read_again_keeps_the_mark(self):
        old = old_room()
        # Read 10 cm off and a little bigger, as a second scan would; the scan's own name and no mark.
        new = room(STAGE, BAR, area("booth", -3.9, 0.05, 2.1, 1.05))
        was_old, was_new = copy.deepcopy(old), copy.deepcopy(new)

        kept = keep_dj_booth(old, new)

        assert (kept.was_marked, kept.place, kept.dropped) == (True, 2, False)
        assert kept.overlap >= MATCH_IOU
        assert marked(kept.shell) == [2] and dj_booth_place(kept.shell) == 2
        # The mark and nothing else: the name set by hand is not carried, and it is still the scan's guess.
        assert kept.shell["risers"][2] == {**new["risers"][2], DJ_BOOTH_KEY: True}
        assert kept.shell["risers"][:2] == new["risers"][:2]
        assert {k: v for k, v in kept.shell.items() if k != "risers"} == {k: v for k, v in new.items() if k != "risers"}
        assert kept.message == "The DJ booth mark was kept on Booth or counter."
        # Neither room given is changed.
        assert old == was_old and new == was_new and kept.shell is not new

    def test_the_mark_goes_where_the_booth_is_now_in_the_list(self):
        # The new reading lists the same areas in another order.
        kept = keep_dj_booth(old_room(), room(DJ, STAGE, BAR))
        assert kept.place == 0 and marked(kept.shell) == [0] and kept.overlap == pytest.approx(1.0)

    def test_with_no_match_the_mark_is_dropped_and_that_is_said(self):
        # The booth is not in the new reading at all: only the stage and the bar.
        new = room(STAGE, BAR)
        kept = keep_dj_booth(old_room(), new)
        assert (kept.was_marked, kept.place, kept.dropped, kept.overlap) == (True, None, True, None)
        assert kept.shell is new and marked(kept.shell) == []
        assert kept.message == (
            "The DJ booth mark was dropped: no raised area in this scan stands where DJ did. "
            "Mark the DJ booth again in Edit Room."
        )

    def test_a_booth_that_only_stands_near_does_not_take_the_mark(self):
        # 2 x 1 moved 0.8 m along: 1.2 shared of 2.8, under a half. It is not given to the nearest.
        near = area("booth", -3.2, 0.0, 2.0, 1.0)
        assert footprint_overlap(DJ, near) == pytest.approx(1.2 / 2.8)
        kept = keep_dj_booth(old_room(), room(STAGE, BAR, near))
        assert kept.dropped and marked(kept.shell) == []

    def test_exactly_a_half_is_enough(self):
        # 2 x 1 moved 2/3 m along: 4/3 shared of 8/3 covered, a half. 0.7 m is just under, 0.6 m just over.
        half = area("booth", -4.0 + 2.0 / 3.0, 0.0, 2.0, 1.0)
        assert footprint_overlap(DJ, half) == pytest.approx(0.5)
        just_under = area("booth", -4.0 + 0.7, 0.0, 2.0, 1.0)
        assert keep_dj_booth(old_room(), room(STAGE, just_under)).dropped
        assert keep_dj_booth(old_room(), room(STAGE, area("booth", -4.0 + 0.6, 0.0, 2.0, 1.0))).place == 1
        assert MATCH_IOU == 0.5
        # Exactly a half, with no rounding in it: 4 x 1 on the same middle shares 2 of the 4 it covers.
        twice = area("booth", -4.0, 0.0, 4.0, 1.0)
        assert footprint_overlap(DJ, twice) == 0.5
        exact = keep_dj_booth(old_room(), room(STAGE, twice))
        assert exact.place == 1 and exact.overlap == 0.5

    def test_another_kind_in_the_same_place_does_not_take_the_mark(self):
        # The scan now calls what stands there a riser. Same footprint, not the same kind: dropped, and said.
        kept = keep_dj_booth(old_room(), room(STAGE, BAR, {**DJ, "kind": "riser", "name": "Riser"}))
        assert kept.dropped and marked(kept.shell) == []

    def test_a_kind_changed_by_hand_is_the_kind_that_is_matched(self):
        # A booth whose stored basis does not say its kind was set by hand (a shell written before that
        # was recorded, or by another client): read again as a riser, nothing says it is the same one,
        # so the mark is dropped. One whose basis does say so is kept: TestAKindSetByHand, slice 31.
        by_hand = old_room()
        scanned_again = room(STAGE, BAR, {**DJ, "kind": "riser", "name": "Riser"})
        assert keep_dj_booth(by_hand, scanned_again).dropped
        # Left a riser and marked as one, it is kept.
        as_riser = room(STAGE, BAR, {**DJ, "kind": "riser", DJ_BOOTH_KEY: True})
        assert keep_dj_booth(as_riser, scanned_again).place == 2

    def test_a_marked_stage_is_kept_as_any_kind_is(self):
        old = room({**STAGE, DJ_BOOTH_KEY: True}, BAR, area("riser", 0.0, -3.5, 2.0, 2.0, base_height=1.0))
        # The riser on the stage shares its middle; it is another kind and a ninth of the overlap.
        new = room(area("riser", 0.0, -3.5, 2.0, 2.0, base_height=1.0), area("stage", 0.1, -3.4, 6.0, 3.2), BAR)
        kept = keep_dj_booth(old, new)
        assert kept.place == 1 and marked(kept.shell) == [1]

    def test_of_two_candidates_the_one_that_overlaps_more_keeps_it(self):
        # The new reading has two booths over the old one: the first shares 60%, the second 82%.
        lesser = area("booth", -3.5, 0.0, 2.0, 1.0)      # 1.5 / 2.5
        better = area("booth", -3.8, 0.0, 2.0, 1.0)      # 1.8 / 2.2
        assert footprint_overlap(DJ, lesser) == pytest.approx(0.6)
        assert footprint_overlap(DJ, better) == pytest.approx(1.8 / 2.2)

        kept = keep_dj_booth(old_room(), room(STAGE, lesser, better))
        assert kept.place == 2 and marked(kept.shell) == [2] and kept.overlap == pytest.approx(0.818, abs=1e-3)
        # Whichever comes first in the list.
        again = keep_dj_booth(old_room(), room(STAGE, better, lesser))
        assert again.place == 1 and marked(again.shell) == [1]

    def test_of_two_that_overlap_as_much_the_earlier_keeps_it(self):
        left, right = area("booth", -4.5, 0.0, 2.0, 1.0), area("booth", -3.5, 0.0, 2.0, 1.0)
        assert footprint_overlap(DJ, left) == footprint_overlap(DJ, right) == pytest.approx(0.6)
        assert keep_dj_booth(old_room(), room(left, right)).place == 0
        assert keep_dj_booth(old_room(), room(right, left)).place == 0
        twins = keep_dj_booth(old_room(), room(STAGE, DJ, DJ))
        assert twins.place == 1 and marked(twins.shell) == [1]

    def test_a_booth_at_a_heading_still_matches(self):
        turned = area("booth", -3.0, 1.0, 2.4, 1.2, heading=30.0)
        old = old_room(turned)
        # Read again a little off and 3 degrees further round.
        new = room(STAGE, BAR, area("booth", -2.95, 1.05, 2.4, 1.2, heading=33.0))
        kept = keep_dj_booth(old, new)
        assert kept.place == 2 and kept.overlap > 0.8 and marked(kept.shell) == [2]
        assert kept.shell["risers"][2]["heading_deg"] == 33.0

    def test_a_booth_at_a_heading_matches_itself_stored_the_other_way_round(self):
        old = old_room(area("booth", -3.0, 1.0, 2.4, 1.2, heading=30.0))
        # The same rectangle with its sides named the other way: 1.2 x 2.4 at -60.
        kept = keep_dj_booth(old, room(STAGE, area("booth", -3.0, 1.0, 1.2, 2.4, heading=-60.0)))
        assert kept.place == 1 and kept.overlap == pytest.approx(1.0)

    def test_a_booth_swung_across_itself_is_not_the_same_booth(self):
        old = old_room(area("booth", -3.0, 1.0, 3.0, 0.6, heading=30.0))
        kept = keep_dj_booth(old, room(STAGE, area("booth", -3.0, 1.0, 3.0, 0.6, heading=-30.0)))
        assert kept.dropped

    def test_a_turned_booth_and_a_square_reading_of_it_match_when_they_share_enough(self):
        # A scan that reads a booth turned 8 degrees as standing square has the same booth.
        old = old_room(area("booth", -3.0, 1.0, 2.0, 1.0, heading=8.0))
        kept = keep_dj_booth(old, room(STAGE, area("booth", -3.0, 1.0, 2.0, 1.0)))
        assert kept.place == 1 and 0.5 < kept.overlap < 1.0


HAND_BASIS = f"scan: a level area. {KIND_BY_HAND}"


def hand_booth(**more):
    """The DJ's booth as Edit Room leaves a scan's riser made a booth and marked: the basis says so."""
    return {**DJ, "name": "DJ", "suggested": False, "basis": HAND_BASIS, DJ_BOOTH_KEY: True, **more}


class TestAKindSetByHand:
    """Slice 31: a kind a person set is kept with the mark, whatever the scan reads there."""

    def test_what_says_a_kind_was_set_by_hand(self):
        assert kind_set_by_hand(hand_booth()) is True
        assert kind_set_by_hand({**DJ, "added_by_hand": True, "basis": "Added by hand."}) is True
        # The scan's own, and one only moved or resized by hand.
        assert kind_set_by_hand(DJ) is False
        assert kind_set_by_hand({**DJ, "suggested": False, "basis": "scan: a level area. Moved by hand."}) is False
        assert kind_set_by_hand({**DJ, "added_by_hand": "yes"}) is False
        for odd in (None, "booth", {}, {"basis": None}):
            assert kind_set_by_hand(odd) is False

    @pytest.mark.parametrize("read_as", ["riser", "stage"])
    def test_a_booth_set_by_hand_read_as_a_riser_or_stage_keeps_the_mark_and_the_kind(self, read_as):
        old = room(BAR, hand_booth())
        reading = area(read_as, -3.9, 0.05, 2.1, 1.05)
        new = room(BAR, reading)
        was_old, was_new = copy.deepcopy(old), copy.deepcopy(new)

        kept = keep_dj_booth(old, new)

        assert (kept.place, kept.dropped, kept.kind_kept, kept.scan_kind) == (1, False, "booth", read_as)
        # The reading's place and size; the person's kind, said in the basis; and the name of that kind,
        # not "Riser": a name typed by hand is not carried, as before.
        assert kept.shell["risers"][1] == {
            **reading, "kind": "booth", "name": "Booth or counter", "suggested": False,
            "basis": HAND_BASIS, DJ_BOOTH_KEY: True,
        }
        assert kept.shell["risers"][0] == BAR and marked(kept.shell) == [1]
        assert kept.message == (
            "The DJ booth mark was kept on Booth or counter. It stays a booth, as set by hand: "
            f"this scan reads it as a {read_as}."
        )
        assert old == was_old and new == was_new

    def test_it_is_kept_at_the_reading_after_that_too(self):
        reading = room(STAGE, BAR, area("riser", -4.0, 0.0, 2.0, 1.0))
        once = keep_dj_booth(room(STAGE, BAR, hand_booth()), reading)
        twice = keep_dj_booth(once.shell, reading)
        thrice = keep_dj_booth(twice.shell, reading)
        assert once.place == twice.place == thrice.place == 2
        assert once.shell == twice.shell == thrice.shell
        assert thrice.shell["risers"][2]["kind"] == "booth" and thrice.kind_kept == "booth"
        # Said once in the basis, however often it is read.
        assert thrice.shell["risers"][2]["basis"].count(KIND_BY_HAND) == 1

    def test_the_overlap_is_still_asked_of_it(self):
        # Set by hand or not, one that only stands near is not the same raised area.
        near = area("riser", -3.2, 0.0, 2.0, 1.0)
        kept = keep_dj_booth(room(STAGE, hand_booth()), room(STAGE, near))
        assert kept.dropped and kept.kind_kept is None and kept.shell["risers"][1] == near
        # Exactly a half is enough, as for any other.
        twice = area("riser", -4.0, 0.0, 4.0, 1.0)
        assert keep_dj_booth(room(STAGE, hand_booth()), room(STAGE, twice)).place == 1

    def test_the_greatest_overlap_takes_it_whatever_its_kind(self):
        lesser = area("booth", -3.5, 0.0, 2.0, 1.0)      # 0.6, and already a booth
        better = area("riser", -3.8, 0.0, 2.0, 1.0)      # 0.818
        kept = keep_dj_booth(room(hand_booth()), room(lesser, better))
        assert kept.place == 1 and kept.kind_kept == "booth" and kept.shell["risers"][1]["kind"] == "booth"
        assert kept.shell["risers"][0] == lesser

    def test_a_reading_that_agrees_with_the_hand_is_left_the_scans(self):
        # The scan now reads a booth there itself: the mark and nothing else, and nothing to say of the kind.
        new = room(STAGE, DJ)
        kept = keep_dj_booth(room(STAGE, hand_booth()), new)
        assert kept.place == 1 and kept.kind_kept is None and kept.scan_kind is None
        assert kept.shell["risers"][1] == {**DJ, DJ_BOOTH_KEY: True}
        assert kept.message == "The DJ booth mark was kept on Booth or counter."

    def test_a_name_the_scan_did_not_give_is_left_alone(self):
        # Only the scan's own word for its kind ("Riser") is swapped for the kept kind's.
        new = room(area("riser", -4.0, 0.0, 2.0, 1.0, name="Platform 2"))
        kept = keep_dj_booth(room(hand_booth()), new)
        assert kept.shell["risers"][0]["name"] == "Platform 2" and kept.shell["risers"][0]["kind"] == "booth"

    def test_any_kind_set_by_hand_is_kept_and_so_is_one_added_by_hand(self):
        # A scan's booth a person made a riser, marked; the scan reads a booth there again.
        old = room({**DJ, "kind": "riser", "name": "Riser", "basis": HAND_BASIS, DJ_BOOTH_KEY: True})
        kept = keep_dj_booth(old, room(DJ))
        assert (kept.place, kept.kind_kept, kept.scan_kind) == (0, "riser", "booth")
        assert kept.shell["risers"][0]["name"] == "Riser"
        # A booth a person added where the scan had found nothing, which a better scan now reads as a riser.
        added = room({**DJ, "added_by_hand": True, "suggested": False, "basis": "Added by hand.", DJ_BOOTH_KEY: True})
        again = keep_dj_booth(added, room(area("riser", -4.0, 0.0, 2.0, 1.0)))
        assert again.place == 0 and again.shell["risers"][0]["kind"] == "booth"
        assert KIND_BY_HAND in again.shell["risers"][0]["basis"]
        assert "added_by_hand" not in again.shell["risers"][0]


class TestWhatAPreviewSays:
    """Slice 31: the same answer, worded for before the apply."""

    def test_a_mark_that_will_be_kept(self):
        kept = keep_dj_booth(old_room(), room(STAGE, BAR, area("booth", -3.9, 0.0, 2.0, 1.0)))
        assert kept.preview() == {
            "kept": True, "dropped": False, "index": 2, "name": "Booth or counter",
            "overlap": kept.overlap, "kind_kept": None,
            "message": "The DJ booth mark will be kept on Booth or counter.",
        }

    def test_a_mark_that_will_be_dropped(self):
        assert keep_dj_booth(old_room(), room(STAGE, BAR)).preview() == {
            "kept": False, "dropped": True, "index": None, "name": None, "overlap": None, "kind_kept": None,
            "message": (
                "The DJ booth mark will be dropped: no raised area in this scan stands where DJ does. "
                "Mark the DJ booth again in Edit Room after applying."
            ),
        }

    def test_a_kind_that_will_be_kept_with_it(self):
        said = keep_dj_booth(room(hand_booth()), room(area("riser", -4.0, 0.0, 2.0, 1.0))).preview()
        assert (said["kept"], said["index"], said["name"], said["kind_kept"]) == (True, 0, "Booth or counter", "booth")
        assert said["message"] == (
            "The DJ booth mark will be kept on Booth or counter. It stays a booth, as set by hand: "
            "this scan reads it as a riser."
        )

    def test_a_room_with_no_mark_has_nothing_to_say(self):
        assert keep_dj_booth(room(STAGE, DJ), room(STAGE, DJ)).preview() is None
        assert keep_dj_booth(None, room(STAGE, DJ)).preview() is None


class TestNothingToKeep:

    @pytest.mark.parametrize("old", [None, {}, {"risers": None}, room(STAGE, BAR, DJ), room()])
    def test_a_room_with_no_mark_leaves_the_new_reading_as_it_is(self, old):
        new = room(STAGE, BAR, DJ)
        kept = keep_dj_booth(old, new)
        assert kept.shell is new and marked(new) == []
        assert (kept.was_marked, kept.place, kept.dropped, kept.message) == (False, None, False, None)

    def test_only_a_stored_true_is_a_mark(self):
        old = room(STAGE, {**DJ, DJ_BOOTH_KEY: "yes"})
        assert keep_dj_booth(old, room(STAGE, DJ)).was_marked is False

    def test_a_room_that_marked_two_keeps_the_first(self):
        old = room({**BAR, DJ_BOOTH_KEY: True}, {**DJ, DJ_BOOTH_KEY: True})
        kept = keep_dj_booth(old, room(DJ, BAR))
        assert kept.place == 1 and marked(kept.shell) == [1]

    def test_only_one_is_marked_even_if_the_reading_came_marked(self):
        # A scan marks nothing, but should a shell ever arrive marked, the kept mark is the only one.
        new = room({**STAGE, DJ_BOOTH_KEY: True}, BAR, DJ)
        kept = keep_dj_booth(old_room(), new)
        assert kept.place == 2 and marked(kept.shell) == [2] and marked(new) == [0]
        gone = keep_dj_booth(old_room(), room({**STAGE, DJ_BOOTH_KEY: True}, BAR))
        assert gone.dropped and marked(gone.shell) == []

    def test_a_marked_area_with_no_footprint_is_dropped_not_guessed(self):
        old = room(STAGE, {**DJ, "width": None, DJ_BOOTH_KEY: True})
        kept = keep_dj_booth(old, room(STAGE, DJ))
        assert kept.dropped and marked(kept.shell) == []

    def test_a_new_room_with_no_raised_areas_drops_it(self):
        kept = keep_dj_booth(old_room(), room())
        assert kept.dropped and kept.shell["risers"] == []
        odd = {"source": "scan", "risers": None}
        assert keep_dj_booth(old_room(), odd).dropped

    def test_an_unnamed_booth_is_still_spoken_of(self):
        old = room({**DJ, "name": "", DJ_BOOTH_KEY: True})
        assert "where The raised area did" in keep_dj_booth(old, room(STAGE)).message
