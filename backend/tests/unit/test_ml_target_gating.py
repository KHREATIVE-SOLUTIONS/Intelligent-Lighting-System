from app.services.effects.effects_engine import EffectsEngine, _TargetGateState


def test_target_gate_requires_consecutive_frames_and_hold_and_hysteresis():
    engine = EffectsEngine()
    gate = _TargetGateState(current="verse", current_confidence=0.6)

    # First strong candidate frame: start streak, but don't accept yet.
    engine.time = 0.0
    assert not engine._gate_target_switch(
        gate,
        candidate="chorus",
        confidence=0.8,
        confidence_on=0.7,
        confidence_off=0.5,
        consecutive_frames=2,
        min_hold_ms=300,
        min_confidence_delta=0.1,
    )

    # Second consecutive frame: accepted.
    engine.time = 0.016
    assert engine._gate_target_switch(
        gate,
        candidate="chorus",
        confidence=0.82,
        confidence_on=0.7,
        confidence_off=0.5,
        consecutive_frames=2,
        min_hold_ms=300,
        min_confidence_delta=0.1,
    )
    assert gate.current == "chorus"

    # During hold window, a stronger alternative is still rejected.
    engine.time = 0.15
    assert not engine._gate_target_switch(
        gate,
        candidate="drop",
        confidence=0.95,
        confidence_on=0.7,
        confidence_off=0.5,
        consecutive_frames=1,
        min_hold_ms=300,
        min_confidence_delta=0.05,
    )

    # After hold window, candidate below hysteresis margin is rejected.
    gate.current_confidence = 0.85
    engine.time = 0.40
    assert not engine._gate_target_switch(
        gate,
        candidate="drop",
        confidence=0.88,
        confidence_on=0.7,
        confidence_off=0.5,
        consecutive_frames=1,
        min_hold_ms=300,
        min_confidence_delta=0.05,
    )

    # Clear hysteresis margin -> accepted.
    engine.time = 0.45
    assert engine._gate_target_switch(
        gate,
        candidate="drop",
        confidence=0.93,
        confidence_on=0.7,
        confidence_off=0.5,
        consecutive_frames=1,
        min_hold_ms=300,
        min_confidence_delta=0.05,
    )
    assert gate.current == "drop"
