"""
Unit Tests for Audio Capture Reconnect
======================================

An unattended install cannot lose audio for the night because a USB interface
blinked. The capture watchdog restarts a device that died or went quiet, and
leaves alone one the operator stopped.
"""

import threading
import time

import numpy as np

from app.services.audio.system_audio_capture import SystemAudioCapture


class _FakeDevice:
    """A backend that delivers `blocks` chunks and then dies or just stops."""

    def __init__(self, capture, blocks, die=True):
        self.capture, self.blocks, self.die = capture, blocks, die
        self.starts = 0

    def start(self, device_index=None):
        self.starts += 1
        capture = self.capture
        capture._running = True
        capture._device_name = "Fake interface"
        blocks = self.blocks if self.starts == 1 else 10 ** 6

        def run():
            sent = 0
            while capture._running and sent < blocks:
                capture._dispatch_chunk(np.zeros(256, dtype=np.float32))
                sent += 1
                time.sleep(0.005)
            if self.die and capture._running:
                capture._running = False  # what a capture loop does on an error

        capture._thread = threading.Thread(target=run, daemon=True)
        capture._thread.start()
        return True


def _capture(blocks, die=True):
    received = []
    capture = SystemAudioCapture(chunk_size=256, on_audio_chunk=received.append)
    capture.WATCH_S = 0.05
    capture.STALL_S = 0.3
    capture.MAX_BACKOFF_S = 0.1
    device = _FakeDevice(capture, blocks, die)
    capture._start_backend = device.start
    capture.list_devices = lambda: []
    return capture, device, received


def _wait(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_a_device_that_dies_is_restarted():
    capture, device, received = _capture(blocks=5, die=True)
    assert capture.start()
    try:
        assert _wait(lambda: device.starts >= 2)
        count = len(received)
        assert _wait(lambda: len(received) > count + 10)
        assert capture.get_status()["reconnecting"] is False
    finally:
        capture.stop()


def test_a_device_that_goes_quiet_is_restarted():
    capture, device, received = _capture(blocks=5, die=False)
    assert capture.start()
    try:
        assert _wait(lambda: device.starts >= 2)
    finally:
        capture.stop()


def test_stopping_on_purpose_is_not_reconnected():
    capture, device, _ = _capture(blocks=10 ** 6)
    assert capture.start()
    capture.stop()
    time.sleep(capture.STALL_S * 3)

    assert device.starts == 1
    assert not capture.is_running


class _LateDevice:
    """A named interface that is not there at boot and appears later."""

    def __init__(self, capture, name="Desk USB", index=7, present_after=3):
        self.capture, self.name, self.index = capture, name, index
        self.present_after = present_after
        self.lookups = 0
        self.opened_with = []

    def list_devices(self):
        self.lookups += 1
        if self.lookups < self.present_after:
            return [{"index": 0, "name": "Built-in Mic"}]
        return [{"index": 0, "name": "Built-in Mic"}, {"index": self.index, "name": self.name}]

    def start(self, device_index=None):
        self.opened_with.append(device_index)
        if device_index != self.index:
            return False
        return _FakeDevice(self.capture, blocks=10 ** 6, die=False).start(device_index)


def _late_capture(**kwargs):
    capture = SystemAudioCapture(chunk_size=256, on_audio_chunk=lambda _: None)
    capture.WATCH_S = 0.05
    capture.STALL_S = 0.3
    capture.MAX_BACKOFF_S = 0.1
    device = _LateDevice(capture, **kwargs)
    capture.list_devices = device.list_devices
    capture._start_backend = device.start
    return capture, device


def test_a_remembered_device_missing_at_boot_is_opened_when_it_appears():
    capture, device = _late_capture(present_after=4)

    assert capture.start(device_name="Desk USB", keep_trying=True) is False
    try:
        assert _wait(lambda: capture.is_running)
        assert device.opened_with[-1] == 7
        # It waited for that device: no other input was ever opened.
        assert set(device.opened_with) <= {-1, 7}
        assert capture.get_status()["reconnecting"] is False
    finally:
        capture.stop()


def test_a_device_found_by_name_opens_at_whatever_index_it_has_now():
    capture, device = _late_capture(index=12, present_after=1)

    assert capture.start(device_name="Desk USB")
    try:
        assert device.opened_with == [12]
    finally:
        capture.stop()


def test_without_keep_trying_a_failed_start_is_just_a_failure():
    capture, device = _late_capture(present_after=10 ** 6)

    assert capture.start(device_name="Desk USB") is False
    time.sleep(capture.STALL_S)
    assert capture._watchdog is None
    assert len(device.opened_with) == 1


def test_an_error_inside_the_watchdog_does_not_end_it():
    capture, device, received = _capture(blocks=5, die=True)
    calls = {"n": 0}
    real_step = capture._watchdog_step

    def flaky_step():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("driver hiccup")
        return real_step()

    capture._watchdog_step = flaky_step
    capture.MAX_BACKOFF_S = 0.05
    assert capture.start()
    try:
        assert _wait(lambda: device.starts >= 2)
        assert capture._watchdog.is_alive()
    finally:
        capture.stop()
