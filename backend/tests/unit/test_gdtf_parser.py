"""
GDTF Parser Tests
=================

Every assertion here is about which DMX slot a channel lands on. Phase 1 made the
profile's channel numbers drive real output, so a channel numbered one slot late
no longer reads as a cosmetic import defect - it points a light on stage at the
wrong thing, silently.

GDTF `Offset` is a comma-separated list of 1-based DMX slots within the mode, most
significant first: "5" is an 8-bit channel at slot 5, "5,6" is a 16-bit channel whose
coarse byte is slot 5 and fine byte slot 6, and an absent or empty Offset is a
virtual channel occupying no slot at all.

The repository ships no .gdtf samples, so archives are synthesised in memory.
"""

import io
import zipfile
from typing import Any, Dict, List, Sequence, Tuple

import pytest

from app.models.fixture import ChannelType
from app.services.fixture_library.gdtf_parser import parse_gdtf


GDTF_NAMESPACE = "http://www.mvrdevelopment.org/GDTF"

_ABSENT = object()

ModeSpec = Tuple[str, Sequence[Dict[str, Any]]]


def _channel_xml(spec: Dict[str, Any]) -> str:
    """One <DMXChannel>. `offset` absent or None emits no Offset attribute."""
    offset = spec.get("offset", _ABSENT)
    offset_attr = "" if offset is _ABSENT or offset is None else f' Offset="{offset}"'

    attribute = spec["attribute"]

    # GDTF writes every DMXValue as "<value>/<byte count>", and the byte count is
    # the number of slots the Offset claims.
    byte_count = len(str(offset).split(",")) if offset_attr else 1

    physical = spec.get("physical")
    physical_attr = ""
    if physical is not None:
        physical_attr = f' PhysicalFrom="{physical[0]}" PhysicalTo="{physical[1]}"'

    channel_sets = "".join(
        f'<ChannelSet Name="{name}" DMXFrom="{dmx_from}/{byte_count}"'
        f' WheelSlotIndex="{index}"/>'
        for index, (name, dmx_from) in enumerate(spec.get("sets", ()))
    )

    return (
        f'<DMXChannel DMXBreak="1"{offset_attr}'
        f' Geometry="{spec.get("geometry", "Head")}" Highlight="255/1">'
        f'<LogicalChannel Attribute="{attribute}" Snap="No" Master="None">'
        f'<ChannelFunction Name="{attribute} 1" Attribute="{attribute}"'
        f' DMXFrom="0/{byte_count}" Default="0/{byte_count}"{physical_attr}>'
        f"{channel_sets}"
        "</ChannelFunction></LogicalChannel></DMXChannel>"
    )


def _mode_xml(name: str, channels: Sequence[Dict[str, Any]]) -> str:
    body = "".join(_channel_xml(spec) for spec in channels)
    return (
        f'<DMXMode Name="{name}" Geometry="Base">'
        f"<DMXChannels>{body}</DMXChannels><Relations/></DMXMode>"
    )


def description_xml(
    modes: Sequence[ModeSpec],
    *,
    manufacturer: str = "Phase2 Lighting",
    model: str = "Phase2 Spot 700",
    short_name: str = "P2S700",
    fixture_type_id: str = "1F2E3D4C-5B6A-4789-8A9B-0C1D2E3F4A5B",
    namespaced: bool = False,
) -> str:
    """A description.xml carrying `modes`, optionally in the GDTF default namespace."""
    xmlns = f' xmlns="{GDTF_NAMESPACE}"' if namespaced else ""
    modes_xml = "".join(_mode_xml(name, channels) for name, channels in modes)

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<GDTF DataVersion="1.2"{xmlns}>'
        f'<FixtureType Name="{model}" ShortName="{short_name}" LongName="{model}"'
        f' Manufacturer="{manufacturer}" Description="Synthesised for tests"'
        f' FixtureTypeID="{fixture_type_id}" RefFT="">'
        "<AttributeDefinitions><ActivationGroups/><FeatureGroups/></AttributeDefinitions>"
        "<Wheels/>"
        "<PhysicalDescriptions>"
        '<Properties><Weight Value="21.5"/><PowerConsumption Value="480"/></Properties>'
        "</PhysicalDescriptions>"
        "<Models/><Geometries/>"
        f"<DMXModes>{modes_xml}</DMXModes>"
        "<Revisions/><FTPresets/><Protocols/>"
        "</FixtureType></GDTF>"
    )


