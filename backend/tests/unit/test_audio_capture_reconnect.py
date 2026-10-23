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
