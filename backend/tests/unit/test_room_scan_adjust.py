"""
Resizing, raising, turning and adding in a stored room, and undoing an edit
===========================================================================

(services/room_scan/edit.py, services/room_scan/edit_undo.py)

What has to hold: a size, a height or a heading changes that one thing and
nothing else in the shell; the shell given is never changed in place; the
whole of a resized, turned or added item stays inside the room's box and its
margin, and one too big to is refused; a value that is not a number, or is
outside its limits, is refused; a truss that is raised, lowered or added is
counted in the hanging-height bands, which never hold an empty band or a count
that is not the room's; an added item is marked as a person's; and each undo
step puts back the whole room as it stood. docs/ROOM_SCAN.md.
"""

import copy
import math

import pytest

from app.services.room_scan.edit import (
    ADDED_BY_HAND, BAND_BASIS_HAND, ITEMS_MAX, MOVED_BY_HAND, RESIZED_BY_HAND, ShellEditError,
    add_item, clean_heading, delete_item, edit_item, edit_words, height_limits, item_centre, line_heading,
)
from app.services.room_scan.edit_undo import STEPS_MAX, pop_step, push_step, undo_summary
from app.services.room_scan.suggest import suggest_positions

from tests.unit.test_room_scan_edit import shell, without


def bands_add_up(found: dict) -> None:
    """Every truss and ring is counted in one band, and no band is empty."""
    bands = found.get("hanging_bands") or []
    assert sum(band.get("lines", 0) for band in bands) == len(found.get("truss_lines") or [])
    assert sum(band.get("rings", 0) for band in bands) == len(found.get("truss_rings") or [])
    assert all(band.get("lines", 0) + band.get("rings", 0) > 0 for band in bands)
    heights = [band["height"] for band in bands]
    assert heights == sorted(heights)


def refused(call, status: int = 422) -> str:
    with pytest.raises(ShellEditError) as error:
        call()
    assert error.value.status == status, error.value.detail
    return error.value.detail


