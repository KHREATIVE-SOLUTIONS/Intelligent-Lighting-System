from types import SimpleNamespace

from app.services.lighting.beam_choreography import compute_beam_width_target
from app.services.lighting.look_spec import build_lighting_look_spec


def test_verse_windows_hit_wider_bars():
    # bar 1 in phrase
    bar1 = compute_beam_width_target("verse", beat_number=1)
    # bar 2 in phrase
    bar2 = compute_beam_width_target("verse", beat_number=5)
    # bar 4 in phrase
    bar4 = compute_beam_width_target("verse", beat_number=13)

    assert bar1.bar_in_phrase == 1
    assert bar2.bar_in_phrase == 2
    assert bar4.bar_in_phrase == 4
    assert bar2.normalized_width > bar1.normalized_width
    assert bar2.normalized_width > bar4.normalized_width


def test_pre_chorus_narrows_over_phrase():
    early = compute_beam_width_target("pre_chorus", beat_number=1)
    late = compute_beam_width_target("pre_chorus", beat_number=29)

    assert early.normalized_width > late.normalized_width
    assert early.beam_width_profile == "narrowing_ramp"


def test_drop_snap_then_open():
    snap = compute_beam_width_target("drop", beat_number=1)
    open_up = compute_beam_width_target("drop", beat_number=17)

    assert snap.normalized_width < 0.12
    assert open_up.normalized_width > snap.normalized_width
    assert open_up.beam_width_profile == "drop_snap_open"


def test_breakdown_stays_sparse_and_wide():
    b1 = compute_beam_width_target("breakdown", beat_number=1)
    b2 = compute_beam_width_target("breakdown", beat_number=5)

    assert b1.normalized_width >= 0.8
    assert b2.normalized_width >= 0.8
    assert b1.beam_width_profile == "sparse_wide_frost"


def test_look_spec_uses_phrase_driven_beam_values():
    engine = SimpleNamespace(
        _pro_lighting_enabled=True,
        section_manager=SimpleNamespace(
            current_section=SimpleNamespace(value="drop"),
            get_buildup_progress=lambda: 0.0,
        ),
        genre_manager=SimpleNamespace(current_genre=SimpleNamespace(value="edm")),
        audio_state=SimpleNamespace(energy=0.8, beat_number=1),
        config=SimpleNamespace(bpm=128.0, palette=SimpleNamespace(value="edm")),
        movement=SimpleNamespace(
            params=SimpleNamespace(
                pattern=SimpleNamespace(value="circle"),
                pan_speed=0.4,
                tilt_speed=0.2,
            )
        ),
        strobe=SimpleNamespace(params=SimpleNamespace(mode=SimpleNamespace(value="off"))),
        beat_count=1,
    )

    spec_hit = build_lighting_look_spec(engine)

    engine.audio_state.beat_number = 17
    engine.beat_count = 17
    spec_open = build_lighting_look_spec(engine)

    assert spec_hit.beam.beam_width_profile == "drop_snap_open"
    assert spec_hit.beam.beam_width_normalized < spec_open.beam.beam_width_normalized
    assert spec_hit.beam.beam_angle_deg < spec_open.beam.beam_angle_deg
