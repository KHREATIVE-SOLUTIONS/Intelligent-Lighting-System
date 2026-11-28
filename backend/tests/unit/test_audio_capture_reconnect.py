"""
Unit Tests for Audio Capture Reconnect
======================================

An unattended install cannot lose audio for the night because a USB interface
blinked. The capture watchdog restarts a device that died or went quiet, and
leaves alone one the operator stopped.

How these stay deterministic (they used to flake about once per full run):
- The stall check reads a manual clock (`capture._clock`), so "the device went
  quiet for STALL_S" only happens when a test advances it. A fake device thread
  starved by a busy machine can no longer look stalled and trigger a restart
  the test did not ask for.
- Each fake capture thread only acts while it is still the capture's current
  thread, so a torn-down thread waking late cannot kill its replacement.
- Nothing asserts after a fixed sleep. Tests poll a condition with a generous
  deadline (returns as soon as it is true), and status is read only after a
  watchdog step has finished, not halfway through one.
- "Nothing reconnects after stop" is shown by the watchdog thread being dead
  (joined), not by sleeping and hoping. Backoff and poll intervals are tiny.
- Audio devices are never opened: `_start_backend` and `list_devices` are fakes.
"""

import threading
import time

import numpy as np

from app.services.audio.system_audio_capture import SystemAudioCapture


class _ManualClock:
    """A monotonic clock that moves only when the test says so."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class _FakeDevice:
    """A backend that delivers `blocks` chunks and then dies or just stops."""

    def __init__(self, capture, blocks, die=True):
        self.capture, self.blocks, self.die = capture, blocks, die
        self.starts = 0
        self.threads = []

    def start(self, device_index=None):
        self.starts += 1
        capture = self.capture
        capture._running = True
        capture._device_name = "Fake interface"
        blocks = self.blocks if self.starts == 1 else 10 ** 6

        def run():
            me = threading.current_thread()
            sent = 0
            # Only the current capture thread delivers audio or dies; one that
            # was torn down and replaced just leaves.
            while capture._running and capture._thread is me and sent < blocks:
                capture._dispatch_chunk(np.zeros(256, dtype=np.float32))
                sent += 1
                time.sleep(0.005)
            if self.die and capture._running and capture._thread is me:
                capture._running = False  # what a capture loop does on an error

        thread = threading.Thread(target=run, daemon=True)
        capture._thread = thread
        self.threads.append(thread)
        thread.start()
        return True


def _watch_steps(capture):
    """Count finished watchdog steps, so status is read between steps."""
    steps = []
    real_step = capture._watchdog_step

    def step():
        try:
            return real_step()
        finally:
            steps.append(capture.is_running)

    capture._watchdog_step = step
    return steps


def _tune(capture):
    capture._clock = _ManualClock()
    capture.WATCH_S = 0.02
    capture.STALL_S = 0.3
    capture.MAX_BACKOFF_S = 0.02
    return _watch_steps(capture)


def _capture(blocks, die=True):
    received = []
    capture = SystemAudioCapture(chunk_size=256, on_audio_chunk=received.append)
    steps = _tune(capture)
    device = _FakeDevice(capture, blocks, die)
    capture._start_backend = device.start
    capture.list_devices = lambda: []
    return capture, device, received, steps


def _wait(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def _wait_for_a_step_after_now(steps):
    """Wait until a watchdog step that began no earlier than now has finished.

    Steps run one at a time on one thread, so once a step finishes after this
    call, any step already in progress when it was made has finished too.
    """
    seen = len(steps)
    return _wait(lambda: len(steps) > seen + 1)


def _stop_and_join(capture):
    watchdog = capture._watchdog
    capture.stop()
    if watchdog is not None:
        watchdog.join(timeout=5.0)
        assert not watchdog.is_alive()


def test_a_device_that_dies_is_restarted():
    capture, device, received, steps = _capture(blocks=5, die=True)
    assert capture.start()
    try:
        assert _wait(lambda: device.starts >= 2)
        count = len(received)
        assert _wait(lambda: len(received) > count + 10)
        assert _wait_for_a_step_after_now(steps)
        assert capture.get_status()["reconnecting"] is False
    finally:
        _stop_and_join(capture)


def test_a_device_that_goes_quiet_is_restarted():
    capture, device, _, _ = _capture(blocks=5, die=False)
    assert capture.start()
    try:
        # The device delivers its blocks and then just stops calling back.
        assert _wait(lambda: not device.threads[0].is_alive())
        assert capture.is_running and device.starts == 1
        capture._clock.advance(capture.STALL_S + 1.0)
        assert _wait(lambda: device.starts >= 2)
    finally:
        _stop_and_join(capture)


def test_stopping_on_purpose_is_not_reconnected():
    capture, device, _, _ = _capture(blocks=10 ** 6)
    assert capture.start()
    watchdog = capture._watchdog
    capture.stop()
    # A dead watchdog cannot reconnect anything; prove it is dead, and that
    # even a long silence afterwards changes nothing.
    watchdog.join(timeout=5.0)
    assert not watchdog.is_alive()
    for thread in device.threads:
        thread.join(timeout=5.0)
        assert not thread.is_alive()
    capture._clock.advance(capture.STALL_S * 3)

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
    steps = _tune(capture)
    device = _LateDevice(capture, **kwargs)
    capture.list_devices = device.list_devices
    capture._start_backend = device.start
    return capture, device, steps


def test_a_remembered_device_missing_at_boot_is_opened_when_it_appears():
    capture, device, steps = _late_capture(present_after=4)

    assert capture.start(device_name="Desk USB", keep_trying=True) is False
    try:
        assert _wait(lambda: capture.is_running)
        assert _wait_for_a_step_after_now(steps)
        assert device.opened_with[-1] == 7
        # It waited for that device: no other input was ever opened.
        assert set(device.opened_with) <= {-1, 7}
        assert capture.get_status()["reconnecting"] is False
    finally:
        _stop_and_join(capture)


def test_a_device_found_by_name_opens_at_whatever_index_it_has_now():
    capture, device, _ = _late_capture(index=12, present_after=1)

    assert capture.start(device_name="Desk USB")
    try:
        assert device.opened_with == [12]
    finally:
        _stop_and_join(capture)


def test_without_keep_trying_a_failed_start_is_just_a_failure():
    capture, device, _ = _late_capture(present_after=10 ** 6)

    assert capture.start(device_name="Desk USB") is False
    # No watchdog was started, so nothing exists that could retry later.
    assert capture._watchdog is None
    assert len(device.opened_with) == 1


def test_an_error_inside_the_watchdog_does_not_end_it():
    capture, device, received, _ = _capture(blocks=5, die=True)
    calls = {"n": 0}
    real_step = capture._watchdog_step

    def flaky_step():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("driver hiccup")
        return real_step()

    capture._watchdog_step = flaky_step
    capture.MAX_BACKOFF_S = 0.02
    assert capture.start()
    try:
        assert _wait(lambda: device.starts >= 2)
        assert capture._watchdog.is_alive()
    finally:
        _stop_and_join(capture)
