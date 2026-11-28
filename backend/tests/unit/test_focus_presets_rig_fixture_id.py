"""
Focus presets: each head's row names the rig fixture it is
==========================================================

The 3D view's preview of a preset (docs/FOCUS_PRESETS.md, "In the app") has to
find the head a row means. `fixture_id` is the console number, which
`assign_numbers` gives out again when two fixtures share one or one has none;
`rig_fixture_id` is the rig fixture row's own id, the one the view draws it by.
The CSV is not changed by it.
"""

from types import SimpleNamespace

from app.services.console_export.model import from_rig
from app.services.focus_presets.table import CSV_COLUMNS, build_table, focus_csv, table_dict

MOVER = [SimpleNamespace(channel_type=t) for t in ("pan", "pan_fine", "tilt", "tilt_fine", "dimmer")]
ROOM = {"room": {"width": 12.0, "depth": 10.0, "height": 6.0}}


def row(row_id, number, name, position):
    return SimpleNamespace(
        id=row_id, fixture_number=number, name=name, universe=0, dmx_address=1 + 20 * row_id,
        position_x=position[0], position_y=position[1], position_z=position[2],
        rotation_x=0.0, rotation_y=0.0, rotation_z=0.0,
        group_name="Movers", tags=["position_source:mvr"], is_active=True, is_inverted=False,
        fixture=SimpleNamespace(manufacturer="Acme", model="Mover", gdtf_file=None, fixture_type="moving_head",
                                pan_range=540.0, tilt_range=270.0),
        mode=SimpleNamespace(name="Std", channel_count=len(MOVER), channels=MOVER),
    )


def table(rows):
    rig = SimpleNamespace(id=3, name="Focus rig", room_shell=ROOM, focus_targets=None)
    return build_table(rig, rows, from_rig(rig, rows))


def test_every_head_row_names_its_rig_fixture():
    rows = [row(41, 1, "Spot L", (-3.0, 6.0, -1.0)), row(57, 2, "Spot R", (3.0, 6.0, -1.0))]
    out = table_dict(table(rows))
    placed = [t for t in out["targets"] if not t["skipped"]]
    assert placed
    for target in placed:
        by_name = {f["name"]: f["rig_fixture_id"] for f in target["fixtures"]}
        assert by_name == {"Spot L": 41, "Spot R": 57}


def test_renumbered_heads_still_name_their_own_row():
    # Both ask for console number 5: the second is renumbered, its row id is not.
    rows = [row(10, 5, "First", (-2.0, 6.0, 0.0)), row(11, 5, "Second", (2.0, 6.0, 0.0))]
    dance = next(t for t in table_dict(table(rows))["targets"] if t["key"] == "dance_floor")
    pairs = sorted((f["fixture_id"], f["rig_fixture_id"]) for f in dance["fixtures"])
    assert pairs[0] == (5, 10)
    assert pairs[1][0] != 5 and pairs[1][1] == 11


def test_the_csv_has_no_new_column():
    rows = [row(41, 1, "Spot L", (-3.0, 6.0, -1.0))]
    header = focus_csv(table(rows)).splitlines()[0].split(",")
    assert "rig_fixture_id" not in header
    assert header == list(CSV_COLUMNS)
