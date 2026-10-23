"""
System Audio Capture — Cross-Platform
======================================

Captures audio from system output with explicit device selection support.

Platform-specific backends:
  Windows : pyaudiowpatch (WASAPI loopback) → sounddevice (Stereo Mix) → soundcard
  macOS   : soundcard (CoreAudio loopback)  → sounddevice (BlackHole / virtual devices)
  Linux   : sounddevice (PulseAudio monitor) → soundcard
"""

import asyncio
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Callable

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
PLATFORM = sys.platform  # "win32" | "darwin" | "linux"

# How long a driver gets to describe itself before we give up on it. Enumeration
# is sub-second on a healthy machine; anything past this is a wedged driver.
DEVICE_SCAN_TIMEOUT_S = 12.0

# Backends that must not be probed in this process because they can hang or abort
# it rather than raise. Measured on Windows: soundcard.all_speakers() returns, then
# reading a speaker's properties never comes back.
_UNSAFE_IN_PROCESS_BACKENDS = frozenset({"soundcard"} if PLATFORM == "win32" else set())

# ---------------------------------------------------------------------------
# Lazy imports — each backend is imported on first use and cached.
# ---------------------------------------------------------------------------
_sc = None  # soundcard
_sd = None  # sounddevice
_pa = None  # pyaudiowpatch (Windows-only)


def _get_soundcard():
    global _sc
    if _sc is None:
        try:
            import soundcard as sc
            _sc = sc
        except Exception as e:
            # Not only ImportError: these bind native audio libraries at import
            # time, and soundcard asserts when no PulseAudio server is running.
            logger.debug(f"soundcard unavailable: {e!r}")
            _sc = False
    return _sc if _sc is not False else None


def _get_sounddevice():
    global _sd
    if _sd is None:
        try:
            import sounddevice as sd
            _sd = sd
        except Exception as e:
            # Not only ImportError: these bind native audio libraries at import
            # time, and soundcard asserts when no PulseAudio server is running.
            logger.debug(f"sounddevice unavailable: {e!r}")
            _sd = False
    return _sd if _sd is not False else None


def _get_pyaudio():
    """pyaudiowpatch is Windows-only (WASAPI)."""
    if PLATFORM != "win32":
        return None
    global _pa
    if _pa is None:
        try:
            import pyaudiowpatch as pyaudio
            _pa = pyaudio
        except Exception as e:
            # Not only ImportError: these bind native audio libraries at import
            # time, and soundcard asserts when no PulseAudio server is running.
            logger.debug(f"pyaudiowpatch unavailable: {e!r}")
            _pa = False
    return _pa if _pa is not False else None


# ---------------------------------------------------------------------------
# Loopback name patterns per platform (for sounddevice detection)
# ---------------------------------------------------------------------------
_LOOPBACK_PATTERNS_WIN = ("loopback", "stereo mix", "what u hear", "wave out")
_LOOPBACK_PATTERNS_MAC = ("blackhole", "loopback", "soundflower", "existential audio",
                          "virtual audio", "ishowu")
_LOOPBACK_PATTERNS_LINUX = ("monitor of", "pulse monitor", "loopback")


def _loopback_patterns() -> tuple:
    if PLATFORM == "darwin":
        return _LOOPBACK_PATTERNS_MAC
    if PLATFORM.startswith("linux"):
        return _LOOPBACK_PATTERNS_LINUX
    return _LOOPBACK_PATTERNS_WIN


def _soundcard_hostapi_label() -> str:
    if PLATFORM == "darwin":
        return "CoreAudio Loopback (soundcard)"
    if PLATFORM.startswith("linux"):
        return "PulseAudio Loopback (soundcard)"
    return "WASAPI Loopback (soundcard)"


