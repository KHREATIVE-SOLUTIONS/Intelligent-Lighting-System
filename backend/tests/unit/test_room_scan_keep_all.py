"""
Keep all, and the carry-over list that outlives the dialog (docs/ROOM_SCAN.md, slice 37)
========================================================================================

A room whose line was named and trimmed by hand and whose ring was trimmed by
hand, read again with the line at another height and the ring to one side:
two losses, two `carry_over` entries, each with the id of its warning.
`carry_all` puts both back or neither; `pending_carry.py` keeps the open ones
with the stored room and drops each when it would be stale.
"""

import copy

import pytest

from app.services.room_scan.carry_over import carry_all
from app.services.room_scan.edit import ShellEditError, delete_item, edit_item
from app.services.room_scan.edit_undo import pop_step, push_step
from app.services.room_scan.keep_edits import keep_hand_edits
from app.services.room_scan.pending_carry import (
    PENDING_KEY, after_delete, pending, prune, to_store, with_pending, without_targets,
)
from tests.unit.test_room_scan_edit import shell
from tests.unit.test_room_scan_keep_overhead import LINES, RINGS, moved


def reading():
    return moved(moved(shell(), LINES, 0, height=5.3, top=5.6), RINGS, 0, center_x=4.5)


def two_lost():
    """(the room as the scan left it with its two entries stored, the applied answer's hand_edits)."""
    old = edit_item(edit_item(shell(), LINES, 0, name="Front truss", height=3.0)[0], RINGS, 0, height=3.4)[0]
    report = keep_hand_edits(old, reading()).report(applied=True)
    got = keep_hand_edits(old, reading())
    return with_pending(got.shell, to_store(report)), report


class TestTheIds:

    def test_each_entry_names_its_warning_by_id_not_by_place(self):
        _, report = two_lost()
        entries = report["carry_over"]
        assert len(entries) == 2
        by_id = {warning["id"]: warning for warning in report["warnings"] if "id" in warning}
        assert sorted(by_id) == sorted(entry["warning_id"] for entry in entries) == ["lost-0", "lost-1"]
        for entry in entries:
            # The old key stays, and points at the same warning.
            assert report["warnings"][entry["warning"]] is by_id[entry["warning_id"]]
            assert by_id[entry["warning_id"]]["name"] in (entry["old_name"], entry["new_name"])

    def test_the_stored_entries_carry_the_sentence_of_their_warning(self):
        room, report = two_lost()
        stored = pending(room)
        assert [{k: v for k, v in e.items() if k != "message"} for e in stored] == report["carry_over"]
        words = {w["id"]: w["message"] for w in report["warnings"] if "id" in w}
        assert all(entry["message"] == words[entry["warning_id"]] for entry in stored)

    def test_a_room_with_nothing_to_put_back_stores_no_key(self):
        assert PENDING_KEY not in with_pending(shell(), [])
        assert PENDING_KEY not in with_pending(with_pending(shell(), [{"kind": LINES}]), [])
        assert pending(None) == [] and pending({PENDING_KEY: "x"}) == []


