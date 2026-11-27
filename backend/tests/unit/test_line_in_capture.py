"""
Line-In Capture on Windows
==========================

A venue's music usually arrives on a cable: the desk or the DJ mixer into a USB
interface. Windows used to accept loopback only, so that feed could not be
chosen at all. These tests pin that a line input is captured from, that
loopback still works and is still what auto mode reaches for, and that the
choice is remembered precisely enough to find the same input again.

No real device is opened anywhere in here. PortAudio is replaced by a fake
that reports a Windows-shaped device list and feeds a known tone to whoever
opens an input.
"""

import numpy as np
import pytest

from app.main import app
from app.services.audio import capture_settings
from app.services.audio import system_audio_capture as sac
from app.services.audio.system_audio_capture import SystemAudioCapture, capture_refusal

LINE_IN = "Line In (USB Audio CODEC)"
LOOPBACK = "Speakers (Realtek Audio) [Loopback]"


def _entry(index, name, hostapi, inputs=2, outputs=0, rate=48000.0, **extra):
    entry = {
        "index": index,
        "name": name,
        "hostapi": hostapi,
        "max_input_channels": inputs,
        "max_output_channels": outputs,
        "default_samplerate": rate,
        "is_loopback": False,
        "device_type": "sounddevice",
        "sd_index": index,
        "platform": "win32",
    }
    entry.update(extra)
    return entry


# What a Windows laptop with a USB interface reports: the speakers' loopback,
# then the interface's line-in once per host API, kernel streaming included.
DEVICES = [
    _entry(0, LOOPBACK, "WASAPI Loopback (pyaudiowpatch)", is_loopback=True,
           device_type="pyaudio_loopback", pa_index=11),
    _entry(1, LINE_IN, "Windows WDM-KS"),
    _entry(2, LINE_IN, "MME", rate=44100.0),
    _entry(3, "Speakers (Realtek Audio)", "MME", inputs=0, outputs=2),
    _entry(4, LINE_IN, "Windows WASAPI"),
]