class SystemAudioCapture:
    """Captures system audio output with selectable device backends."""

    def __init__(
        self,
        sample_rate: int = 22050,
        chunk_size: int = 1024,
        channels: int = 1,
        on_audio_chunk: Optional[Callable] = None,
    ):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.channels = channels
        self.on_audio_chunk = on_audio_chunk

        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        # Backend resources
        self._stream = None
        self._pyaudio_instance = None

        # Selected device bookkeeping
        self._device_index: Optional[int] = None
        self._device_name = "None"
        self._capture_method = "none"  # soundcard_loopback | sounddevice | pyaudio_loopback
        self._chunk_count = 0
        self._last_rms = 0.0
        self._last_peak = 0.0

        # Reconnect watchdog: see `_watchdog_loop`.
        self._wanted = False
        self._selection: Optional[int] = None
        self._watchdog: Optional[threading.Thread] = None
        self._watchdog_stop = threading.Event()
        self._last_chunk_t: Optional[float] = None
        self._reconnecting = False
        self._reconnect_attempts = 0

    # ------------------------------------------------------------------
    # Device enumeration
    # ------------------------------------------------------------------
    @staticmethod
    def list_devices() -> list:
        """Every audio device this machine offers, loopback ones included.

        Enumeration is done in a child process. Asking a driver to describe itself
        runs native code that this process cannot defend against: on Windows the
        soundcard backend hangs forever partway through enumerating speakers, and a
        bad probe elsewhere can abort the interpreter outright. Neither is a Python
        exception, so `try` does not help and a worker thread cannot be killed - and
        both would take the show down, because this shares an event loop with the
        DMX output. A child can simply be waited on and abandoned.
        """
        devices = _enumerate_via_subprocess()
        if devices is not None:
            return devices

        logger.warning(
            "Device enumeration subprocess unavailable; enumerating in-process "
            "without the backends known to hang here"
        )
        return SystemAudioCapture._enumerate_devices(skip=_UNSAFE_IN_PROCESS_BACKENDS)

    @staticmethod
    def _enumerate_devices(skip=frozenset()) -> list:
        """Walk every installed backend that is not in `skip`."""
        result = []
        api_index = 0

        # --- soundcard (macOS CoreAudio / Linux PulseAudio / Windows WASAPI) ---
        sc = None if "soundcard" in skip else _get_soundcard()
        if sc is not None:
            try:
                for speaker in sc.all_speakers():
                    result.append(
                        {
                            "index": api_index,
                            "name": f"[Loopback] {speaker.name}",
                            "max_input_channels": speaker.channels,
                            "max_output_channels": speaker.channels,
                            "default_samplerate": 44100,
                            "hostapi": _soundcard_hostapi_label(),
                            "is_loopback": True,
                            "device_type": "soundcard_speaker",
                            "speaker_id": speaker.id,
                            "platform": PLATFORM,
                        }
                    )
                    api_index += 1
            except Exception as e:
                logger.debug(f"Error listing soundcard devices: {e}")

        # --- sounddevice (cross-platform PortAudio) ---
        sd = None if "sounddevice" in skip else _get_sounddevice()
        if sd is not None:
            patterns = _loopback_patterns()
            try:
                devices = sd.query_devices()
                for i, dev in enumerate(devices):
                    hostapi_name = sd.query_hostapis(dev["hostapi"])["name"]
                    name_lower = dev["name"].lower()
                    is_loopback = any(p in name_lower for p in patterns)
                    result.append(
                        {
                            "index": api_index,
                            "name": dev["name"],
                            "max_input_channels": dev["max_input_channels"],
                            "max_output_channels": dev["max_output_channels"],
                            "default_samplerate": dev["default_samplerate"],
                            "hostapi": hostapi_name,
                            "is_loopback": is_loopback and dev["max_input_channels"] > 0,
                            "device_type": "sounddevice",
                            "sd_index": i,
                            "platform": PLATFORM,
                        }
                    )
                    api_index += 1
            except Exception as e:
                logger.debug(f"Error listing sounddevice devices: {e}")

        # --- pyaudiowpatch (Windows WASAPI loopback only) ---
        pa = None if "pyaudiowpatch" in skip else _get_pyaudio()
        if pa is not None:
            p = pa.PyAudio()
            try:
                for i in range(p.get_device_count()):
                    info = p.get_device_info_by_index(i)
                    if info.get("isLoopbackDevice", False):
                        result.append(
                            {
                                "index": api_index,
                                "name": info["name"],
                                "max_input_channels": info.get("maxInputChannels", 0),
                                "max_output_channels": info.get("maxOutputChannels", 0),
                                "default_samplerate": info.get("defaultSampleRate", 44100),
                                "hostapi": "WASAPI Loopback (pyaudiowpatch)",
                                "is_loopback": True,
                                "device_type": "pyaudio_loopback",
                                "pa_index": i,
                                "platform": PLATFORM,
                            }
                        )
                        api_index += 1
            except Exception as e:
                logger.debug(f"Error listing pyaudiowpatch devices: {e}")
            finally:
                p.terminate()

        return result

    # ------------------------------------------------------------------
    # Chunk dispatch
    # ------------------------------------------------------------------
    def _dispatch_chunk(self, audio_data: np.ndarray):
        if not self._running:
            return
        self._last_chunk_t = time.monotonic()
        if not self.on_audio_chunk:
            return
        try:
            if audio_data.size > 0:
                self._chunk_count += 1
                self._last_rms = float(np.sqrt(np.mean(np.square(audio_data))))
                self._last_peak = float(np.max(np.abs(audio_data)))
        except Exception:
            pass
        try:
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self._async_on_chunk(audio_data), self._loop)
            else:
                self.on_audio_chunk(audio_data)
        except Exception as e:
            logger.debug(f"Audio chunk dispatch error: {e}")

    async def _async_on_chunk(self, audio_data: np.ndarray):
        try:
            result = self.on_audio_chunk(audio_data)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            logger.debug(f"Async chunk processing error: {e}")

    # ------------------------------------------------------------------
    # soundcard backend
    # ------------------------------------------------------------------
    def _start_soundcard_loopback(self, speaker_id: Optional[str] = None) -> bool:
        sc = _get_soundcard()
        if sc is None:
            return False
        try:
            speaker = None
            if speaker_id:
                for s in sc.all_speakers():
                    if s.id == speaker_id:
                        speaker = s
                        break
            if speaker is None:
                speaker = sc.default_speaker()
            if speaker is None:
                return False

            loopback_mic = sc.get_microphone(speaker.id, include_loopback=True)
            if loopback_mic is None:
                return False

            self._device_name = f"[Loopback] {speaker.name}"
            self._capture_method = "soundcard_loopback"
            self._running = True
            self._thread = threading.Thread(
                target=self._soundcard_capture_loop, args=(loopback_mic,), daemon=True
            )
            self._thread.start()
            logger.info(f"Audio capture started on soundcard loopback: {self._device_name}")
            return True
        except Exception as e:
            logger.warning(f"soundcard loopback start failed: {e}")
            return False

    def _soundcard_capture_loop(self, loopback_mic):
        try:
            with loopback_mic.recorder(
                samplerate=self.sample_rate,
                channels=[0],
                blocksize=self.chunk_size,
            ) as recorder:
                while self._running:
                    data = recorder.record(numframes=self.chunk_size)
                    audio_data = data.flatten().astype(np.float32)
                    self._dispatch_chunk(audio_data)
        except Exception as e:
            if self._running:
                logger.error(f"soundcard capture loop error: {e}")
            self._running = False

    # ------------------------------------------------------------------
    # sounddevice backend
    # ------------------------------------------------------------------
    def _find_sounddevice_input(self) -> Optional[int]:
        sd = _get_sounddevice()
        if sd is None:
            return None
        devices = sd.query_devices()
        patterns = _loopback_patterns()

        # First pass: loopback / virtual audio devices
        for i, dev in enumerate(devices):
            name_lower = dev["name"].lower()
            if dev["max_input_channels"] > 0 and any(p in name_lower for p in patterns):
                return i

        # Fallback: default input device
        try:
            default_input = sd.default.device[0]
            if default_input is not None and default_input >= 0:
                dev = devices[default_input]
                if dev["max_input_channels"] > 0:
                    return default_input
        except Exception:
            pass

        # Last resort: any input device
        for i, dev in enumerate(devices):
            if dev["max_input_channels"] > 0:
                return i

        return None

    def _sounddevice_callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            logger.debug(f"sounddevice status: {status}")
        audio_data = indata.copy()
        if audio_data.ndim > 1:
            audio_data = np.mean(audio_data, axis=1)
        self._dispatch_chunk(audio_data.astype(np.float32).flatten())

    def _start_sounddevice(self, sd_index: int) -> bool:
        sd = _get_sounddevice()
        if sd is None:
            return False
        try:
            dev_info = sd.query_devices(sd_index)
            max_channels = int(dev_info["max_input_channels"])
            if max_channels <= 0:
                logger.error(f"sounddevice index {sd_index} has no input channels")
                return False

            capture_channels = min(self.channels, max(1, max_channels))
            self._stream = sd.InputStream(
                device=sd_index,
                samplerate=self.sample_rate,
                channels=capture_channels,
                blocksize=self.chunk_size,
                dtype=np.float32,
                callback=self._sounddevice_callback,
            )
            self._stream.start()
            self._running = True
            self._device_name = dev_info["name"]
            self._capture_method = "sounddevice"
            logger.info(f"Audio capture started on sounddevice: {self._device_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to start sounddevice capture: {e}")
            return False

    # ------------------------------------------------------------------
    # pyaudiowpatch backend (Windows only)
    # ------------------------------------------------------------------
    def _pyaudio_callback(self, in_data, frame_count, time_info, status):
        pa = _get_pyaudio()
        if not self._running or pa is None:
            return (None, pa.paComplete if pa is not None else 0)
        try:
            audio_data = np.frombuffer(in_data, dtype=np.float32)
            if len(audio_data) > frame_count:
                channels = max(1, len(audio_data) // frame_count)
                audio_data = audio_data.reshape(-1, channels).mean(axis=1)
            self._dispatch_chunk(audio_data.astype(np.float32))
        except Exception as e:
            logger.debug(f"pyaudio callback error: {e}")
        return (None, pa.paContinue)

    def _start_pyaudio_loopback(self, pa_index: int) -> bool:
        pa = _get_pyaudio()
        if pa is None:
            return False
        try:
            self._pyaudio_instance = pa.PyAudio()
            info = self._pyaudio_instance.get_device_info_by_index(pa_index)
            channels = int(info.get("maxInputChannels", 1)) or 1
            rate = int(info.get("defaultSampleRate", self.sample_rate))

            self._stream = self._pyaudio_instance.open(
                format=pa.paFloat32,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=pa_index,
                frames_per_buffer=self.chunk_size,
                stream_callback=self._pyaudio_callback,
            )
            self.sample_rate = rate
            self._stream.start_stream()
            self._running = True
            self._device_name = info.get("name", f"pyaudio:{pa_index}")
            self._capture_method = "pyaudio_loopback"
            logger.info(f"Audio capture started on pyaudiowpatch: {self._device_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to start pyaudiowpatch capture: {e}")
            if self._pyaudio_instance:
                try:
                    self._pyaudio_instance.terminate()
                except Exception:
                    pass
                self._pyaudio_instance = None
            self._stream = None
            return False

    # ------------------------------------------------------------------
    # Start / stop
    # ------------------------------------------------------------------
    def start(self, device_index: Optional[int] = None, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Start capture with explicit device index or platform-aware auto-fallback.

        Once started, a watchdog keeps it running: if the device disappears or
        stops delivering audio, capture is torn down and restarted on the same
        selection until `stop()` is called.
        """
        if self._running:
            logger.warning("Audio capture already running")
            return True

        self._loop = loop
        if not self._start_backend(device_index):
            return False
        self._wanted = True
        self._selection = device_index
        self._last_chunk_t = time.monotonic()
        self._reconnecting = False
        self._reconnect_attempts = 0
        if self._watchdog is None or not self._watchdog.is_alive():
            self._watchdog_stop.clear()
            self._watchdog = threading.Thread(target=self._watchdog_loop, daemon=True)
            self._watchdog.start()
        return True

    # Seconds without a single block (silence still delivers blocks) before the
    # device counts as gone, how often the watchdog looks, and the longest wait
    # between reconnect attempts.
    STALL_S = 5.0
    WATCH_S = 1.0
    MAX_BACKOFF_S = 30.0

    def _watchdog_loop(self):
        """Restart capture whenever it dies or goes quiet without being stopped.

        A venue install runs unattended: an unplugged interface, a driver reset
        or a sleeping USB hub used to end audio for the night, because the
        capture thread exits on the first error and nothing restarts it.
        """
        while not self._watchdog_stop.wait(self.WATCH_S):
            if not self._wanted:
                return
            last = self._last_chunk_t
            stalled = (not self._running) or last is None or (time.monotonic() - last) > self.STALL_S
            if not stalled:
                continue
            if not self._reconnecting:
                logger.warning("Audio capture lost (%s); reconnecting", self._device_name)
            self._reconnecting = True
            self._teardown()
            if not self._wanted:
                return
            try:
                ok = self._start_backend(self._reconnect_target())
            except Exception as e:
                logger.debug(f"Audio reconnect attempt failed: {e}")
                ok = False
            if ok:
                logger.info("Audio capture reconnected: %s", self._device_name)
                self._last_chunk_t = time.monotonic()
                self._reconnecting = False
                self._reconnect_attempts = 0
                continue
            self._reconnect_attempts += 1
            wait = min(self.MAX_BACKOFF_S, 2.0 ** min(self._reconnect_attempts, 5))
            if self._watchdog_stop.wait(wait):
                return

    def _reconnect_target(self) -> Optional[int]:
        """The device to reconnect to: the same one, even if its index moved.

        Indices shift when a USB device is replugged, so an explicit selection
        is found again by name. Auto mode reconnects through the auto chain.
        """
        if self._selection is None:
            return None
        try:
            devices = self.list_devices()
        except Exception:
            return self._selection
        name = self._device_name.replace("[Loopback] ", "")
        if any(d.get("index") == self._selection and name in str(d.get("name", "")) for d in devices):
            return self._selection
        for d in devices:
            if name and name in str(d.get("name", "")):
                return d.get("index")
        return self._selection

    def _start_backend(self, device_index: Optional[int] = None) -> bool:
        """Open one capture backend; no watchdog."""

        # --- Explicit device selection ---
        if device_index is not None:
            devices = self.list_devices()
            selected = next((d for d in devices if d["index"] == device_index), None)
            if selected is None:
                logger.error(f"Device index {device_index} not found")
                return False

            self._device_index = device_index
            dtype = selected.get("device_type")
            if dtype == "soundcard_speaker":
                return self._start_soundcard_loopback(selected.get("speaker_id"))
            if dtype == "sounddevice":
                sd_index = selected.get("sd_index")
                if sd_index is None:
                    logger.error("Selected sounddevice entry is missing sd_index")
                    return False
                return self._start_sounddevice(int(sd_index))
            if dtype == "pyaudio_loopback":
                pa_index = selected.get("pa_index")
                if pa_index is None:
                    logger.error("Selected pyaudio entry is missing pa_index")
                    return False
                return self._start_pyaudio_loopback(int(pa_index))
            logger.error(f"Unsupported device type: {dtype}")
            return False

        # --- Auto mode: platform-aware fallback chain ---
        if PLATFORM == "darwin":
            # macOS: soundcard (CoreAudio loopback) → sounddevice
            if self._start_soundcard_loopback():
                return True
            sd_index = self._find_sounddevice_input()
            if sd_index is not None and self._start_sounddevice(sd_index):
                return True

        elif PLATFORM == "win32":
            # Windows: pyaudiowpatch (WASAPI) → sounddevice (Stereo Mix) → soundcard
            devices = self.list_devices()
            pyaudio_entry = next((d for d in devices if d.get("device_type") == "pyaudio_loopback"), None)
            if pyaudio_entry and self._start_pyaudio_loopback(int(pyaudio_entry["pa_index"])):
                return True
            sd_index = self._find_sounddevice_input()
            if sd_index is not None and self._start_sounddevice(sd_index):
                return True
            if self._start_soundcard_loopback():
                return True

        else:
            # Linux: sounddevice (PulseAudio monitor) → soundcard
            sd_index = self._find_sounddevice_input()
            if sd_index is not None and self._start_sounddevice(sd_index):
                return True
            if self._start_soundcard_loopback():
                return True

        logger.error("No suitable audio capture backend/device found")
        return False

    def stop(self):
        """Stop capture on purpose. The watchdog stops too."""
        self._wanted = False
        self._reconnecting = False
        self._watchdog_stop.set()
        self._teardown()
        if (
            self._watchdog is not None
            and self._watchdog.is_alive()
            and self._watchdog is not threading.current_thread()
        ):
            self._watchdog.join(timeout=2.0)
        self._watchdog = None
        logger.info("Audio capture stopped")

    def _teardown(self):
        """Release the backend; leaves the watchdog's intent alone."""
        self._running = False

        if self._stream is not None:
            try:
                if hasattr(self._stream, "stop_stream"):
                    self._stream.stop_stream()
                else:
                    self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if self._pyaudio_instance is not None:
            try:
                self._pyaudio_instance.terminate()
            except Exception:
                pass
            self._pyaudio_instance = None

        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)
        self._thread = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def device_name(self) -> str:
        return self._device_name

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "device_index": self._device_index,
            "device_name": self._device_name,
            "capture_method": self._capture_method,
            "sample_rate": self.sample_rate,
            "chunk_size": self.chunk_size,
            "channels": self.channels,
            "platform": PLATFORM,
            "soundcard_available": _get_soundcard() is not None,
            "sounddevice_available": _get_sounddevice() is not None,
            "pyaudiowpatch_available": _get_pyaudio() is not None,
            "chunk_count": self._chunk_count,
            "reconnecting": self._reconnecting,
            "reconnect_attempts": self._reconnect_attempts,
            "last_rms": self._last_rms,
            "last_peak": self._last_peak,
        }


