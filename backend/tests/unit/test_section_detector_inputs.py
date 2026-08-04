"""What the live section detector is entitled to assume about its inputs.

Two properties, both newly load-bearing now that this detector is what the
renderer switches on: it has to run on one timeline rather than two, and the
one decision of its that reaches the strobe has to need absolute loudness as
well as relative.

`tests/musical` measures the same detector through the real analyser and real
DMX; these are the fast unit-level guards for the arguments it is handed.
"""

import time

import pytest

from app.services.lighting.section_manager import (
    SectionManager,
    StreamingSectionDetector,
)

DT = 1.0 / 60.0


def drive(detector, seconds, *, energy, bass, now_from_caller=True,
          start=0.0, bpm=128.0, flux=0.05):
    """Feed `seconds` of steady programme with a beat every half second."""
    frames = int(round(seconds / DT))
    beat_every = max(1, int(round(0.5 / DT)))
    beat_number = 0
    for i in range(frames):
        t = start + i * DT
        is_beat = (i % beat_every) == 0
        if is_beat:
            beat_number += 1
        detector.update(
            DT,
            energy=energy,
            bass=bass if is_beat else bass * 0.4,
            spectral_flux=flux,
            is_beat=is_beat,
            beat_number=beat_number,
            bpm=bpm,
            now=(t if now_from_caller else None),
        )
    return start + frames * DT


def test_the_detector_runs_on_the_callers_clock_not_the_wall_clock():
    """Its filters advance on delta_time; its timers used to read time.time().

    Any caller stepping the engine at other than real speed — an offline
    render, a demo endpoint ticking a fixed 1/60 per HTTP poll — folded minutes
    of audio into a detector that still believed it was inside warm-up, and a
    poll gap over five seconds silently rebased the whole thing.
    """
    detector = StreamingSectionDetector(now=0.0)
    started = time.time()
    end = drive(detector, 8.0, energy=0.05, bass=0.04)
    end = drive(detector, 8.0, energy=0.55, bass=0.60, start=end)
    elapsed = time.time() - started

    assert detector.section != "verse", detector.debug()

    # The contrast only means anything while the run really was faster than
    # real time, which is the situation the split hides in.
    if elapsed < StreamingSectionDetector._WARMUP_S:
        wall = StreamingSectionDetector(now=0.0)
        drive(wall, 8.0, energy=0.05, bass=0.04, now_from_caller=False)
        drive(wall, 8.0, energy=0.55, bass=0.60, now_from_caller=False)
        assert wall.section == "verse", (
            "the wall-clock fallback committed a section it could not have "
            "heard enough audio for, so this guard is not measuring the split"
        )


def test_a_detector_stepped_faster_than_real_time_is_not_rebased():
    """`t > last + 5 s` means a dropped stream, not a fast caller."""
    detector = StreamingSectionDetector(now=0.0)
    end = drive(detector, 10.0, energy=0.40, bass=0.35)
    centre_before = detector.debug()["centre"]
    drive(detector, 2.0, energy=0.40, bass=0.35, start=end)
    assert detector.debug()["centre"] == pytest.approx(centre_before, abs=0.05)


def _run_to_drop(programme_level):
    """A quiet stretch, then a hard entry, and whether it read as a drop."""
    detector = StreamingSectionDetector(now=0.0)
    end = drive(detector, 12.0, energy=0.06, bass=0.05)
    frames = int(round(6.0 / DT))
    beat_every = max(1, int(round(0.5 / DT)))
    beat_number = 999
    saw_drop = False
    for i in range(frames):
        is_beat = (i % beat_every) == 0
        if is_beat:
            beat_number += 1
        decision = detector.update(
            DT,
            energy=0.95,
            bass=0.95 if is_beat else 0.5,
            spectral_flux=0.30,
            is_beat=is_beat,
            beat_number=beat_number,
            bpm=128.0,
            programme_level=programme_level,
            now=end + i * DT,
        )
        saw_drop = saw_drop or decision.section == "drop"
    return saw_drop


def test_a_source_publishing_no_loudness_does_not_lose_its_drops():
    """None is "no opinion". A caller with no normalised value keeps working."""
    assert _run_to_drop(None) is True


def test_a_loud_hit_in_quiet_material_is_not_promoted_to_a_drop():
    """Everything else in the drop test is relative, so a small excursion in a
    quiet passage satisfies all of it. An accent in a quiet passage is worse
    than no accent, and absolute programme loudness is the only thing that can
    tell the two apart at a playback level nobody controls."""
    below = StreamingSectionDetector._DROP_MIN_PROGRAMME - 0.05
    assert _run_to_drop(below) is False
    assert _run_to_drop(StreamingSectionDetector._DROP_MIN_PROGRAMME) is True


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
def test_an_unusable_loudness_value_does_not_stop_the_show(bad):
    """Runs at 60 fps: a bad number keeps the previous section, never raises."""
    manager = SectionManager()
    name = manager.update_section_from_audio(
        DT, energy=0.5, bass=0.5, programme_level=bad, now=0.0
    )
    assert name in {"breakdown", "verse", "buildup", "chorus", "drop"}
