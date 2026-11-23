"""
Raised areas in Edit Room: the fixtures standing on one, its kind and its base
==============================================================================

services/room_scan/carry.py works out which fixtures stand on a raised area of
a stored room and where they go when it is moved, raised, resized or given a
quarter turn; services/room_scan/edit.py makes one another kind and gives it a
base height. docs/ROOM_SCAN.md, slice 18.

What has to hold: a fixture stands on a raised area when it is over its
footprint (and 0.15 m round it) at its top surface, never when it hangs on a
truss, and on the nearer top of two; each kind of change keeps its place on
the area; one carried out of the room refuses the edit; a kind change keeps
the place in the list; a base height is a finite number from 0 to 10 m with
the top under the ceiling; and a suggestion goes by the first stage of the
shell it is given.

No database and no device: the fixtures are plain objects.
"""

import math
from types import SimpleNamespace

import pytest

from app.services.room_scan.carry import (
    carried_moves, carried_words, put_back, put_back_words, quarter_turned, refuse_outside, standing_fixtures,
    stands_on,
)
from app.services.room_scan.edit import (
    KIND_BY_HAND, ShellEditError, add_item, base_of, deck_top, edit_item, edit_words, first_stage,
)
from app.services.room_scan.edit_undo import pop_step, push_step
from app.services.room_scan.suggest import suggest_positions

GUESS = ["position_source:template", "position_unconfirmed"]
PATCH = {"dmx_address": 17, "universe": 1, "mode_id": 3}


def light(fixture_id, x, y, z, heading=0.0, name=None, group="Floor"):
    return SimpleNamespace(
        id=fixture_id, name=name or f"Par {fixture_id}", position_x=x, position_y=y, position_z=z,
        rotation_y=heading, group_name=group, tags=list(GUESS), **PATCH,
    )


def room(lines=None, extra=None):
    """A 12 m by 10 m by 6 m room: a 6 by 3 stage 0.6 m high upstage, and a 2 by 2 riser downstage left."""
    return {
        "source": "scan",
        "room": {"width": 12.0, "depth": 10.0, "height": 6.0},
        "risers": [
            {"center_x": 0.0, "center_z": -3.5, "width": 6.0, "depth": 3.0, "height": 0.6, "base_height": 0.0,
             "name": "Stage", "kind": "stage", "suggested": True},
            {"center_x": 4.0, "center_z": 2.0, "width": 2.0, "depth": 2.0, "height": 0.3,
             "name": "Riser", "kind": "riser", "suggested": True},
        ] + list(extra or []),
        "truss_lines": lines if lines is not None else [],
        "truss_rings": [],
        "hanging_bands": [],
    }


def carried(shell, index, fixtures, **changes):
    """The edit, and the moves it would carry: (shell after, item after, moves)."""
    after, item = edit_item(shell, "risers", index, **changes)
    return after, item, carried_moves(shell, "risers", index, item, fixtures)


def to_of(moves):
    return {move["rig_fixture_id"]: (move["to"]["x"], move["to"]["y"], move["to"]["z"]) for move in moves}


