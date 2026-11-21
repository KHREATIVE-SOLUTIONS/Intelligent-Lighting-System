"""
The wire tier's instruments, checked without booting a backend.

The wire tests (tests/wire, opt-in) are only as good as the decoder and the soak
verdict behind them. These run in the default suite so a broken instrument is caught
on every push, not on the next occasion somebody runs the slow tier.
"""
import socket
import struct
import time
from collections import Counter

import numpy as np
import pytest

from tests.wire import harness as H
from tests.wire import soak


# ---------------------------------------------------------------------------
# Art-Net parsing
# ---------------------------------------------------------------------------
def artdmx(universe=0, seq=1, payload=bytes(512), protver=14, opcode=0x5000, length=None):
    length = len(payload) if length is None else length
    return (b"Art-Net\x00" + struct.pack("<H", opcode) + struct.pack(">H", protver)
            + bytes([seq, 0, universe & 0xFF, universe >> 8]) + struct.pack(">H", length) + payload)


def test_a_valid_artdmx_packet_parses_clean():
    bad = Counter()
    universe, seq, length, payload = H.Capture.parse(artdmx(universe=0x0102, seq=7), bad)
    assert (universe, seq, length, len(payload)) == (0x0102, 7, 512, 512)
    assert not bad


@pytest.mark.parametrize("packet, fault", [
    (b"Not-Art\x00" + bytes(530), "not_artnet"),
    (artdmx(opcode=0x2000), "op_0x2000"),
])
def test_foreign_packets_are_counted_and_dropped(packet, fault):
    bad = Counter()
    assert H.Capture.parse(packet, bad) is None
    assert bad[fault] == 1


@pytest.mark.parametrize("packet, fault", [
    (artdmx(protver=13), "protver_13"),
    (artdmx(payload=bytes(511)), "length_illegal"),
    (artdmx(length=510), "length_mismatch"),
])
def test_malformed_artdmx_is_kept_but_counted(packet, fault):
    bad = Counter()
    assert H.Capture.parse(packet, bad) is not None
    assert bad[fault] == 1


def test_sequence_wrap_from_255_to_1_is_not_a_break():
    seqs = list(range(250, 256)) + list(range(1, 6))
    assert H.sequence_breaks(seqs) == 0


@pytest.mark.parametrize("seqs", [
    [1, 2, 4, 5],       # a frame lost
    [1, 2, 2, 3],       # a frame repeated
    [254, 255, 0, 1],   # 0 means "sequence disabled"
])
def test_a_lost_repeated_or_zero_sequence_is_a_break(seqs):
    assert H.sequence_breaks(seqs) >= 1


# ---------------------------------------------------------------------------
# Decoding a fixture out of a universe
# ---------------------------------------------------------------------------
def fixture(address, types, universe=0, name="fx"):
    return {
        "name": name, "universe": universe, "address": address, "channel_count": len(types),
        "channels": [{"offset": i, "type": t, "name": t, "default": 0,
                      "is_fine": t.endswith("_fine")} for i, t in enumerate(types)],
    }


def frames_with(values: dict, n=4):
    frames = np.zeros((n, 512), dtype=np.uint8)
    for channel, value in values.items():
        frames[:, channel - 1] = value
    return frames


def test_rgb_level_is_the_brightest_colour():
    par = fixture(10, ["red", "green", "blue"])
    level = H.fixture_series(par, frames_with({10: 51, 11: 255, 12: 0}))["level"]
    assert level == pytest.approx(np.ones(4))


def test_dimmer_scales_the_colour():
    spot = fixture(1, ["dimmer", "red", "green", "blue"])
    level = H.fixture_series(spot, frames_with({1: 128, 2: 255}))["level"]
    assert level == pytest.approx(np.full(4, 128 / 255.0))


def test_cmy_is_subtractive_so_zero_is_open():
    wash = fixture(1, ["dimmer", "cyan", "magenta", "yellow"])
    open_white = H.fixture_series(wash, frames_with({1: 255}))["level"]
    flagged_out = H.fixture_series(wash, frames_with({1: 255, 2: 255, 3: 255, 4: 255}))["level"]
    assert open_white == pytest.approx(np.ones(4))
    assert flagged_out == pytest.approx(np.zeros(4))


def test_pan_is_read_as_sixteen_bit_when_a_fine_channel_exists():
    mover = fixture(1, ["pan", "pan_fine", "tilt"])
    series = H.fixture_series(mover, frames_with({1: 2, 2: 3, 3: 9}))
    pan, pan_is_16 = series["pan"]
    tilt, tilt_is_16 = series["tilt"]
    assert pan[0] == 2 * 256 + 3 and pan_is_16
    assert tilt[0] == 9 * 256 and not tilt_is_16


# ---------------------------------------------------------------------------
# Analysing a capture
# ---------------------------------------------------------------------------
class FakeCapture:
    """Stands in for H.Capture: frames at an exact 40 fps on chosen universes."""

    def __init__(self, per_universe: dict, seconds=2.0):
        n = int(seconds * 40)
        self.times = np.arange(n) / 40.0
        self.per = {u: np.repeat(f[:1], n, axis=0) for u, f in per_universe.items()}

    def window(self, t0, t1):
        keep = (self.times >= t0) & (self.times < t1)
        seqs = (np.arange(len(self.times)) % 255 + 1)[keep]
        return {u: (self.times[keep], f[keep], seqs) for u, f in self.per.items()}


def test_analyse_reports_rate_level_and_a_clean_footprint():
    patch = [fixture(1, ["red", "green", "blue"])]
    cap = FakeCapture({0: frames_with({1: 255})})
    a = H.analyse(cap, patch, 0.0, 2.0)
    assert a["transport"][0]["fps"] == 40.0
    assert a["transport"][0]["seq_breaks"] == 0
    assert a["nonzero_channels_outside_patch"] == 0
    assert a["unpatched_universes_transmitted"] == []
    assert a["level"]["rig_mean"] == pytest.approx(1.0)