class TestResize:

    def test_a_raised_area_takes_a_new_width_and_depth_about_its_middle(self):
        before = shell()
        edited, item = edit_item(before, "risers", 0, width=8.0, depth=2.5)

        assert (item["width"], item["depth"]) == (8.0, 2.5)
        assert (item["center_x"], item["center_z"], item["height"]) == (0.0, -3.5, 0.6)
        assert item["suggested"] is False and item["basis"].endswith(RESIZED_BY_HAND)
        assert MOVED_BY_HAND not in item["basis"]
        assert without(edited, "risers", 0) == without(before, "risers", 0)
        assert before == shell()

    def test_one_side_given_keeps_the_other(self):
        _, item = edit_item(shell(), "risers", 1, width=3.0)
        assert (item["width"], item["depth"]) == (3.0, 1.0)

    def test_a_size_it_already_has_changes_nothing(self):
        before = shell()
        edited, item = edit_item(before, "risers", 0, width=6.0, depth=3.0, height=0.6)
        assert edited == before and item["suggested"] is True
        edited, _ = edit_item(before, "truss_lines", 1, length=5.0, heading_deg=36.9, height=4.25)
        assert edited == before
        edited, _ = edit_item(before, "truss_rings", 0, radius=1.5, height=4.2)
        assert edited == before

    def test_a_line_takes_a_new_length_about_its_middle_along_its_heading(self):
        before = shell()
        edited, item = edit_item(before, "truss_lines", 1, length=10.0)

        # 3-4-5: it ran from (-3, 1) to (1, 4), and now twice as far either side of (-1, 2.5).
        assert (item["x1"], item["z1"], item["x2"], item["z2"]) == (-5.0, -0.5, 3.0, 5.5)
        assert item["length"] == 10.0 and item["axis"] == "angled" and item["heading_deg"] == 36.9
        assert item_centre("truss_lines", item) == pytest.approx((-1.0, 2.5))
        assert item["suggested"] is False and RESIZED_BY_HAND in item["basis"] and MOVED_BY_HAND not in item["basis"]
        assert without(edited, "truss_lines", 1) == without(before, "truss_lines", 1)

    def test_a_ring_takes_a_new_radius(self):
        before = shell()
        edited, item = edit_item(before, "truss_rings", 0, radius=2.25)
        assert item["radius"] == 2.25 and (item["center_x"], item["center_z"]) == (3.0, 2.0)
        assert RESIZED_BY_HAND in item["basis"]
        assert without(edited, "truss_rings", 0) == without(before, "truss_rings", 0)

    def test_resized_twice_says_so_once(self):
        once, _ = edit_item(shell(), "risers", 0, width=7.0)
        _, item = edit_item(once, "risers", 0, width=8.0)
        assert item["basis"].count(RESIZED_BY_HAND) == 1

    def test_the_whole_of_a_resized_item_is_kept_inside_the_room_and_its_margin(self):
        # The room is 12 m across: with the margin, 8 m either side of the middle.
        _, item = edit_item(shell(), "risers", 1, width=10.0)
        # It stood at 4.0 and would have reached 9.0: its middle is brought in to 3.0.
        assert item["center_x"] == 3.0 and item["width"] == 10.0
        assert MOVED_BY_HAND in item["basis"] and RESIZED_BY_HAND in item["basis"]

        _, ring = edit_item(shell(), "truss_rings", 0, radius=6.0)
        # 10 m deep: 7 m either side, so a 6 m ring's middle is within 1 m of the middle.
        assert (ring["center_x"], ring["center_z"]) == (2.0, 1.0)

        _, line = edit_item(shell(), "truss_lines", 0, length=15.0, center_x=3.0)
        assert (line["x1"], line["x2"]) == (-7.0, 8.0)

    def test_a_plain_move_still_holds_only_the_middle(self):
        _, item = edit_item(shell(), "risers", 0, center_x=50.0)
        assert item["center_x"] == 8.0

    def test_a_size_too_big_for_the_room_is_refused(self):
        assert "16 m" in refused(lambda: edit_item(shell(), "risers", 0, width=16.5))
        assert "14 m" in refused(lambda: edit_item(shell(), "risers", 0, depth=14.2))
        refused(lambda: edit_item(shell(), "truss_rings", 0, radius=7.1))
        refused(lambda: edit_item(shell(), "truss_lines", 0, length=16.1))
        # Up and down the room there is less of it.
        refused(lambda: edit_item(shell(), "truss_lines", 0, length=15.0, heading_deg=90))
        # Exactly the room and its margin fits.
        _, item = edit_item(shell(), "risers", 0, width=16.0)
        assert (item["width"], item["center_x"]) == (16.0, 0.0)

    @pytest.mark.parametrize("kind, index, sizes", [
        ("risers", 0, {"width": 0.29}), ("risers", 0, {"depth": 0.0}), ("risers", 0, {"width": -2.0}),
        ("risers", 0, {"width": 100.5}),
        ("truss_lines", 0, {"length": 0.49}), ("truss_lines", 0, {"length": -1.0}),
        ("truss_rings", 0, {"radius": 0.29}), ("truss_rings", 0, {"radius": 0}),
    ])
    def test_a_size_outside_its_limits_is_refused(self, kind, index, sizes):
        assert "must be between" in refused(lambda: edit_item(shell(), kind, index, **sizes))

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, "2", True])
    def test_a_size_that_is_not_a_number_is_refused(self, value):
        for call in (
            lambda: edit_item(shell(), "risers", 0, width=value),
            lambda: edit_item(shell(), "truss_lines", 0, length=value),
            lambda: edit_item(shell(), "truss_lines", 0, heading_deg=value),
            lambda: edit_item(shell(), "truss_rings", 0, radius=value),
            lambda: edit_item(shell(), "truss_rings", 0, height=value),
        ):
            assert "must be a number" in refused(call)

    @pytest.mark.parametrize("kind, sizes", [
        ("risers", {"length": 2.0}), ("risers", {"radius": 2.0}), ("risers", {"heading_deg": 45.0}),
        ("truss_lines", {"width": 2.0}), ("truss_lines", {"radius": 2.0}),
        ("truss_rings", {"length": 2.0}), ("truss_rings", {"heading_deg": 45.0}), ("truss_rings", {"depth": 2.0}),
    ])
    def test_a_size_the_item_does_not_have_is_refused(self, kind, sizes):
        assert "It takes:" in refused(lambda: edit_item(shell(), kind, 0, **sizes))

    def test_an_item_with_no_position_cannot_be_resized_but_can_be_raised(self):
        broken = shell()
        del broken["truss_lines"][0]["x2"]
        assert "resized or turned" in refused(lambda: edit_item(broken, "truss_lines", 0, length=4.0), 409)
        _, item = edit_item(broken, "truss_lines", 0, height=4.4)
        assert item["height"] == 4.4

    def test_a_refused_edit_leaves_the_shell_given_alone(self):
        before = shell()
        refused(lambda: edit_item(before, "risers", 0, name="Main stage", width=99.0))
        assert before == shell()


