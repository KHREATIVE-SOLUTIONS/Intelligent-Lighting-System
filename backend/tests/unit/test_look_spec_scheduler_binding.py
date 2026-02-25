from types import SimpleNamespace

from app.services.lighting.look_spec import build_lighting_look_spec


class _PaletteValue:
    def __init__(self, value: str):
        self.value = value


def test_look_spec_uses_active_beam_look_zoom_and_speed_multiplier():
    engine = SimpleNamespace(
        _pro_lighting_enabled=False,
        decision=SimpleNamespace(state=SimpleNamespace(value="verse")),
        audio_state=SimpleNamespace(energy=0.4, beat_number=16),
        config=SimpleNamespace(bpm=120.0, palette=_PaletteValue("edm")),
        movement=SimpleNamespace(
            params=SimpleNamespace(
                pattern=SimpleNamespace(value="sweep"),
                pan_speed=0.6,
                tilt_speed=0.3,
            )
        ),
        strobe=SimpleNamespace(params=SimpleNamespace(mode=SimpleNamespace(value="off"))),
        _current_song_palette=_PaletteValue("edm"),
        _palette_version=1,
        _palette_locked=False,
        _active_beam_look=SimpleNamespace(zoom=0.77, speed_multiplier=1.2),
    )

    spec = build_lighting_look_spec(engine)

    assert spec.spot.zoom == 0.77
    assert spec.beam.movement_speed_hz == 0.72
