from app.api.endpoints.websocket import (
    REACTIVE_PRESETS,
    _apply_deadband,
    _resolve_reactive_config,
    _section_gain,
)


def test_reactive_presets_include_requested_variants():
    assert {"subtle", "concert", "festival"}.issubset(REACTIVE_PRESETS.keys())


def test_deadband_suppresses_small_values_and_rescales():
    assert _apply_deadband(0.01, 0.02) == 0.0

    result = _apply_deadband(0.52, 0.02)
    assert 0.50 <= result <= 0.52


def test_config_resolution_applies_preset_and_overrides():
    cfg = _resolve_reactive_config({
        "preset": "festival",
        "params": {"pan_range": 1.9, "deadband_bass": 0.005},
    })

    assert cfg.pan_range == 1.9
    assert cfg.deadband_bass == 0.005
    assert cfg.section_gain_drop > 1.0


def test_section_gain_scales_verse_lower_than_chorus():
    cfg = REACTIVE_PRESETS["concert"]
    assert _section_gain(cfg, "verse") < _section_gain(cfg, "chorus")
    assert _section_gain(cfg, "drop") >= _section_gain(cfg, "chorus")
