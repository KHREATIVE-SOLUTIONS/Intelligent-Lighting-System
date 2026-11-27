"""
Undoing a room scan's moves: what is put back and what is left alone
====================================================================

services/room_scan/undo.py, without a database. The rule under test: an undo
takes back only what the scan did. A fixture is put back only while it is still
the guess the scan left, standing where the scan put it; anything a person has
done to it since is skipped, with the reason.
"""

from types import SimpleNamespace

from app.services.room_scan.undo import plan_undo, record_moves, restore, undo_count, undo_message

GUESS = ["position_source:template", "position_unconfirmed"]
SHIFTED = ["position_source:template", "position_unconfirmed", "position_hint:room_scan"]


def fixture(fixture_id, at, tags, name=None):
    return SimpleNamespace(
        id=fixture_id, name=name or f"Spot {fixture_id}",
        position_x=at[0], position_y=at[1], position_z=at[2], tags=list(tags),
    )


def moved(fixture_id, came_from, went_to, tags_before=GUESS):
    return {
        "rig_fixture_id": fixture_id, "name": f"Spot {fixture_id}",
        "from": came_from, "to": went_to, "tags_before": list(tags_before),
    }


def place(f):
    return (f.position_x, f.position_y, f.position_z)


class TestRecord:

    def test_an_apply_that_moved_nothing_keeps_the_earlier_record(self):
        first = record_moves(None, [moved(1, (0, 6, -1.5), (0, 4, 0.5))], "club.obj")
        assert record_moves(first, [], "club.obj") is first
        assert record_moves(None, [], "club.obj") is None

    def test_the_record_says_where_each_fixture_stood_and_went(self):
        record = record_moves(None, [moved(1, (0, 6, -1.5), (0, 4, 0.5))], "club.obj")
        assert undo_count(record) == 1 and record["file"] == "club.obj" and record["applied_at"]
        entry = record["moves"][0]
        assert entry["from"] == {"x": 0, "y": 6, "z": -1.5}
        assert entry["to"] == {"x": 0, "y": 4, "z": 0.5}
        assert entry["tags_before"] == GUESS

    def test_a_second_scan_keeps_the_place_before_any_scan(self):
        first = record_moves(None, [
            moved(1, (0, 6, -1.5), (0, 4, 0.5)),
            moved(2, (2, 6, -1.5), (2, 4, 0.5)),
        ], "first.obj")
        # The second scan shifts fixture 1 again and a third fixture for the first time.
        second = record_moves(first, [
            moved(1, (0, 4, 0.5), (0, 4.2, 1.0), tags_before=SHIFTED),
            moved(3, (4, 6, -1.5), (4, 4.2, 1.0)),
        ], "second.obj")

        entries = {entry["rig_fixture_id"]: entry for entry in second["moves"]}
        assert set(entries) == {1, 2, 3}
        # Fixture 1 goes all the way back, to its tags before the first scan.
        assert entries[1]["from"] == {"x": 0, "y": 6, "z": -1.5}
        assert entries[1]["to"] == {"x": 0, "y": 4.2, "z": 1.0}
        assert entries[1]["tags_before"] == GUESS
        # Fixture 2, moved by the first scan only, keeps its entry.
        assert entries[2]["to"] == {"x": 2, "y": 4, "z": 0.5}
        assert second["file"] == "second.obj"


class TestUndo:

    def record(self):
        return record_moves(None, [
            moved(n, (n, 6.0, -1.5), (n, 4.0, 0.5)) for n in range(1, 7)
        ], "club.obj")

    def test_a_fixture_still_where_the_scan_left_it_goes_back(self):
        spot = fixture(1, (1, 4.0, 0.5), SHIFTED + ["group:Truss"])
        plan = plan_undo([spot], record_moves(None, [moved(1, (1, 6.0, -1.5), (1, 4.0, 0.5))], "club.obj"))

        assert len(plan.restores) == 1 and plan.skipped == []
        assert plan.to_dict()["restores"][0]["to"] == {"x": 1, "y": 6.0, "z": -1.5}
        # Planning writes nothing.
        assert place(spot) == (1, 4.0, 0.5)

        assert restore(plan) == 1
        assert place(spot) == (1, 6.0, -1.5)
        # The scan's hint is gone, and a tag added since the scan is kept.
        assert spot.tags == GUESS + ["group:Truss"]

    def test_what_a_person_did_since_is_skipped_with_the_reason(self):
        fixtures = [
            fixture(1, (1, 4.0, 0.5), SHIFTED),                                   # untouched: goes back
            fixture(2, (2.3, 4.0, 0.9), ["position_source:tap"]),                 # dragged or tapped
            fixture(3, (3, 4.0, 0.5), ["position_source:confirmed"]),             # confirmed in place
            fixture(4, (4, 4.0, 0.5), ["position_source:row_fit", "position_unconfirmed"]),
            fixture(5, (5.5, 4.0, 0.5), SHIFTED),                                 # moved in the layout view
            # 6 was removed from the rig.
        ]
        plan = plan_undo(fixtures, self.record())

        assert [r.fixture.id for r in plan.restores] == [1]
        reasons = {item["rig_fixture_id"]: item["reason"] for item in plan.skipped}
        assert set(reasons) == {2, 3, 4, 5, 6}
        assert "tapped or dragged" in reasons[2]
        assert "confirmed" in reasons[3]
        assert "fitted between" in reasons[4]
        assert "moved since the scan" in reasons[5]
        assert "no longer in the rig" in reasons[6]

        before = {f.id: (place(f), list(f.tags)) for f in fixtures}
        restore(plan)
        for f in fixtures[1:]:
            assert (place(f), f.tags) == before[f.id]

    def test_a_confirmed_fixture_that_was_not_moved_is_still_skipped(self):
        """Confirmed exactly where the scan put it: the person agreed with that place."""
        spot = fixture(1, (1, 4.0, 0.5), ["position_source:confirmed", "position_hint:room_scan"])
        plan = plan_undo([spot], self.record())
        assert plan.restores == [] and plan.skipped[0]["rig_fixture_id"] == 1

    def test_no_record_is_nothing_to_undo(self):
        plan = plan_undo([fixture(1, (0, 0, 0), GUESS)], None)
        assert plan.restores == [] and plan.skipped == []
        assert undo_count(None) == 0

    def test_a_damaged_record_is_skipped_not_raised(self):
        record = {"moves": [{"rig_fixture_id": 1, "from": {"x": "?"}, "to": None}, "junk"]}
        plan = plan_undo([fixture(1, (0, 0, 0), SHIFTED)], record)
        assert plan.restores == [] and len(plan.skipped) == 1

    def test_the_message_counts_both(self):
        assert undo_message(0, 0) == "There were no room scan moves to undo."
        assert undo_message(7, 0) == "7 fixtures put back where they stood before the scan."
        text = undo_message(1, 2)
        assert text.startswith("1 fixture put back where it stood") and "2 fixtures left alone" in text
        assert undo_message(0, 1).startswith("No fixture was put back. 1 fixture left alone")