class _FakeStream:
    """An input stream that hands three blocks of a 440 Hz tone to its callback."""

    def __init__(self, owner, **kwargs):
        self.owner, self.kwargs = owner, kwargs
        self.closed = False
        owner.opened.append(kwargs)
        rate = kwargs["samplerate"]
        if owner.only_rate is not None and int(rate) != owner.only_rate:
            raise RuntimeError(f"Invalid sample rate {rate}")

    def start(self):
        frames = self.kwargs["blocksize"]
        t = np.arange(frames, dtype=np.float32) / float(self.kwargs["samplerate"])
        tone = (0.5 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
        block = np.repeat(tone[:, None], self.kwargs["channels"], axis=1)
        for _ in range(3):
            self.kwargs["callback"](block, frames, None, None)

    def stop(self):
        pass

    def close(self):
        self.closed = True


class _FakeSoundDevice:
    """Stands in for the sounddevice module."""

    def __init__(self, only_rate=None):
        self.only_rate = only_rate  # a shared WASAPI input opens at one rate only
        self.opened = []

    def query_devices(self, index=None):
        return DEVICES if index is None else DEVICES[index]

    def InputStream(self, **kwargs):
        return _FakeStream(self, **kwargs)


@pytest.fixture
def windows(monkeypatch):
    """A Windows box whose audio hardware is entirely fake."""
    fake = _FakeSoundDevice()
    monkeypatch.setattr(sac, "PLATFORM", "win32")
    monkeypatch.setattr(sac, "_get_sounddevice", lambda: fake)
    monkeypatch.setattr(sac, "_get_pyaudio", lambda: None)
    monkeypatch.setattr(sac, "_get_soundcard", lambda: None)
    return fake


@pytest.fixture
def capture(windows):
    received = []
    cap = SystemAudioCapture(sample_rate=22050, chunk_size=256, on_audio_chunk=received.append)
    cap.list_devices = lambda: [dict(d) for d in DEVICES]
    cap.received = received
    yield cap
    cap.stop()


# ---------------------------------------------------------------------------
# Capture from the selected device
# ---------------------------------------------------------------------------

def test_a_line_in_is_captured_from(capture, windows):
    assert capture.start(device_index=4)

    status = capture.get_status()
    assert status["running"] is True
    assert status["device_name"] == LINE_IN
    assert status["capture_method"] == "sounddevice"
    assert windows.opened[-1]["device"] == 4
    # The tone the interface delivered reached the analysis callback, in mono.
    assert len(capture.received) == 3
    assert capture.received[0].shape == (256,)
    assert status["last_peak"] == pytest.approx(0.5, abs=0.05)


def test_the_input_is_opened_shared_never_exclusive(capture, windows):
    assert capture.start(device_index=4)

    # Exclusive mode is something a caller has to ask PortAudio for. Nothing
    # here asks: other programs keep the device.
    assert set(windows.opened[-1]) == {
        "device", "samplerate", "channels", "blocksize", "dtype", "callback"
    }


def test_an_input_that_only_opens_at_its_own_rate_is_followed(capture, windows):
    """Shared WASAPI refuses 22050 Hz; the analyzer follows the device instead."""
    windows.only_rate = 48000

    assert capture.start(device_index=4)

    assert [int(o["samplerate"]) for o in windows.opened] == [22050, 48000]
    assert capture.sample_rate == 48000
    assert len(capture.received) == 3


def test_an_input_that_will_not_open_at_all_is_a_clean_failure(capture, windows):
    windows.only_rate = 96000

    assert capture.start(device_index=4) is False
    assert capture.is_running is False
    assert capture.sample_rate == 22050


def test_a_kernel_streaming_entry_is_never_opened(capture, windows):
    assert capture.start(device_index=1) is False
    assert windows.opened == []


def test_an_output_only_device_is_never_opened(capture, windows):
    assert capture.start(device_index=3) is False
    assert windows.opened == []


# ---------------------------------------------------------------------------
# Loopback is untouched, and still the default
# ---------------------------------------------------------------------------

def test_picking_loopback_still_goes_to_the_loopback_backend(capture, windows):
    opened = []

    def fake_loopback(pa_index):
        opened.append(pa_index)
        capture._running = True
        capture._device_name = LOOPBACK
        return True

    capture._start_pyaudio_loopback = fake_loopback

    assert capture.start(device_index=0)
    assert opened == [11]
    assert windows.opened == []


def test_auto_mode_still_prefers_loopback_over_a_line_in(capture, windows):
    opened = []

    def fake_loopback(pa_index):
        opened.append(pa_index)
        capture._running = True
        capture._device_name = LOOPBACK
        return True

    capture._start_pyaudio_loopback = fake_loopback

    assert capture.start()
    assert opened == [11]
    assert windows.opened == []


# ---------------------------------------------------------------------------
# Finding the remembered device again
# ---------------------------------------------------------------------------

def test_a_remembered_line_in_is_found_by_name_and_host_api(capture, windows):
    assert capture.start(device_name=LINE_IN, device_hostapi="MME")

    assert windows.opened[-1]["device"] == 2


def test_a_name_alone_never_lands_on_the_kernel_streaming_entry(capture, windows):
    """WDM-KS is listed first under the same name; it must be skipped."""
    assert capture.start(device_name=LINE_IN)

    assert windows.opened[-1]["device"] == 2


def test_the_choice_is_remembered_with_its_host_api(tmp_path):
    capture_settings.save(LINE_IN, running=True, data_dir=tmp_path, hostapi="Windows WASAPI")

    assert capture_settings.load(tmp_path) == {
        "device_name": LINE_IN, "running": True, "hostapi": "Windows WASAPI",
    }

    capture_settings.set_running(False, data_dir=tmp_path)

    assert capture_settings.load(tmp_path) == {
        "device_name": LINE_IN, "running": False, "hostapi": "Windows WASAPI",
    }


# ---------------------------------------------------------------------------
# What may be captured from
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hostapi", ["MME", "Windows DirectSound", "Windows WASAPI"])
def test_windows_accepts_a_line_in_on_every_shared_host_api(hostapi):
    assert capture_refusal(_entry(1, LINE_IN, hostapi), platform="win32") is None


@pytest.mark.parametrize("hostapi", ["Windows WDM-KS", "ASIO"])
def test_windows_refuses_host_apis_that_take_the_device(hostapi):
    assert capture_refusal(_entry(1, LINE_IN, hostapi), platform="win32")


def test_loopback_is_accepted_whatever_its_channels_say():
    assert capture_refusal(DEVICES[0], platform="win32") is None
    assert capture_refusal({"is_loopback": True, "max_input_channels": 0}, platform="win32") is None


def test_a_device_with_no_inputs_is_refused_everywhere():
    for platform in ("win32", "darwin", "linux"):
        assert capture_refusal(DEVICES[3], platform=platform) == "Selected device has no input channels"


def test_other_platforms_are_not_filtered_by_host_api():
    assert capture_refusal(_entry(1, "Scarlett", "ASIO"), platform="darwin") is None


# ---------------------------------------------------------------------------
# The dashboard's endpoints
# ---------------------------------------------------------------------------

@pytest.fixture
def box(capture, monkeypatch, tmp_path):
    """The app with the fake capture installed and its memory in a temp dir.

    The memory must not land in the suite's shared data dir: a remembered
    "running" choice there would make a later lifespan test start capture.
    """
    path = tmp_path / capture_settings.FILENAME
    monkeypatch.setattr(capture_settings, "settings_path", lambda data_dir=None: path)
    monkeypatch.setattr(app.state, "audio_capture", capture, raising=False)
    monkeypatch.setattr(app.state, "effects_engine", None, raising=False)
    return capture


async def test_the_dashboard_can_start_capture_from_a_line_in(client, box, windows):
    response = await client.post("/api/audio/capture/start", params={"device_index": 4})

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "started", "device": LINE_IN}
    assert windows.opened[-1]["device"] == 4

    status = (await client.get("/api/audio/capture/status")).json()
    assert status["running"] is True
    assert status["capture_method"] == "sounddevice"
    assert status["chunk_count"] == 3
    assert status["remembered_device"] == LINE_IN
    assert status["remembered_hostapi"] == "Windows WASAPI"


