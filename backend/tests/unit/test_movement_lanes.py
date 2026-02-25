from app.services.lighting.fixture_capabilities import (
    DEFAULT_CAPABILITY_PROFILES,
    get_capability_profile_for_fixture,
)
from app.services.lighting.movement_patterns import ProMovementEngine, ProMovementPattern


def test_lane_envelopes_diverge_for_same_musical_input():
    engine = ProMovementEngine()
    engine.set_pattern(
        ProMovementPattern.FIGURE_8,
        bpm=128.0,
        beat_divisor=1.0,
        pan_amplitude=60.0,
        tilt_amplitude=35.0,
        smoothing=1.0,
    )

    samples = {
        "beam": [],
        "spot": [],
        "wash": [],
    }

    for _ in range(20):
        engine.update(0.05)
        samples["beam"].append(
            engine.get_position(
                "beam_fixture", 0, 6, -2.0, 0.0, 0.0, role="beam", movement_speed_class="fast"
            )
        )
        samples["spot"].append(
            engine.get_position(
                "spot_fixture", 0, 6, -2.0, 0.0, 0.0, role="spot", movement_speed_class="medium"
            )
        )
        samples["wash"].append(
            engine.get_position(
                "wash_fixture", 0, 6, -2.0, 0.0, 0.0, role="wash", movement_speed_class="slow"
            )
        )

    def mean_abs_axis(points, axis):
        return sum(abs(pair[axis]) for pair in points) / len(points)

    beam_pan_mean = mean_abs_axis(samples["beam"], 0)
    spot_pan_mean = mean_abs_axis(samples["spot"], 0)
    wash_pan_mean = mean_abs_axis(samples["wash"], 0)

    beam_tilt_mean = mean_abs_axis(samples["beam"], 1)
    wash_tilt_mean = mean_abs_axis(samples["wash"], 1)

    def mean_step(points, axis):
        steps = [abs(points[i][axis] - points[i - 1][axis]) for i in range(1, len(points))]
        return sum(steps) / len(steps)

    beam_pan_step = mean_step(samples["beam"], 0)
    wash_pan_step = mean_step(samples["wash"], 0)

    assert beam_pan_mean > spot_pan_mean > wash_pan_mean
    assert beam_pan_step > wash_pan_step
    assert beam_tilt_mean > wash_tilt_mean


def test_lane_rate_limit_clamps_jerky_pan_transitions():
    engine = ProMovementEngine()
    engine.set_pattern(
        ProMovementPattern.SNAP_HOLD,
        bpm=128.0,
        beat_divisor=1.0,
        pan_amplitude=80.0,
        tilt_amplitude=40.0,
        smoothing=1.0,
        snap_positions=[(0.0, -0.5), (-1.0, 0.0)],
    )

    engine.update(0.01)
    pan_a, _ = engine.get_position(
        "wash_fixture", 0, 4, 0.0, 0.0, 0.0, role="wash", movement_speed_class="slow"
    )

    engine.trigger_beat()
    engine.update(0.01)
    pan_b, _ = engine.get_position(
        "wash_fixture", 0, 4, 0.0, 0.0, 0.0, role="wash", movement_speed_class="slow"
    )

    max_step = 95.0 * 0.01
    assert abs(pan_b - pan_a) <= max_step + 1e-6


def test_capability_profile_resolution_maps_fixture_types_to_lanes():
    assert "wash" in DEFAULT_CAPABILITY_PROFILES

    beam_profile = get_capability_profile_for_fixture("moving_head")
    spot_profile = get_capability_profile_for_fixture("spot")
    wash_profile = get_capability_profile_for_fixture("led_bar")

    assert beam_profile.role == "beam"
    assert spot_profile.role == "spot"
    assert wash_profile.role == "wash"
    assert wash_profile.movement_speed_class == "slow"
