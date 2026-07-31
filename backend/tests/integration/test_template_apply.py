"""
Applying a Venue Template
=========================

The gallery is only worth seeding if the rig it produces is one the engine can
drive and the owner can talk about: a fixture patched onto a mode nothing can
raise is dark forever, and a rig with no zones still cannot say which light is
on the singer.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.services.rig.fixture_choice import mode_makes_light
from app.models.fixture import (
    ChannelType,
    Fixture as FixtureProfile,
    FixtureChannel,
    FixtureMode,
    FixtureType,
)
from app.models.rig import RigFixture
from app.models.template import RigTemplate


async def _effect_profile_with_a_dark_first_mode(db_session):
    """The shape the bundled ADJ Hyper Gem has: a macro+speed mode listed first,
    a drivable RGB mode second."""
    profile = FixtureProfile(
        manufacturer="Test",
        model="Dark First Effect",
        fixture_type=FixtureType.EFFECT,
        source_id="test-template-effect",
    )
    db_session.add(profile)
    await db_session.flush()

    dark = FixtureMode(fixture_id=profile.id, name="2-Channel", channel_count=2)
    db_session.add(dark)
    await db_session.flush()
    for number, channel_type in enumerate((ChannelType.MACRO, ChannelType.SPEED), start=1):
        db_session.add(FixtureChannel(
            mode_id=dark.id, channel_number=number,
            channel_type=channel_type, name=channel_type.value,
        ))

    usable = FixtureMode(fixture_id=profile.id, name="5-Channel", channel_count=5)
    db_session.add(usable)
    await db_session.flush()
    for number, channel_type in enumerate(
        (ChannelType.RED, ChannelType.GREEN, ChannelType.BLUE,
         ChannelType.STROBE, ChannelType.SPEED), start=1,
    ):
        db_session.add(FixtureChannel(
            mode_id=usable.id, channel_number=number,
            channel_type=channel_type, name=channel_type.value,
        ))

    await db_session.flush()
    return profile, dark, usable


async def _template(db_session, slots, name="Test Venue"):
    template = RigTemplate(
        name=name,
        description="A template for testing",
        venue_type="test_venue",
        stage_width=8.0,
        stage_depth=6.0,
        stage_height=4.0,
        fixture_slots=slots,
        is_system=True,
        is_public=True,
        usage_count=0,
    )
    db_session.add(template)
    await db_session.flush()
    return template


async def test_applying_a_template_carries_its_zones_onto_the_rig(
    client: AsyncClient, db_session, sample_fixture_data
):
    """The seeded groups are called "Key Light", "Drum Fill", "Booth Bars" - the
    zone vocabulary in English. Dropping the zone on the way in is the one place
    a non-expert could have had zones for free."""
    created = await client.post("/api/fixtures/", json=sample_fixture_data)
    assert created.status_code in (200, 201), created.text

    template = await _template(db_session, [
        {
            "fixture_type": "moving_head", "count": 2, "group_name": "Key Light",
            "mounting": "front_truss", "zone": "stage_center",
            "mode_channel_count": 16,
            "positions": [
                {"x": -1.0, "y": 3.5, "z": 2.1, "rotation_y": 180.0},
                {"x": 1.0, "y": 3.5, "z": 2.1, "rotation_y": 180.0},
            ],
        },
        {
            "fixture_type": "moving_head", "count": 1, "group_name": "Back Wash",
            "mounting": "back_truss", "zone": None,
            "mode_channel_count": 16,
            "positions": [{"x": 0.0, "y": 3.0, "z": -2.1, "rotation_y": 0.0}],
        },
    ])

    applied = await client.post(
        f"/api/templates/{template.id}/apply", params={"rig_name": "Zoned From Template"}
    )
    assert applied.status_code in (200, 201), applied.text
    rig_id = applied.json()["id"]

    listed = await client.get(f"/api/rigs/{rig_id}/fixtures")
    rows = {row["name"]: row for row in listed.json()}

    assert rows["Key Light 1"].get("zone") == "stage_center", (
        "apply_template never reads the slot's zone, so every template-created "
        "rig has no zones and the key-lighting work is inert for exactly the "
        "users templates exist for"
    )
    assert rows["Key Light 2"].get("zone") == "stage_center"
    assert rows["Back Wash 1"].get("zone") is None
    assert rows["Key Light 1"]["rotation_y"] == pytest.approx(180.0)
    assert rows["Key Light 1"]["position_z"] == pytest.approx(2.1)


async def test_applying_a_template_patches_a_mode_that_can_make_light(
    client: AsyncClient, db_session
):
    """"First fixture of the type, first mode" patches an effect slot onto
    macro+speed: it holds a DMX address, shows on the plan, and is dark forever.
    That is the symptom the identify walkthrough exists to diagnose, shipped
    deliberately."""
    profile, dark_mode, usable_mode = await _effect_profile_with_a_dark_first_mode(db_session)

    template = await _template(db_session, [{
        "fixture_type": "effect", "count": 2, "group_name": "Effects",
        "mounting": "back_truss", "zone": None, "mode_channel_count": 5,
        "positions": [
            {"x": -1.0, "y": 3.0, "z": -2.1, "rotation_y": 0.0},
            {"x": 1.0, "y": 3.0, "z": -2.1, "rotation_y": 0.0},
        ],
    }], name="Effects Venue")

    applied = await client.post(
        f"/api/templates/{template.id}/apply", params={"rig_name": "Effect Rig"}
    )
    assert applied.status_code in (200, 201), applied.text
    rig_id = applied.json()["id"]

    result = await db_session.execute(
        select(RigFixture)
        .where(RigFixture.rig_id == rig_id)
        .options(selectinload(RigFixture.mode).selectinload(FixtureMode.channels))
    )
    fixtures = result.scalars().all()
    assert fixtures, "the effect group was dropped entirely"

    for rf in fixtures:
        assert rf.mode_id != dark_mode.id, (
            f"'{rf.name}' was patched onto the macro+speed mode; no renderer "
            f"writes a macro channel, so it can never be turned on"
        )
        assert rf.mode is not None and mode_makes_light(rf.mode.channels), (
            f"'{rf.name}' is patched onto mode '{rf.mode.name if rf.mode else None}' "
            f"with channels "
            f"{[c.channel_type.value for c in (rf.mode.channels if rf.mode else [])]} "
            f"- it holds a DMX address, appears on the plan, and is dark forever"
        )
    assert usable_mode.id  # the drivable mode exists; which profile wins is the library's call