class TestHeading:

    def test_a_line_turns_about_its_middle_and_keeps_its_length(self):
        before = shell()
        edited, item = edit_item(before, "truss_lines", 0, heading_deg=90)

        # 8 m across the room at z -2, now 8 m from upstage to downstage through the same middle.
        assert (item["x1"], item["z1"], item["x2"], item["z2"]) == (0.0, -6.0, 0.0, 2.0)
        assert (item["axis"], item["heading_deg"], item["length"]) == ("z", 90.0, 8.0)
        assert RESIZED_BY_HAND in item["basis"] and MOVED_BY_HAND not in item["basis"]
        assert without(edited, "truss_lines", 0) == without(before, "truss_lines", 0)
        bands_add_up(edited)

    def test_an_angle_is_written_from_stage_right_to_stage_left(self):
        _, item = edit_item(shell(), "truss_lines", 2, heading_deg=-30)
        assert item["x1"] < item["x2"] and item["z1"] > item["z2"]
        assert item["axis"] == "angled" and item["heading_deg"] == -30.0
        assert math.hypot(item["x2"] - item["x1"], item["z2"] - item["z1"]) == pytest.approx(8.0, abs=0.002)
        assert line_heading(item) == pytest.approx(-30.0, abs=0.05)
        assert item_centre("truss_lines", item) == pytest.approx((0.0, 0.0), abs=0.001)

    @pytest.mark.parametrize("given, stored, axis", [
        (0, 0.0, "x"), (180, 0.0, "x"), (-180, 0.0, "x"), (360, 0.0, "x"), (1.5, 1.5, "x"),
        (90, 90.0, "z"), (-90, 90.0, "z"), (270, 90.0, "z"), (88.5, 88.5, "z"), (-88.5, -88.5, "z"),
        (45, 45.0, "angled"), (135, -45.0, "angled"), (-135, 45.0, "angled"), (225, 45.0, "angled"),
    ])
    def test_a_heading_is_stored_as_a_line_has_one(self, given, stored, axis):
        assert clean_heading(given) == stored
        _, item = edit_item(shell(), "truss_lines", 2, heading_deg=given, length=4.0)
        assert (item["heading_deg"], item["axis"]) == (stored, axis)

    def test_a_heading_beyond_a_full_turn_is_refused(self):
        assert "360" in refused(lambda: edit_item(shell(), "truss_lines", 0, heading_deg=361))
        refused(lambda: edit_item(shell(), "truss_lines", 0, heading_deg=-720))

    def test_a_turned_line_is_held_inside_the_room(self):
        # 8 m long at z 4, turned up and down a room 10 m deep: it reaches 7 m, so its middle comes to 3.
        moved, _ = edit_item(shell(), "truss_lines", 0, center_z=4.0)
        _, item = edit_item(moved, "truss_lines", 0, heading_deg=90)
        assert (item["z1"], item["z2"]) == (-1.0, 7.0)

    def test_a_line_with_both_ends_at_one_point_needs_a_length_to_turn(self):
        stub = shell()
        stub["truss_lines"][0].update({"x1": 1.0, "z1": 1.0, "x2": 1.0, "z2": 1.0})
        assert "too short to turn" in refused(lambda: edit_item(stub, "truss_lines", 0, heading_deg=45))
        _, item = edit_item(stub, "truss_lines", 0, length=4.0)
        # It keeps the heading it was stored with.
        assert (item["x1"], item["z1"], item["x2"], item["z2"]) == (-1.0, 1.0, 3.0, 1.0)

    def test_a_move_a_turn_and_a_length_together(self):
        _, item = edit_item(shell(), "truss_lines", 0, center_x=1.0, center_z=0.0, length=6.0, heading_deg=90)
        assert (item["x1"], item["z1"], item["x2"], item["z2"]) == (1.0, -3.0, 1.0, 3.0)
        assert MOVED_BY_HAND in item["basis"] and RESIZED_BY_HAND in item["basis"]


