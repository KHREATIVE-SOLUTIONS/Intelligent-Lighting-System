"""
Hand edits kept when a room is scanned again (services/room_scan/keep_edits.py, slice 32)
=========================================================================================

A person named a raised area, set its height or its base height, or added one
the scan never saw; the scan is read again and makes a new room. What has to
hold: a stored raised area with such an edit that matches a new one (the DJ
booth mark's rule, `best_match`) gives it the name and the heights set by hand
and nothing else, the place and size staying the scan's; the new one's basis
says so again, so it holds at the reading after; of two stored that pick one
new area the greater overlap has it; one added by hand that the scan has
nothing in the place of is kept as it is at the end of the list; one the scan
overlaps is replaced and reported; a room with no hand edits comes back as the
same object with nothing to report; and neither room given is changed.
docs/ROOM_SCAN.md.
"""

import copy

from app.services.room_scan.edit import (
    BASE_BY_HAND, DJ_BOOTH_KEY, HEIGHT_BY_HAND, KIND_BY_HAND, NAME_BY_HAND, RESIZED_BY_HAND, add_item, edit_item,
)
from app.services.room_scan.keep_edits import hand_edits, keep_hand_edits
from app.services.room_scan.keep_mark import best_match, keep_dj_booth
from tests.unit.test_room_scan_keep_mark import BAR, DJ, STAGE, area, marked, room

SCAN = "scan: a level area."
RISER = area("riser", -4.0, 0.0, 2.0, 1.0)


def stored(*risers):
    """A room as the scan left it: a stage, the bar and a riser, or the raised areas given."""
    return room(*(risers or (STAGE, BAR, RISER)))


def edited(shell, index, **changes):
    """The room after Edit Room changed one raised area: the marks are the ones edit.py writes."""
    return edit_item(shell, "risers", index, **changes)[0]


def added(shell, **item):
    return add_item(shell, "risers", **item)[0]


class TestWhatSaysAFieldWasSetByHand:

    def test_the_marks_edit_room_writes(self):
        shell = stored()
        assert hand_edits(shell["risers"][2]) == ()
        assert hand_edits(edited(shell, 2, name="Drum riser")["risers"][2]) == ("name",)
        assert hand_edits(edited(shell, 2, height=0.4)["risers"][2]) == ("height",)
        assert hand_edits(edited(shell, 2, base_height=0.5)["risers"][2]) == ("base_height",)
        all_three = edited(edited(shell, 2, name="Drum riser", height=0.4), 2, base_height=0.5)["risers"][2]
        assert hand_edits(all_three) == ("name", "height", "base_height")
        for mark in (NAME_BY_HAND, HEIGHT_BY_HAND, BASE_BY_HAND, RESIZED_BY_HAND):
            assert all_three["basis"].count(mark) == 1

    def test_a_rename_leaves_it_the_scans_suggestion_and_one_to_the_same_name_says_nothing(self):
        shell = stored()
        named = edited(shell, 2, name="Drum riser")["risers"][2]
        assert named["suggested"] is True and named["basis"] == f"{SCAN} {NAME_BY_HAND}"
        assert edited(shell, 2, name="Riser", center_x=-3.0)["risers"][2]["basis"].count(NAME_BY_HAND) == 0

    def test_a_width_a_move_and_a_kind_are_not_among_them(self):
        shell = stored()
        assert hand_edits(edited(shell, 2, width=2.4)["risers"][2]) == ()
        assert hand_edits(edited(shell, 2, center_x=-3.0)["risers"][2]) == ()
        # The name a change of kind gives ("Booth or counter") is not one a person typed.
        assert hand_edits(edited(shell, 2, riser_kind="booth")["risers"][2]) == ()
        # Resized by hand alone (a room edited before the marks were written) says none of them.
        assert hand_edits({**RISER, "suggested": False, "basis": f"{SCAN} {RESIZED_BY_HAND}"}) == ()

    def test_one_added_by_hand_is_a_persons_throughout(self):
        shell = added(stored(), name="Drum riser", center_x=3.0, center_z=-1.0, width=2.0, depth=2.0, height=0.3)
        assert hand_edits(shell["risers"][3]) == ("name", "height", "base_height")
        # Added without a name it is called what its kind is: not a name to carry.
        plain = added(stored(), center_x=3.0, center_z=-1.0, width=2.0, depth=2.0, height=0.3)
        assert hand_edits(plain["risers"][3]) == ("height", "base_height")

    def test_what_is_not_a_raised_area_has_none(self):
        for odd in (None, "riser", {}, {"basis": None}):
            assert hand_edits(odd) == ()


