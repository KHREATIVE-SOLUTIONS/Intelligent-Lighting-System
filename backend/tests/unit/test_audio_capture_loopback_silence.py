"""
Loopback silence is not a lost device
=====================================

WASAPI loopback (pyaudiowpatch, soundcard on Windows) delivers no callbacks at
all while nothing is playing. The watchdog used to read that as a dead device
and tear the stream down and rescan every few seconds, so music that started
mid-rescan was missed. These drive `_watchdog_step` directly with fake
backends; no audio hardware, no subprocess.
"""

import threading
import time

import numpy as np

from app.services.audio.system_audio_capture import SystemAudioCapture


class _FakePaStream:
    def __init__(self):
        self.active = True
        self.closed = False

    def is_active(self):
        return self.active

    def stop_stream(self):
        self.active = False

    def close(self):
        self.closed = True


def _loopback_capture(method="pyaudio_loopback", listed=True):
    capture = SystemAudioCapture(chunk_size=256, on_audio_chunk=lambda _: None)
    capture.STALL_S = 0.05
    starts = []

    def fake_start(device_index=None):
        starts.append(device_index)
        capture._running = True
        capture._capture_method = method
        capture._device_name = "Speakers (Studio 24c) [Loopback]"
        if method == "pyaudio_loopback":
            capture._stream = _FakePaStream()
        else:
            stop = threading.Event()
            capture._thread = threading.Thread(target=stop.wait, args=(5.0,), daemon=True)
            capture._thread.start()
        return True

    capture._start_backend = fake_start
    state = {"listed": listed}
    capture.list_devices = lambda: (
        [{"index": 0, "name": "Speakers (Studio 24c) [Loopback]"}] if state["listed"] else
        [{"index": 0, "name": "Something else"}])
    assert fake_start() is True
    capture._wanted = True
    capture._dispatch_chunk(np.full(256, 0.2, dtype=np.float32))
    return capture, starts, state


def test_silent_pyaudio_loopback_stays_open():
    capture, starts, _ = _loopback_capture()
    stream = capture._stream
    time.sleep(0.1)                       # longer than STALL_S, no blocks
    for _ in range(5):
        capture._watchdog_step()
    assert capture._stream is stream and not stream.closed
    assert len(starts) == 1, "silence must not reconnect"
    assert capture.get_status()["silent"] is True
    assert capture.get_status()["reconnecting"] is False


def test_silent_soundcard_loopback_stays_open():
    capture, starts, _ = _loopback_capture(method="soundcard_loopback")
    time.sleep(0.1)
    capture._watchdog_step()
    assert len(starts) == 1
    assert capture._running


def test_an_inactive_loopback_stream_is_reconnected():
    capture, starts, _ = _loopback_capture()
    capture._stream.active = False        # the driver stopped it (unplugged)
    time.sleep(0.1)
    capture._watchdog_step()
    assert len(starts) == 2


def test_a_device_gone_from_the_list_is_reconnected():
    capture, starts, state = _loopback_capture()
    state["listed"] = False
    time.sleep(0.1)
    capture._presence_checked_t = -1.0e9   # due for a presence check
    capture._watchdog_step()
    assert len(starts) == 2


def test_a_scan_that_finds_nothing_is_not_a_missing_device():
    capture, starts, _ = _loopback_capture()
    capture.list_devices = lambda: []
    time.sleep(0.1)
    capture._presence_checked_t = -1.0e9
    capture._watchdog_step()
    assert len(starts) == 1


def test_blocks_returning_end_the_silence():
    capture, _, _ = _loopback_capture()
    time.sleep(0.1)
    capture._watchdog_step()
    assert capture._silent
    capture._dispatch_chunk(np.full(256, 0.2, dtype=np.float32))
    capture._watchdog_step()
    assert not capture._silent


def test_sounddevice_gap_is_still_a_lost_device():
    capture, starts, _ = _loopback_capture(method="sounddevice")
    time.sleep(0.1)
    capture._watchdog_step()
    assert len(starts) == 2


def test_the_level_meter_ages_out_a_stale_block():
    capture, _, _ = _loopback_capture()
    capture.LEVEL_STALE_S = 0.05
    meter = capture.level_meter()
    assert meter["rms"] > 0.1 and meter["rms_dbfs"] > -20.0
    time.sleep(0.1)
    meter = capture.level_meter()
    assert meter["rms"] == 0.0 and meter["peak"] == 0.0
    assert meter["rms_dbfs"] == -120.0
    assert meter["running"] is True
