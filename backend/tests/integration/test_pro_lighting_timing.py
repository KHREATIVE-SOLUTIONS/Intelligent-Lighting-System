"""Integration coverage for pro-lighting boundary commit timing."""

from app.services.effects.decision_engine import AudioState, DecisionEngine
from app.services.effects.effects_engine import EffectsEngine


def _beat(engine: DecisionEngine, beat_number: int):
    audio = AudioState(is_beat=True, beat_number=beat_number, bpm=128.0)
    engine.update(audio, delta_time=1 / 60)


def test_change_requested_mid_bar_commits_at_boundary_downbeat():
    """Section changes requested mid-bar should commit on next phrase downbeat."""
    decision = DecisionEngine()

    # Mid-bar request (beat 2): should stage, not commit.
    decision.set_section("chorus")
    mid_bar_audio = AudioState(is_beat=True, beat_number=2, bpm=128.0)
    decision.update(mid_bar_audio, delta_time=1 / 60)

    debug = decision.get_transition_debug()
    assert debug["pending_effect"] is not None
    assert debug["commit_in_bars"] == 4
    assert decision.state.value == "intro"

    # Walk to bar 4 downbeat (beat 13): commit should happen exactly there.
    for beat in range(3, 13):
        _beat(decision, beat)
        assert decision.state.value == "intro"

    _beat(decision, 13)
    assert decision.state.value == "peak"
    debug = decision.get_transition_debug()
    assert debug["pending_effect"] is None
    assert debug["last_commit_bar"] == 4


def test_pro_lighting_payload_exposes_transition_debug_fields():
    """Pro-lighting API payload includes pending/commit debug fields."""
    engine = EffectsEngine()
    engine.enable_pro_lighting(True)

    engine.decision.set_section("chorus")
    engine.decision.update(AudioState(is_beat=True, beat_number=2), delta_time=1 / 60)

    state = engine.get_pro_lighting_state()
    assert "pending_effect" in state
    assert "commit_in_bars" in state
    assert "last_commit_bar" in state
    assert "pre_cue_active" in state
    assert state["pending_effect"] is not None
