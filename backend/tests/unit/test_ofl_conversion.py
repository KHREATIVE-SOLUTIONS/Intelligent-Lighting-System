"""
Open Fixture Library Conversion Tests
=====================================

OFL expresses a 16-bit channel as an alias listed in `fineChannelAliases` on the
parent channel and referenced by name from the mode's channel list - the alias is
never a key in `availableChannels`. A converter that only looks in
`availableChannels` sees an unknown key and types the row `other`, which the engine
never drives: every OFL import loses the fine byte of its movement.

No test here touches the network. Fixture definitions are hand-built, and the two
client tests replace httpx's transport so a request that would leave the machine
raises instead.
"""

import asyncio
import json
from typing import Any, Dict, List

import httpx

from app.models.fixture import ChannelType
from app.schemas.fixture import ChannelValueRange
from app.services.effects.fixture_groups import Fixture as EngineFixture, _render_fixture
from app.services.fixture_library.ofl_client import OFLClient, convert_ofl_to_internal


# Shaped like a real OFL fixture definition, verified against the published
# schema: an availableChannels entry carries no type of its own, only a single
# `capability` or a list of `capabilities`, and the type lives on those.
MOVER: Dict[str, Any] = {
    "name": "Auro Beam 150",
    "categories": ["Moving Head"],
    "physical": {"weight": 12.5, "power": 200, "lens": {"degreesMinMax": [3, 3]}},
    "wheels": {
        "Gobo Wheel": {
            "slots": [
                {"type": "Open"},
                {"type": "Gobo", "name": "Gobo 1"},
                {"type": "Gobo", "name": "Gobo 2"},
                {"type": "Gobo", "name": "Gobo 3"},
            ],
        },
    },
    "availableChannels": {
        # "Pan LSB" shares no suffix with its parent, so only fineChannelAliases
        # can resolve it: a converter that ignores the alias map cannot pass.
        "Pan": {
            "fineChannelAliases": ["Pan LSB"],
            "defaultValue": 128,
            "capability": {"type": "Pan", "angleStart": "0deg", "angleEnd": "540deg"},
        },
        "Tilt": {
            "fineChannelAliases": ["Tilt fine"],
            "capability": {"type": "Tilt", "angleStart": "0deg", "angleEnd": "270deg"},
        },
        "Dimmer": {
            "fineChannelAliases": ["Dimmer fine"],
            "capability": {"type": "Intensity"},
        },
        # Real OFL alias names are free text; nothing guarantees the word "fine".
        "Zoom": {
            "fineChannelAliases": ["Zoom LSB"],
            "capability": {"type": "Zoom", "angleStart": "10deg", "angleEnd": "40deg"},
        },
        "Red": {"capability": {"type": "ColorIntensity", "color": "Red"}},
        "Green": {"capability": {"type": "ColorIntensity", "color": "Green"}},
        "Blue": {"capability": {"type": "ColorIntensity", "color": "Blue"}},
        "Gobo Wheel": {
            "capabilities": [
                {"dmxRange": [0, 9], "type": "WheelSlot",
                 "wheel": "Gobo Wheel", "slotNumber": 1},
                {"dmxRange": [10, 19], "type": "WheelSlot",
                 "wheel": "Gobo Wheel", "slotNumber": 2},
                {"dmxRange": [20, 29], "type": "WheelSlot",
                 "wheel": "Gobo Wheel", "slotNumber": 3},
                {"dmxRange": [30, 255], "type": "WheelSlot",
                 "wheel": "Gobo Wheel", "slotNumber": 4},
            ],
        },
    },
    "modes": [
        {
            "name": "12-channel",
            "shortName": "12ch",
            "channels": [
                "Pan", "Pan LSB", "Tilt", "Tilt fine",
                "Dimmer", "Dimmer fine",
                "Zoom", "Zoom LSB",
                "Red", "Green", "Blue",
                "Gobo Wheel",
            ],
        },
    ],
}


def _convert(ofl_data: Dict[str, Any] = None) -> Dict[str, Any]:
    return convert_ofl_to_internal(
        MOVER if ofl_data is None else ofl_data, "cameo", "auro-beam-150"
    )