def test_analyse_sees_a_channel_lit_outside_the_patch():
    patch = [fixture(1, ["red", "green", "blue"])]
    cap = FakeCapture({0: frames_with({1: 255, 400: 9})})
    assert H.analyse(cap, patch, 0.0, 2.0)["nonzero_channels_outside_patch"] == 1


def test_analyse_sees_a_universe_the_rig_does_not_own():
    patch = [fixture(1, ["red", "green", "blue"])]
    cap = FakeCapture({0: frames_with({1: 255}), 5: frames_with({})})
    assert H.analyse(cap, patch, 0.0, 2.0)["unpatched_universes_transmitted"] == [5]


# ---------------------------------------------------------------------------
# The capture process, on loopback
# ---------------------------------------------------------------------------
def test_capture_process_stamps_packets_on_our_clock_and_prunes():
    cfg_port = H._free_port(socket.SOCK_DGRAM)
    cap = H.Capture(cfg_port)
    try:
        t_before = time.perf_counter()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            for seq in (1, 2, 3):
                s.sendto(artdmx(seq=seq, payload=bytes([seq]) * 512), ("127.0.0.1", cfg_port))
            s.sendto(b"junk", ("127.0.0.1", cfg_port))
        deadline = time.perf_counter() + 5.0
        while (cap.total < 3 or not cap.bad) and time.perf_counter() < deadline:
            time.sleep(0.01)
        t_after = time.perf_counter()

        assert cap.total == 3
        times, frames, seqs = cap.window(t_before - 1.0, t_after + 1.0)[0]
        assert seqs.tolist() == [1, 2, 3]
        assert frames[:, 0].tolist() == [1, 2, 3]
        # On our clock: between the moments either side of the sends.
        assert t_before - 0.05 <= times[0] and times[-1] <= t_after + 0.05

        cap.prune(float(times[1]))
        assert [p[2] for p in cap.since(0.0)] == [2, 3]
        assert cap.total == 3
    finally:
        cap.close()
    assert cap.bad["not_artnet"] == 1


# ---------------------------------------------------------------------------
# The soak verdict
# ---------------------------------------------------------------------------
def soak_rows(n=480, **overrides):
    rows = []
    for minute in range(1, n + 1):
        row = {
            "minute": minute, "backend_alive": True, "fps": 40.0, "gap_ms_p99": 33.8,
            "gap_ms_max": 54.0, "seq_breaks": 0, "stray_channels": 0, "unpatched_universes": [],
            "malformed_packets": 0, "feed_reconnects": 0, "send_errors": 0,
            "rss_mb": 350.0 + (minute % 3),
        }
        for key, value in overrides.items():
            row[key] = value(minute) if callable(value) else value
        rows.append(row)
    return rows


def failed(verdict):
    return sorted(name for name, c in verdict["checks"].items() if c["passed"] is not True)


def test_a_clean_eight_hours_passes():
    verdict = soak.evaluate(soak_rows(), expected_minutes=480)
    assert verdict["passed"], soak.format_verdict(verdict)


def test_one_gap_over_100_ms_fails_the_soak():
    rows = soak_rows(gap_ms_max=lambda m: 104.1 if m == 300 else 54.0)
    verdict = soak.evaluate(rows, expected_minutes=480)
    assert failed(verdict) == ["frame_gap"]
    assert "minute 300" in verdict["checks"]["frame_gap"]["detail"]


def test_a_minute_off_40_fps_fails_the_soak():
    verdict = soak.evaluate(soak_rows(fps=lambda m: 38.9 if m == 7 else 40.0), expected_minutes=480)
    assert failed(verdict) == ["frame_rate"]


def test_a_slow_leak_fails_the_soak():
    # 6 MB an hour: invisible in nine minutes, 48 MB by the end of the night.
    verdict = soak.evaluate(soak_rows(rss_mb=lambda m: 350.0 + m * 0.1), expected_minutes=480)
    assert failed(verdict) == ["memory_flat"]


def test_memory_that_settles_after_warm_up_passes():
    rows = soak_rows(rss_mb=lambda m: 300.0 + min(m, 8) * 6.0)
    assert soak.evaluate(rows, expected_minutes=480)["passed"]


def test_a_run_cut_short_has_not_passed():
    verdict = soak.evaluate(soak_rows(n=120), expected_minutes=480)
    assert failed(verdict) == ["complete"]


def test_too_few_samples_cannot_claim_flat_memory():
    verdict = soak.evaluate(soak_rows(n=3), expected_minutes=3)
    assert verdict["checks"]["memory_flat"]["passed"] is None
    assert not verdict["passed"]


@pytest.mark.parametrize("fault", [
    {"send_errors": 2}, {"stray_channels": 1}, {"unpatched_universes": [5]},
    {"malformed_packets": 1}, {"seq_breaks": 1},
])
def test_a_dishonest_wire_fails_the_soak(fault):
    verdict = soak.evaluate(soak_rows(**fault), expected_minutes=480)
    assert failed(verdict) == ["wire_integrity"]


def test_a_backend_that_died_fails_the_soak():
    rows = soak_rows(n=200)
    rows[-1].update(backend_alive=False, fps=None, gap_ms_max=None, rss_mb=None)
    verdict = soak.evaluate(rows, expected_minutes=480)
    assert verdict["checks"]["backend_alive"]["passed"] is False
    assert not verdict["passed"]


def test_no_rows_is_a_failure_not_a_pass():
    assert soak.evaluate([], expected_minutes=480)["passed"] is False