class TestWhatStandsOnIt:

    def test_a_fixture_over_the_footprint_at_the_top_surface_stands_on_it(self):
        stage = room()["risers"][0]
        assert stands_on(stage, light(1, 0.0, 0.6, -3.5))
        # 0.15 m past the edge and 0.6 m above the top is still on it; a little more is not.
        assert stands_on(stage, light(2, 3.15, 1.2, -1.85))
        assert not stands_on(stage, light(3, 3.2, 0.6, -3.5))
        assert not stands_on(stage, light(4, 0.0, 0.6, -1.8))
        assert not stands_on(stage, light(5, 0.0, 1.25, -3.5))
        # Drawn a little into the deck it still stands there; on the floor under it, it does not.
        assert stands_on(stage, light(6, 0.0, 0.55, -3.5))
        assert not stands_on(stage, light(7, 0.0, 0.5, -3.5))
        assert not stands_on(stage, light(8, 0.0, 0.0, -3.5))

    def test_a_floating_area_is_stood_on_at_its_base_and_height_together(self):
        balcony = {"center_x": 0.0, "center_z": 3.0, "width": 4.0, "depth": 2.0, "height": 0.3, "base_height": 2.7}
        assert stands_on(balcony, light(1, 1.0, 3.0, 3.0))
        assert stands_on(balcony, light(2, 1.0, 3.5, 3.0))
        # At the height alone, under the floating deck, nothing stands on it.
        assert not stands_on(balcony, light(3, 1.0, 0.3, 3.0))

    def test_an_area_with_a_number_missing_is_stood_on_by_nothing(self):
        assert not stands_on({"center_x": 0.0, "center_z": 0.0, "width": 2.0, "height": 0.3}, light(1, 0.0, 0.3, 0.0))
        assert not stands_on(None, light(1, 0.0, 0.3, 0.0))
        assert not stands_on(room()["risers"][0], SimpleNamespace(id=1, position_x=None, position_y=0.6, position_z=0.0))

    def test_a_fixture_hung_on_a_truss_over_the_stage_is_the_truss_s(self):
        low = [{"name": "Low truss", "x1": -3.0, "z1": -3.5, "x2": 3.0, "z2": -3.5, "height": 1.0, "top": 1.3}]
        shell = room(lines=low)
        hung, stood = light(1, 1.0, 1.0, -3.5), light(2, 1.0, 0.8, -2.5)

        assert stands_on(shell["risers"][0], hung)
        assert standing_fixtures(shell, 0, [hung, stood]) == [stood]
        # With no truss there it is the stage's.
        assert standing_fixtures(room(), 0, [hung, stood]) == [hung, stood]

    def test_a_fixture_over_two_areas_stands_on_the_nearer_top_and_the_first_listed_when_as_near(self):
        on_stage = {"center_x": 0.0, "center_z": -3.5, "width": 1.0, "depth": 1.0, "height": 0.3, "base_height": 0.6}
        shell = room(extra=[on_stage])
        on_riser, beside = light(1, 0.0, 0.9, -3.5), light(2, 2.0, 0.6, -3.5)
        between = light(3, 0.0, 0.75, -3.5)

        assert standing_fixtures(shell, 2, [on_riser, beside, between]) == [on_riser]
        assert standing_fixtures(shell, 0, [on_riser, beside, between]) == [beside, between]
        assert standing_fixtures(shell, 1, [on_riser, beside, between]) == []
        assert standing_fixtures(None, 0, [on_riser]) == [] and standing_fixtures(shell, 9, [on_riser]) == []