async def test_the_choice_outlives_a_stop_so_the_chooser_reopens_on_it(client, box):
    await client.post("/api/audio/capture/start", params={"device_index": 4})
    assert (await client.post("/api/audio/capture/stop")).status_code == 200

    status = (await client.get("/api/audio/capture/status")).json()
    assert status["running"] is False
    assert status["remembered_device"] == LINE_IN
    assert capture_settings.load() == {
        "device_name": LINE_IN, "running": False, "hostapi": "Windows WASAPI",
    }


async def test_the_remembered_choice_restarts_the_same_input(client, box, windows):
    """What boot does with the file the dashboard left behind."""
    await client.post("/api/audio/capture/start", params={"device_index": 4})
    box.stop()
    remembered = capture_settings.load()

    assert box.start(
        device_name=remembered["device_name"],
        device_hostapi=remembered.get("hostapi"),
        keep_trying=True,
    )
    assert windows.opened[-1]["device"] == 4


async def test_the_dashboard_refuses_a_kernel_streaming_entry(client, box, windows):
    response = await client.post("/api/audio/capture/start", params={"device_index": 1})

    assert response.status_code == 400
    assert "other programs" in response.json()["detail"]
    assert windows.opened == []
    assert capture_settings.load()["device_name"] is None


async def test_the_dashboard_refuses_an_output_only_device(client, box, windows):
    response = await client.post("/api/audio/capture/start", params={"device_index": 3})

    assert response.status_code == 400
    assert windows.opened == []


async def test_nothing_remembered_reads_as_none(client, box):
    status = (await client.get("/api/audio/capture/status")).json()

    assert status["remembered_device"] is None
    assert status["remembered_hostapi"] is None