class TestANameAndAHeightSetByHand:

    def test_a_name_set_by_hand_is_kept_on_the_same_raised_area_read_a_little_off(self):
        old = edited(stored(), 2, name="Drum riser")
        read = area("riser", -3.8, 0.1, 2.2, 1.0)
        new = stored(STAGE, BAR, read)

        got = keep_hand_edits(old, new)

        # Where and as big as the scan reads it; the name, and that it is a person's.
        assert got.shell["risers"][2] == {**read, "name": "Drum riser", "basis": f"{SCAN} {NAME_BY_HAND}"}
        assert got.shell["risers"][:2] == new["risers"][:2]
        # The mark's own rule decides which one it is, and by how much.
        place, overlap = best_match(old["risers"][2], new["risers"])
        assert place == 2 and 0.5 <= overlap < 1.0
        assert got.kept == [{"index": 2, "edits": ["name"], "overlap": round(overlap, 3)}]
        assert got.added_kept == [] and got.added_replaced == []

    def test_a_height_and_a_base_height_set_by_hand_are_kept_against_the_reading(self):
        old = edited(edited(stored(), 2, height=0.45), 0, base_height=0.2)
        new = stored(STAGE, BAR, {**RISER, "height": 0.31})

        got = keep_hand_edits(old, new)

        riser, stage = got.shell["risers"][2], got.shell["risers"][0]
        assert riser["height"] == 0.45 and riser["suggested"] is False
        assert HEIGHT_BY_HAND in riser["basis"] and RESIZED_BY_HAND in riser["basis"]
        assert riser["name"] == "Riser" and NAME_BY_HAND not in riser["basis"]
        assert stage["base_height"] == 0.2 and stage["height"] == STAGE["height"]
        assert BASE_BY_HAND in stage["basis"] and HEIGHT_BY_HAND not in stage["basis"]
        assert sorted((entry["index"], entry["edits"]) for entry in got.kept) == [(0, ["base_height"]), (2, ["height"])]

    def test_the_footprint_and_the_kind_are_the_scans(self):
        # Widened, moved and named by hand: the name is kept, the width and the place are read again.
        old = edited(stored(), 2, name="Drum riser", width=2.4, center_x=-3.9)
        got = keep_hand_edits(old, stored())
        assert got.shell["risers"][2] == {**RISER, "name": "Drum riser", "basis": f"{SCAN} {NAME_BY_HAND}"}
        # A kind set by hand matches whatever is read there (the mark's rule) but is not itself carried.
        booth = edited(stored(), 2, name="Merch", riser_kind="booth")
        again = keep_hand_edits(booth, stored())
        assert again.shell["risers"][2]["name"] == "Merch" and again.shell["risers"][2]["kind"] == "riser"
        assert KIND_BY_HAND not in again.shell["risers"][2]["basis"]

    def test_it_holds_at_the_reading_after_and_the_one_after_that(self):
        once = keep_hand_edits(edited(stored(), 2, name="Drum riser", height=0.45), stored())
        twice = keep_hand_edits(once.shell, stored())
        thrice = keep_hand_edits(twice.shell, stored())
        assert once.shell == twice.shell == thrice.shell
        kept = thrice.shell["risers"][2]
        assert (kept["name"], kept["height"]) == ("Drum riser", 0.45)
        for mark in (NAME_BY_HAND, HEIGHT_BY_HAND, RESIZED_BY_HAND):
            assert kept["basis"].count(mark) == 1

    def test_the_same_rule_as_the_mark_another_kind_or_too_far_keeps_nothing(self):
        old = edited(stored(), 2, name="Drum riser")
        # A booth read where the riser stood; and the riser read 1.5 m along (a quarter shared).
        for new in (stored(STAGE, BAR, {**RISER, "kind": "booth"}), stored(STAGE, BAR, area("riser", -2.5, 0.0, 2.0, 1.0))):
            got = keep_hand_edits(old, new)
            assert got.shell is new and not got.any and got.report() is None

    def test_two_stored_that_pick_one_new_area_the_greater_overlap_has_it(self):
        near = {**RISER, "name": "Near", "basis": f"{SCAN} {NAME_BY_HAND}"}
        nearer = {**area("riser", -3.9, 0.0, 2.0, 1.0), "name": "Nearer", "basis": f"{SCAN} {NAME_BY_HAND}"}
        new = stored(area("riser", -3.8, 0.0, 2.0, 1.0))
        for old in (stored(near, nearer), stored(nearer, near)):
            got = keep_hand_edits(old, new)
            assert got.shell["risers"][0]["name"] == "Nearer" and len(got.kept) == 1
        # Two that overlap exactly as much: the earlier.
        got = keep_hand_edits(stored(near, {**near, "name": "Second"}), new)
        assert got.shell["risers"][0]["name"] == "Near"

    def test_neither_room_is_changed(self):
        old, new = edited(stored(), 2, name="Drum riser", height=0.45), stored()
        was_old, was_new = copy.deepcopy(old), copy.deepcopy(new)
        keep_hand_edits(old, new)
        assert old == was_old and new == was_new


