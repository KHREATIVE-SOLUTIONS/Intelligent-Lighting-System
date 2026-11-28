"""
grandMA2 starter presets in the handoff pack
============================================

GET /api/rigs/{id}/handoff-pack carries <rig>_ma2_starter_presets.txt by
default and leaves it out with ?starter_presets=false. In the LIV subset
import 34 fixtures sit on the demo GDTF modes and two have no mode (channels
unknown: a dimmer is assumed, colour and beam are left out and say why). The
palette maths is in tests/unit/test_console_export_starter_presets.py.
"""

import io
import zipfile

import pytest
from httpx import AsyncClient

from tests.integration.test_api_handoff_pack import PACK, pack
from tests.integration.test_api_readiness import imported_liv

NAME = "Readiness_LIV_ma2_starter_presets.txt"


@pytest.mark.asyncio
async def test_the_pack_holds_the_starter_presets_for_the_liv_rig(client: AsyncClient, db_session):
    rig_id = await imported_liv(client)

    zf = await pack(client, rig_id)

    assert NAME in zf.namelist()
    text = zf.read(NAME).decode("utf-8")
    assert text.startswith("# Readiness LIV: grandMA2 starter presets")
    assert 'Store Preset 1.1\nLabel Preset 1.1 "Full"' in text
    assert 'Store Preset 1.5\nLabel Preset 1.5 "Out"' in text
    # 34 fixtures are on the demo GDTF modes; the two booth washes (130, 131) have no mode.
    assert "Fixture 1 Thru 34 + 130 + 131\nAttribute \"Dim\" At 100" in text
    assert "#   fixture 130 + 131: no DMX mode is set, so its channels are not known; a dimmer is assumed" in text
    assert "# Fixture 130 is in no colour preset: no DMX mode is set" in text
    assert ('Fixture 1 Thru 34\nAttribute "ColorRGB1" At 100\nAttribute "ColorRGB2" At 0\n'
            'Attribute "ColorRGB3" At 0\nAttribute "ColorRGB5" At 0') in text
    assert 'Store Preset 4.3\nLabel Preset 4.3 "Red"' in text
    # The demo profiles name no strobe range: no strobe preset is made up.
    assert "# Preset 5.2 Strobe Slow: not stored. No fixture can take it." in text
    assert "#   fixture 1 Thru 34 left out: its profile names no strobe range" in text
    assert "Store Preset 5.2" not in text and "Store Preset 5.3" not in text
    assert 'Store Preset 5.4\nLabel Preset 5.4 "Zoom Narrow"' in text
    assert NAME in zf.read("README.txt").decode("utf-8")


@pytest.mark.asyncio
async def test_turning_the_option_off_leaves_the_file_out(client: AsyncClient, db_session):
    rig_id = await imported_liv(client)

    response = await client.get(PACK.format(rig_id), params={"starter_presets": "false"})

    assert response.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(response.content))
    assert NAME not in zf.namelist()
    assert "Readiness_LIV_ma2_script.txt" in zf.namelist()
    assert "starter_presets" not in zf.read("README.txt").decode("utf-8")
