"""
Editing a stored room by hand (services/room_scan/edit.py)
==========================================================

What has to hold: one item is renamed, moved or taken out and nothing else in
the shell changes; the shell given is never changed in place (the column it
came from is plain JSON); a moved line keeps its length and heading; a moved
item stops being a suggestion; a deleted truss stops counting towards a hanging
height; and an edit that cannot be made says why. docs/ROOM_SCAN.md.
"""

import copy
import math

import pytest

from app.services.room_scan.edit import (
    MOVED_BY_HAND, NAME_MAX, ShellEditError, delete_item, edit_item, item_centre, item_name,
)
from app.services.room_scan.suggest import suggest_positions


def shell():
    """A 12 m by 10 m room: a stage and a booth, two trusses at 4.2 m, one at 5.5 m and a ring at 4.2 m."""
    return {
        "source": "scan",
        "suggested": True,
        "room": {"width": 12.0, "depth": 10.0, "height": 6.0, "suggested": True},
        "risers": [
            {"center_x": 0.0, "center_z": -3.5, "width": 6.0, "depth": 3.0, "height": 0.6, "base_height": 0.0,
             "name": "Stage", "kind": "stage", "suggested": True, "basis": "scan: a level area."},
            {"center_x": 4.0, "center_z": 3.0, "width": 2.0, "depth": 1.0, "height": 1.0, "base_height": 0.0,
             "name": "Booth or counter", "kind": "booth", "suggested": True, "basis": "scan: a level area."},
        ],
        "truss_lines": [
            {"name": "Overhead line 1", "x1": -4.0, "z1": -2.0, "x2": 4.0, "z2": -2.0, "height": 4.2, "top": 4.5,
             "length": 8.0, "across": 0.3, "axis": "x", "heading_deg": 0.0, "suggested": True, "basis": "scan: a bar."},
            {"name": "Overhead line 2", "x1": -3.0, "z1": 1.0, "x2": 1.0, "z2": 4.0, "height": 4.25, "top": 4.5,
             "length": 5.0, "across": 0.3, "axis": "angled", "heading_deg": 36.9, "suggested": True,
             "basis": "scan: a bar."},
            {"name": "Overhead line 3", "x1": -4.0, "z1": 0.0, "x2": 4.0, "z2": 0.0, "height": 5.5, "top": 5.8,
             "length": 8.0, "across": 0.3, "axis": "x", "heading_deg": 0.0, "suggested": True, "basis": "scan: a bar."},
        ],
        "truss_rings": [
            {"name": "Overhead ring 1", "center_x": 3.0, "center_z": 2.0, "radius": 1.5, "height": 4.2, "top": 4.5,
             "across": 0.3, "suggested": True, "basis": "scan: a ring."},
        ],
        "hanging_bands": [
            {"height": 4.2, "top": 4.5, "lines": 2, "rings": 1, "suggested": True,
             "basis": "scan: long thin objects hanging clear of the walls at this height"},
            {"height": 5.5, "top": 5.8, "lines": 1, "rings": 0, "suggested": True,
             "basis": "scan: long thin objects hanging clear of the walls at this height"},
        ],
        "scan": {"file": "club.obj", "format": "obj"},
    }


def without(found: dict, kind: str, index: int) -> dict:
    """The shell with one item's place blanked, to compare everything else."""
    rest = copy.deepcopy(found)
    rest[kind][index] = None
    return rest


class TestRename:

    def test_a_rename_changes_the_name_and_nothing_else(self):
        before = shell()
        edited, item = edit_item(before, "risers", 1, name="  The   bar ")

        assert item["name"] == "The bar"
        # Slice 32: a raised area's basis also says the name is a person's, so a scan applied again keeps it.
        was = before["risers"][1]
        assert edited["risers"][1] == {**was, "name": "The bar", "basis": was["basis"] + " Name set by hand."}
        # A line says nothing more: only raised areas are kept across a reading.
        assert edit_item(before, "truss_lines", 0, name="Front")[1] == {**before["truss_lines"][0], "name": "Front"}
        # Still the scan's guess of where it is: only a move says otherwise.
        assert item["suggested"] is True and MOVED_BY_HAND not in item["basis"]
        assert without(edited, "risers", 1) == without(before, "risers", 1)

    def test_the_shell_given_is_not_changed(self):
        before = shell()
        kept = copy.deepcopy(before)

        edited, _ = edit_item(before, "truss_lines", 0, name="Front truss", center_z=-3.0)
        deleted, _ = delete_item(before, "truss_rings", 0)

        assert before == kept
        assert edited is not before and edited["truss_lines"] is not before["truss_lines"]
        assert deleted["truss_rings"] is not before["truss_rings"]

    @pytest.mark.parametrize("name", ["", "   ", "\n\t"])
    def test_a_blank_name_is_refused(self, name):
        with pytest.raises(ShellEditError) as refused:
            edit_item(shell(), "risers", 0, name=name)
        assert refused.value.status == 422 and "name" in refused.value.detail

    def test_a_name_too_long_is_refused_and_one_at_the_limit_is_not(self):
        with pytest.raises(ShellEditError) as refused:
            edit_item(shell(), "risers", 0, name="x" * (NAME_MAX + 1))
        assert refused.value.status == 422 and str(NAME_MAX) in refused.value.detail

        _, item = edit_item(shell(), "risers", 0, name="x" * NAME_MAX)
        assert item["name"] == "x" * NAME_MAX