class TestWhereTheyGo:

    def test_a_move_shifts_them_by_what_the_middle_shifted(self):
        shell = room()
        lights = [light(1, -2.0, 0.6, -4.0), light(2, 2.0, 0.8, -3.0), light(3, 4.0, 0.3, 2.0), light(4, 0.0, 0.0, 0.0)]

        _, item, moves = carried(shell, 0, lights, center_x=1.0, center_z=-3.0)

        assert (item["center_x"], item["center_z"]) == (1.0, -3.0)
        assert to_of(moves) == {1: (-1.0, 0.6, -3.5), 2: (3.0, 0.8, -2.5)}
        assert moves[0]["from"] == {"x": -2.0, "y": 0.6, "z": -4.0, "rotation_y": 0.0}
        assert moves[0]["to"]["rotation_y"] == 0.0 and moves[0]["name"] == "Par 1"

    def test_a_height_and_a_base_height_raise_them_by_what_the_top_moved(self):
        shell = room()
        lights = [light(1, -2.0, 0.6, -4.0), light(2, 2.0, 0.8, -3.0)]

        _, _, higher = carried(shell, 0, lights, height=0.9)
        assert to_of(higher) == {1: (-2.0, 0.9, -4.0), 2: (2.0, 1.1, -3.0)}

        _, item, floated = carried(shell, 0, lights, base_height=1.0)
        assert item["base_height"] == 1.0 and deck_top(item) == pytest.approx(1.6)
        assert to_of(floated) == {1: (-2.0, 1.6, -4.0), 2: (2.0, 1.8, -3.0)}

        _, _, both = carried(shell, 0, lights, base_height=1.0, height=0.3)
        assert to_of(both) == {1: (-2.0, 1.3, -4.0), 2: (2.0, 1.5, -3.0)}

    def test_a_resize_keeps_each_at_the_same_share_of_the_footprint(self):
        shell = room()
        lights = [light(1, -2.0, 0.6, -4.5), light(2, 3.0, 0.6, -3.5), light(3, 0.0, 0.6, -3.5)]

        _, _, narrower = carried(shell, 0, lights, width=3.0)
        # Half as wide: each is half as far across from the middle, and as far up and down stage as it was.
        assert to_of(narrower) == {1: (-1.0, 0.6, -4.5), 2: (1.5, 0.6, -3.5)}

        _, _, deeper = carried(shell, 0, lights, depth=4.0)
        assert to_of(deeper) == {1: (-2.0, 0.6, pytest.approx(-3.5 - 4.0 / 3.0, abs=0.001))}

    def test_a_quarter_turn_swings_them_clockwise_about_the_middle_and_turns_them(self):
        shell = room()
        lights = [light(1, 2.0, 0.6, -3.0, heading=0.0), light(2, -3.0, 0.6, -4.5, heading=170.0), light(3, 0.0, 0.6, -3.5)]

        after, item, moves = carried(shell, 0, lights, width=3.0, depth=6.0)

        assert quarter_turned(shell["risers"][0], item)
        # What was stage left of the middle is now downstage of it, as with a turned truss.
        assert to_of(moves) == {1: (-0.5, 0.6, -1.5), 2: (1.0, 0.6, -6.5), 3: (0.0, 0.6, -3.5)}
        assert [move["to"]["rotation_y"] for move in moves] == [-90.0, 80.0, -90.0]
        # A size that is not the two changed places is a resize, and a square area has no turn.
        assert not quarter_turned(shell["risers"][0], {"width": 3.0, "depth": 5.0})
        assert not quarter_turned(shell["risers"][1], shell["risers"][1])
        refuse_outside(after, "risers", item, moves)

    def test_a_middle_brought_in_to_fit_is_the_one_they_follow(self):
        shell = room()
        shell["risers"][1].update({"center_x": 7.0})
        lamp = light(1, 7.5, 0.3, 2.0)

        # 2 m wide at 7 reaches 8, the limit; 4 m wide has to come in to 6.
        _, item, moves = carried(shell, 1, [lamp], width=4.0)

        assert item["center_x"] == 6.0
        assert to_of(moves) == {1: (7.0, 0.3, 2.0)}

    def test_a_rename_a_kind_change_and_no_change_carry_nothing(self):
        shell = room()
        lights = [light(1, -2.0, 0.6, -4.0)]
        assert carried(shell, 0, lights, name="Main stage")[2] == []
        assert carried(shell, 0, lights, riser_kind="booth")[2] == []
        assert carried(shell, 0, lights, height=0.6, base_height=0.0)[2] == []
        assert carried_moves(shell, "risers", 5, shell["risers"][0], lights) == []

    def test_nothing_about_a_carried_fixture_changes_but_its_place_and_heading(self):
        shell = room()
        lamp = light(1, 2.0, 0.6, -3.0)
        before = dict(vars(lamp))
        after, item, moves = carried(shell, 0, [lamp], width=3.0, depth=6.0, center_x=0.5, height=0.9)

        from app.services.room_scan.carry import apply_moves
        apply_moves([lamp], moves)

        changed = {key for key, value in vars(lamp).items() if value != before[key]}
        assert changed == {"position_x", "position_y", "position_z", "rotation_y"}
        assert (lamp.position_x, lamp.position_y, lamp.position_z, lamp.rotation_y) == (0.0, 0.9, -1.5, -90.0)
        # The undo puts it back exactly, and leaves one moved since.
        restored, skipped = put_back([lamp], moves)
        assert len(restored) == 1 and skipped == [] and vars(lamp) == before


class TestOutOfTheRoom:

    def test_a_fixture_carried_past_the_margin_refuses_the_edit_in_its_own_words(self):
        shell = room()
        lights = [light(1, 2.5, 0.6, -3.5, name="Par 1"), light(2, -2.5, 0.6, -3.5, name="Par 2")]
        # A plain move holds the stage's middle to 8 m; the light 2.5 m stage left of it would be at 10.4.
        after, item, moves = carried(shell, 0, lights, center_x=7.9)

        with pytest.raises(ShellEditError) as refused:
            refuse_outside(after, "risers", item, moves)

        assert refused.value.status == 422
        assert "carry 1 fixture standing on Stage out of the room and the 2 m round it" in refused.value.detail
        assert "Par 1 to 10.4, 0.6, -3.5" in refused.value.detail and "Par 2" not in refused.value.detail
        assert "Change the raised area by less" in refused.value.detail

    def test_a_fixture_raised_through_the_ceiling_margin_refuses_it_too(self):
        shell = room()
        shell["room"]["height"] = 3.0
        high = light(1, 0.0, 1.2, -3.5)
        after, item, moves = carried(shell, 0, [high], base_height=2.4, height=0.6)
        assert to_of(moves) == {1: (0.0, 3.6, -3.5)}
        refuse_outside(after, "risers", item, moves)   # 3.6 is within 2 m of a 3 m ceiling
        shell["room"]["height"] = 1.5
        with pytest.raises(ShellEditError):
            refuse_outside(shell, "risers", item, moves)


