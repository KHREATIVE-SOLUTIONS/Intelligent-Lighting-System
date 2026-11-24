"""
"This one is the DJ's booth" (services/room_scan/edit.py, slice 28)
===================================================================

A scan calls a bar counter a "Booth or counter" too, so a person marks the
raised area the DJ plays at. What has to hold: at most one raised area is
marked at a time; the mark is on the raised area itself, so it keeps its
place when another is deleted and goes out with its own; a raised area made
another kind loses it unless the same edit sets it; a raised area that is not
marked stores no key, so a room nobody marked is exactly what it was; the
shell given is never changed in place; and a mark that cannot be made says
why. docs/ROOM_SCAN.md.
"""

import copy

import pytest

from app.services.room_scan.edit import (
    DJ_BOOTH_KEY, ShellEditError, add_item, delete_item, dj_booth_place, edit_item, edit_words, marked_dj_booth,
    one_dj_booth,
)


def shell():
    """A 12 m by 10 m room: a stage, a bar the scan called a booth, the DJ's own booth, a riser and a truss."""
    return {
        "source": "scan",
        "suggested": True,
        "room": {"width": 12.0, "depth": 10.0, "height": 6.0, "suggested": True},
        "risers": [
            {"center_x": 0.0, "center_z": -3.5, "width": 6.0, "depth": 3.0, "height": 0.6, "base_height": 0.0,
             "name": "Stage", "kind": "stage", "suggested": True, "basis": "scan: a level area."},
            {"center_x": 4.0, "center_z": 3.0, "width": 2.0, "depth": 1.0, "height": 1.0, "base_height": 0.0,
             "name": "Booth or counter", "kind": "booth", "suggested": True, "basis": "scan: a level area."},
            {"center_x": -4.0, "center_z": 0.0, "width": 1.0, "depth": 2.0, "height": 1.0, "base_height": 0.0,
             "name": "Booth or counter", "kind": "booth", "suggested": True, "basis": "scan: a level area."},
            {"center_x": 0.0, "center_z": -3.5, "width": 2.0, "depth": 2.0, "height": 0.3, "base_height": 0.6,
             "name": "Riser", "kind": "riser", "suggested": True, "basis": "scan: a level area."},
        ],
        "truss_lines": [
            {"name": "Overhead line 1", "x1": -4.0, "z1": -2.0, "x2": 4.0, "z2": -2.0, "height": 4.2, "top": 4.5,
             "length": 8.0, "across": 0.3, "axis": "x", "heading_deg": 0.0, "suggested": True, "basis": "scan: a bar."},
        ],
        "truss_rings": [],
        "hanging_bands": [
            {"height": 4.2, "top": 4.5, "lines": 1, "rings": 0, "suggested": True,
             "basis": "scan: long thin objects hanging clear of the walls at this height"},
        ],
        "scan": {"file": "club.obj", "format": "obj"},
    }


def marked(found: dict) -> list:
    """The places of every raised area that carries the mark."""
    return [place for place, item in enumerate(found["risers"]) if DJ_BOOTH_KEY in item]


