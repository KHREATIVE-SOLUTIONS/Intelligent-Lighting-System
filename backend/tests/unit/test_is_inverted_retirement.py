"""Retire is_inverted by mapping it onto tilt_invert (Q20)."""

from app.schemas.rig import RigFixtureCreate, RigFixtureUpdate, apply_is_inverted_alias


def _create(**kwargs) -> RigFixtureCreate:
    return RigFixtureCreate(fixture_id=1, dmx_address=1, **kwargs)


def test_create_maps_is_inverted_onto_tilt_invert_when_tilt_is_omitted():
    created = _create(is_inverted=True)
    assert created.tilt_invert is True
    assert created.is_inverted is True
    assert created.pan_invert is False
    assert created.pan_tilt_swap is False


def test_create_does_not_override_an_explicit_tilt_invert():
    created = _create(is_inverted=True, tilt_invert=False)
    assert created.tilt_invert is False
    assert created.is_inverted is True


def test_create_leaves_clear_fixtures_alone():
    created = _create()
    assert created.is_inverted is False
    assert created.tilt_invert is False


def test_update_maps_is_inverted_onto_tilt_invert_when_tilt_is_omitted():
    update = RigFixtureUpdate(is_inverted=True)
    assert update.tilt_invert is True
    assert update.is_inverted is True
    dumped = update.model_dump(exclude_unset=True)
    assert dumped["tilt_invert"] is True
    assert dumped["is_inverted"] is True
    assert "pan_invert" not in dumped
    assert "pan_tilt_swap" not in dumped


def test_update_does_not_override_an_explicit_tilt_invert():
    update = RigFixtureUpdate(is_inverted=True, tilt_invert=False)
    assert update.tilt_invert is False
    assert update.model_dump(exclude_unset=True)["tilt_invert"] is False


def test_update_without_is_inverted_does_not_touch_tilt():
    update = RigFixtureUpdate(name="Left")
    dumped = update.model_dump(exclude_unset=True)
    assert dumped == {"name": "Left"}


def test_apply_is_inverted_alias_on_a_batch_dict():
    item = {"id": 1, "is_inverted": True}
    apply_is_inverted_alias(item)
    assert item["tilt_invert"] is True
    assert item["is_inverted"] is True


def test_apply_is_inverted_alias_does_not_override_tilt():
    item = {"id": 1, "is_inverted": True, "tilt_invert": False}
    apply_is_inverted_alias(item)
    assert item["tilt_invert"] is False