class TestKindChange:

    def test_a_riser_made_a_stage_keeps_its_place_and_is_called_a_stage(self):
        shell = room()

        after, item = edit_item(shell, "risers", 1, riser_kind="stage")

        assert after["risers"][1] is item and len(after["risers"]) == 2
        assert item["kind"] == "stage" and item["name"] == "Stage"
        assert item["suggested"] is False and KIND_BY_HAND in item["basis"]
        assert after["risers"][0] == shell["risers"][0]
        assert edit_words("risers", shell["risers"][1], item) == "Riser made a stage"
        # The shell given is not changed.
        assert shell["risers"][1]["kind"] == "riser"
        # Still the first stage: the one listed first.
        assert first_stage(after) == 0

    def test_a_name_somebody_gave_is_kept_and_a_name_sent_with_it_wins(self):
        shell = room()
        shell["risers"][1]["name"] = "Drum riser"
        _, kept = edit_item(shell, "risers", 1, riser_kind="booth")
        assert kept["kind"] == "booth" and kept["name"] == "Drum riser"
        assert edit_words("risers", shell["risers"][1], kept) == "Drum riser made a booth"

        _, named = edit_item(room(), "risers", 1, riser_kind="booth", name="DJ booth")
        assert named["name"] == "DJ booth"
        assert edit_words("risers", room()["risers"][1], named) == "Riser renamed and made a booth"

    def test_the_kind_it_already_is_changes_nothing(self):
        shell = room()
        after, item = edit_item(shell, "risers", 0, riser_kind="stage")
        assert after == shell and edit_words("risers", shell["risers"][0], item) is None

    @pytest.mark.parametrize("kind, wrong", [("risers", "balcony"), ("risers", ""), ("risers", 3),
                                             ("truss_lines", "stage")])
    def test_a_kind_that_is_not_one_is_refused(self, kind, wrong):
        shell = room(lines=[{"name": "T", "x1": -2.0, "z1": 0.0, "x2": 2.0, "z2": 0.0, "height": 4.0}])
        with pytest.raises(ShellEditError) as refused:
            edit_item(shell, kind, 0, riser_kind=wrong)
        assert refused.value.status == 422
        assert ("one of: stage, riser, booth" in refused.value.detail) == (kind == "risers")

    def test_the_first_stage_is_the_first_listed_that_is_one(self):
        shell = room()
        assert first_stage(shell) == 0
        demoted, _ = edit_item(shell, "risers", 0, riser_kind="riser")
        assert first_stage(demoted) is None
        swapped, _ = edit_item(demoted, "risers", 1, riser_kind="stage")
        assert first_stage(swapped) == 1
        assert first_stage(None) is None and first_stage({"risers": "x"}) is None

    def test_a_suggestion_puts_floor_lights_on_the_first_stage_of_the_shell_it_is_given(self):
        shell = room()
        # A row on the floor where the riser is, and nowhere near the stage.
        row = [light(n, 3.5 + 0.5 * n, 0.0, 2.0) for n in range(1, 3)]
        assert suggest_positions(row, shell)[0] == []

        demoted, _ = edit_item(shell, "risers", 0, riser_kind="riser")
        swapped, _ = edit_item(demoted, "risers", 1, riser_kind="stage")
        moves, _ = suggest_positions(row, swapped)

        assert len(moves) == 2
        assert all(move.to_position[1] == pytest.approx(0.3) and "onto the stage" in move.reason for move in moves)

    def test_a_suggestion_lifts_onto_the_top_of_a_stage_that_floats(self):
        shell, _ = edit_item(room(), "risers", 0, base_height=1.0)
        row = [light(n, -1.0 + n, 0.2, -3.5) for n in range(1, 3)]
        moves, _ = suggest_positions(row, shell)
        assert [move.to_position[1] for move in moves] == [pytest.approx(1.8), pytest.approx(1.8)]
        assert all("(1.60 m up)" in move.reason for move in moves)


