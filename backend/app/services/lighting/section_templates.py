"""
Section Cue Templates
=====================

Genre/section-driven templates for movement, dimmer, strobe, and dynamic scaling.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SectionCueTemplate:
    movement_preset: str
    dimmer_preset: str
    strobe_preset: str
    base_intensity_scale: float
    blackout_policy: str = "phrase_boundary"
    enable_mib: bool = True


SECTION_CUE_TEMPLATES: dict[str, dict[str, SectionCueTemplate]] = {
    "edm": {
        "intro": SectionCueTemplate("circle_slow", "breathing", "off", 0.45),
        "verse": SectionCueTemplate("slow_sweep", "half_time", "off", 0.62),
        "pre_chorus": SectionCueTemplate("center_out", "build_up", "off", 0.75),
        "buildup": SectionCueTemplate("center_out", "build_up", "off", 0.8),
        "chorus": SectionCueTemplate("circle_chase", "beat_kick", "beat_lock", 0.95),
        "drop": SectionCueTemplate("vortex", "beat_kick", "drop_burst", 1.0, blackout_policy="drop_button"),
        "peak": SectionCueTemplate("vortex", "beat_kick", "drop_burst", 1.0, blackout_policy="drop_button"),
        "breakdown": SectionCueTemplate("spiral_expand", "breathing", "off", 0.5),
        "bridge": SectionCueTemplate("mirror_sweep", "breathing", "off", 0.65),
        "outro": SectionCueTemplate("none", "fade_out", "off", 0.35, blackout_policy="button"),
    },
    "rock": {
        "intro": SectionCueTemplate("gentle_tilt", "breathing", "off", 0.5),
        "verse": SectionCueTemplate("slow_sweep", "half_time", "off", 0.68),
        "pre_chorus": SectionCueTemplate("mirror_sweep", "build_up", "off", 0.78),
        "buildup": SectionCueTemplate("mirror_sweep", "build_up", "off", 0.82),
        "chorus": SectionCueTemplate("alternating_sweep", "beat_kick", "beat_lock", 0.95),
        "drop": SectionCueTemplate("ballyhoo_classic", "beat_kick", "drop_burst", 1.0, blackout_policy="drop_button"),
        "peak": SectionCueTemplate("ballyhoo_classic", "beat_kick", "drop_burst", 1.0, blackout_policy="drop_button"),
        "breakdown": SectionCueTemplate("none", "breathing", "off", 0.48),
        "bridge": SectionCueTemplate("tilt_wave", "half_time", "off", 0.66),
        "outro": SectionCueTemplate("none", "fade_out", "off", 0.35, blackout_policy="button"),
    },
    "pop": {
        "intro": SectionCueTemplate("circle_slow", "breathing", "off", 0.5),
        "verse": SectionCueTemplate("mirror_sweep", "half_time", "off", 0.66),
        "pre_chorus": SectionCueTemplate("center_out", "build_up", "off", 0.78),
        "buildup": SectionCueTemplate("center_out", "build_up", "off", 0.82),
        "chorus": SectionCueTemplate("circle_chase", "beat_kick", "beat_lock", 0.95),
        "drop": SectionCueTemplate("alternating_sweep", "beat_kick", "drop_burst", 1.0, blackout_policy="drop_button"),
        "peak": SectionCueTemplate("alternating_sweep", "beat_kick", "drop_burst", 1.0, blackout_policy="drop_button"),
        "breakdown": SectionCueTemplate("spiral_expand", "breathing", "off", 0.52),
        "bridge": SectionCueTemplate("mirror_sweep", "half_time", "off", 0.68),
        "outro": SectionCueTemplate("none", "fade_out", "off", 0.35, blackout_policy="button"),
    },
    "hip_hop": {
        "intro": SectionCueTemplate("none", "breathing", "off", 0.48),
        "verse": SectionCueTemplate("slow_sweep", "half_time", "off", 0.7),
        "pre_chorus": SectionCueTemplate("mirror_sweep", "build_up", "off", 0.8),
        "buildup": SectionCueTemplate("mirror_sweep", "build_up", "off", 0.82),
        "chorus": SectionCueTemplate("mirror_sweep", "beat_kick", "beat_lock", 0.9),
        "drop": SectionCueTemplate("vortex", "beat_kick", "drop_burst", 0.96, blackout_policy="drop_button"),
        "peak": SectionCueTemplate("vortex", "beat_kick", "drop_burst", 0.96, blackout_policy="drop_button"),
        "breakdown": SectionCueTemplate("none", "breathing", "off", 0.5),
        "bridge": SectionCueTemplate("tilt_wave", "half_time", "off", 0.66),
        "outro": SectionCueTemplate("none", "fade_out", "off", 0.35, blackout_policy="button"),
    },
    "jazz": {
        "intro": SectionCueTemplate("none", "breathing", "off", 0.35),
        "verse": SectionCueTemplate("gentle_tilt", "breathing", "off", 0.45),
        "pre_chorus": SectionCueTemplate("gentle_tilt", "half_time", "off", 0.52),
        "buildup": SectionCueTemplate("gentle_tilt", "half_time", "off", 0.56),
        "chorus": SectionCueTemplate("circle_slow", "breathing", "off", 0.62),
        "drop": SectionCueTemplate("slow_sweep", "breathing", "off", 0.64),
        "peak": SectionCueTemplate("slow_sweep", "breathing", "off", 0.64),
        "breakdown": SectionCueTemplate("none", "breathing", "off", 0.4),
        "bridge": SectionCueTemplate("gentle_tilt", "breathing", "off", 0.5),
        "outro": SectionCueTemplate("none", "fade_out", "off", 0.3, blackout_policy="button"),
    },
}


def get_section_template(genre: str, section: str) -> SectionCueTemplate:
    genre_key = (genre or "edm").lower()
    section_key = (section or "verse").lower()
    genre_templates = SECTION_CUE_TEMPLATES.get(genre_key, SECTION_CUE_TEMPLATES["edm"])
    return genre_templates.get(section_key, genre_templates.get("verse", SECTION_CUE_TEMPLATES["edm"]["verse"]))