def _enumerate_via_subprocess():
    """Device list assembled from one child process per backend.

    One child per backend rather than one for all of them: a driver that never
    returns then costs only its own devices, and the backends that do work still
    report. Enumerating all three in a single child means one wedged driver hides
    every device on the machine.

    Returns None only if no backend produced anything at all.
    """
    import json
    import subprocess

    root = str(Path(__file__).resolve().parents[3])
    merged = []
    any_ok = False

    for backend in ("pyaudiowpatch", "sounddevice", "soundcard"):
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "app.services.audio.system_audio_capture",
                 "--list-json", backend],
                cwd=root, capture_output=True, timeout=DEVICE_SCAN_TIMEOUT_S, text=True,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "Audio backend %r did not return from enumeration within %.0fs and was "
                "killed; its devices are unavailable", backend, DEVICE_SCAN_TIMEOUT_S
            )
            continue
        except Exception as e:
            logger.warning("Could not scan audio backend %r: %s", backend, e)
            continue

        if proc.returncode != 0:
            logger.warning(
                "Audio backend %r aborted the scan (exit %s); its devices are "
                "unavailable", backend, proc.returncode
            )
            continue

        payload = None
        for line in (proc.stdout or "").splitlines():
            if line.startswith("DEVICES_JSON:"):
                try:
                    payload = json.loads(line[len("DEVICES_JSON:"):])
                except ValueError as e:
                    logger.warning("Audio backend %r returned unreadable output: %s", backend, e)
                break

        if payload is None:
            continue
        any_ok = True
        merged.extend(payload)

    if not any_ok:
        return None

    # Indices are handed back to the UI as the device selector, so they have to be
    # dense and stable for this list rather than carrying each child's numbering.
    for i, dev in enumerate(merged):
        dev["index"] = i
    return merged


if __name__ == "__main__":
    # Child entry point for list_devices(). Enumerates exactly one backend and
    # prints a single JSON line, so whatever the audio libraries write to stdout on
    # import cannot be mistaken for the payload.
    import json as _json

    if "--list-json" in sys.argv:
        logging.disable(logging.CRITICAL)
        _pos = sys.argv.index("--list-json")
        _only = sys.argv[_pos + 1] if len(sys.argv) > _pos + 1 else None
        _all = {"soundcard", "sounddevice", "pyaudiowpatch"}
        _skip = frozenset(_all - {_only}) if _only in _all else frozenset()
        print("DEVICES_JSON:" + _json.dumps(SystemAudioCapture._enumerate_devices(skip=_skip)),
              flush=True)
