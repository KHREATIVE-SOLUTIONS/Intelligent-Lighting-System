"""
Audio Device Enumeration
========================

Asking a driver to describe itself runs native code, and on a real machine that
code misbehaves. Measured on this developer's Windows box, the same soundcard
backend variously returned 8 speakers, hung forever partway through reading their
properties, and aborted the interpreter with an access violation (0xC0000005) -
across three consecutive runs, with no change but which Bluetooth devices happened
to be settling.

Neither a hang nor an access violation is a Python exception, so the `try` around
each backend cannot see them, and the enumeration shares an event loop with DMX
output: in-process, a wedged driver takes the whole show down. It is isolated in a
child process for that reason, and these tests pin the properties that matter.
"""

import subprocess
import sys

import pytest

from app.services.audio import system_audio_capture as sac
from app.services.audio.system_audio_capture import SystemAudioCapture


def test_enumeration_returns_a_list_without_raising():
    """The live call, against whatever hardware this machine actually has."""
    devices = SystemAudioCapture.list_devices()

    assert isinstance(devices, list)
    for d in devices:
        assert isinstance(d, dict)
        assert d.get("name")
        assert "is_loopback" in d


def test_indices_are_dense_and_unique():
    """The index is the UI's device selector, so gaps or repeats mis-select."""
    devices = SystemAudioCapture.list_devices()
    indices = [d["index"] for d in devices]

    assert indices == list(range(len(devices)))


def test_a_backend_that_hangs_does_not_hang_the_caller(monkeypatch):
    """A wedged driver must cost its own devices and nothing else."""
    real_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if any("soundcard" == str(a) for a in cmd):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 1))
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    devices = SystemAudioCapture.list_devices()

    assert isinstance(devices, list)


def test_a_backend_that_aborts_does_not_take_down_the_caller(monkeypatch):
    """An access violation in a driver is an exit code here, not a crash."""
    real_run = subprocess.run

    class _Crashed:
        returncode = 3221225477  # 0xC0000005, what soundcard actually returned
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        if any("soundcard" == str(a) for a in cmd):
            return _Crashed()
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    devices = SystemAudioCapture.list_devices()

    assert isinstance(devices, list)


def test_every_backend_failing_still_returns_a_list(monkeypatch):
    """No devices is a legitimate answer; an exception out of here is not."""
    def fake_run(cmd, **kwargs):
        raise OSError("no subprocesses available")

    monkeypatch.setattr(subprocess, "run", fake_run)

    devices = SystemAudioCapture.list_devices()

    assert isinstance(devices, list)


@pytest.mark.parametrize("backend", ["pyaudiowpatch", "sounddevice", "soundcard"])
def test_the_child_entry_point_answers_for_one_backend_only(backend):
    """Each child probes a single backend, so one bad driver cannot hide the rest."""
    proc = subprocess.run(
        [sys.executable, "-m", "app.services.audio.system_audio_capture",
         "--list-json", backend],
        cwd=str(sac.Path(__file__).resolve().parents[2]),
        capture_output=True, text=True, timeout=sac.DEVICE_SCAN_TIMEOUT_S + 5,
    )

    # A backend is allowed to hang or abort - that is the whole premise. What it may
    # not do is exit cleanly having printed something the parent cannot read.
    if proc.returncode == 0:
        payloads = [l for l in proc.stdout.splitlines() if l.startswith("DEVICES_JSON:")]
        assert len(payloads) == 1, f"{backend} exited 0 without exactly one payload"
