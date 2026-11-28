"""The meter block published on the websocket and the capture status."""

from app.services.audio.meter import build_meter_block
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine

KEYS = {"rms", "peak", "rms_dbfs", "peak_dbfs", "bpm", "beat_count", "seconds_since_beat",
        "beat_phase", "device_name", "running"}


def test_the_block_has_every_field_with_nothing_attached():
    block = build_meter_block(None, None)
    assert KEYS <= set(block)
    assert block["running"] is False and block["rms_dbfs"] == -120.0


def test_the_block_carries_the_engine_beat():
    engine = EffectsEngine(EffectsConfig())
    for i in range(120):
        engine.update_audio(energy=0.4, is_beat=(i % 28 == 0), beat_number=i // 28, bpm=128.0)
        engine.update(delta_time=1.0 / 60.0)
    block = build_meter_block(None, engine)
    assert block["beat_count"] > 0
    assert block["bpm"] and block["bpm"] > 0


class _Capture:
    def level_meter(self):
        return {"rms": 0.2, "peak": 0.66, "rms_dbfs": -14.0, "peak_dbfs": -3.6,
                "running": True, "device_name": "Speakers (Studio 24c)"}


def test_the_block_carries_the_capture_level():
    block = build_meter_block(_Capture(), None)
    assert block["running"] is True and block["peak"] == 0.66
    assert block["device_name"] == "Speakers (Studio 24c)"


class _Broken:
    def level_meter(self):
        raise RuntimeError("driver")

    def beat_meter(self):
        raise RuntimeError("engine")


def test_a_failing_source_still_gives_a_block():
    block = build_meter_block(_Broken(), _Broken())
    assert KEYS <= set(block)