class TestNothingToCarry:

    def test_a_room_with_no_hand_edits_comes_back_as_it_is(self):
        new = stored()
        got = keep_hand_edits(stored(), new)
        assert got.shell is new and not got.any and got.report() is None

    def test_no_room_before_or_one_with_no_raised_areas(self):
        new = stored()
        for old in (None, {}, {"risers": None}, room()):
            got = keep_hand_edits(old, new)
            assert got.shell is new and not got.any

    def test_a_move_or_a_resize_alone_is_not_carried(self):
        new = stored()
        got = keep_hand_edits(edited(stored(), 2, center_x=-3.8, width=2.2), new)
        assert got.shell is new and not got.any


class TestARaisedAreaAddedByHand:

    DRUM = dict(name="Drum riser", center_x=3.0, center_z=-1.0, width=2.0, depth=2.0, height=0.3)

    def test_one_the_scan_has_nothing_in_the_place_of_is_kept_as_it_is(self):
        old = added(stored(), **self.DRUM)
        new = stored()

        got = keep_hand_edits(old, new)

        # At the end, so every place the scan gave is what it was; and exactly as it was stored.
        assert got.shell["risers"] == [*new["risers"], old["risers"][3]]
        assert got.added_kept == [{"index": 3}] and got.kept == [] and got.added_replaced == []
        assert got.shell["risers"][3]["added_by_hand"] is True
        # And again at the next reading.
        assert keep_hand_edits(got.shell, stored()).shell == got.shell

    def test_one_the_scan_now_overlaps_is_replaced_and_reported(self):
        old = added(stored(), **self.DRUM)
        # The scan reads something half across it: not the same footprint (under a half), but in its place.
        new = stored(STAGE, BAR, RISER, area("riser", 4.5, -1.0, 2.0, 2.0))

        got = keep_hand_edits(old, new)

        assert got.shell is new
        assert got.added_replaced == [{"name": "Drum riser", "by_index": 3}]
        assert got.added_kept == [] and got.kept == []
        said = got.report(applied=True)
        assert said["added_replaced"] == [{"name": "Drum riser", "by_index": 3, "by": "Riser"}]
        assert said["areas"] == 0 and said["message"] == (
            "Drum riser, which you added, was replaced by the scan's Riser: the scan has a raised area there now."
        )

    def test_one_that_only_touches_a_new_raised_area_is_kept(self):
        old = added(stored(), **self.DRUM)
        beside = area("riser", 5.0, -1.0, 2.0, 2.0)
        got = keep_hand_edits(old, stored(STAGE, BAR, RISER, beside))
        assert got.added_kept == [{"index": 4}] and got.added_replaced == []

    def test_one_the_scan_now_reads_gives_it_its_name_and_heights(self):
        old = added(stored(), **{**self.DRUM, "riser_kind": "booth", "base_height": 0.1})
        read = area("riser", 3.1, -1.0, 2.0, 2.0)
        new = stored(STAGE, BAR, RISER, read)

        got = keep_hand_edits(old, new)

        kept = got.shell["risers"][3]
        assert len(got.shell["risers"]) == 4 and "added_by_hand" not in kept
        assert (kept["name"], kept["height"], kept["base_height"]) == ("Drum riser", 0.3, 0.1)
        assert (kept["center_x"], kept["kind"]) == (3.1, "riser")
        assert got.kept[0]["edits"] == ["name", "height", "base_height"] and got.added_kept == []
        # Now the scan's, with the marks: the reading after keeps the same.
        assert keep_hand_edits(got.shell, new).shell == got.shell

    def test_one_added_on_top_of_the_scans_own_does_not_take_its_place(self):
        # Exactly over the scan's riser, floating at 3 m under another name. The scan's riser, read
        # again, is the scan's riser (the earlier of two that overlap as much): the added one is
        # replaced, and the riser is not renamed or lifted.
        over = {**self.DRUM, "center_x": RISER["center_x"], "center_z": RISER["center_z"], "width": 2.0, "depth": 1.0}
        old = added(stored(), **{**over, "name": "Balcony", "base_height": 3.0})
        new = stored()

        got = keep_hand_edits(old, new)

        assert got.shell is new and got.kept == [] and got.added_kept == []
        assert got.added_replaced == [{"name": "Balcony", "by_index": 2}]
        # A name set on the scan's riser itself is still kept, with the added one replaced beside it.
        both = keep_hand_edits(edited(old, 2, name="Drum riser"), new)
        assert both.shell["risers"][2]["name"] == "Drum riser" and both.shell["risers"][2]["base_height"] == 0.0
        assert both.added_replaced == [{"name": "Balcony", "by_index": 2}] and len(both.shell["risers"]) == 3

    def test_a_marked_booth_added_by_hand_and_kept_keeps_its_mark(self):
        old = added(stored(), **{**self.DRUM, "name": "DJ", "riser_kind": "booth", "is_dj_booth": True})
        got = keep_hand_edits(old, stored())
        mark = keep_dj_booth(old, got.shell)
        assert mark.place == 3 and mark.overlap == 1.0 and not mark.dropped
        assert marked(mark.shell) == [3] and mark.message == "The DJ booth mark was kept on DJ."