class TestHeight:

    def test_a_deck_is_raised_and_nothing_else_changes(self):
        before = shell()
        edited, item = edit_item(before, "risers", 0, height=0.9)
        assert item["height"] == 0.9 and item["base_height"] == 0.0
        assert item["suggested"] is False and RESIZED_BY_HAND in item["basis"]
        assert without(edited, "risers", 0) == without(before, "risers", 0)

    def test_a_deck_has_limits(self):
        assert height_limits(shell(), "risers") == (0.05, 3.0)
        refused(lambda: edit_item(shell(), "risers", 0, height=0.04))
        refused(lambda: edit_item(shell(), "risers", 0, height=3.01))
        refused(lambda: edit_item(shell(), "risers", 0, height=-1.0))
        _, item = edit_item(shell(), "risers", 0, height=3.0)
        assert item["height"] == 3.0

    def test_a_deck_stays_under_a_low_ceiling(self):
        low = shell()
        low["room"]["height"] = 2.4
        low["risers"][0]["base_height"] = 0.4
        assert height_limits(low, "risers", low["risers"][0]) == (0.05, 2.0)
        assert "between 0.05 m and 2 m" in refused(lambda: edit_item(low, "risers", 0, height=2.1))

    def test_a_truss_takes_its_top_with_it(self):
        _, item = edit_item(shell(), "truss_lines", 2, height=5.0)
        assert (item["height"], item["top"]) == (5.0, 5.3)
        _, ring = edit_item(shell(), "truss_rings", 0, height=3.0)
        assert (ring["height"], ring["top"]) == (3.0, 3.3)

    def test_a_truss_hangs_between_half_a_metre_and_the_ceiling(self):
        assert height_limits(shell(), "truss_lines") == (0.5, 6.0)
        refused(lambda: edit_item(shell(), "truss_lines", 0, height=0.49))
        assert "between 0.5 m and 6 m" in refused(lambda: edit_item(shell(), "truss_lines", 0, height=6.01))
        refused(lambda: edit_item(shell(), "truss_rings", 0, height=9.0))
        _, item = edit_item(shell(), "truss_lines", 0, height=6.0)
        assert item["height"] == 6.0

    def test_a_room_with_no_height_has_a_limit_of_its_own(self):
        open_air = shell()
        del open_air["room"]["height"]
        assert height_limits(open_air, "truss_rings") == (0.5, 30.0)
        refused(lambda: edit_item(open_air, "truss_rings", 0, height=30.5))

    def test_a_truss_raised_within_its_band_stays_counted_there(self):
        edited, _ = edit_item(shell(), "truss_lines", 0, height=4.4)
        assert [(b["height"], b["lines"], b["rings"]) for b in edited["hanging_bands"]] == [(4.2, 2, 1), (5.5, 1, 0)]
        bands_add_up(edited)

    def test_a_truss_raised_into_another_band_is_counted_there(self):
        edited, _ = edit_item(shell(), "truss_lines", 0, height=5.6)
        assert [(b["height"], b["lines"], b["rings"]) for b in edited["hanging_bands"]] == [(4.2, 1, 1), (5.5, 2, 0)]
        bands_add_up(edited)

    def test_a_truss_set_where_nothing_hangs_starts_a_band_of_its_own(self):
        edited, item = edit_item(shell(), "truss_lines", 0, height=3.0)
        assert [(b["height"], b["top"], b["lines"], b["rings"]) for b in edited["hanging_bands"]] == [
            (3.0, 3.3, 1, 0), (4.2, 4.5, 1, 1), (5.5, 5.8, 1, 0),
        ]
        made = edited["hanging_bands"][0]
        assert made["suggested"] is False and made["basis"] == BAND_BASIS_HAND
        assert item["top"] == 3.3
        bands_add_up(edited)

    def test_the_last_truss_of_a_band_takes_the_band_with_it(self):
        edited, _ = edit_item(shell(), "truss_lines", 2, height=4.3)
        assert [(b["height"], b["lines"], b["rings"]) for b in edited["hanging_bands"]] == [(4.2, 3, 1)]
        bands_add_up(edited)

        alone, _ = edit_item(shell(), "truss_lines", 2, height=2.5)
        assert [b["height"] for b in alone["hanging_bands"]] == [2.5, 4.2]
        bands_add_up(alone)

    def test_a_ring_lowered_out_of_its_band(self):
        edited, _ = edit_item(shell(), "truss_rings", 0, height=3.5)
        assert [(b["height"], b["lines"], b["rings"]) for b in edited["hanging_bands"]] == [
            (3.5, 0, 1), (4.2, 2, 0), (5.5, 1, 0),
        ]
        bands_add_up(edited)

    def test_a_size_or_a_move_leaves_the_bands_alone(self):
        before = shell()
        for edited in (
            edit_item(before, "truss_lines", 0, length=6.0)[0],
            edit_item(before, "truss_rings", 0, radius=2.0)[0],
            edit_item(before, "truss_lines", 1, center_x=1.0)[0],
            edit_item(before, "risers", 0, height=1.0)[0],
        ):
            assert edited["hanging_bands"] == before["hanging_bands"]

    def test_a_shell_stored_with_no_bands_gets_one_for_a_raised_truss(self):
        old = shell()
        del old["hanging_bands"]
        edited, _ = edit_item(old, "truss_lines", 0, height=3.0)
        assert [(b["height"], b["lines"]) for b in edited["hanging_bands"]] == [(3.0, 1)]

    def test_a_row_is_hung_at_the_height_a_ring_was_set_to(self):
        """What counting the band is for: suggest.py hangs a row with no truss across the room at the lowest band."""
        class Light:
            def __init__(self, n):
                self.id, self.name, self.group_name = n, f"Wash {n}", None
                self.position_x, self.position_y, self.position_z = 20.0 + n, 5.0, 20.0
                self.tags = ["position_source:template", "position_unconfirmed"]
                self.dmx_address, self.universe, self.is_active = n, 0, True

        found = shell()
        found["truss_lines"] = []
        found["hanging_bands"] = [dict(found["hanging_bands"][0], lines=0, rings=1)]
        lowered, _ = edit_item(found, "truss_rings", 0, height=3.4)
        assert [b["height"] for b in lowered["hanging_bands"]] == [3.4]
        # Whatever a suggestion does with the lights, it no longer names the height the ring left.
        moves, _ = suggest_positions([Light(n) for n in range(2)], lowered)
        assert not any(move.to_position[1] == pytest.approx(4.2) for move in moves)


