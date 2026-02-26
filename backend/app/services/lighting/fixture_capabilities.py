"""
Fixture Capability Profiles
===========================

Capability descriptors used by look/cue engines and visualizers.
"""

from app.schemas.lighting_look import FixtureCapabilityProfile


DEFAULT_CAPABILITY_PROFILES: dict[str, FixtureCapabilityProfile] = {
    "beam": FixtureCapabilityProfile(
        role="beam",
        supports_gobo=True,
        supports_prism=True,
        supports_frost=True,
        supports_zoom=False,
        supports_focus=True,
        supports_iris=False,
        movement_speed_class="fast",
    ),
    "spot": FixtureCapabilityProfile(
        role="spot",
        supports_gobo=True,
        supports_prism=False,
        supports_frost=True,
        supports_zoom=True,
        supports_focus=True,
        supports_iris=True,
        movement_speed_class="slow",
    ),
    "effect": FixtureCapabilityProfile(
        role="effect",
        supports_gobo=False,
        supports_prism=False,
        supports_frost=False,
        supports_zoom=False,
        supports_focus=False,
        supports_iris=False,
        movement_speed_class="static",
    ),
    "wash": FixtureCapabilityProfile(
        role="wash",
        supports_gobo=False,
        supports_prism=False,
        supports_frost=True,
        supports_zoom=True,
        supports_focus=False,
        supports_iris=False,
        movement_speed_class="slow",
    ),
}


FIXTURE_TYPE_TO_ROLE: dict[str, str] = {
    "beam": "beam",
    "moving_head": "beam",
    "mover": "beam",
    "spot": "spot",
    "profile": "spot",
    "wash": "wash",
    "led_par": "wash",
    "par": "wash",
    "led_bar": "wash",
    "bar": "wash",
    "strobe": "effect",
    "laser": "effect",
    "effect": "effect",
}


def get_capability_profile_for_fixture(
    fixture_type: str | None,
    role_hint: str | None = None,
) -> FixtureCapabilityProfile:
    """
    Resolve a fixture capability profile from fixture metadata.

    Priority:
    1) Explicit role hint
    2) Fixture type mapping
    3) Beam default profile
    """
    role_key = (role_hint or "").strip().lower()
    if role_key in DEFAULT_CAPABILITY_PROFILES:
        return FixtureCapabilityProfile.model_validate(
            DEFAULT_CAPABILITY_PROFILES[role_key].model_dump()
        )

    fixture_key = (fixture_type or "").strip().lower()
    mapped_role = FIXTURE_TYPE_TO_ROLE.get(fixture_key, "beam")

    return FixtureCapabilityProfile.model_validate(
        DEFAULT_CAPABILITY_PROFILES[mapped_role].model_dump()
    )