class TestMove:

    def test_a_raised_area_goes_where_its_middle_is_put(self):
        before = shell()
        edited, item = edit_item(before, "risers", 0, center_x=1.2346, center_z=-4.0)

        # Stored to the millimetre.
        assert (item["center_x"], item["center_z"]) == (1.235, -4.0)
        assert item["suggested"] is False and item["basis"].endswith(MOVED_BY_HAND)
        # Its size, height and name are its own.
        for key in ("width", "depth", "height", "base_height", "name", "kind"):
            assert item[key] == before["risers"][0][key]
        assert without(edited, "risers", 0) == without(before, "risers", 0)

    def test_one_axis_given_keeps_the_other(self):
        _, item = edit_item(shell(), "truss_rings", 0, center_z=-1.0)
        assert (item["center_x"], item["center_z"]) == (3.0, -1.0)
        assert item["radius"] == 1.5 and item["height"] == 4.2

    def test_a_line_keeps_its_length_and_heading(self):
        before = shell()
        line = before["truss_lines"][1]
        edited, item = edit_item(before, "truss_lines", 1, center_x=2.0, center_z=-1.0)

        assert item_centre("truss_lines", item) == pytest.approx((2.0, -1.0))
        assert (item["x2"] - item["x1"], item["z2"] - item["z1"]) == pytest.approx((4.0, 3.0))
        assert math.hypot(item["x2"] - item["x1"], item["z2"] - item["z1"]) == pytest.approx(line["length"])
        for key in ("length", "axis", "heading_deg", "height", "top", "across"):
            assert item[key] == line[key]
        assert item["suggested"] is False
        assert edited["hanging_bands"] == before["hanging_bands"]

    def test_a_move_to_where_it_already_is_changes_nothing(self):
        before = shell()
        edited, item = edit_item(before, "truss_lines", 0, center_x=0.0, center_z=-2.0)
        assert edited == before and item["suggested"] is True

    def test_moved_twice_says_so_once(self):
        once, _ = edit_item(shell(), "risers", 0, center_x=1.0)
        twice, item = edit_item(once, "risers", 0, center_x=2.0)
        assert item["basis"].count(MOVED_BY_HAND) == 1 and item["center_x"] == 2.0

    def test_the_middle_is_held_to_the_room_and_its_margin(self):
        # 12 m by 10 m: 6 and 5 from the middle to a wall, and 2 m beyond it.
        _, item = edit_item(shell(), "risers", 1, center_x=500.0, center_z=-500.0)
        assert (item["center_x"], item["center_z"]) == (8.0, -7.0)

        _, line = edit_item(shell(), "truss_lines", 0, center_x=-500.0)
        assert item_centre("truss_lines", line) == pytest.approx((-8.0, -2.0))
        assert line["x2"] - line["x1"] == pytest.approx(8.0)

    def test_a_room_with_no_size_holds_nothing(self):
        found = shell()
        found["room"] = None
        _, item = edit_item(found, "risers", 0, center_x=40.0)
        assert item["center_x"] == 40.0

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "3"])
    def test_a_centre_that_is_not_a_number_is_refused(self, value):
        with pytest.raises(ShellEditError) as refused:
            edit_item(shell(), "risers", 0, center_x=value)
        assert refused.value.status == 422

    def test_an_item_with_no_position_cannot_be_moved_but_can_be_renamed_and_deleted(self):
        found = shell()
        found["truss_lines"][0]["x1"] = None
        with pytest.raises(ShellEditError) as refused:
            edit_item(found, "truss_lines", 0, center_x=1.0)
        assert refused.value.status == 409 and "Delete it" in refused.value.detail

        _, item = edit_item(found, "truss_lines", 0, name="Broken")
        assert item["name"] == "Broken"
        deleted, _ = delete_item(found, "truss_lines", 0)
        assert [line["name"] for line in deleted["truss_lines"]] == ["Overhead line 2", "Overhead line 3"]

    def test_a_name_and_a_move_together(self):
        _, item = edit_item(shell(), "truss_rings", 0, name="Centre ring", center_x=0.0, center_z=0.0)
        assert (item["name"], item["center_x"], item["center_z"]) == ("Centre ring", 0.0, 0.0)