class TestAdd:

    def test_a_stage_is_added_at_the_end_of_its_list(self):
        before = shell()
        edited, item, index = add_item(
            before, "risers", name=" Drum  riser ", center_x=1.0, center_z=-1.0,
            width=2.0, depth=2.0, height=0.3, riser_kind="riser",
        )
        assert index == 2 and edited["risers"][2] is item
        assert item == {
            "center_x": 1.0, "center_z": -1.0, "width": 2.0, "depth": 2.0, "height": 0.3, "base_height": 0.0,
            "name": "Drum riser", "kind": "riser", "suggested": False, "added_by_hand": True, "basis": ADDED_BY_HAND,
        }
        assert edited["risers"][:2] == before["risers"]
        assert {k: v for k, v in edited.items() if k != "risers"} == {k: v for k, v in before.items() if k != "risers"}
        assert before == shell()

    @pytest.mark.parametrize("riser_kind, name", [
        ("stage", "Stage"), ("riser", "Riser"), ("booth", "Booth or counter"), (None, "Riser"),
    ])
    def test_a_raised_area_with_no_name_is_called_what_it_is(self, riser_kind, name):
        _, item, _ = add_item(
            shell(), "risers", center_x=0, center_z=0, width=2, depth=2, height=0.5, riser_kind=riser_kind,
        )
        assert item["name"] == name and item["kind"] == (riser_kind or "riser")

    def test_a_truss_is_added_across_the_room_and_counted(self):
        before = shell()
        edited, item, index = add_item(before, "truss_lines", center_x=0.0, center_z=3.0, length=6.0, height=4.3)
        assert index == 3
        assert item == {
            "name": "Overhead line 4", "x1": -3.0, "z1": 3.0, "x2": 3.0, "z2": 3.0, "height": 4.3, "top": 4.6,
            "length": 6.0, "across": 0.3, "axis": "x", "heading_deg": 0.0,
            "suggested": False, "added_by_hand": True, "basis": ADDED_BY_HAND,
        }
        assert [(b["height"], b["lines"]) for b in edited["hanging_bands"]] == [(4.2, 3), (5.5, 1)]
        bands_add_up(edited)
        assert edited["truss_lines"][:3] == before["truss_lines"]

    def test_a_truss_added_at_a_heading(self):
        _, item, _ = add_item(shell(), "truss_lines", center_x=0, center_z=0, length=4.0, height=3.0, heading_deg=90)
        assert (item["x1"], item["z1"], item["x2"], item["z2"], item["axis"]) == (0.0, -2.0, 0.0, 2.0, "z")

    def test_a_ring_is_added_where_nothing_hangs_and_starts_a_band(self):
        edited, item, index = add_item(
            shell(), "truss_rings", name="Mirror ball ring", center_x=-2.0, center_z=1.0, radius=1.0, height=3.0,
        )
        assert index == 1
        assert item == {
            "name": "Mirror ball ring", "center_x": -2.0, "center_z": 1.0, "radius": 1.0,
            "height": 3.0, "top": 3.3, "across": 0.3,
            "suggested": False, "added_by_hand": True, "basis": ADDED_BY_HAND,
        }
        assert [(b["height"], b["lines"], b["rings"], b["suggested"]) for b in edited["hanging_bands"]] == [
            (3.0, 0, 1, False), (4.2, 2, 1, True), (5.5, 1, 0, True),
        ]
        bands_add_up(edited)

    def test_a_ring_is_added_to_a_shell_stored_before_rings_were_read(self):
        old = shell()
        del old["truss_rings"]
        for band in old["hanging_bands"]:
            del band["rings"]
        edited, _, index = add_item(old, "truss_rings", center_x=0, center_z=0, radius=1.0, height=4.3)
        assert index == 0 and len(edited["truss_rings"]) == 1
        assert edited["hanging_bands"][0]["rings"] == 1

    def test_an_added_item_can_then_be_edited_and_deleted(self):
        added, _, index = add_item(shell(), "truss_lines", center_x=0, center_z=3, length=6, height=3.0)
        raised, item = edit_item(added, "truss_lines", index, height=5.6, name="Back truss")
        assert item["added_by_hand"] is True and item["name"] == "Back truss"
        bands_add_up(raised)
        gone, _ = delete_item(raised, "truss_lines", index)
        assert gone["truss_lines"] == shell()["truss_lines"] and gone["hanging_bands"] == shell()["hanging_bands"]

    def test_the_whole_of_an_added_item_is_held_inside_the_room(self):
        _, item, _ = add_item(shell(), "risers", center_x=20, center_z=-20, width=4, depth=2, height=0.5)
        assert (item["center_x"], item["center_z"]) == (6.0, -6.0)
        _, ring, _ = add_item(shell(), "truss_rings", center_x=-20, center_z=0, radius=2, height=4)
        assert ring["center_x"] == -6.0

    def test_what_cannot_be_added_says_why(self):
        base = dict(center_x=0, center_z=0)
        assert "needs a width and a depth and a height" in refused(lambda: add_item(shell(), "risers", **base))
        assert "needs a length" in refused(lambda: add_item(shell(), "truss_lines", height=4, **base))
        assert "needs a radius" in refused(lambda: add_item(shell(), "truss_rings", height=4, **base))
        assert "where its middle goes" in refused(
            lambda: add_item(shell(), "truss_rings", radius=1, height=4, center_x=0))
        assert "one of: stage, riser, booth" in refused(
            lambda: add_item(shell(), "risers", width=2, depth=2, height=0.5, riser_kind="bar", **base))
        assert "Only a raised area" in refused(
            lambda: add_item(shell(), "truss_rings", radius=1, height=4, riser_kind="stage", **base))
        assert "It takes:" in refused(lambda: add_item(shell(), "truss_rings", radius=1, height=4, width=2, **base))
        assert "must be between" in refused(lambda: add_item(shell(), "truss_rings", radius=0.1, height=4, **base))
        assert "must be between" in refused(lambda: add_item(shell(), "truss_lines", length=4, height=7, **base))
        assert "must be between" in refused(
            lambda: add_item(shell(), "risers", width=2, depth=2, height=3.5, **base))
        assert "room for 16 m" in refused(lambda: add_item(shell(), "truss_lines", length=17, height=4, **base))
        assert "must be a number" in refused(
            lambda: add_item(shell(), "truss_lines", length=math.inf, height=4, **base))
        assert "must be a number" in refused(
            lambda: add_item(shell(), "truss_lines", length=4, height=4, center_x=math.nan, center_z=0))
        assert "at least one letter" in refused(
            lambda: add_item(shell(), "truss_lines", length=4, height=4, name="  ", **base))

    @pytest.mark.parametrize("stored", [None, {}, {"source": "preset"}])
    def test_nothing_is_added_to_a_rig_with_no_scanned_room(self, stored):
        detail = refused(lambda: add_item(stored, "risers", center_x=0, center_z=0, width=2, depth=2, height=1), 404)
        assert "no scanned room" in detail

    def test_only_the_three_lists_take_an_item(self):
        refused(lambda: add_item(shell(), "hanging_bands", center_x=0, center_z=0, height=4), 404)

    def test_a_list_can_only_hold_so_many(self):
        full = shell()
        full["risers"] = [dict(full["risers"][0]) for _ in range(ITEMS_MAX)]
        detail = refused(
            lambda: add_item(full, "risers", center_x=0, center_z=0, width=2, depth=2, height=0.5), 409)
        assert "Delete one first" in detail