class TestMarking:

    def test_a_room_nobody_marked_has_no_dj_booth_and_no_key(self):
        assert dj_booth_place(shell()) is None and marked(shell()) == []
        # Nor has no room at all, a room with no list, or a list with something that is not an item in it.
        for odd in (None, {}, {"risers": None}, {"risers": "stage"}, {"risers": [None, 3, "booth"]}):
            assert dj_booth_place(odd) is None

    def test_marking_one_stores_true_on_it_and_changes_nothing_else(self):
        before = shell()
        kept = copy.deepcopy(before)

        edited, item = edit_item(before, "risers", 2, is_dj_booth=True)

        assert item == {**kept["risers"][2], DJ_BOOTH_KEY: True}
        assert edited == {**kept, "risers": [item if place == 2 else area for place, area in enumerate(kept["risers"])]}
        assert dj_booth_place(edited) == 2 and marked(edited) == [2]
        # It is still the scan's guess of a booth: the mark says whose it is, not where or how big.
        assert item["suggested"] is True and item["basis"] == "scan: a level area."
        # The shell given is the caller's column as it was loaded: never changed in place.
        assert before == kept

    def test_marking_another_takes_the_mark_off_the_first(self):
        first, _ = edit_item(shell(), "risers", 1, is_dj_booth=True)
        kept = copy.deepcopy(first)

        second, item = edit_item(first, "risers", 2, is_dj_booth=True)

        assert marked(second) == [2] and dj_booth_place(second) == 2 and item[DJ_BOOTH_KEY] is True
        # The one that was the booth is exactly what the scan found again: no key, not a false one.
        assert second["risers"][1] == shell()["risers"][1]
        assert first == kept and marked(first) == [1]

    def test_any_kind_of_raised_area_can_be_the_dj_booth(self):
        # A DJ who plays on the stage, in a room whose only "booth" is the bar.
        for place in range(4):
            edited, item = edit_item(shell(), "risers", place, is_dj_booth=True)
            assert dj_booth_place(edited) == place and item["kind"] == shell()["risers"][place]["kind"]

    def test_false_takes_the_mark_off_and_leaves_no_key(self):
        is_booth, _ = edit_item(shell(), "risers", 2, is_dj_booth=True)

        edited, item = edit_item(is_booth, "risers", 2, is_dj_booth=False)

        assert edited == shell() and item == shell()["risers"][2]
        # False on one that is not marked changes nothing, and does not unmark the one that is.
        other, untouched = edit_item(is_booth, "risers", 1, is_dj_booth=False)
        assert other == is_booth and untouched == is_booth["risers"][1]

    def test_marking_the_marked_one_again_is_no_change(self):
        is_booth, was = edit_item(shell(), "risers", 2, is_dj_booth=True)
        again, item = edit_item(is_booth, "risers", 2, is_dj_booth=True)
        assert again == is_booth and item == was
        assert edit_words("risers", is_booth["risers"][2], item) is None

    def test_a_mark_goes_with_a_rename_a_move_and_a_resize_in_one_edit(self):
        edited, item = edit_item(
            shell(), "risers", 2, name="DJ booth", center_x=-3.5, width=1.5, height=1.1, is_dj_booth=True,
        )
        assert (item["name"], item["center_x"], item["width"], item["height"]) == ("DJ booth", -3.5, 1.5, 1.1)
        assert item[DJ_BOOTH_KEY] is True and dj_booth_place(edited) == 2
        # And a later move of the booth keeps it the booth.
        moved, later = edit_item(edited, "risers", 2, center_z=1.0)
        assert later[DJ_BOOTH_KEY] is True and dj_booth_place(moved) == 2

    def test_only_a_stored_true_is_a_mark(self):
        found = shell()
        for odd in (1, "true", "yes", [True], {"a": 1}, 0, False, None):
            found["risers"][1][DJ_BOOTH_KEY] = odd
            assert not marked_dj_booth(found["risers"][1]) and dj_booth_place(found) is None
        # A shell written by hand with two: the first is the one, and marking either leaves one.
        found["risers"][1][DJ_BOOTH_KEY] = True
        found["risers"][3][DJ_BOOTH_KEY] = True
        assert dj_booth_place(found) == 1
        edited, _ = edit_item(found, "risers", 0, is_dj_booth=True)
        assert marked(edited) == [0]


class TestAChangeOfKind:

    def test_a_booth_made_another_kind_is_no_longer_the_dj_booth(self):
        is_booth, _ = edit_item(shell(), "risers", 2, is_dj_booth=True)

        edited, item = edit_item(is_booth, "risers", 2, riser_kind="riser")

        assert item["kind"] == "riser" and DJ_BOOTH_KEY not in item
        assert dj_booth_place(edited) is None and marked(edited) == []
        assert edit_words("risers", is_booth["risers"][2], item) == (
            "Booth or counter made a riser and no longer marked as the DJ booth"
        )

    def test_the_kind_it_already_is_keeps_the_mark(self):
        is_booth, was = edit_item(shell(), "risers", 2, is_dj_booth=True)
        edited, item = edit_item(is_booth, "risers", 2, riser_kind="booth")
        assert edited == is_booth and item == was

    def test_a_change_of_kind_that_sets_the_mark_in_the_same_edit_keeps_it(self):
        is_booth, _ = edit_item(shell(), "risers", 2, is_dj_booth=True)

        edited, item = edit_item(is_booth, "risers", 2, riser_kind="stage", is_dj_booth=True)

        assert item["kind"] == "stage" and item[DJ_BOOTH_KEY] is True and dj_booth_place(edited) == 2
        assert edit_words("risers", is_booth["risers"][2], item) == "Booth or counter made a stage"
        # And one that was not the booth is made a kind and the booth together.
        both, made = edit_item(shell(), "risers", 3, riser_kind="booth", is_dj_booth=True)
        assert made["kind"] == "booth" and dj_booth_place(both) == 3
        assert edit_words("risers", shell()["risers"][3], made) == "Riser made a booth and marked as the DJ booth"

    def test_another_raised_area_changing_kind_leaves_the_booth_alone(self):
        is_booth, _ = edit_item(shell(), "risers", 2, is_dj_booth=True)
        edited, _ = edit_item(is_booth, "risers", 1, riser_kind="riser")
        assert dj_booth_place(edited) == 2 and marked(edited) == [2]


class TestWords:

    def test_what_a_mark_did_is_said_for_the_undo(self):
        found = shell()
        is_booth, item = edit_item(found, "risers", 2, is_dj_booth=True)
        assert edit_words("risers", found["risers"][2], item) == "Booth or counter marked as the DJ booth"
        _, off = edit_item(is_booth, "risers", 2, is_dj_booth=False)
        assert edit_words("risers", is_booth["risers"][2], off) == "Booth or counter no longer marked as the DJ booth"
        _, both = edit_item(found, "risers", 0, name="Main stage", is_dj_booth=True)
        assert edit_words("risers", found["risers"][0], both) == "Stage renamed and marked as the DJ booth"