class TestTheMarkAfterTheEdits:

    def test_the_marks_sentence_uses_the_kept_name(self):
        old = edited(room(STAGE, BAR, DJ), 2, name="DJ", is_dj_booth=True)
        got = keep_hand_edits(old, room(STAGE, BAR, DJ))
        mark = keep_dj_booth(old, got.shell)
        assert mark.place == 2 and mark.message == "The DJ booth mark was kept on DJ."
        assert mark.shell["risers"][2] == {**DJ, "name": "DJ", "basis": f"{SCAN} {NAME_BY_HAND}", DJ_BOOTH_KEY: True}

    def test_a_kind_set_by_hand_on_the_marked_one_is_still_kept_and_said(self):
        old = edited(stored(), 2, riser_kind="booth", is_dj_booth=True, height=0.9)
        got = keep_hand_edits(old, stored())
        mark = keep_dj_booth(old, got.shell)
        assert (mark.kind_kept, mark.scan_kind) == ("booth", "riser")
        kept = mark.shell["risers"][2]
        assert (kept["kind"], kept["name"], kept["height"]) == ("booth", "Booth or counter", 0.9)
        assert got.report(mark.shell)["kept"] == [
            {"index": 2, "edits": ["height"], "overlap": 1.0, "name": "Booth or counter"},
        ]


class TestWhatAnAnswerSays:

    def test_a_preview_and_an_apply(self):
        old = added(edited(edited(stored(), 2, name="Drum riser", height=0.45), 0, base_height=0.2), **{
            "name": "Podium", "center_x": 3.0, "center_z": -1.0, "width": 1.0, "depth": 1.0, "height": 0.5,
        })
        got = keep_hand_edits(old, stored())

        before = got.report()
        assert before == {
            "areas": 2,
            "kept": [
                {"index": 0, "edits": ["base_height"], "overlap": 1.0, "name": "Stage"},
                {"index": 2, "edits": ["name", "height"], "overlap": 1.0, "name": "Drum riser"},
            ],
            "added_kept": [{"index": 3, "name": "Podium"}],
            "added_replaced": [],
            "message": (
                "Will keep your edits on 2 raised areas: Stage (base height), Drum riser (name, height). "
                "1 raised area you added will be kept as it is: Podium."
            ),
            # Slice 35: the same, one thing at a time.
            "items": [
                {"kind": "raised area", "name": "Stage", "outcome": "kept your edits"},
                {"kind": "raised area", "name": "Drum riser", "outcome": "kept your edits"},
                {"kind": "raised area", "name": "Podium", "outcome": "added by hand, kept"},
            ],
        }
        after = got.report(applied=True)
        assert {**after, "message": None} == {**before, "message": None}
        assert after["message"] == (
            "Kept your edits on 2 raised areas: Stage (base height), Drum riser (name, height). "
            "1 raised area you added was kept as it is: Podium."
        )