def gdtf_archive(
    modes: Sequence[ModeSpec],
    *,
    extra_files: Sequence[Tuple[str, bytes]] = (),
    **kwargs: Any,
) -> bytes:
    """A .gdtf archive: a ZIP whose description.xml declares `modes`."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in extra_files:
            archive.writestr(name, payload)
        archive.writestr("description.xml", description_xml(modes, **kwargs))
    return buffer.getvalue()


def _parse(modes: Sequence[ModeSpec], **kwargs: Any) -> Dict[str, Any]:
    return parse_gdtf(gdtf_archive(modes, **kwargs))


def _mode(result: Dict[str, Any], name: str = None) -> Dict[str, Any]:
    modes = result["modes"]
    if name is None:
        assert len(modes) == 1, f"expected one mode, got {[m['name'] for m in modes]}"
        return modes[0]
    matching = [m for m in modes if m["name"] == name]
    assert len(matching) == 1, f"mode {name!r} not in {[m['name'] for m in modes]}"
    return matching[0]


def _slots(mode: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    """channel_number -> channel row. Two rows on one slot is itself a failure."""
    rows: Dict[int, Dict[str, Any]] = {}
    for channel in mode["channels"]:
        number = channel["channel_number"]
        assert number not in rows, (
            f"channels {rows[number]['name']!r} and {channel['name']!r} both claim "
            f"DMX slot {number}"
        )
        rows[number] = channel
    return rows


def _types(rows: Dict[int, Dict[str, Any]]) -> Dict[int, str]:
    return {number: rows[number]["channel_type"] for number in sorted(rows)}


def _ranges(channel: Dict[str, Any]) -> List[Dict[str, Any]]:
    ranges = channel.get("value_ranges") or []
    for entry in ranges:
        assert set(entry) >= {"name", "min_value", "max_value"}, (
            f"value_ranges entry {entry!r} is not a FixtureChannelCreate value range; "
            "the schema is {name, min_value, max_value}"
        )
    return sorted(ranges, key=lambda entry: entry["min_value"])


# The trap this whole file exists for: a 16-bit channel in the middle of a mode.
# Numbering DMXChannel elements sequentially yields 1..6 here, putting Zoom on
# slot 5 and Focus on slot 6 - two slots early, and pointing at Tilt's bytes.
MID_MODE_16_BIT = [
    {"offset": "1", "attribute": "Dimmer"},
    {"offset": "2", "attribute": "ColorAdd_R"},
    {"offset": "3,4", "attribute": "Pan"},
    {"offset": "5,6", "attribute": "Tilt"},
    {"offset": "7", "attribute": "Zoom"},
    {"offset": "8", "attribute": "Focus"},
]

EIGHT_BIT_ONLY = [
    {"offset": "1", "attribute": "Dimmer"},
    {"offset": "2", "attribute": "ColorAdd_R"},
    {"offset": "3", "attribute": "ColorAdd_G"},
    {"offset": "4", "attribute": "ColorAdd_B"},
    {"offset": "5", "attribute": "Shutter"},
]


def test_a_16_bit_channel_mid_mode_does_not_shift_the_channels_after_it():
    result = _parse([("Extended", MID_MODE_16_BIT)])
    mode = _mode(result)
    rows = _slots(mode)

    assert _types(rows) == {
        1: ChannelType.DIMMER.value,
        2: ChannelType.RED.value,
        3: ChannelType.PAN.value,
        4: ChannelType.PAN_FINE.value,
        5: ChannelType.TILT.value,
        6: ChannelType.TILT_FINE.value,
        7: ChannelType.ZOOM.value,
        8: ChannelType.FOCUS.value,
    }, "channel numbers must come from Offset, not from a running counter"

    assert mode["channel_count"] == 8


def test_the_coarse_row_is_not_the_one_marked_fine():
    rows = _slots(_mode(_parse([("Extended", MID_MODE_16_BIT)])))

    for number in (1, 2, 3, 5, 7, 8):
        assert rows[number]["is_fine"] is False, (
            f"slot {number} is a coarse channel and must not be marked fine"
        )
        assert rows[number].get("coarse_channel") is None, (
            f"slot {number} is a coarse channel and must not point at one"
        )

    for fine, coarse in ((4, 3), (6, 5)):
        assert rows[fine]["is_fine"] is True, (
            f"slot {fine} is the fine byte of slot {coarse}"
        )
        assert rows[fine]["coarse_channel"] == coarse, (
            f"slot {fine} must point at coarse channel {coarse}, "
            f"got {rows[fine].get('coarse_channel')!r}"
        )


def test_an_8_bit_only_mode_is_numbered_1_to_n_with_no_gaps():
    result = _parse([("Basic", EIGHT_BIT_ONLY)])
    mode = _mode(result)
    rows = _slots(mode)

    assert sorted(rows) == [1, 2, 3, 4, 5]
    assert mode["channel_count"] == 5
    assert len(mode["channels"]) == 5

    for number, channel in rows.items():
        assert channel["is_fine"] is False, f"slot {number} has no fine byte to be"
        assert channel.get("coarse_channel") is None


def test_a_namespaced_description_parses_instead_of_falling_through_to_a_placeholder():
    result = _parse([("Extended", MID_MODE_16_BIT)], namespaced=True)

    assert result["manufacturer"] == "Phase2 Lighting"
    assert result["model"] == "Phase2 Spot 700"

    mode = _mode(result, "Extended")
    assert mode["channel_count"] == 8, (
        "a namespaced document is a real GDTF Share file, not a 1-channel placeholder"
    )
    assert _types(_slots(mode)) == _types(
        _slots(_mode(_parse([("Extended", MID_MODE_16_BIT)])))
    ), "namespacing a document must not change what it declares"


def test_cmy_channels_map_to_cyan_magenta_yellow_and_set_has_cmy():
    result = _parse([("CMY", [
        {"offset": "1", "attribute": "Dimmer"},
        {"offset": "2", "attribute": "ColorSub_C"},
        {"offset": "3", "attribute": "ColorSub_M"},
        {"offset": "4", "attribute": "ColorSub_Y"},
        {"offset": "5", "attribute": "ColorAdd_W"},
    ])])

    rows = _slots(_mode(result))

    assert _types(rows) == {
        1: ChannelType.DIMMER.value,
        2: ChannelType.CYAN.value,
        3: ChannelType.MAGENTA.value,
        4: ChannelType.YELLOW.value,
        5: ChannelType.WHITE.value,
    }
    assert result["has_cmy"] is True
    assert result["has_rgb"] is False


def test_an_additive_fixture_does_not_claim_cmy():
    result = _parse([("Basic", EIGHT_BIT_ONLY)])

    assert result["has_rgb"] is True
    assert result.get("has_cmy") is not True


def test_channel_set_slots_land_in_value_ranges():
    result = _parse([("Gobo", [
        {"offset": "1", "attribute": "Dimmer"},
        {"offset": "2", "attribute": "Gobo1", "sets": [
            ("Open", 0),
            ("Gobo 1", 10),
            ("Gobo 2", 20),
            ("Gobo 3", 30),
        ]},
    ])])

    rows = _slots(_mode(result))
    ranges = _ranges(rows[2])

    assert [entry["name"] for entry in ranges] == ["Open", "Gobo 1", "Gobo 2", "Gobo 3"]

    # A ChannelSet runs until the next one starts; the last runs to the end of its
    # ChannelFunction, which is the whole 8-bit range here. Ending each slot at its
    # own start instead would leave DMX 15 nameless on a wheel that has a gobo there.
    assert [(e["min_value"], e["max_value"]) for e in ranges] == [
        (0, 9), (10, 19), (20, 29), (30, 255),
    ]

    for earlier, later in zip(ranges, ranges[1:]):
        assert earlier["max_value"] < later["min_value"], (
            f"{earlier['name']!r} and {later['name']!r} overlap, so no DMX value "
            "names exactly one slot"
        )

    holding = [e for e in ranges if e["min_value"] <= 15 <= e["max_value"]]
    assert [e["name"] for e in holding] == ["Gobo 1"]

    assert not rows[1].get("value_ranges"), (
        "a channel with no ChannelSet has no named slots to expose"
    )


def test_a_virtual_channel_occupies_no_dmx_slot():
    result = _parse([("Virtual", [
        {"offset": "1", "attribute": "Dimmer"},
        {"offset": "", "attribute": "NoFunction"},
        {"offset": "2", "attribute": "ColorAdd_R"},
        {"attribute": "Macro"},
        {"offset": "3", "attribute": "ColorAdd_G"},
    ])])

    mode = _mode(result)
    rows = _slots(mode)

    assert sorted(rows) == [1, 2, 3], (
        "a channel with no Offset takes no DMX slot and must not be numbered"
    )
    assert _types(rows) == {
        1: ChannelType.DIMMER.value,
        2: ChannelType.RED.value,
        3: ChannelType.GREEN.value,
    }
    assert mode["channel_count"] == 3


def test_mode_channel_count_is_the_highest_slot_used_not_the_row_count():
    result = _parse([("Sparse", [
        {"offset": "1", "attribute": "Dimmer"},
        {"offset": "2,3", "attribute": "Pan"},
        {"offset": "12", "attribute": "Macro"},
    ])])

    mode = _mode(result)

    assert sorted(_slots(mode)) == [1, 2, 3, 12]
    assert mode["channel_count"] == 12, (
        "the mode spans 12 DMX slots; patching it as 4 would overlap the next fixture"
    )


def test_a_3_slot_channel_does_not_shift_the_channel_after_it():
    result = _parse([("Ultra", [
        {"offset": "1", "attribute": "Dimmer"},
        {"offset": "2,3", "attribute": "Pan"},
        {"offset": "4,5,6", "attribute": "Tilt"},
        {"offset": "7", "attribute": "Zoom"},
    ])])

    mode = _mode(result)
    rows = _slots(mode)

    assert rows[1]["channel_type"] == ChannelType.DIMMER.value
    assert rows[2]["channel_type"] == ChannelType.PAN.value
    assert rows[3]["channel_type"] == ChannelType.PAN_FINE.value
    assert rows[4]["channel_type"] == ChannelType.TILT.value
    assert rows[4]["is_fine"] is False
    assert rows[7]["channel_type"] == ChannelType.ZOOM.value

    # A 24-bit channel may contribute its ultra byte or drop it, but never a slot
    # outside the three it declares, and never one belonging to another attribute.
    assert set(rows) <= {1, 2, 3, 4, 5, 6, 7}
    for slot in (5, 6):
        if slot in rows:
            assert rows[slot]["channel_type"] == ChannelType.TILT_FINE.value
            assert rows[slot]["is_fine"] is True
            assert rows[slot]["coarse_channel"] == 4

    assert mode["channel_count"] == 7


def test_a_fine_byte_with_no_dedicated_type_keeps_its_coarse_channels_type():
    rows = _slots(_mode(_parse([("Wide", [
        {"offset": "1,2", "attribute": "Dimmer"},
        {"offset": "3,4", "attribute": "Zoom"},
        {"offset": "5", "attribute": "Shutter"},
    ])])))

    assert _types(rows) == {
        1: ChannelType.DIMMER.value,
        2: ChannelType.DIMMER.value,
        3: ChannelType.ZOOM.value,
        4: ChannelType.ZOOM.value,
        5: ChannelType.SHUTTER.value,
    }, "ChannelType has no DIMMER_FINE or ZOOM_FINE, so the fine byte keeps its type"

    for fine, coarse in ((2, 1), (4, 3)):
        assert rows[fine]["is_fine"] is True
        assert rows[fine]["coarse_channel"] == coarse
    for coarse in (1, 3, 5):
        assert rows[coarse]["is_fine"] is False


def test_fine_bytes_grouped_at_the_end_of_a_mode_keep_their_declared_slots():
    mode = _mode(_parse([("Split", [
        {"offset": "1,5", "attribute": "Pan", "physical": (-270.0, 270.0)},
        {"offset": "2,6", "attribute": "Tilt", "physical": (-135.0, 135.0)},
        {"offset": "3", "attribute": "Dimmer"},
        {"offset": "4", "attribute": "Shutter"},
    ])]))
    rows = _slots(mode)

    assert _types(rows) == {
        1: ChannelType.PAN.value,
        2: ChannelType.TILT.value,
        3: ChannelType.DIMMER.value,
        4: ChannelType.SHUTTER.value,
        5: ChannelType.PAN_FINE.value,
        6: ChannelType.TILT_FINE.value,
    }, "a mode may put its fine bytes anywhere; only Offset says where"

    assert rows[5]["coarse_channel"] == 1
    assert rows[6]["coarse_channel"] == 2
    assert mode["channel_count"] == 6


def test_each_mode_is_numbered_independently():
    result = _parse([("Basic", EIGHT_BIT_ONLY), ("Extended", MID_MODE_16_BIT)])

    basic = _mode(result, "Basic")
    extended = _mode(result, "Extended")

    assert basic["channel_count"] == 5
    assert extended["channel_count"] == 8
    assert sorted(_slots(basic)) == [1, 2, 3, 4, 5]
    assert sorted(_slots(extended)) == [1, 2, 3, 4, 5, 6, 7, 8]


def test_pan_and_tilt_travel_come_from_the_declared_physical_range():
    result = _parse([("Travel", [
        {"offset": "1", "attribute": "Dimmer"},
        {"offset": "2,3", "attribute": "Pan", "physical": (-315.0, 315.0)},
        {"offset": "4,5", "attribute": "Tilt", "physical": (-140.0, 140.0)},
    ])])

    assert result["pan_range"] == pytest.approx(630.0)
    assert result["tilt_range"] == pytest.approx(280.0)


def test_basic_metadata_survives_the_parse():
    result = _parse([("Basic", EIGHT_BIT_ONLY)])

    assert result["manufacturer"] == "Phase2 Lighting"
    assert result["model"] == "Phase2 Spot 700"
    assert result["gdtf_id"] == "1F2E3D4C-5B6A-4789-8A9B-0C1D2E3F4A5B"
    assert result["source"] == "gdtf"
    assert result["weight"] == pytest.approx(21.5)
    assert result["power"] == pytest.approx(480.0)


def test_description_is_found_among_the_archives_other_entries():
    archive = gdtf_archive(
        [("Basic", EIGHT_BIT_ONLY)],
        extra_files=[
            ("wheels/gobo1.png", b"\x89PNG\r\n\x1a\n"),
            ("models/gltf/base.glb", b"glTF"),
        ],
    )

    assert _mode(parse_gdtf(archive))["channel_count"] == 5


def test_a_payload_that_is_not_a_zip_is_rejected():
    with pytest.raises(ValueError):
        parse_gdtf(b"<GDTF>this is loose xml, not an archive</GDTF>")


def test_an_archive_without_a_description_is_rejected():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("wheels/gobo1.png", b"\x89PNG\r\n\x1a\n")

    with pytest.raises(ValueError):
        parse_gdtf(buffer.getvalue())
