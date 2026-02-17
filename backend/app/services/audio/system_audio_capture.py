"""
System Audio Capture (WASAPI Loopback)
======================================

Captures audio from system output with explicit device selection support.
Backends (in priority order for auto mode):
1) soundcard WASAPI loopback
2) sounddevice input/loopback devices
3) pyaudiowpatch WASAPI loopback devices
"""

import asyncio
import logging
import threading
from typing import Optional, Callable

import numpy as np

logger = logging.getLogger(__name__)

# Lazy imports
_sc = None  # soundcard
_sd = None  # sounddevice
_pa = None  # pyaudiowpatch
ENABLE_SOUNDCARD_BACKEND = False


def _get_soundcard():
    if not ENABLE_SOUNDCARD_BACKEND:
        return None
    global _sc
    if _sc is None:
        try:
            import soundcard as sc
            _sc = sc
        except ImportError:
            _sc = False
    return _sc if _sc is not False else None


def _get_sounddevice():
    global _sd
    if _sd is None:
        try:
            import sounddevice as sd
            _sd = sd
        except ImportError:
            _sd = False
    return _sd if _sd is not False else None


def _get_pyaudio():
    global _pa
    if _pa is None:
        try:
            import pyaudiowpatch as pyaudio
            _pa = pyaudio
        except ImportError:
            _pa = False
    return _pa if _pa is not False else None


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

    @staticmethod
    def list_devices() -> list:
        """Return unified device list with stable API indices for this process."""
        result = []
        api_index = 0

        sc = _get_soundcard()
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
                            "hostapi": "WASAPI Loopback (soundcard)",
                            "is_loopback": True,
                            "device_type": "soundcard_speaker",
                            "speaker_id": speaker.id,
                        }
                    )
                    api_index += 1
            except Exception as e:
                logger.debug(f"Error listing soundcard devices: {e}")

        sd = _get_sounddevice()
        if sd is not None:
            try:
                devices = sd.query_devices()
                for i, dev in enumerate(devices):
                    hostapi_name = sd.query_hostapis(dev["hostapi"])["name"]
                    name_lower = dev["name"].lower()
                    is_loopback = (
                        "loopback" in name_lower
                        or "stereo mix" in name_lower
                        or "what u hear" in name_lower
                        or "wave out" in name_lower
                    )
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
                        }
                    )
                    api_index += 1
            except Exception as e:
                logger.debug(f"Error listing sounddevice devices: {e}")

        pa = _get_pyaudio()
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
                            }
                        )
                        api_index += 1
            except Exception as e:
                logger.debug(f"Error listing pyaudiowpatch devices: {e}")
            finally:
                p.terminate()

        return result

    def _dispatch_chunk(self, audio_data: np.ndarray):
        if not self.on_audio_chunk or not self._running:
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

    def _find_sounddevice_input(self) -> Optional[int]:
        sd = _get_sounddevice()
        if sd is None:
            return None
        devices = sd.query_devices()

        for i, dev in enumerate(devices):
            name_lower = dev["name"].lower()
            if dev["max_input_channels"] > 0 and (
                "loopback" in name_lower
                or "stereo mix" in name_lower
                or "what u hear" in name_lower
                or "wave out" in name_lower
            ):
                return i

        try:
            default_input = sd.default.device[0]
            if default_input is not None and default_input >= 0:
                dev = devices[default_input]
                if dev["max_input_channels"] > 0:
                    return default_input
        except Exception:
            pass

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

    def start(self, device_index: Optional[int] = None, loop: Optional[asyncio.AbstractEventLoop] = None):
        """Start capture with explicit device index or backend auto-fallback."""
        if self._running:
            logger.warning("Audio capture already running")
            return True

        self._loop = loop

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

        # Auto mode (used only if explicitly desired in backend config)
        if self._start_soundcard_loopback():
            return True

        sd_index = self._find_sounddevice_input()
        if sd_index is not None and self._start_sounddevice(sd_index):
            return True

        devices = self.list_devices()
        pyaudio_entry = next((d for d in devices if d.get("device_type") == "pyaudio_loopback"), None)
        if pyaudio_entry and self._start_pyaudio_loopback(int(pyaudio_entry["pa_index"])):
            return True

        logger.error("No suitable audio capture backend/device found")
        return False

    def stop(self):
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

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

        logger.info("Audio capture stopped")

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
            "soundcard_available": _get_soundcard() is not None,
            "sounddevice_available": _get_sounddevice() is not None,
            "pyaudiowpatch_available": _get_pyaudio() is not None,
            "chunk_count": self._chunk_count,
            "last_rms": self._last_rms,
            "last_peak": self._last_peak,
        }