class TestKeepAll:

    def test_both_are_put_back_and_the_room_given_is_not_changed(self):
        room, _ = two_lost()
        before = copy.deepcopy(room)
        carried_room, carried, moves, areas, labels = carry_all(room, pending(room))
        assert room == before
        assert (carried_room[LINES][0]["name"], carried_room[LINES][0]["height"]) == ("Front truss", 3.0)
        assert carried_room[RINGS][0]["height"] == 3.4
        assert [entry["changed"] for entry in carried] == [True, True]
        assert sorted(entry["warning_id"] for entry in carried) == ["lost-0", "lost-1"]
        assert len(labels) == 2 and moves == [] and areas == []

    def test_one_stale_entry_refuses_them_all(self):
        room, _ = two_lost()
        before = copy.deepcopy(room)
        good, stale = pending(room)
        with pytest.raises(ShellEditError) as e:
            carry_all(room, [good, {**stale, "new_name": "Not what it is called"}])
        assert e.value.status == 409 and room == before
        # Stale first or last, the same.
        with pytest.raises(ShellEditError):
            carry_all(room, [{**good, "new_index": 9}, stale])

    def test_one_that_is_not_an_entry_refuses_them_all(self):
        room, _ = two_lost()
        good, other = pending(room)
        with pytest.raises(ShellEditError) as e:
            carry_all(room, [good, {**other, "edits": []}])
        assert e.value.status == 422

    def test_two_for_the_same_item_are_a_422_that_names_both(self):
        room, _ = two_lost()
        line = next(entry for entry in pending(room) if entry["kind"] == LINES)
        other = {**line, "old_name": "Back truss", "warning_id": "lost-9"}
        with pytest.raises(ShellEditError) as e:
            carry_all(room, [line, other])
        assert e.value.status == 422
        assert "Front truss" in e.value.detail and "Back truss" in e.value.detail
        assert line["new_name"] in e.value.detail

    @pytest.mark.parametrize("entries", [None, [], "all", [1]])
    def test_a_list_that_is_not_one_is_a_422(self, entries):
        with pytest.raises(ShellEditError) as e:
            carry_all(shell(), entries)
        assert e.value.status == 422

    def test_a_fixture_two_of_them_would_move_is_a_422(self):
        room, _ = two_lost()

        def both_move_it(before, kind, index, edited, item):
            return edited, [{"rig_fixture_id": 5}], []

        with pytest.raises(ShellEditError) as e:
            carry_all(room, pending(room), both_move_it)
        assert e.value.status == 422 and "more than one" in e.value.detail


class TestTheListIsDroppedWhenStale:

    def test_a_renamed_or_re_trimmed_item_loses_its_entry_and_the_other_stays(self):
        room, _ = two_lost()
        for change in ({"name": "Mid truss"}, {"height": 4.0}):
            edited = prune(room, edit_item(room, LINES, 0, **change)[0])
            assert [entry["kind"] for entry in pending(edited)] == [RINGS]

    def test_a_moved_item_keeps_its_entry(self):
        room, _ = two_lost()
        edited = edit_item(room, RINGS, 0, center_x=4.0)[0]
        assert prune(room, edited) is edited and len(pending(edited)) == 2

    def test_a_deleted_item_loses_its_entry_and_those_after_it_move_up(self):
        room, _ = two_lost()
        ring = next(entry for entry in pending(room) if entry["kind"] == RINGS)
        later = {**ring, "kind": LINES, "new_index": 2, "warning_id": "x"}
        room = with_pending(room, pending(room) + [later])
        gone = after_delete(delete_item(room, LINES, 0)[0], LINES, 0)
        assert [(entry["kind"], entry["new_index"]) for entry in pending(gone)] == [(RINGS, 0), (LINES, 1)]

    def test_carried_entries_go_and_every_other_for_the_same_item(self):
        room, _ = two_lost()
        line = next(entry for entry in pending(room) if entry["kind"] == LINES)
        room = with_pending(room, pending(room) + [{**line, "warning_id": "twin"}])
        left = without_targets(room, [(LINES, 0)])
        assert [entry["kind"] for entry in pending(left)] == [RINGS]

    def test_the_room_read_again_is_a_new_list(self):
        room, _ = two_lost()
        again = keep_hand_edits(room, reading())
        # The stored list is not carried onto the new reading: the new answer's is stored, or none.
        assert PENDING_KEY not in again.shell

    def test_an_undo_brings_the_entry_back(self):
        room, _ = two_lost()
        renamed = prune(room, edit_item(room, LINES, 0, name="Mid truss")[0])
        record = push_step(None, room, "Overhead line 1 renamed")
        _, step = pop_step(record)
        assert len(pending(renamed)) == 1 and pending(step["shell"]) == pending(room)