class TestWords:

    def test_what_an_edit_did(self):
        before = shell()

        def words(kind, index, **changes):
            _, item = edit_item(before, kind, index, **changes)
            return edit_words(kind, before[kind][index], item)

        assert words("risers", 0, name="Main stage") == "Stage renamed"
        assert words("risers", 0, center_x=1.0) == "Stage moved"
        assert words("risers", 0, width=7.0) == "Stage resized"
        assert words("risers", 0, height=0.9) == "Stage resized"
        assert words("truss_lines", 0, length=6.0) == "Overhead line 1 resized"
        assert words("truss_lines", 0, heading_deg=45) == "Overhead line 1 turned"
        assert words("truss_lines", 0, height=4.4) == "Overhead line 1 resized"
        assert words("truss_rings", 0, radius=2.0, center_z=0.0, name="Halo") == (
            "Overhead ring 1 renamed, moved and resized"
        )
        assert words("truss_lines", 0, length=6.0, heading_deg=45) == "Overhead line 1 resized and turned"

    def test_an_edit_that_changed_nothing_is_not_a_step(self):
        before = shell()
        assert edit_words("risers", before["risers"][0], edit_item(before, "risers", 0, name="Stage")[1]) is None
        assert edit_words("risers", before["risers"][0], edit_item(before, "risers", 0, width=6.0)[1]) is None


