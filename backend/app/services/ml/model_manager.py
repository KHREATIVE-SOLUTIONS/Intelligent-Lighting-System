"""
ML Model Manager
================

Manages loading and inference for ML models (BeatNet, HuBERT, YOLOv9).
"""

import asyncio
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional

from app.core.config import settings


class ModelManager:
    """Manages ML model loading and inference."""

    def __init__(self):
        """Initialize the model manager."""
        self.models: Dict[str, Any] = {}
        self.processors: Dict[str, Any] = {}
        self.model_paths = {
            'beatnet': settings.BEATNET_MODEL_PATH,
            'hubert': settings.HUBERT_MODEL_PATH,
            'yolo': settings.YOLO_MODEL_PATH,
        }
        self.loaded = False

    async def load_models(self):
        """Load all ML models."""
        # Load models in background to not block startup
        asyncio.create_task(self._load_models_async())

    async def _load_models_async(self):
        """Asynchronously load ML models."""
        try:
            await self._load_beatnet()
        except Exception as e:
            print(f"Warning: Could not load BeatNet model: {e}")

        try:
            await self._load_hubert()
        except Exception as e:
            print(f"Warning: Could not load HuBERT model: {e}")

        try:
            await self._load_yolo()
        except Exception as e:
            print(f"Warning: Could not load YOLOv9 model: {e}")

        self.loaded = True
        print(f"Model loading complete. Loaded models: {list(self.models.keys())}")

    async def _load_beatnet(self):
        """Load BeatNet model for beat detection."""
        try:
            from BeatNet.BeatNet import BeatNet

            # Initialize BeatNet with online mode for real-time analysis
            # mode: 'online' for real-time, 'offline' for file analysis
            # inference_model: 'DBN' (Dynamic Bayesian Network) or 'PF' (Particle Filter)
            self.models['beatnet'] = BeatNet(
                1,  # Model number (1 is the default)
                mode='online',
                inference_model='DBN',
                plot=[],  # Disable plotting
                thread=False
            )
            print("BeatNet model loaded successfully")

        except ImportError:
            print("BeatNet package not installed. Run: pip install BeatNet")
        except Exception as e:
            print(f"BeatNet initialization error: {e}")

    async def _load_hubert(self):
        """Load HuBERT/Wav2Vec2 model for emotion classification."""
        model_dir = Path(self.model_paths['hubert']).parent

        if not model_dir.exists():
            print(f"HuBERT model directory not found at {model_dir}")
            return

        try:
            from transformers import (
                AutoFeatureExtractor,
                AutoModelForAudioClassification
            )
            import torch

            # Load the emotion recognition model
            print(f"Loading emotion model from {model_dir}...")

            self.processors['hubert'] = AutoFeatureExtractor.from_pretrained(str(model_dir))
            self.models['hubert'] = AutoModelForAudioClassification.from_pretrained(str(model_dir))

            # Move to GPU if available
            if torch.cuda.is_available():
                self.models['hubert'] = self.models['hubert'].cuda()
                print("HuBERT model loaded on GPU")
            else:
                print("HuBERT model loaded on CPU")

        except ImportError:
            print("Transformers not installed. Run: pip install transformers")
        except Exception as e:
            print(f"HuBERT loading error: {e}")

    async def _load_yolo(self):
        """Load YOLOv9 model for fixture detection."""
        model_path = Path(self.model_paths['yolo'])

        # Check for model.pt in the yolov9 directory
        if not model_path.exists():
            model_dir = model_path.parent
            alt_path = model_dir / "model.pt"
            if alt_path.exists():
                model_path = alt_path
            else:
                print(f"YOLOv9 model not found at {model_path}")
                return

        try:
            from ultralytics import YOLO

            print(f"Loading YOLOv9 model from {model_path}...")
            self.models['yolo'] = YOLO(str(model_path))
            print("YOLOv9 model loaded successfully")

        except ImportError:
            print("Ultralytics not installed. Run: pip install ultralytics")
        except Exception as e:
            print(f"YOLOv9 loading error: {e}")

    def has_model(self, model_name: str) -> bool:
        """Check if a model is loaded."""
        return model_name in self.models

    async def detect_beats(self, audio_data: np.ndarray, sample_rate: int = 22050) -> Dict[str, Any]:
        """
        Detect beats using BeatNet model.

        Args:
            audio_data: Audio samples as float32 array
            sample_rate: Sample rate of the audio

        Returns:
            Dictionary with beat detection results
        """
        if 'beatnet' not in self.models:
            return self._fallback_beat_detection(audio_data, sample_rate)

        try:
            beatnet = self.models['beatnet']

            # Process audio through BeatNet
            # BeatNet expects audio at 22050 Hz
            output = beatnet.process(audio_data)

            # Parse BeatNet output
            beats = []
            downbeats = []

            if output is not None:
                for beat_info in output:
                    beat_time = beat_info[0]
                    beat_type = beat_info[1]  # 1 = beat, 2 = downbeat

                    beats.append(beat_time)
                    if beat_type == 2:
                        downbeats.append(beat_time)

            return {
                'beats': beats,
                'downbeats': downbeats,
                'bpm': self._estimate_bpm(beats),
                'confidence': 0.9 if len(beats) > 0 else 0.0,
            }

        except Exception as e:
            print(f"Beat detection error: {e}")
            return self._fallback_beat_detection(audio_data, sample_rate)

    def _fallback_beat_detection(self, audio_data: np.ndarray, sample_rate: int) -> Dict[str, Any]:
        """Simple onset-based beat detection fallback."""
        try:
            import librosa

            # Use librosa for basic beat tracking
            tempo, beat_frames = librosa.beat.beat_track(y=audio_data, sr=sample_rate)
            beat_times = librosa.frames_to_time(beat_frames, sr=sample_rate)

            return {
                'beats': beat_times.tolist(),
                'downbeats': beat_times[::4].tolist() if len(beat_times) > 0 else [],
                'bpm': float(tempo) if isinstance(tempo, (int, float)) else float(tempo[0]),
                'confidence': 0.7,
            }
        except Exception:
            return {
                'beats': [],
                'downbeats': [],
                'bpm': 0.0,
                'confidence': 0.0,
            }

    def _estimate_bpm(self, beats: list) -> float:
        """Estimate BPM from beat times."""
        if len(beats) < 2:
            return 0.0

        intervals = np.diff(beats)
        if len(intervals) == 0:
            return 0.0

        avg_interval = np.median(intervals)
        if avg_interval > 0:
            return 60.0 / avg_interval
        return 0.0

    async def classify_mood(self, audio_data: np.ndarray, sample_rate: int = 16000) -> Dict[str, Any]:
        """
        Classify mood/emotion using HuBERT/Wav2Vec2 model.

        Args:
            audio_data: Audio samples as float32 array
            sample_rate: Sample rate of the audio (model expects 16000)

        Returns:
            Dictionary with mood classification results
        """
        if 'hubert' not in self.models or 'hubert' not in self.processors:
            return self._fallback_mood_classification(audio_data)

        try:
            import torch
            import librosa

            # Resample to 16kHz if needed
            if sample_rate != 16000:
                audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=16000)

            # Process through feature extractor
            inputs = self.processors['hubert'](
                audio_data,
                sampling_rate=16000,
                return_tensors="pt",
                padding=True
            )

            # Move to GPU if model is on GPU
            device = next(self.models['hubert'].parameters()).device
            inputs = {k: v.to(device) for k, v in inputs.items()}

            # Run inference
            with torch.no_grad():
                outputs = self.models['hubert'](**inputs)
                logits = outputs.logits
                probs = torch.softmax(logits, dim=-1)[0]

            # Get emotion labels from model config if available, otherwise use defaults
            model = self.models['hubert']
            if hasattr(model, 'config') and hasattr(model.config, 'id2label'):
                emotion_labels = [model.config.id2label[i] for i in range(len(probs))]
            else:
                # Fallback labels - wav2vec2-lg-xlsr-en-speech-emotion-recognition
                emotion_labels = ['angry', 'disgust', 'fear', 'happy', 'neutral', 'sad', 'surprise']

            # Build emotions dict safely
            emotions = {}
            for i in range(len(probs)):
                if i < len(emotion_labels):
                    emotions[emotion_labels[i]] = float(probs[i])
                else:
                    emotions[f'emotion_{i}'] = float(probs[i])

            # Calculate valence and arousal from emotions
            valence = self._emotions_to_valence(emotions)
            arousal = self._emotions_to_arousal(emotions)

            # Get dominant emotion safely
            dominant_idx = int(probs.argmax())
            if dominant_idx < len(emotion_labels):
                dominant_emotion = emotion_labels[dominant_idx]
            else:
                dominant_emotion = f'emotion_{dominant_idx}'

            return {
                'valence': valence,
                'arousal': arousal,
                'confidence': float(probs.max()),
                'emotions': emotions,
                'dominant_emotion': dominant_emotion,
            }

        except Exception as e:
            print(f"Mood classification error: {e}")
            return self._fallback_mood_classification(audio_data)

    def _emotions_to_valence(self, emotions: Dict[str, float]) -> float:
        """Convert emotions to valence score (0-1, negative to positive)."""
        # Valence weights: positive emotions increase valence
        weights = {
            'happy': 1.0, 'surprise': 0.5, 'neutral': 0.5,
            'sad': 0.0, 'angry': 0.2, 'fear': 0.2, 'disgust': 0.1
        }

        total = sum(emotions.get(e, 0) * weights.get(e, 0.5) for e in emotions)
        norm = sum(emotions.values()) or 1
        return max(0, min(1, total / norm))

    def _emotions_to_arousal(self, emotions: Dict[str, float]) -> float:
        """Convert emotions to arousal score (0-1, calm to excited)."""
        # Arousal weights: high energy emotions increase arousal
        weights = {
            'angry': 0.9, 'fear': 0.8, 'surprise': 0.7, 'happy': 0.6,
            'disgust': 0.5, 'sad': 0.3, 'neutral': 0.4
        }

        total = sum(emotions.get(e, 0) * weights.get(e, 0.5) for e in emotions)
        norm = sum(emotions.values()) or 1
        return max(0, min(1, total / norm))

    def _fallback_mood_classification(self, audio_data: np.ndarray) -> Dict[str, Any]:
        """Simple energy-based mood estimation fallback."""
        try:
            # Simple RMS energy and zero-crossing rate analysis
            rms = np.sqrt(np.mean(audio_data ** 2))
            zcr = np.mean(np.abs(np.diff(np.sign(audio_data)))) / 2

            # Map to valence/arousal (very rough approximation)
            arousal = min(1.0, rms * 10)  # Higher energy = higher arousal
            valence = 0.5 + (0.5 - zcr) * 0.5  # Rough heuristic

            return {
                'valence': float(valence),
                'arousal': float(arousal),
                'confidence': 0.3,
                'emotions': {},
                'dominant_emotion': 'neutral',
            }
        except Exception:
            return {
                'valence': 0.5,
                'arousal': 0.5,
                'confidence': 0.0,
                'emotions': {},
                'dominant_emotion': 'neutral',
            }

    async def detect_fixtures(self, image: np.ndarray, confidence_threshold: float = 0.5) -> Dict[str, Any]:
        """
        Detect fixtures in an image using YOLOv9.

        Args:
            image: Image as numpy array (H, W, C) in BGR format
            confidence_threshold: Minimum confidence for detections

        Returns:
            Dictionary with detected fixtures
        """
        if 'yolo' not in self.models:
            return {
                'fixtures': [],
                'count': 0,
                'confidence': 0.0,
            }

        try:
            # Run YOLO inference
            results = self.models['yolo'](image, conf=confidence_threshold)

            fixtures = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    fixtures.append({
                        'class_id': int(box.cls[0]),
                        'class_name': result.names[int(box.cls[0])],
                        'confidence': float(box.conf[0]),
                        'bbox': {
                            'x1': float(box.xyxy[0][0]),
                            'y1': float(box.xyxy[0][1]),
                            'x2': float(box.xyxy[0][2]),
                            'y2': float(box.xyxy[0][3]),
                        },
                        'center': {
                            'x': float((box.xyxy[0][0] + box.xyxy[0][2]) / 2),
                            'y': float((box.xyxy[0][1] + box.xyxy[0][3]) / 2),
                        }
                    })

            return {
                'fixtures': fixtures,
                'count': len(fixtures),
                'confidence': np.mean([f['confidence'] for f in fixtures]) if fixtures else 0.0,
            }

        except Exception as e:
            print(f"Fixture detection error: {e}")
            return {
                'fixtures': [],
                'count': 0,
                'confidence': 0.0,
            }

    def get_model_info(self) -> Dict[str, Any]:
        """Get information about loaded models."""
        return {
            'loaded': self.loaded,
            'models': {
                'beatnet': {
                    'loaded': 'beatnet' in self.models,
                    'type': 'Beat Detection',
                    'description': 'Real-time beat and downbeat tracking'
                },
                'hubert': {
                    'loaded': 'hubert' in self.models,
                    'type': 'Emotion Recognition',
                    'description': 'Audio emotion/mood classification'
                },
                'yolo': {
                    'loaded': 'yolo' in self.models,
                    'type': 'Object Detection',
                    'description': 'Fixture detection in images'
                },
            },
            'paths': self.model_paths,
        }
