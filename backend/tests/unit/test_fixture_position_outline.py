"""
Where a dragged fixture is held in a scanned room that is not a box
===================================================================

PUT /api/rigs/{id}/fixtures/{fid}/position holds a position to within 2 m of
the room. For a box that is the box. For a room with a floor outline it is the
outline: the notch of an L is outside the room, and a fixture put deep in it
comes back to 2 m from the notch's walls.

The 3D view holds a drag to the same line before it saves
(frontend/src/components/rig/previs/fixtureDrag.ts), so HELD below is the same
table as in frontend/src/__tests__/outlineBounds.test.ts. Change one, change
both: where they differ a fixture jumps when it is dropped.

Plain functions, no database and no event loop. docs/ROOM_SCAN.md.
"""

from types import SimpleNamespace

import pytest

from app.api.endpoints.fixture_position import (
    OUTSIDE_MARGIN_M, hold_near_outline, hold_position, inside_outline, position_limits, position_outline,
)

# 16 m by 14 m with everything downstage of z = -1 and stage left of x = -2
# walled off: a notch 10 m by 8 m, deep enough that its middle is more than
# 2 m from every wall. The middle of the room's box, (0, 0), is in the notch.
DEEP = [(-8, -7), (8, -7), (8, -1), (-2, -1), (-2, 7), (-8, 7)]

# (put at) -> (held at), x and z. The same table as the frontend test.
HELD = [
    # Inside the room: left alone.
    ((-5.0, 3.0), (-5.0, 3.0)),
    ((6.0, -4.0), (6.0, -4.0)),
    # In the notch but within 2 m of a wall of it: left alone.
    ((0.0, 0.0), (0.0, 0.0)),
    ((-0.5, 6.0), (-0.5, 6.0)),
    # Deep in the notch: back to 2 m from the nearest wall of it.
    ((4.0, 4.0), (4.0, 1.0)),
    ((7.0, 6.5), (7.0, 1.0)),
    ((3.0, 5.0), (0.0, 5.0)),
    # Beyond the outer walls: 2 m out, as for a box.
    ((-20.0, 0.0), (-10.0, 0.0)),
    ((0.0, -30.0), (0.0, -9.0)),
    # Beyond an outer corner: 2 m from the corner itself.
    ((20.0, -19.0), (9.414, -8.414)),
]


def rig(outline=DEEP, source="scan", room=None, stage=(16.0, 14.0, 6.0)):
    shell_room = {"width": 16.0, "depth": 14.0, "height": 6.0} if room is None else room
    if outline is not None:
        shell_room = {**shell_room, "outline": [{"x": x, "z": z} for x, z in outline]}
    return SimpleNamespace(
        stage_width=stage[0], stage_depth=stage[1], stage_height=stage[2],
        room_shell={"source": source, "room": shell_room},
    )


class TestWhichRoomsHaveAnOutline:

    def test_a_scanned_room_that_is_not_a_box_has_one(self):
        assert position_outline(rig()) == [(float(x), float(z)) for x, z in DEEP]

    def test_a_box_room_an_old_shell_and_a_preset_have_none(self):
        assert position_outline(rig(outline=None)) is None
        assert position_outline(rig(source="preset")) is None
        assert position_outline(SimpleNamespace(room_shell=None)) is None
        assert position_outline(SimpleNamespace(room_shell={"source": "scan"})) is None
        assert position_outline(SimpleNamespace(room_shell={"source": "scan", "room": None})) is None

    @pytest.mark.parametrize("outline", [
        [],
        DEEP[:2],
        [(0, 0), (5, 0), (10, 0)],            # no area
        [(0, 0), (0.5, 0), (0.5, 0.5)],       # under a square metre
    ])
    def test_an_outline_that_is_not_one_is_ignored(self, outline):
        assert position_outline(rig(outline=outline)) is None

    def test_a_corner_with_a_number_missing_is_ignored(self):
        broken = rig()
        broken.room_shell["room"]["outline"][3] = {"x": float("nan"), "z": 1.0}
        assert position_outline(broken) is None
        broken.room_shell["room"]["outline"][3] = {"x": "2", "z": 1.0}
        assert position_outline(broken) is None
        broken.room_shell["room"]["outline"][3] = {"x": 2.0}
        assert position_outline(broken) is None
        broken.room_shell["room"]["outline"] = "L"
        assert position_outline(broken) is None

    def test_a_room_with_no_usable_size_has_none(self):
        assert position_outline(rig(room={"width": 16.0, "depth": 14.0, "height": 1.0})) is None
        assert position_outline(rig(room={"width": "16", "depth": 14.0, "height": 6.0})) is None
        assert position_outline(rig(room={"depth": 14.0, "height": 6.0})) is None


class TestHeldToTheOutline:

    def test_the_notch_is_outside_the_room(self):
        outline = position_outline(rig())
        assert inside_outline(outline, -5.0, 3.0)
        assert inside_outline(outline, 6.0, -4.0)
        assert not inside_outline(outline, 4.0, 4.0)
        assert not inside_outline(outline, 0.0, 0.0)
        assert not inside_outline(outline, 9.0, -4.0)

    @pytest.mark.parametrize("put, held", HELD)
    def test_a_position_is_held_to_within_the_margin_of_the_room(self, put, held):
        assert hold_position(rig(), *put) == pytest.approx(held, abs=0.0006)

    @pytest.mark.parametrize("put, held", HELD)
    def test_what_is_held_is_never_further_than_the_margin_from_the_room(self, put, held):
        outline = position_outline(rig())
        x, z = hold_near_outline(outline, *put)
        assert (x, z) == pytest.approx(held, abs=0.0006)
        # Holding it again moves it no further.
        assert hold_near_outline(outline, x, z) == pytest.approx((x, z), abs=1e-9)

    def test_the_corners_may_come_in_either_order(self):
        backwards = rig(outline=DEEP[::-1])
        for put, held in HELD:
            assert hold_position(backwards, *put) == pytest.approx(held, abs=0.0006)

    def test_the_box_is_still_the_outer_limit(self):
        """The same two steps as the 3D view: the outline first, then the box."""
        limit_x, limit_z, top = position_limits(rig())
        assert (limit_x, limit_z, top) == (10.0, 9.0, 8.0)
        for put in [(500.0, 500.0), (-500.0, 3.0), (3.0, -500.0), (500.0, -500.0)]:
            x, z = hold_position(rig(), *put)
            assert abs(x) <= limit_x and abs(z) <= limit_z

    def test_a_box_room_is_held_exactly_as_it_was(self):
        box = rig(outline=None)
        assert hold_position(box, 500.0, -500.0) == (10.0, -9.0)
        assert hold_position(box, 4.0, 4.0) == (4.0, 4.0)
        assert hold_position(box, 1.23456, -2.34567) == (1.235, -2.346)
        # With no room at all: the stage and its margin.
        bare = SimpleNamespace(stage_width=12.0, stage_depth=10.0, stage_height=8.0, room_shell=None)
        assert hold_position(bare, 500.0, -500.0) == (8.0, -7.0)

    def test_the_margin_is_the_one_a_box_is_held_to(self):
        assert OUTSIDE_MARGIN_M == 2.0
        outline = position_outline(rig())
        assert hold_near_outline(outline, 4.0, 4.0, margin=0.5) == pytest.approx((4.0, -0.5))
