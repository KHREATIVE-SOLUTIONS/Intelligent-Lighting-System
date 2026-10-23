"""
Console Patch Import: grandMA XML
=================================

A real grandMA2 export puts every element in the MA namespace, names the
fixture type in a child element and stores the patch as an absolute address.
The old parser matched none of that, and an attribute-only <Patch/> element is
falsy in ElementTree, so every fixture landed at universe 0, address 1.
"""

from app.services.fixture_library.console_parsers import (
    detect_and_parse,
    parse_grandma_xml,
)

MA2_EXPORT = """<?xml version="1.0" encoding="utf-8"?>
<MA xmlns="http://schemas.malighting.de/grandma2/xml/MA" major_vers="3" minor_vers="9">
  <Layer index="1" name="Movers">
    <Fixture index="0" name="Spot 1" fixture_id="101">
      <FixtureType name="Martin MAC Aura XB"><No>12</No></FixtureType>
      <SubFixture index="0" react_to_grandmaster="true">
        <Patch><Address>1125</Address></Patch>
      </SubFixture>
    </Fixture>
    <Fixture index="1" name="Spot 2" fixture_id="102">
      <FixtureType name="Martin MAC Aura XB"><No>12</No></FixtureType>
      <SubFixture index="0"><Patch><Address>1</Address></Patch></SubFixture>
    </Fixture>
  </Layer>
</MA>
"""


def test_a_namespaced_grandma2_export_is_read():
    fixtures = parse_grandma_xml(MA2_EXPORT)
    assert [f["name"] for f in fixtures] == ["Spot 1", "Spot 2"]
    first, second = fixtures
    # 1125 = (3 - 1) * 512 + 101: MA universe 3, address 101 -> internal universe 2
    assert (first["universe"], first["dmx_address"]) == (2, 101)
    assert (second["universe"], second["dmx_address"]) == (0, 1)
    assert first["manufacturer"] == "Martin"
    assert first["model"] == "MAC Aura XB"


def test_an_attribute_only_patch_element_is_not_ignored():
    xml = ('<Patch><Fixture Name="Wash" FixtureType="Chauvet Rogue R2 Wash">'
           '<Patch Universe="3" Address="101"/></Fixture></Patch>')
    (fixture,) = parse_grandma_xml(xml)
    assert (fixture["universe"], fixture["dmx_address"]) == (2, 101)


def test_universe_dot_address_text_is_read():
    xml = '<Show><Fixture Name="Bar"><DMX><Address>4.17</Address></DMX></Fixture></Show>'
    (fixture,) = parse_grandma_xml(xml)
    assert (fixture["universe"], fixture["dmx_address"]) == (3, 17)


def test_auto_detect_routes_xml_to_the_grandma_parser():
    assert len(detect_and_parse(MA2_EXPORT)) == 2


def test_broken_xml_returns_nothing_rather_than_raising():
    assert parse_grandma_xml("<MA><Fixture") == []