class TestUndoRecord:

    def test_each_edit_leaves_the_room_as_it_was(self):
        first = shell()
        second, _ = edit_item(first, "risers", 0, name="Main stage")
        third, _ = delete_item(second, "truss_lines", 0)

        record = push_step(None, first, "Stage renamed")
        record = push_step(record, second, "Overhead line 1 deleted")
        assert undo_summary(record) == {"available": 2, "label": "Overhead line 1 deleted"}

        record, step = pop_step(record)
        assert step["shell"] == second and step["label"] == "Overhead line 1 deleted" and step["at"]
        assert undo_summary(record) == {"available": 1, "label": "Stage renamed"}
        record, step = pop_step(record)
        assert step["shell"] == first and record is None
        assert pop_step(record) == (None, None)
        assert third != second

    def test_the_record_given_is_not_changed(self):
        record = push_step(None, shell(), "one")
        kept = copy.deepcopy(record)
        longer = push_step(record, shell(), "two")
        assert record == kept and longer is not record and len(longer["steps"]) == 2
        shorter, _ = pop_step(longer)
        assert len(longer["steps"]) == 2 and len(shorter["steps"]) == 1

    def test_the_oldest_step_is_forgotten_past_the_limit(self):
        record = None
        for n in range(STEPS_MAX + 3):
            record = push_step(record, shell(), f"edit {n}")
        assert len(record["steps"]) == STEPS_MAX
        assert record["steps"][0]["label"] == "edit 3" and undo_summary(record)["label"] == f"edit {STEPS_MAX + 2}"

    @pytest.mark.parametrize("record", [
        None, {}, {"steps": None}, {"steps": "x"}, {"steps": [None, {"label": "no room"}, {"shell": []}]}, [],
    ])
    def test_a_record_that_cannot_be_read_holds_nothing(self, record):
        assert undo_summary(record) == {"available": 0, "label": None}
        assert pop_step(record) == (None, None)
        assert len(push_step(record, shell(), "first")["steps"]) == 1

    def test_undo_puts_back_a_dropped_band_and_a_place_in_the_list(self):
        """What a whole room is kept for: a delete moves the rest up and may drop a band."""
        before = shell()
        after, _ = delete_item(before, "truss_lines", 2)
        assert len(after["hanging_bands"]) == 1
        record = push_step(None, before, "Overhead line 3 deleted")
        _, step = pop_step(record)
        assert step["shell"] == shell()
        bands_add_up(step["shell"])
