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
        movement_speed_class="medium",
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
}

