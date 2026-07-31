"""
Bundled Library Channel Types
=============================

The shipped profiles predate the extended ChannelType set, so every subtractive
flag, iris, frost, blade and colour-correction channel in them was stored as
'other' - a type the engine never drives. Alembic revision 003 retypes the rows
already in a database; these JSON definitions are what a fresh install seeds
from, so they have to carry the corrected types too or the fix reaches only half
the installs.

The retype is name-driven, and the trap it has to avoid is an RGB+ LED engine
whose "Cyan" is an additive emitter rather than a subtractive flag: driving one
of those through the renderer's complement lights it fully at blackout.
"""

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple

import pytest

from app.models.fixture import ChannelType


BACKEND_DIR = Path(__file__).resolve().parents[2]
BUNDLED_DIR = BACKEND_DIR.parent / "data" / "fixtures" / "bundled"
MIGRATION = BACKEND_DIR / "alembic" / "versions" / "003_extended_channel_types.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("_revision_003", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


revision_003 = _load_migration()


def _definitions() -> Iterator[Tuple[str, Dict[str, Any]]]:
    for path in sorted(BUNDLED_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as f:
            yield path.name, json.load(f)


def _channels(data: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    for mode in data.get("modes", []):
        for channel in mode.get("channels", []):
            yield channel


def test_the_bundled_library_is_seedable_at_all():
    names = [name for name, _ in _definitions()]
    assert len(names) >= 50, names


def test_no_bundled_channel_still_hides_behind_other():
    """A row the migration would retype must already be right in the JSON."""
    stale = []
    for filename, data in _definitions():
        subtractive = bool(data.get("has_cmy"))
        for channel in _channels(data):
            if channel.get("channel_type") != ChannelType.OTHER.value:
                continue
            member = revision_003._retyped(channel.get("name", ""), subtractive)
            if member is not None:
                stale.append(f"{filename}:{channel['name']} -> {member.lower()}")

    assert stale == [], (
        "these channels name a mechanism the engine can drive but are typed "
        f"'other', so a fresh install seeds them undrivable: {stale}"
    )


def test_every_bundled_channel_type_is_a_real_member():
    for filename, data in _definitions():
        for channel in _channels(data):
            ChannelType(channel["channel_type"])  # raises on an unknown value


@pytest.mark.parametrize("stem", ["etc_source_four_led_s2", "etc_desire_d22_studio"])
def test_an_additive_cyan_emitter_is_not_retyped_as_a_subtractive_flag(stem):
    with (BUNDLED_DIR / f"{stem}.json").open(encoding="utf-8") as f:
        data = json.load(f)

    assert data["has_rgb"] is True and data["has_cmy"] is False
    cyan = [c for c in _channels(data) if c["name"].lower() == "cyan"]
    assert cyan, f"{stem} no longer declares a Cyan channel; this test is stale"
    for channel in cyan:
        assert channel["channel_type"] != ChannelType.CYAN.value, (
            "this fixture mixes additively; typing its cyan emitter as a "
            "subtractive flag drives it to full at blackout"
        )


def test_a_cmy_spot_declares_its_flags_as_cmy():
    with (BUNDLED_DIR / "ayrton_ghibli.json").open(encoding="utf-8") as f:
        data = json.load(f)

    mode = next(m for m in data["modes"] if m["name"] == "36-Channel")
    typed = {c["name"]: c["channel_type"] for c in mode["channels"]}

    assert typed["Cyan"] == ChannelType.CYAN.value
    assert typed["Magenta"] == ChannelType.MAGENTA.value
    assert typed["Yellow"] == ChannelType.YELLOW.value
    # Per the fine-channel convention, a fine row repeats its parent's type.
    assert typed["Cyan Fine"] == ChannelType.CYAN.value
    assert typed["CTO"] == ChannelType.CTO.value
    assert typed["Iris"] == ChannelType.IRIS.value
    assert typed["Frost"] == ChannelType.FROST.value


def test_the_retype_rules_leave_an_ambiguous_name_alone():
    for name in ("Color Temp", "CTC", "Fan Control", "Hue", "Saturation", "Effect"):
        assert revision_003._retyped(name, True) is None, name


def _stale_database(tmp_path, rows):
    """A pre-003 library: channels typed 'other' whose names say what they are."""
    import sqlalchemy as sa

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'stale.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE fixtures (id INTEGER PRIMARY KEY, has_cmy BOOLEAN)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE fixture_modes (id INTEGER PRIMARY KEY, fixture_id INTEGER)"
        )
        conn.exec_driver_sql(
            "CREATE TABLE fixture_channels (id INTEGER PRIMARY KEY, mode_id INTEGER, "
            "channel_type VARCHAR(13), name VARCHAR(100))"
        )
        conn.exec_driver_sql("INSERT INTO fixtures VALUES (1, 1), (2, 0)")
        conn.exec_driver_sql(
            "INSERT INTO fixture_modes VALUES (10, 1), (20, 2)"
        )
        for channel_id, mode_id, channel_type, name in rows:
            conn.exec_driver_sql(
                "INSERT INTO fixture_channels VALUES (?, ?, ?, ?)",
                (channel_id, mode_id, channel_type, name),
            )
    return engine


def test_the_migration_retypes_rows_already_in_a_database(tmp_path):
    engine = _stale_database(tmp_path, [
        (1, 10, "OTHER", "Cyan"),
        (2, 10, "OTHER", "Cyan Fine"),
        (3, 10, "OTHER", "CTO"),
        (4, 10, "OTHER", "Blade 1A"),
        (5, 10, "OTHER", "Iris"),
        (6, 10, "OTHER", "CTC"),
        (7, 10, "DIMMER", "Dimmer"),
        # A fixture that mixes additively: its Cyan is an emitter, not a flag.
        (8, 20, "OTHER", "Cyan"),
        (9, 20, "OTHER", "Lime"),
    ])

    with engine.begin() as conn:
        revision_003._backfill_channel_types(conn)

    with engine.connect() as conn:
        typed = dict(
            conn.exec_driver_sql(
                "SELECT id, channel_type FROM fixture_channels"
            ).fetchall()
        )

    assert typed[1] == "CYAN"
    assert typed[2] == "CYAN"
    assert typed[3] == "CTO"
    assert typed[4] == "FRAMING"
    assert typed[5] == "IRIS"
    assert typed[6] == "OTHER", "'CTC' does not name a member; guessing is worse"
    assert typed[7] == "DIMMER", "a row that already has a type is not rewritten"
    assert typed[8] == "OTHER", (
        "this fixture does not declare CMY mixing, so its Cyan is an additive "
        "emitter and must not be driven as a subtractive flag"
    )
    assert typed[9] == "LIME"
    assert len(typed) == 9, "the back-fill must not add or drop rows"