def _slots(mode: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    rows: Dict[int, Dict[str, Any]] = {}
    for channel in mode["channels"]:
        number = channel["channel_number"]
        assert number not in rows, f"two channels claim DMX slot {number}"
        rows[number] = channel
    return rows


def _ranges(channel: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Value ranges exactly as they are written to the JSON column.

    ChannelValueRange accepts either "min"/"max" or "min_value"/"max_value", so
    validating through it cannot see which spelling landed in the column - and
    app/schemas/rig.py passes the column through raw on rig export. The raw keys
    are asserted here, then the schema is run over them to prove the API can
    still read what was written.
    """
    entries = list(channel.get("value_ranges") or [])
    for entry in entries:
        assert set(entry) == {"name", "min_value", "max_value"}, (
            f"value_ranges is stored raw; {sorted(entry)} is not the column's "
            "spelling and a consumer reading it directly regresses silently"
        )
        ChannelValueRange(**entry)
    return sorted(entries, key=lambda entry: entry["min_value"])


def _entries(value: Any) -> List[Any]:
    """The fixture list out of whatever container the client hands back."""
    if value is None:
        return []
    if isinstance(value, dict):
        for key in ("results", "items", "fixtures", "data"):
            if isinstance(value.get(key), list):
                return value[key]
        return []
    return list(value)


def _install_transport(monkeypatch, responder) -> List[httpx.Request]:
    """Route every httpx request through `responder`. Nothing reaches the network."""
    seen: List[httpx.Request] = []

    async def handle_async_request(self, request):
        seen.append(request)
        return responder(request)

    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", handle_async_request
    )
    return seen


def _unreachable(request):
    raise httpx.ConnectError("no route to host", request=request)


def _run(scenario):
    """Drive an async scenario without depending on a pytest async plugin.

    requirements.txt pins pytest-asyncio, but it is not installed here and pytest
    reports `asyncio_mode = auto` as an unknown option, so a bare `async def` test
    is collected and then errored rather than run - it neither passes nor fails on
    its assertions. Owning the event loop keeps these three honest either way.
    """
    return asyncio.run(scenario())


def test_fine_channel_aliases_resolve_to_their_parent_channel():
    mode = _convert()["modes"][0]
    rows = _slots(mode)

    assert rows[2]["channel_type"] == ChannelType.PAN_FINE.value
    assert rows[2]["is_fine"] is True
    assert rows[2]["coarse_channel"] == 1

    assert rows[4]["channel_type"] == ChannelType.TILT_FINE.value
    assert rows[4]["is_fine"] is True
    assert rows[4]["coarse_channel"] == 3


def test_an_alias_without_a_matching_fine_channel_type_keeps_its_parents_type():
    rows = _slots(_convert()["modes"][0])

    # ChannelType has no DIMMER_FINE or ZOOM_FINE member, so the fine row carries
    # the parent's type and is distinguished by is_fine/coarse_channel.
    assert rows[6]["channel_type"] == ChannelType.DIMMER.value
    assert rows[6]["is_fine"] is True
    assert rows[6]["coarse_channel"] == 5

    assert rows[8]["channel_type"] == ChannelType.ZOOM.value
    assert rows[8]["is_fine"] is True
    assert rows[8]["coarse_channel"] == 7


def test_an_alias_name_without_the_word_fine_is_still_a_fine_channel():
    rows = _slots(_convert()["modes"][0])

    assert rows[8]["name"] == "Zoom LSB"
    assert rows[8]["is_fine"] is True, (
        "the alias is declared in fineChannelAliases; its name is free text and "
        "must not be what decides"
    )


def test_no_channel_of_a_fully_declared_fixture_falls_through_to_other():
    mode = _convert()["modes"][0]

    stray = [
        (ch["channel_number"], ch["name"])
        for ch in mode["channels"]
        if ch["channel_type"] == ChannelType.OTHER.value
    ]

    assert stray == [], (
        f"every channel in this mode is declared by OFL, but {stray} were typed "
        "'other', which the engine never drives"
    )


def test_the_mode_spans_every_slot_it_lists():
    mode = _convert()["modes"][0]
    rows = _slots(mode)

    assert sorted(rows) == list(range(1, 13))
    assert mode["channel_count"] == 12
    assert mode["name"] == "12-channel"

    assert [rows[n]["channel_type"] for n in (9, 10, 11)] == [
        ChannelType.RED.value, ChannelType.GREEN.value, ChannelType.BLUE.value,
    ]
    assert rows[12]["channel_type"] == ChannelType.GOBO.value


def test_a_null_mode_slot_holds_its_dmx_slot():
    ofl_data = dict(MOVER)
    ofl_data["modes"] = [{
        "name": "gapped",
        "channels": ["Dimmer", None, "Red", "Green"],
    }]

    rows = _slots(convert_ofl_to_internal(ofl_data, "cameo", "auro-beam-150")["modes"][0])

    assert sorted(rows) == [1, 2, 3, 4]
    assert rows[1]["channel_type"] == ChannelType.DIMMER.value
    assert rows[3]["channel_type"] == ChannelType.RED.value, (
        "an unused slot still consumes a DMX address; collapsing it shifts "
        "everything after it"
    )
    assert rows[4]["channel_type"] == ChannelType.GREEN.value


def test_capabilities_become_value_ranges():
    rows = _slots(_convert()["modes"][0])
    ranges = _ranges(rows[12])

    assert [(e["min_value"], e["max_value"]) for e in ranges] == [
        (0, 9), (10, 19), (20, 29), (30, 255),
    ]
    # The wheel names its slots; the ranges are useless for cueing a gobo unless
    # that name comes with them.
    assert [e["name"] for e in ranges] == ["Open", "Gobo 1", "Gobo 2", "Gobo 3"]

    holding = [e for e in ranges if e["min_value"] <= 15 <= e["max_value"]]
    assert [e["name"] for e in holding] == ["Gobo 1"]


def test_fixture_identity_and_capabilities_survive_the_conversion():
    result = _convert()

    assert result["model"] == "Auro Beam 150"
    assert result["source"] == "ofl"
    assert result["source_id"] == "cameo/auro-beam-150"
    assert result["fixture_type"] == "moving_head"
    assert result["has_rgb"] is True
    assert result["weight"] == 12.5


SUBTRACTIVE: Dict[str, Any] = {
    "name": "Sub Mover 1200",
    "categories": ["Moving Head"],
    "availableChannels": {
        "Dimmer": {"capability": {"type": "Intensity"}},
        "Cyan": {"capability": {"type": "ColorIntensity", "color": "Cyan"}},
        "Magenta": {"capability": {"type": "ColorIntensity", "color": "Magenta"}},
        "Yellow": {"capability": {"type": "ColorIntensity", "color": "Yellow"}},
    },
    "modes": [{
        "name": "4-channel",
        "channels": ["Dimmer", "Cyan", "Magenta", "Yellow"],
    }],
}


def test_subtractive_colour_channels_map_to_cyan_magenta_yellow():
    rows = _slots(
        convert_ofl_to_internal(SUBTRACTIVE, "robe", "sub-mover-1200")["modes"][0]
    )

    assert [rows[n]["channel_type"] for n in (1, 2, 3, 4)] == [
        ChannelType.DIMMER.value,
        ChannelType.CYAN.value,
        ChannelType.MAGENTA.value,
        ChannelType.YELLOW.value,
    ], "a CMY mover typed 'other' is a mover the engine can never colour"
    assert convert_ofl_to_internal(SUBTRACTIVE, "robe", "sub-mover-1200")["has_cmy"] is True


def test_a_percentage_default_value_is_not_silently_zero():
    # OFL writes defaults as "50%" as readily as it writes a number. Reading a
    # percentage as 0 parks a mover against its pan end stop instead of centring it.
    percent = {
        "name": "Percent Mover",
        "categories": ["Moving Head"],
        "availableChannels": {
            "Pan": {
                "defaultValue": "50%",
                "capability": {"type": "Pan", "angleStart": "0deg", "angleEnd": "540deg"},
            },
        },
        "modes": [{"name": "1-channel", "channels": ["Pan"]}],
    }
    converted = _slots(convert_ofl_to_internal(percent, "test", "percent")["modes"][0])

    assert converted[1]["default_value"] in (127, 128), (
        f"'50%' became {converted[1]['default_value']}"
    )


COMBINED_INTENSITY_STROBE: Dict[str, Any] = {
    "name": "Stage Par 6in1",
    "categories": ["Color Changer"],
    "availableChannels": {
        "Red": {"capability": {"type": "ColorIntensity", "color": "Red"}},
        "Green": {"capability": {"type": "ColorIntensity", "color": "Green"}},
        "Blue": {"capability": {"type": "ColorIntensity", "color": "Blue"}},
        # Master intensity that also owns a strobe band. 199 DMX values of
        # intensity against 47 of strobe.
        "Dimmer / Chase / Strobe": {"capabilities": [
            {"dmxRange": [0, 190], "type": "Intensity"},
            {"dmxRange": [191, 200], "type": "Effect", "effectName": "Chase"},
            {"dmxRange": [201, 247], "type": "ShutterStrobe", "shutterEffect": "Strobe"},
            {"dmxRange": [248, 255], "type": "Intensity", "brightness": "100%"},
        ]},
        # A dedicated strobe rate: Open is its resting state, at the bottom.
        "Strobe": {"capabilities": [
            {"dmxRange": [0, 0], "type": "ShutterStrobe", "shutterEffect": "Open"},
            {"dmxRange": [1, 5], "type": "ShutterStrobe", "shutterEffect": "Strobe"},
            {"dmxRange": [6, 10], "type": "ShutterStrobe", "shutterEffect": "Open"},
            {"dmxRange": [11, 255], "type": "ShutterStrobe", "shutterEffect": "Strobe"},
        ]},
        "Master Dimmer": {"capability": {"type": "Intensity"}},
    },
    "modes": [
        {"name": "4-channel", "channels": [
            "Red", "Green", "Blue", "Dimmer / Chase / Strobe"]},
        {"name": "5-channel", "channels": [
            "Master Dimmer", "Red", "Green", "Blue", "Strobe"]},
    ],
}

CONVENTIONAL_SHUTTER: Dict[str, Any] = {
    "name": "Conventional Spot",
    "categories": ["Moving Head"],
    "availableChannels": {
        "Shutter": {"capabilities": [
            {"dmxRange": [0, 31], "type": "ShutterStrobe", "shutterEffect": "Closed"},
            {"dmxRange": [32, 63], "type": "ShutterStrobe", "shutterEffect": "Open"},
            {"dmxRange": [64, 95], "type": "ShutterStrobe", "shutterEffect": "Strobe"},
            {"dmxRange": [96, 255], "type": "ShutterStrobe", "shutterEffect": "Open"},
        ]},
        "Dimmer": {"capability": {"type": "Intensity"}},
    },
    "modes": [{"name": "2-channel", "channels": ["Shutter", "Dimmer"]}],
}


def _render(mode: Dict[str, Any], **state: float) -> Dict[str, int]:
    """The DMX bytes the engine would emit for a fixture patched in this mode."""
    fixture = EngineFixture(
        id="f1",
        name="F1",
        dmx_address=1,
        channels={ch["channel_type"]: ch["channel_number"] - 1 for ch in mode["channels"]},
        pan_range=0.0,
        tilt_range=0.0,
    )
    for name, value in state.items():
        setattr(fixture, name, value)
    return _render_fixture(fixture)


def test_a_master_intensity_channel_that_also_strobes_is_not_typed_strobe():
    mode = convert_ofl_to_internal(
        COMBINED_INTENSITY_STROBE, "briteq", "bt-stagepar-6in1"
    )["modes"][0]
    rows = _slots(mode)

    assert rows[4]["channel_type"] == ChannelType.DIMMER.value, (
        "199 of this channel's 256 values are intensity; typing it 'strobe' makes "
        "the renderer write 0 there, which is 0% intensity"
    )
    assert _render(mode, dimmer=1.0, red=1.0)[ChannelType.DIMMER.value] == 255, (
        "the fixture is dead on stage at full"
    )


def test_a_strobe_rate_channel_rests_where_the_shutter_is_open():
    mode = convert_ofl_to_internal(
        COMBINED_INTENSITY_STROBE, "briteq", "bt-stagepar-6in1"
    )["modes"][1]
    rows = _slots(mode)

    assert rows[5]["channel_type"] == ChannelType.STROBE.value, (
        "Open at DMX 0 is this channel's 'no strobe' state; typing it 'shutter' "
        "makes the renderer write 255, which is the fastest strobe it has"
    )
    assert _render(mode, dimmer=1.0)[ChannelType.STROBE.value] == 0


def test_a_shutter_whose_open_state_is_at_the_top_stays_a_shutter():
    mode = convert_ofl_to_internal(
        CONVENTIONAL_SHUTTER, "test", "conventional-spot"
    )["modes"][0]
    rows = _slots(mode)

    assert rows[1]["channel_type"] == ChannelType.SHUTTER.value
    assert _render(mode, dimmer=1.0)[ChannelType.SHUTTER.value] == 255, (
        "DMX 255 is Open on this channel, so the renderer's resting value is right"
    )


def test_a_colour_channel_carrying_a_strobe_band_keeps_its_colour():
    gigbar = {
        "name": "GigBAR 2",
        "categories": ["Effect"],
        "availableChannels": {
            "Red/Green Par": {"capabilities": [
                {"dmxRange": [0, 0], "type": "NoFunction"},
                {"dmxRange": [1, 200], "type": "ColorIntensity", "color": "Red"},
                {"dmxRange": [201, 255], "type": "ShutterStrobe",
                 "shutterEffect": "Strobe"},
            ]},
        },
        "modes": [{"name": "1-channel", "channels": ["Red/Green Par"]}],
    }
    rows = _slots(convert_ofl_to_internal(gigbar, "chauvet-dj", "gigbar-2")["modes"][0])

    assert rows[1]["channel_type"] == ChannelType.RED.value, (
        "a mode whose only colour channel is typed 'strobe' has no colour at all"
    )


def test_search_posts_to_the_endpoint_the_live_api_actually_serves(monkeypatch):
    seen = _install_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json=["cameo/auro-beam-150"]),
    )

    async def scenario():
        client = OFLClient()
        try:
            return await client.search_fixtures("auro beam")
        finally:
            await client.close()

    results = _run(scenario)

    assert len(seen) == 1, f"expected one request, got {[str(r.url) for r in seen]}"
    request = seen[0]

    assert request.method == "POST", (
        "GET /fixtures/search answers 500 on the live API; the search that works is "
        "a POST to get-search-results"
    )
    assert request.url.path.endswith("/get-search-results"), request.url

    body = json.loads(request.content)
    assert body["searchQuery"] == "auro beam"
    assert body["manufacturersQuery"] == []
    assert body["categoriesQuery"] == []

    assert any("auro-beam-150" in str(entry) for entry in _entries(results)), (
        f"the search result did not carry the fixture the API returned: {results!r}"
    )


def test_a_search_that_cannot_reach_the_library_does_not_read_as_no_results(
    monkeypatch,
):
    async def search():
        client = OFLClient()
        try:
            return await client.search_fixtures("nothing-matches-this-query")
        finally:
            await client.close()

    seen = _install_transport(monkeypatch, lambda request: httpx.Response(200, json=[]))
    empty = _run(search)

    assert seen, "the client never issued a request; the transport patch missed it"
    assert not _entries(empty)

    seen = _install_transport(monkeypatch, _unreachable)
    try:
        failed = _run(search)
    except Exception as e:
        assert not isinstance(e, (AttributeError, NameError, TypeError)), (
            f"the failure surfaced as a coding error, not a reachability one: {e!r}"
        )
    else:
        assert failed != empty, (
            "an unreachable library returned exactly what a zero-result search "
            "returns, so the browse tab can only ever say 'no results'"
        )

    assert seen, "the client never issued a request; the transport patch missed it"


def test_a_fixture_fetch_that_cannot_reach_the_library_does_not_return_none(
    monkeypatch,
):
    seen = _install_transport(monkeypatch, _unreachable)

    async def scenario():
        client = OFLClient()
        try:
            return await client.get_fixture("cameo", "auro-beam-150")
        finally:
            await client.close()

    try:
        fixture = _run(scenario)
    except Exception as e:
        assert not isinstance(e, (AttributeError, NameError, TypeError)), (
            f"the failure surfaced as a coding error, not a reachability one: {e!r}"
        )
    else:
        assert fixture is not None, (
            "an unreachable library produced None, which the import endpoint turns "
            "into 404 'Fixture not found on OFL'"
        )

    assert seen, "the client never issued a request; the transport patch missed it"
