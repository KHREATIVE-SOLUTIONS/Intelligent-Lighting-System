"""
MERT-v1-95M Music Emotion Recognition
======================================

Replaces HuBERT (speech emotion model) with MERT (music-native model).
MERT is pre-trained on 160K hours of music, producing embeddings that
capture tonal, rhythmic, and timbral information.

Output: EmotionVector with 7 lighting-relevant dimensions.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from pathlib import Path
from collections import deque
import logging
import time

logger = logging.getLogger(__name__)


@dataclass
class EmotionVector:
    """Multi-dimensional emotion output mapped to lighting parameters.

    Each dimension maps to a specific lighting control:
        valence      -> color temperature (cool blues for negative, warm oranges for positive)
        arousal      -> intensity/speed of changes
        dominance    -> fixture coverage (narrow spot vs full wash)
        tension      -> color saturation, movement irregularity, strobe likelihood
        energy_trajectory -> movement complexity ramp-up/down (building/sustaining/falling)
        groove       -> beat-sync strength, dimmer pulse depth
        darkness     -> dimmer base level, palette saturation (aesthetic darkness)
    """
    valence: float = 0.0            # -1 (sad/dark) to +1 (happy/bright)
    arousal: float = 0.0            # -1 (calm) to +1 (excited/energetic)
    dominance: float = 0.0          # -1 (submissive/sparse) to +1 (dominant/full)
    tension: float = 0.0            # 0 (relaxed) to 1 (tense/anxious)
    energy_trajectory: float = 0.0  # -1 (falling) to +1 (building)
    groove: float = 0.0             # 0 (static/rigid) to 1 (highly groovy)
    darkness: float = 0.0           # 0 (light/bright aesthetic) to 1 (dark/heavy aesthetic)
    confidence: float = 0.0         # 0 to 1, overall confidence in prediction
    timestamp: float = 0.0


@dataclass
class LightingEmotionMapping:
    """Maps EmotionVector to concrete lighting parameters."""
    color_temp_k: float = 5600.0     # Color temperature in Kelvin (2700-8000)
    base_intensity: float = 0.5      # 0-1
    movement_speed: float = 0.5      # 0-1
    strobe_probability: float = 0.0  # 0-1, likelihood of strobe being appropriate
    chase_complexity: float = 0.3    # 0-1
    color_saturation: float = 0.7    # 0-1
    palette_warmth: float = 0.5      # 0 (cool blues/greens) to 1 (warm reds/oranges)
    coverage: float = 0.5           # 0 (narrow spot) to 1 (full wash)
    pulse_depth: float = 0.3        # 0-1, how much to pulse on beat


class MERTModel:
    """MERT-v1-95M music emotion recognition model.

    Loads MERT encoder and a fine-tuned regression head for
    multi-dimensional emotion prediction. Uses ONNX Runtime
    with GPU->CPU fallback chain.
    """

    # Sliding window parameters
    WINDOW_SIZE_SEC = 5.0       # 5-second analysis windows
    HOP_SIZE_SEC = 0.5          # 2 Hz output rate (every 500ms)
    SAMPLE_RATE = 16000         # MERT expects 16kHz input
    HISTORY_SIZE = 30           # Keep 15 seconds of emotion history

    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = Path(model_dir) if model_dir else None
        self.model = None
        self.processor = None
        self.emotion_head = None
        self.onnx_session = None
        self.device = "cpu"
        self.loaded = False

        # Sliding window state
        self._audio_buffer = np.zeros(
            int(self.WINDOW_SIZE_SEC * self.SAMPLE_RATE), dtype=np.float32
        )
        self._buffer_pos = 0
        self._emotion_history: deque = deque(maxlen=self.HISTORY_SIZE)
        self._last_inference_time = 0.0

    async def load(self, model_dir: Optional[str] = None) -> bool:
        """Load MERT model with GPU->CPU fallback chain.

        Tries in order:
        1. ONNX Runtime with CUDA EP (fastest)
        2. ONNX Runtime with CPU EP
        3. PyTorch with CUDA
        4. PyTorch with CPU
        """
        if model_dir:
            self.model_dir = Path(model_dir)

        if not self.model_dir or not self.model_dir.exists():
            logger.warning("MERT model directory not found at %s", self.model_dir)
            return False

        # Try ONNX first
        onnx_path = self.model_dir / "mert_emotion.onnx"
        if onnx_path.exists():
            if await self._load_onnx(onnx_path):
                return True

        # Fall back to PyTorch
        return await self._load_pytorch()

    async def _load_onnx(self, onnx_path: Path) -> bool:
        """Load ONNX model with automatic execution provider selection."""
        try:
            import onnxruntime as ort

            # Try GPU first, fall back to CPU
            providers = []
            available = ort.get_available_providers()
            if "TensorrtExecutionProvider" in available:
                providers.append("TensorrtExecutionProvider")
            if "CUDAExecutionProvider" in available:
                providers.append("CUDAExecutionProvider")
            providers.append("CPUExecutionProvider")

            self.onnx_session = ort.InferenceSession(
                str(onnx_path), providers=providers
            )
            active_provider = self.onnx_session.get_providers()[0]
            self.device = "cuda" if "CUDA" in active_provider or "Tensorrt" in active_provider else "cpu"
            self.loaded = True
            logger.info("MERT ONNX model loaded with %s", active_provider)
            return True
        except Exception as e:
            logger.warning("ONNX loading failed: %s", e)
            return False

    async def _load_pytorch(self) -> bool:
        """Load PyTorch MERT model from HuggingFace format."""
        try:
            from transformers import AutoModel, AutoFeatureExtractor
            import torch

            self.processor = AutoFeatureExtractor.from_pretrained(
                str(self.model_dir), trust_remote_code=True
            )
            self.model = AutoModel.from_pretrained(
                str(self.model_dir), trust_remote_code=True
            )
            self.model.eval()

            # Load emotion regression head if available
            head_path = self.model_dir / "emotion_head.pt"
            if head_path.exists():
                self.emotion_head = torch.load(
                    str(head_path), map_location="cpu", weights_only=True
                )
                self.emotion_head.eval()

            # Move to GPU if available
            if torch.cuda.is_available():
                self.model = self.model.cuda().half()
                if self.emotion_head:
                    self.emotion_head = self.emotion_head.cuda().half()
                self.device = "cuda"
                logger.info("MERT PyTorch model loaded on GPU")
            else:
                self.device = "cpu"
                logger.info("MERT PyTorch model loaded on CPU")

            self.loaded = True
            return True
        except ImportError:
            logger.warning("transformers package not installed for MERT")
            return False
        except Exception as e:
            logger.warning("MERT PyTorch loading error: %s", e)
            return False

    def feed_audio(self, audio_data: np.ndarray, sample_rate: int = 44100):
        """Feed audio data into the sliding window buffer.

        Args:
            audio_data: Audio samples as float32 array (-1.0 to 1.0)
            sample_rate: Sample rate of input audio
        """
        # Resample to 16kHz if needed
        if sample_rate != self.SAMPLE_RATE:
            ratio = self.SAMPLE_RATE / sample_rate
            target_len = int(len(audio_data) * ratio)
            if target_len > 0:
                indices = np.linspace(0, len(audio_data) - 1, target_len).astype(int)
                audio_data = audio_data[indices]

        # Append to circular buffer
        n = len(audio_data)
        buf_len = len(self._audio_buffer)

        if n >= buf_len:
            # Data fills entire buffer
            self._audio_buffer[:] = audio_data[-buf_len:]
            self._buffer_pos = buf_len
        elif self._buffer_pos + n <= buf_len:
            self._audio_buffer[self._buffer_pos:self._buffer_pos + n] = audio_data
            self._buffer_pos += n
        else:
            # Shift buffer left to make room
            remaining = buf_len - self._buffer_pos
            self._audio_buffer[self._buffer_pos:] = audio_data[:remaining]
            overflow = n - remaining
            self._audio_buffer[:overflow] = audio_data[remaining:]
            self._buffer_pos = overflow

    async def get_emotion(self) -> EmotionVector:
        """Get current emotion vector from the audio buffer.

        Runs inference at 2Hz (every 500ms). Returns cached result
        if called more frequently.
        """
        current_time = time.time()

        # Rate limit to 2Hz
        if current_time - self._last_inference_time < self.HOP_SIZE_SEC:
            if self._emotion_history:
                return self._emotion_history[-1]
            return EmotionVector()

        self._last_inference_time = current_time

        if not self.loaded:
            return self._fallback_emotion()

        try:
            if self.onnx_session:
                emotion = await self._infer_onnx()
            elif self.model:
                emotion = await self._infer_pytorch()
            else:
                emotion = self._fallback_emotion()
        except Exception as e:
            logger.warning("MERT inference error: %s", e)
            emotion = self._fallback_emotion()

        emotion.timestamp = current_time
        self._emotion_history.append(emotion)
        return emotion

    async def _infer_onnx(self) -> EmotionVector:
        """Run ONNX Runtime inference."""
        audio_window = self._get_audio_window()
        input_data = audio_window.reshape(1, -1).astype(np.float32)

        outputs = self.onnx_session.run(
            None, {"audio_input": input_data}
        )
        return self._parse_model_output(outputs[0][0])

    async def _infer_pytorch(self) -> EmotionVector:
        """Run PyTorch inference."""
        import torch

        audio_window = self._get_audio_window()

        # Process through MERT feature extractor
        inputs = self.processor(
            audio_window,
            sampling_rate=self.SAMPLE_RATE,
            return_tensors="pt",
            padding=True,
        )

        device = next(self.model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)
            # Use last hidden state, take mean across time
            hidden = outputs.last_hidden_state.mean(dim=1)  # (1, hidden_dim)

            if self.emotion_head:
                emotion_values = self.emotion_head(hidden)
                return self._parse_model_output(
                    emotion_values.cpu().numpy()[0]
                )
            else:
                # Without fine-tuned head, derive from embeddings heuristically
                return self._derive_emotion_from_embeddings(
                    hidden.cpu().numpy()[0]
                )

    def _get_audio_window(self) -> np.ndarray:
        """Get the current analysis window from the circular buffer."""
        return self._audio_buffer.copy()

    def _parse_model_output(self, values: np.ndarray) -> EmotionVector:
        """Parse raw model output into EmotionVector.

        Expects 7 values: [valence, arousal, dominance, tension,
                           energy_trajectory, groove, darkness]
        """
        n = len(values)
        return EmotionVector(
            valence=float(np.clip(values[0], -1, 1)) if n > 0 else 0.0,
            arousal=float(np.clip(values[1], -1, 1)) if n > 1 else 0.0,
            dominance=float(np.clip(values[2], -1, 1)) if n > 2 else 0.0,
            tension=float(np.clip(values[3], 0, 1)) if n > 3 else 0.0,
            energy_trajectory=float(np.clip(values[4], -1, 1)) if n > 4 else 0.0,
            groove=float(np.clip(values[5], 0, 1)) if n > 5 else 0.0,
            darkness=float(np.clip(values[6], 0, 1)) if n > 6 else 0.0,
            confidence=0.85,
        )

    def _derive_emotion_from_embeddings(
        self, embeddings: np.ndarray
    ) -> EmotionVector:
        """Derive emotion dimensions from raw MERT embeddings.

        Uses projection of embedding dimensions to approximate
        emotion axes. This is a heuristic fallback when no
        fine-tuned regression head is available.
        """
        # Use spectral characteristics of the audio buffer for heuristic
        audio = self._get_audio_window()
        spectrum = np.abs(np.fft.rfft(audio))
        freqs = np.fft.rfftfreq(len(audio), 1.0 / self.SAMPLE_RATE)

        total_energy = np.sum(spectrum ** 2) + 1e-10
        low_energy = np.sum(spectrum[freqs < 250] ** 2)
        mid_energy = np.sum(spectrum[(freqs >= 250) & (freqs < 2000)] ** 2)
        high_energy = np.sum(spectrum[freqs >= 2000] ** 2)

        rms = float(np.sqrt(np.mean(audio ** 2)))
        spectral_centroid = float(np.sum(freqs * spectrum) / (np.sum(spectrum) + 1e-10))

        # Embedding norm as proxy for overall audio activity
        embed_norm = float(np.linalg.norm(embeddings[:64]))
        embed_mean = float(np.mean(embeddings[:64]))

        # Heuristic mappings
        arousal = float(np.clip(rms * 5 - 0.5, -1, 1))
        valence = float(np.clip(
            (high_energy / total_energy - low_energy / total_energy) * 4 + embed_mean * 0.1,
            -1, 1
        ))
        dominance = float(np.clip(rms * 3 - 0.3, -1, 1))
        tension = float(np.clip(spectral_centroid / 4000 - 0.2, 0, 1))

        # Energy trajectory from recent history
        energy_trajectory = 0.0
        if len(self._emotion_history) >= 3:
            recent = [e.arousal for e in list(self._emotion_history)[-3:]]
            energy_trajectory = float(np.clip((recent[-1] - recent[0]) * 2, -1, 1))

        groove = float(np.clip(low_energy / total_energy * 3, 0, 1))
        darkness = float(np.clip(1.0 - valence * 0.5 - arousal * 0.3, 0, 1))

        return EmotionVector(
            valence=valence,
            arousal=arousal,
            dominance=dominance,
            tension=tension,
            energy_trajectory=energy_trajectory,
            groove=groove,
            darkness=darkness,
            confidence=0.4,  # Lower confidence for heuristic
        )

    def _fallback_emotion(self) -> EmotionVector:
        """Energy-based emotion estimation when no model is available.

        Uses spectral analysis of the audio buffer as a last resort.
        """
        audio = self._get_audio_window()
        if np.max(np.abs(audio)) < 1e-6:
            return EmotionVector(confidence=0.1)

        rms = float(np.sqrt(np.mean(audio ** 2)))
        spectrum = np.abs(np.fft.rfft(audio))
        freqs = np.fft.rfftfreq(len(audio), 1.0 / self.SAMPLE_RATE)

        total_energy = float(np.sum(spectrum ** 2)) + 1e-10
        low_ratio = float(np.sum(spectrum[freqs < 250] ** 2)) / total_energy
        high_ratio = float(np.sum(spectrum[freqs > 2000] ** 2)) / total_energy
        spectral_centroid = float(np.sum(freqs * spectrum) / (np.sum(spectrum) + 1e-10))

        # Zero-crossing rate for "noisiness"
        zcr = float(np.mean(np.abs(np.diff(np.sign(audio)))) / 2)

        arousal = float(np.clip(rms * 6 - 0.5, -1, 1))
        valence = float(np.clip((high_ratio - low_ratio) * 3, -1, 1))
        tension = float(np.clip(zcr * 2 + spectral_centroid / 5000 - 0.3, 0, 1))
        groove = float(np.clip(low_ratio * 2.5, 0, 1))
        darkness = float(np.clip(low_ratio * 1.5 + (1 - high_ratio) * 0.3, 0, 1))

        return EmotionVector(
            valence=valence,
            arousal=arousal,
            dominance=float(np.clip(rms * 3, -1, 1)),
            tension=tension,
            energy_trajectory=0.0,
            groove=groove,
            darkness=darkness,
            confidence=0.2,
        )

    def map_to_lighting(self, emotion: EmotionVector) -> LightingEmotionMapping:
        """Map emotion vector to concrete lighting parameters.

        This is the core emotion-to-lighting translation:
            valence      -> color_temp, palette_warmth
            arousal      -> base_intensity, movement_speed
            dominance    -> coverage
            tension      -> strobe_probability, color_saturation
            groove       -> pulse_depth, chase_complexity
            darkness     -> base_intensity reduction
            energy_trajectory -> movement_speed modifier
        """
        # Color temperature: sad/dark -> cool (3000K), happy -> warm (7000K)
        color_temp = 5000 + emotion.valence * 2000

        # Palette warmth follows valence
        palette_warmth = (emotion.valence + 1) / 2  # Map [-1,1] -> [0,1]

        # Base intensity: arousal drives it, darkness pulls it down
        base_intensity = 0.3 + emotion.arousal * 0.35 + (1 - emotion.darkness) * 0.2
        base_intensity = max(0.05, min(1.0, base_intensity))

        # Movement speed: arousal + energy trajectory
        movement_speed = (emotion.arousal + 1) / 2 * 0.7 + max(0, emotion.energy_trajectory) * 0.3
        movement_speed = max(0.0, min(1.0, movement_speed))

        # Strobe probability: tension-driven
        strobe_prob = emotion.tension * 0.6 + max(0, emotion.arousal - 0.3) * 0.4
        strobe_prob = max(0.0, min(1.0, strobe_prob))

        # Chase complexity: groove-driven
        chase_complexity = emotion.groove * 0.6 + (emotion.arousal + 1) / 2 * 0.4
        chase_complexity = max(0.0, min(1.0, chase_complexity))

        # Color saturation: tension increases, calm decreases
        saturation = 0.5 + emotion.tension * 0.3 + emotion.darkness * 0.2
        saturation = max(0.2, min(1.0, saturation))

        # Coverage: dominance maps directly
        coverage = (emotion.dominance + 1) / 2
        coverage = max(0.1, min(1.0, coverage))

        # Pulse depth: groove drives beat-sync visibility
        pulse_depth = emotion.groove * 0.7 + max(0, emotion.arousal) * 0.3
        pulse_depth = max(0.0, min(1.0, pulse_depth))

        return LightingEmotionMapping(
            color_temp_k=color_temp,
            base_intensity=base_intensity,
            movement_speed=movement_speed,
            strobe_probability=strobe_prob,
            chase_complexity=chase_complexity,
            color_saturation=saturation,
            palette_warmth=palette_warmth,
            coverage=coverage,
            pulse_depth=pulse_depth,
        )

    def get_smoothed_emotion(self, window: int = 5) -> EmotionVector:
        """Get temporally smoothed emotion over recent history.

        Args:
            window: Number of recent frames to average
        """
        if not self._emotion_history:
            return EmotionVector()

        recent = list(self._emotion_history)[-window:]
        n = len(recent)
        return EmotionVector(
            valence=sum(e.valence for e in recent) / n,
            arousal=sum(e.arousal for e in recent) / n,
            dominance=sum(e.dominance for e in recent) / n,
            tension=sum(e.tension for e in recent) / n,
            energy_trajectory=sum(e.energy_trajectory for e in recent) / n,
            groove=sum(e.groove for e in recent) / n,
            darkness=sum(e.darkness for e in recent) / n,
            confidence=sum(e.confidence for e in recent) / n,
            timestamp=recent[-1].timestamp,
        )

    def get_info(self) -> Dict[str, Any]:
        """Get model status information."""
        return {
            "loaded": self.loaded,
            "device": self.device,
            "backend": "onnx" if self.onnx_session else ("pytorch" if self.model else "none"),
            "has_emotion_head": self.emotion_head is not None,
            "history_length": len(self._emotion_history),
            "model_dir": str(self.model_dir) if self.model_dir else None,
        }