class TestDeletingAndAdding:

    def test_the_mark_keeps_its_raised_area_when_one_before_it_is_deleted(self):
        is_booth, _ = edit_item(shell(), "risers", 2, is_dj_booth=True)

        edited, removed = delete_item(is_booth, "risers", 0)

        assert removed["kind"] == "stage" and DJ_BOOTH_KEY not in removed
        # Everything after the stage moved up a place, and the booth is still the booth there.
        assert dj_booth_place(edited) == 1 and edited["risers"][1] == is_booth["risers"][2]
        assert dj_booth_place(is_booth) == 2

    def test_a_deleted_booth_takes_its_mark_with_it(self):
        is_booth, _ = edit_item(shell(), "risers", 2, is_dj_booth=True)

        edited, removed = delete_item(is_booth, "risers", 2)

        assert removed[DJ_BOOTH_KEY] is True
        # Nothing is promoted in its place: no raised area is the DJ's until somebody says so.
        assert dj_booth_place(edited) is None and marked(edited) == []

    def test_one_added_as_the_booth_takes_the_mark_from_any_other(self):
        is_booth, _ = edit_item(shell(), "risers", 1, is_dj_booth=True)
        kept = copy.deepcopy(is_booth)

        edited, item, index = add_item(
            is_booth, "risers", center_x=2.0, center_z=-1.0, width=2.0, depth=1.0, height=1.0,
            riser_kind="booth", is_dj_booth=True,
        )

        assert index == 4 and item[DJ_BOOTH_KEY] is True and item["added_by_hand"] is True
        assert marked(edited) == [4] and dj_booth_place(edited) == 4
        assert edited["risers"][1] == shell()["risers"][1]
        assert is_booth == kept

    def test_one_added_without_the_mark_or_with_false_leaves_the_booth_where_it_is(self):
        is_booth, _ = edit_item(shell(), "risers", 1, is_dj_booth=True)
        for flag in (None, False):
            edited, item, _ = add_item(
                is_booth, "risers", center_x=2.0, center_z=-1.0, width=2.0, depth=1.0, height=1.0,
                riser_kind="booth", is_dj_booth=flag,
            )
            assert DJ_BOOTH_KEY not in item and dj_booth_place(edited) == 1


class TestRefusals:

    def test_a_mark_that_is_not_true_or_false_is_refused(self):
        for wrong in (1, 0, "true", "yes", 2.5, float("inf"), [], {}):
            with pytest.raises(ShellEditError) as refused:
                edit_item(shell(), "risers", 2, is_dj_booth=wrong)
            assert refused.value.status == 422 and "true or false" in refused.value.detail
            with pytest.raises(ShellEditError) as refused:
                add_item(
                    shell(), "risers", center_x=0.0, center_z=0.0, width=1.0, depth=1.0, height=0.5,
                    is_dj_booth=wrong,
                )
            assert refused.value.status == 422 and "true or false" in refused.value.detail

    def test_a_truss_or_a_ring_cannot_be_the_dj_booth(self):
        for flag in (True, False):
            with pytest.raises(ShellEditError) as refused:
                edit_item(shell(), "truss_lines", 0, is_dj_booth=flag)
            assert refused.value.status == 422
            assert refused.value.detail == "Only a raised area can be the DJ booth; this is a overhead line."
        with pytest.raises(ShellEditError) as refused:
            add_item(shell(), "truss_rings", center_x=0.0, center_z=0.0, radius=1.0, height=4.0, is_dj_booth=True)
        assert refused.value.status == 422 and "Only a raised area can be the DJ booth" in refused.value.detail

    def test_a_raised_area_that_is_not_there_cannot_be_marked(self):
        for place in (4, 99, -1):
            with pytest.raises(ShellEditError) as refused:
                edit_item(shell(), "risers", place, is_dj_booth=True)
            assert refused.value.status == 404
        with pytest.raises(ShellEditError) as refused:
            edit_item(None, "risers", 0, is_dj_booth=True)
        assert refused.value.status == 404


class TestOneDjBooth:
    """A stack carried with the raised area under it is written back from the room as it was."""

    def test_a_carried_area_written_back_with_its_old_mark_loses_it(self):
        found = shell()
        found["risers"][0][DJ_BOOTH_KEY] = True
        found["risers"][3][DJ_BOOTH_KEY] = True
        kept = copy.deepcopy(found)

        edited = one_dj_booth(found, 0)

        assert marked(edited) == [0] and edited["risers"][3] == shell()["risers"][3]
        assert found == kept

    def test_a_room_with_nothing_to_take_off_is_given_back_as_it_is(self):
        found = shell()
        assert one_dj_booth(found, 0) is found
        found["risers"][3][DJ_BOOTH_KEY] = True
        # The edited area is not the booth, so the one that is keeps its mark.
        assert one_dj_booth(found, 0) is found
        assert one_dj_booth(found, 3) is found
        for place in (-1, 4):
            assert one_dj_booth(found, place) is found