class TestBaseHeight:

    def test_a_base_floats_the_area_and_is_stored_to_the_millimetre(self):
        shell = room()
        after, item = edit_item(shell, "risers", 1, base_height=2.4996)
        assert item["base_height"] == 2.5 and base_of(item) == 2.5 and deck_top(item) == pytest.approx(2.8)
        assert item["suggested"] is False and "Resized by hand." in item["basis"]
        assert edit_words("risers", shell["risers"][1], item) == "Riser raised"
        down, lowered = edit_item(after, "risers", 1, base_height=0)
        assert lowered["base_height"] == 0.0
        assert edit_words("risers", item, lowered) == "Riser lowered"

    def test_an_area_stored_without_a_base_stands_on_the_floor_and_a_base_of_nothing_changes_nothing(self):
        shell = room()
        assert "base_height" not in shell["risers"][1] and base_of(shell["risers"][1]) == 0.0
        after, item = edit_item(shell, "risers", 1, base_height=0.0)
        assert after == shell and "base_height" not in item
        assert edit_words("risers", shell["risers"][1], item) is None

    @pytest.mark.parametrize("wrong", [math.nan, math.inf, -math.inf, -0.1, 10.001, "2", True])
    def test_a_base_that_is_not_a_number_from_nothing_to_ten_metres_is_refused(self, wrong):
        with pytest.raises(ShellEditError) as refused:
            edit_item(room(), "risers", 0, base_height=wrong)
        assert refused.value.status == 422 and "base height" in refused.value.detail

    def test_the_limits_are_nothing_and_ten_metres(self):
        tall = room()
        tall["room"]["height"] = 12.0
        assert edit_item(tall, "risers", 0, base_height=10.0)[1]["base_height"] == 10.0
        assert edit_item(tall, "risers", 0, base_height=0.001)[1]["base_height"] == 0.001

    def test_a_top_above_the_ceiling_is_refused_and_a_height_goes_by_the_new_base(self):
        shell = room()   # 6 m to the ceiling, the stage 0.6 m high
        assert edit_item(shell, "risers", 0, base_height=5.4)[1]["base_height"] == 5.4
        with pytest.raises(ShellEditError) as refused:
            edit_item(shell, "risers", 0, base_height=5.5)
        assert refused.value.status == 422 and "ceiling is at 6 m" in refused.value.detail
        # With a lower deck sent in the same change it fits.
        assert edit_item(shell, "risers", 0, base_height=5.5, height=0.5)[1]["height"] == 0.5
        with pytest.raises(ShellEditError):
            edit_item(shell, "risers", 0, base_height=4.0, height=2.5)

    def test_a_truss_has_no_base_height(self):
        shell = room(lines=[{"name": "T", "x1": -2.0, "z1": 0.0, "x2": 2.0, "z2": 0.0, "height": 4.0}])
        with pytest.raises(ShellEditError) as refused:
            edit_item(shell, "truss_lines", 0, base_height=1.0)
        assert refused.value.status == 422 and "no base height to set" in refused.value.detail

    def test_an_added_area_stands_on_the_floor_unless_given_a_base(self):
        sizes = {"center_x": 0.0, "center_z": 3.0, "width": 4.0, "depth": 2.0, "height": 0.3}
        _, on_floor, _ = add_item(room(), "risers", **sizes)
        assert on_floor["base_height"] == 0.0
        _, balcony, at = add_item(room(), "risers", riser_kind="riser", name="Balcony", base_height=2.7, **sizes)
        assert balcony["base_height"] == 2.7 and at == 2
        with pytest.raises(ShellEditError):
            add_item(room(), "risers", base_height=5.8, **sizes)
        with pytest.raises(ShellEditError):
            add_item(room(), "risers", base_height=math.nan, **sizes)


class TestWords:

    def test_the_answer_says_standing_for_a_raised_area(self):
        stage = room()["risers"][0]
        assert carried_words("risers", stage, 3, True) == "3 fixtures standing on Stage moved with it."
        assert carried_words("risers", stage, 1, True) == "1 fixture standing on Stage moved with it."
        assert carried_words("risers", stage, 0, True) == "No fixture was moved: none that stands on it had to move."
        assert carried_words("risers", stage, 0, False) == (
            "The fixtures standing on Stage were left where they are, as asked."
        )

    def test_an_undo_says_where_they_stood_and_the_step_remembers_which(self):
        assert put_back_words(2, 0, "risers") == "2 fixtures put back where they stood before it."
        assert put_back_words(1, 1, "risers") == (
            "1 fixture put back where it stood before it. 1 fixture left alone, because it has been moved since."
        )
        assert put_back_words(2, 0) == put_back_words(2, 0, "truss_lines") == (
            "2 fixtures put back where they hung before it."
        )
        moves = [{"rig_fixture_id": 1, "name": "Par 1", "from": {}, "to": {}}]
        _, step = pop_step(push_step(None, room(), "Stage moved, with 1 fixture", fixtures=moves, kind="risers"))
        assert step["kind"] == "risers" and step["fixtures"] == moves
        # A step that carried nothing says nothing of a kind.
        assert "kind" not in pop_step(push_step(None, room(), "Stage renamed", kind="risers"))[1]
