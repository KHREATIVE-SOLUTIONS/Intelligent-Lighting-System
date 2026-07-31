"""
Fixture Capability Derivation
=============================

`derive_fixture_capabilities` accepts several shapes of "fixture", and the two
that come straight out of the library ORM are the ones a caller is most likely
to reach for. Neither carries what the naive attribute lookup expects: an
`app.models.fixture.Fixture` hangs its channels off modes, and a `FixtureMode`
has no pan/tilt travel of its own. Both used to answer with a fabricated guess
rather than an error, so nothing downstream could tell.
"""

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from app.models.fixture import ChannelType, Fixture, FixtureChannel, FixtureMode, FixtureType
from app.services.lighting.fixture_capabilities import derive_fixture_capabilities


BUNDLED_DIR = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "bundled"


def _profile(data: Dict[str, Any]) -> Fixture:
    """A detached ORM profile graph, as a library query would return it."""
    fixture = Fixture(
        manufacturer=data["manufacturer"],
        model=data["model"],
        fixture_type=FixtureType(data.get("fixture_type", "other")),
        pan_range=data.get("pan_range", 540.0),
        tilt_range=data.get("tilt_range", 270.0),
        has_rgb=data.get("has_rgb", False),
        has_cmy=data.get("has_cmy", False),
    )
    fixture.modes = []
    for mode_data in data.get("modes", []):
        mode = FixtureMode(
            name=mode_data["name"], channel_count=mode_data["channel_count"]
        )
        mode.channels = [
            FixtureChannel(
                channel_number=ch["channel_number"],
                channel_type=ChannelType(ch.get("channel_type", "other")),
                name=ch["name"],
                is_fine=ch.get("is_fine", False),
            )
            for ch in mode_data["channels"]
        ]
        mode.fixture = fixture
        fixture.modes.append(mode)
    return fixture


def _bundled(stem: str) -> Dict[str, Any]:
    with (BUNDLED_DIR / f"{stem}.json").open(encoding="utf-8") as f:
        return json.load(f)


def test_a_library_profile_is_read_from_its_modes_not_the_type_table():
    data = _bundled("etc_source_four_led_s2")
    caps = derive_fixture_capabilities(_profile(data))

    # Nothing in this fixture's channel list is a gobo, zoom, focus or iris. The
    # spot entry of the type table claims all four.
    assert caps.supports_gobo is False
    assert caps.supports_zoom is False
    assert caps.supports_focus is False
    assert caps.supports_iris is False
    assert caps.supports_rgb is True
    assert caps.movement_speed_class == "static"
    assert caps.supports_movement is False


def test_a_mode_reports_the_travel_its_profile_declares():
    data = _bundled("robe_robin_megapointe")
    profile = _profile(data)
    mode = max(profile.modes, key=lambda m: m.channel_count)

    caps = derive_fixture_capabilities(mode, fixture_type="beam")

    assert caps.tilt_range == pytest.approx(data["tilt_range"])
    assert caps.pan_range == pytest.approx(data["pan_range"])


def test_a_profile_and_one_of_its_modes_agree_on_travel():
    profile = _profile(_bundled("robe_robin_megapointe"))
    mode = max(profile.modes, key=lambda m: m.channel_count)

    assert derive_fixture_capabilities(mode).tilt_range == pytest.approx(
        derive_fixture_capabilities(profile).tilt_range
    )


def test_an_engine_channel_map_still_reads_as_before():
    caps = derive_fixture_capabilities(
        {'pan': 0, 'pan_fine': 1, 'tilt': 2, 'dimmer': 3, 'gobo': 4, 'cyan': 5,
         'magenta': 6, 'yellow': 7},
        fixture_type="spot",
    )

    assert caps.supports_gobo is True
    assert caps.supports_cmy is True
    assert caps.supports_16bit_pan is True
    assert caps.supports_16bit_tilt is False
