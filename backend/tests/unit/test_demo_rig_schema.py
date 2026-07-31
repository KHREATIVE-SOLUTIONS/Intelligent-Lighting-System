"""
Demo Rig Payload
================

/api/demo/rig is the rig the visualizer loads when no database rig exists. Its
channel maps come straight from the venue presets, so a channel name the
ChannelType enum does not have makes the payload unvalidatable the moment it is
round-tripped through any Rig or Fixture schema.
"""

import pytest

from app.api.endpoints.demo import get_demo_rig
from app.models.fixture import ChannelType
from app.schemas.fixture import FixtureChannelBase
from app.schemas.rig import RigResponse
from app.services.demo.venue_presets import VENUE_PRESETS


@pytest.mark.asyncio
@pytest.mark.parametrize("preset", sorted(VENUE_PRESETS))
async def test_the_demo_rig_payload_validates_against_the_real_schemas(preset):
    rig = await get_demo_rig(preset)

    RigResponse.model_validate(rig)

    valid = {member.value for member in ChannelType}
    for patch in rig["fixtures"]:
        for mode in patch["fixture"]["modes"]:
            assert mode["channels"]
            for channel in mode["channels"]:
                assert channel["channel_type"] in valid, channel
                FixtureChannelBase(**{
                    key: value for key, value in channel.items()
                    if key in FixtureChannelBase.model_fields
                })


@pytest.mark.asyncio
async def test_static_demo_fixtures_declare_no_travel():
    rig = await get_demo_rig("large_concert")

    for patch in rig["fixtures"]:
        profile = patch["fixture"]
        channels = {
            channel["channel_type"]
            for mode in profile["modes"]
            for channel in mode["channels"]
        }
        if "pan" not in channels:
            assert profile["pan_range"] == 0
            assert profile["tilt_range"] == 0