class TestDelete:

    def test_a_raised_area_is_taken_out_and_the_rest_move_up(self):
        before = shell()
        edited, removed = delete_item(before, "risers", 0)

        assert removed == before["risers"][0]
        assert edited["risers"] == [before["risers"][1]]
        # A raised area hangs nowhere: the bands are as they were.
        assert edited["hanging_bands"] == before["hanging_bands"]
        assert edited["truss_lines"] == before["truss_lines"] and edited["room"] == before["room"]

    def test_a_deleted_truss_is_taken_out_of_its_band(self):
        edited, removed = delete_item(shell(), "truss_lines", 1)

        assert removed["name"] == "Overhead line 2"
        assert [line["name"] for line in edited["truss_lines"]] == ["Overhead line 1", "Overhead line 3"]
        assert [(band["height"], band["lines"], band["rings"]) for band in edited["hanging_bands"]] == [
            (4.2, 1, 1), (5.5, 1, 0),
        ]

    def test_a_band_left_with_nothing_is_dropped(self):
        edited, _ = delete_item(shell(), "truss_lines", 2)
        assert [band["height"] for band in edited["hanging_bands"]] == [4.2]

    def test_a_band_left_with_only_a_ring_says_so(self):
        found, _ = delete_item(shell(), "truss_lines", 0)
        found, _ = delete_item(found, "truss_lines", 0)
        low = found["hanging_bands"][0]
        assert (low["height"], low["lines"], low["rings"]) == (4.2, 0, 1)
        assert "ring" in low["basis"] and "long thin" not in low["basis"]

    def test_a_deleted_ring_is_taken_out_of_its_band(self):
        edited, _ = delete_item(shell(), "truss_rings", 0)
        assert edited["truss_rings"] == []
        assert [(band["height"], band["lines"], band["rings"]) for band in edited["hanging_bands"]] == [
            (4.2, 2, 0), (5.5, 1, 0),
        ]

    def test_with_nothing_left_overhead_there_is_no_hanging_height(self):
        found = shell()
        for kind, count in (("truss_lines", 3), ("truss_rings", 1)):
            for _ in range(count):
                found, _ = delete_item(found, kind, 0)
        assert found["truss_lines"] == [] and found["truss_rings"] == [] and found["hanging_bands"] == []

    def test_a_shell_stored_before_rings_were_counted(self):
        found = shell()
        del found["truss_rings"]
        for band in found["hanging_bands"]:
            del band["rings"]
        edited, _ = delete_item(found, "truss_lines", 2)
        assert [band["height"] for band in edited["hanging_bands"]] == [4.2]
        assert "truss_rings" not in edited

    def test_a_row_is_no_longer_hung_at_the_height_of_a_deleted_truss(self):
        """What dropping the band is for: suggest.py hangs a row with no truss at the lowest band."""
        class Light:
            def __init__(self, n):
                self.id, self.name, self.group_name = n, f"Spot {n}", "Truss Spots"
                self.position_x, self.position_y, self.position_z = -1.0 + n, 3.0, 4.5
                self.tags = ["position_source:template", "position_unconfirmed"]
                self.dmx_address, self.universe, self.is_active = n, 0, True

        found = shell()
        found["truss_lines"] = found["truss_lines"][:1]
        found["truss_rings"] = []
        found["hanging_bands"] = [dict(found["hanging_bands"][0], lines=1, rings=0)]
        lights = [Light(n) for n in range(3)]

        before, _ = suggest_positions(lights, found)
        assert before and all(move.to_position[1] == pytest.approx(4.2) for move in before)

        cleared, _ = delete_item(found, "truss_lines", 0)
        after, _ = suggest_positions(lights, cleared)
        assert not any(move.to_position[1] == pytest.approx(4.2) for move in after)


class TestRefusals:

    @pytest.mark.parametrize("stored", [None, {}, {"dome": {"radius": 9.0}}, {"source": "preset", "risers": [{}]}])
    def test_a_rig_with_no_scanned_room_has_nothing_to_edit(self, stored):
        for call in (lambda: edit_item(stored, "risers", 0, name="Bar"), lambda: delete_item(stored, "risers", 0)):
            with pytest.raises(ShellEditError) as refused:
                call()
            assert refused.value.status == 404 and "no scanned room" in refused.value.detail

    @pytest.mark.parametrize("kind", ["room", "hanging_bands", "scan", "led_walls", ""])
    def test_only_raised_areas_lines_and_rings_can_be_edited(self, kind):
        with pytest.raises(ShellEditError) as refused:
            delete_item(shell(), kind, 0)
        assert refused.value.status == 404 and "truss_lines" in refused.value.detail

    @pytest.mark.parametrize("kind, index", [("risers", 2), ("risers", -1), ("truss_lines", 3), ("truss_rings", 1)])
    def test_a_place_that_is_not_in_the_list_is_refused(self, kind, index):
        for call in (lambda: edit_item(shell(), kind, index, name="X"), lambda: delete_item(shell(), kind, index)):
            with pytest.raises(ShellEditError) as refused:
                call()
            assert refused.value.status == 404 and "load the rig again" in refused.value.detail

    def test_an_edit_that_asks_for_nothing_is_refused(self):
        with pytest.raises(ShellEditError) as refused:
            edit_item(shell(), "risers", 0)
        assert refused.value.status == 422 and "Nothing to change" in refused.value.detail


def test_an_item_is_called_by_its_name_or_by_what_it_is():
    assert item_name("risers", {"name": "The bar"}) == "The bar"
    assert item_name("truss_lines", {"name": "  "}) == "The overhead line"
    assert item_name("truss_rings", {}) == "The overhead ring"
