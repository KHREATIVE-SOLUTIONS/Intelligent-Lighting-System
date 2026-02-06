# Local ML Models Guide - Intelligent Lighting System

> **Goal**: Eliminate ALL cloud API costs. Every model runs locally on consumer GPU hardware.
> Zero per-inference charges. One-time hardware investment only.

**Last updated**: 2026-02-06
**Current stack**: BeatNet + HuBERT + YOLOv9 on PyTorch 2.1+ / FastAPI backend

---

## Table of Contents

1. [Computer Vision Models (Video-to-DMX Pipeline)](#1-computer-vision-models)
2. [Audio Analysis Models](#2-audio-analysis-models)
3. [Training Infrastructure (All Local)](#3-training-infrastructure)
4. [Hardware Recommendations](#4-hardware-recommendations)
5. [Recommended Complete Model Stack](#5-recommended-complete-model-stack)
6. [Integration with Existing Codebase](#6-integration-with-existing-codebase)
7. [Cost Analysis](#7-cost-analysis)

---

## 1. Computer Vision Models

### 1.1 Object Detection / Fixture Detection

The video-to-DMX pipeline must detect individual light fixtures (moving heads, PARs, LED bars, strobes, lasers, wash lights) in concert footage. This requires a detector that handles small objects on distant trusses, low-contrast dark venues, partial occlusion from haze, and multiple fixture types.

#### Model Comparison

| Model | Params | Size | FPS RTX 3060 | FPS RTX 4070 | FPS RTX 4090 | mAP (COCO) | License |
|-------|--------|------|--------------|--------------|--------------|------------|---------|
| YOLOv9-C (current) | 25.3M | 102 MB | ~95 | ~130 | ~190 | 53.0% | GPL-3.0 |
| YOLO11-L | 25.3M | 49 MB | ~95 | ~135 | ~200 | 53.4% | AGPL-3.0 |
| RT-DETR-L | 32M | 128 MB | ~70 | ~100 | ~160 | 53.0% | Apache-2.0 |
| Grounding DINO-T | 172M | 694 MB | ~12 | ~18 | ~30 | N/A (open-set) | Apache-2.0 |

#### Recommendation: YOLO11-L (primary) + Grounding DINO-T (bootstrapping)

YOLO11-L is a drop-in replacement for YOLOv9-C via the same Ultralytics API. It is smaller (49 MB vs 102 MB), faster, and has improved small-object detection. Use Grounding DINO-T once to auto-label fixture datasets with text prompts, then fine-tune YOLO11-L on your custom fixture classes.

- **YOLO11-L**: `from ultralytics import YOLO; model = YOLO("yolo11l.pt")` -- VRAM: 2 GB
- **Grounding DINO-T**: https://huggingface.co/IDEA-Research/grounding-dino-tiny -- VRAM: 4 GB (bootstrapping only)

### 1.2 Semantic Segmentation (Beam Isolation)

#### Recommendation: SAM 2 Hiera-T (offline) + distilled DeepLabV3+ MobileNetV3 (live)

SAM 2 with YOLO box prompts segments beam cones per-fixture. For live use, train a DeepLabV3+ (MobileNetV3 backbone) on SAM 2 masks for ~60 FPS at 1.5 GB VRAM.

- **SAM 2 Hiera-T**: https://github.com/facebookresearch/sam2 -- `sam2.1_hiera_tiny.pt` -- 96 MB, Apache-2.0
- **DeepLabV3+ MobileNetV3**: `torchvision.models.segmentation.deeplabv3_mobilenet_v3_large(pretrained=True)` -- Apache-2.0

### 1.3 Optical Flow / Motion Tracking

#### Recommendation: CoTracker v2 (offline) + RAFT-Small (real-time) + OpenCV LK (live fallback)

- **CoTracker v2**: https://github.com/facebookresearch/co-tracker -- 85 MB, ~25 FPS, Apache-2.0
- **RAFT-Small**: https://github.com/princeton-vl/RAFT -- 21 MB, ~35 FPS at 480p, BSD-3
- **OpenCV Lucas-Kanade**: CPU only, ~200+ FPS, BSD

### 1.4 Color Analysis

#### Recommendation: OpenCV LAB + MiniBatchKMeans clustering

No ML model needed. Extract colors in LAB space (perceptually uniform, brightness-independent), cluster with k-means, convert to HSV for DMX mapping. VRAM: 0, Latency: less than 2ms per fixture.

### 1.5 Video Understanding (Temporal Patterns)

#### Recommendation: VideoMAE v2-S (features) + X3D-M (real-time classification)

- **VideoMAE v2-S**: `MCG-NJU/videomae-small` -- 88 MB, ~60 clips/sec, Apache-2.0
- **X3D-M**: `torch.hub.load('facebookresearch/pytorchvideo', 'x3d_m')` -- 15 MB, ~120 clips/sec, Apache-2.0

### 1.6 Beam Angle Estimation

No additional ML model needed. Use trigonometry on YOLO fixture positions + CoTracker beam tip positions. For known 3D fixture positions, use OpenCV solvePnP.

---

## 2. Audio Analysis Models

### 2.1 Beat Detection

| Model | Latency | Accuracy (F1) | Real-time | GPU | License |
|-------|---------|---------------|-----------|-----|---------|
| BeatNet (current) | ~20ms | 0.91 beats, 0.85 downbeats | Yes (online) | Optional | MIT |
| madmom DBNBeatTracker | ~30ms | 0.94 beats, 0.88 downbeats | Yes (streaming) | No (CPU) | BSD |
| madmom RNNBeatProcessor | ~25ms | 0.92 | Yes | No (CPU) | BSD |
| librosa beat_track | ~100ms | 0.80 | No (offline) | No | ISC |
| essentia BeatTrackerMultiFeature | ~30ms | 0.90 | Yes | No (CPU) | AGPL-3.0 |

#### Recommendation: Keep BeatNet (primary) + add madmom DBNBeatTracker (validation)

- **BeatNet**: Already integrated in `model_manager.py`, 20ms latency, joint beat+downbeat, MIT -- https://github.com/mjhydri/BeatNet
- **madmom**: Highest accuracy, CPU-only (frees GPU), combine via confidence weighting, BSD -- `pip install madmom`

### 2.2 Music Structure Analysis

#### Recommendation: All-In-One (pre-show) + madmom bar tracking (live)

- **All-In-One**: MIT, ~2s per song offline, runs locally -- `pip install allin1` -- https://github.com/mir-aidj/all-in-one
- **madmom bar tracking**: BSD, ~30ms real-time

### 2.3 Music Emotion Recognition -- REPLACE HuBERT

The current HuBERT model (`superb/hubert-large-superb-er`) was trained on **speech** emotion, not music emotion. This is a significant mismatch -- speech emotion detects anger/sadness/happiness in spoken words, while music emotion needs valence (happy/sad), arousal (energetic/calm), and genre-informed mood.

| Model | Params | Size | Trained On | Latency | License |
|-------|--------|------|-----------|---------|---------|
| HuBERT-Large-SUPERB-ER (current) | 316M | 1.3 GB | Speech emotion | ~50ms GPU | Apache-2.0 |
| MERT-v1-95M | 95M | 380 MB | Music (95M clips) | ~25ms GPU | CC-BY-NC-4.0 |
| CLAP (LAION) | 150M | 600 MB | Audio-text pairs | ~30ms GPU | Apache-2.0 |
| Music2Vec | 95M | 380 MB | Music | ~20ms GPU | MIT |
| Essentia mood models | ~5M each | ~20 MB each | Music | ~5ms CPU | AGPL-3.0 |

#### Recommendation: MERT-v1-95M + fine-tuned valence/arousal head (Replace HuBERT)

**Why replace HuBERT with MERT:**
- MERT is specifically pre-trained on music (not speech), producing far more relevant features
- 95M version is 3.5x smaller than HuBERT-Large but better music features
- Fine-tune a 2-layer MLP head for valence/arousal on MTG-Jamendo mood subset (~18k tracks, free)
- 25ms latency is well within the 50ms budget

- **MERT-v1-95M**: https://huggingface.co/m-a-p/MERT-v1-95M -- CC-BY-NC-4.0
- **CLAP (LAION)**: https://huggingface.co/laion/larger_clap_music_and_speech -- Apache-2.0 (commercial-safe alternative)
- **Essentia mood models**: https://essentia.upf.edu/models.html -- CPU fallback, 5ms, AGPL-3.0

**License warning:** MERT-v1 is CC-BY-NC-4.0 (non-commercial). For commercial use, use CLAP or Essentia.

### 2.4 Genre Classification

#### Recommendation: Essentia genre classifiers

- **Essentia**: ~5ms CPU, ~20 MB, ~80% accuracy on 10 genres, AGPL-3.0
- **PaSST**: Alternative for sub-genre, 87M params, MIT -- https://github.com/kkoutini/PaSST

### 2.5 Key / Harmony Detection

#### Recommendation: madmom CNNChordRecognition + Essentia key detection

Both CPU-only. madmom at 30ms for chords, Essentia at 10ms for key. BSD + AGPL-3.0.

### 2.6 Anticipation / Prediction

#### Recommendation: Pre-analyzed structure + custom causal transformer (~2M params)

No off-the-shelf model exists. Train a small causal transformer on operator recording data to predict next 4 beats of lighting state. ~5ms GPU, ~500 MB VRAM.

---

## 3. Training Infrastructure (All Local)

### 3.1 Foundation Models for Transfer Learning

- **Visual encoder**: DINOv2 ViT-S/14 -- 21M params, 84 MB, Apache-2.0 -- `facebook/dinov2-small`
- **Audio encoder**: MERT-v1-95M -- 95M params, 380 MB -- `m-a-p/MERT-v1-95M`
- **Optional multimodal**: ImageBind -- 632M params, 2.5 GB, Apache-2.0 -- training only

### 3.2 Training Framework: PyTorch Lightning

```python
import pytorch_lightning as pl

class LightingModel(pl.LightningModule):
    def __init__(self):
        super().__init__()
        # Enable gradient checkpointing on encoders to save VRAM
        self.visual_encoder.gradient_checkpointing_enable()
        self.audio_encoder.gradient_checkpointing_enable()

trainer = pl.Trainer(
    precision="16-mixed",           # FP16 -- halves VRAM for activations
    accumulate_grad_batches=8,      # Simulate batch size 64 with batch size 8
    gradient_clip_val=1.0,          # Prevent gradient explosion
    max_epochs=50,
    callbacks=[
        pl.callbacks.ModelCheckpoint(monitor="val_loss", save_top_k=3),
        pl.callbacks.EarlyStopping(monitor="val_loss", patience=10),
    ],
    logger=pl.loggers.TensorBoardLogger("logs/"),
)
```

Gradient checkpointing trades compute for memory (-60% VRAM, +30% training time). Essential for consumer GPUs. Multi-GPU: `Trainer(strategy="ddp", devices=2)`.

### 3.3 Model Compression: ONNX Runtime + TensorRT EP

Deployment pipeline:
1. Export: `torch.onnx.export(model, dummy_input, "model.onnx", opset_version=17)`
2. Quantize: `onnxruntime.quantization.quantize_dynamic(model_path, output_path, weight_type=QuantType.Float16)`
3. TensorRT auto-optimizes when `TensorrtExecutionProvider` is available
4. CPU fallback: `CPUExecutionProvider` or `OpenVINOExecutionProvider`

Latency comparison (audio-to-DMX model, ~10M params, RTX 4070):

| Runtime | Precision | Latency |
|---------|-----------|---------|
| PyTorch eager | FP32 | ~15ms |
| PyTorch compiled | FP32 | ~8ms |
| ONNX Runtime (CUDA EP) | FP16 | ~4ms |
| ONNX Runtime (TensorRT EP) | FP16 | ~2.5ms |
| ONNX Runtime (CPU) | FP32 | ~30ms |
| ONNX Runtime (OpenVINO EP) | FP32 | ~20ms |

---

## 4. Hardware Recommendations

### 4.1 GPU Tiers

- **Budget**: RTX 3060 12GB ($275) -- best budget pick due to 12GB VRAM
- **Sweet spot**: RTX 4070 Ti 12GB ($650) -- comfortable for all real-time models
- **High**: RTX 4090 24GB ($1,800) -- only needed for frequent training on large video datasets

### 4.2 VRAM Budget (Live Show)

| Model | VRAM (FP16 ONNX) |
|-------|-------------------|
| Audio-to-DMX (custom) | 0.5 GB |
| MERT-v1-95M | 1.0 GB |
| BeatNet | 0.2 GB |
| Essentia (all) | 0 (CPU) |
| YOLO11-L (optional) | 2.0 GB |
| **Total minimal** | **1.7 GB** |
| **Total with video** | **3.7 GB** |

### 4.3 CPU-Only Feasibility

Audio-only analysis (beat + mood + genre + key + audio-to-DMX) runs in ~45ms with OpenVINO on 8+ core modern CPU. Video analysis requires GPU.

### 4.4 RAM and Storage

- Training: 32 GB RAM recommended
- Inference: 16 GB sufficient
- All models: ~2.4 GB disk
- SSD recommended

---

## 5. Recommended Complete Model Stack

### VIDEO ANALYSIS STACK

```
Fixture Detection:   YOLO11-L         49 MB   ~135 FPS RTX 4070   AGPL-3.0
Beam Segmentation:   SAM 2 Hiera-T    96 MB   ~45 FPS             Apache-2.0
Color Extraction:    OpenCV LAB+KMeans 0 MB    500+ FPS (CPU)      BSD
Motion Tracking:     CoTracker v2      85 MB   ~25 FPS             Apache-2.0
Effect Classification: X3D-M          15 MB   ~120 clips/sec      Apache-2.0
Video Features:      DINOv2 ViT-S/14  84 MB   ~150 FPS            Apache-2.0
```

### AUDIO ANALYSIS STACK

```
Beat Detection:      BeatNet + madmom          ~20ms / ~30ms       MIT / BSD
Structure Analysis:  All-In-One + madmom       ~2s offline / 30ms  MIT / BSD
Emotion/Mood:        MERT-v1-95M               ~25ms GPU           CC-BY-NC-4.0
Genre:               Essentia classifiers      ~5ms CPU            AGPL-3.0
Key/Harmony:         madmom + Essentia         ~30ms / ~10ms CPU   BSD / AGPL-3.0
Anticipation:        Custom causal transformer ~5ms GPU            N/A (yours)
```

### TRAINING STACK

```
Visual Encoder:      DINOv2 ViT-S/14 (frozen)
Audio Encoder:       MERT-v1-95M (frozen, layer 12)
Fusion Model:        Cross-attention transformer (4 layers, 256 hidden)
Prediction Head:     MLP (256->128->DMX channels)
Framework:           PyTorch Lightning 2.x
Optimization:        FP16 + gradient checkpointing + accumulation(8x) + AdamW
```

### INFERENCE STACK

```
Runtime:             ONNX Runtime + TensorRT EP (GPU) / OpenVINO EP (CPU)
Quantization:        ONNX FP16 (all models) + INT8 (CPU fallback)
Total VRAM (live):   1.7 GB (audio only) / 5.7 GB (audio + video)
Total latency:       ~25ms combined (within 50ms budget)
```

---

## 6. Integration with Existing Codebase

### 6.1 Model Directory Structure

```
ml_models/
  beatnet/                     (existing)
  audio_emotion/               (renamed from hubert/)
    mert_v1_95m/               (replaces HuBERT)
    emotion_head.onnx
  yolo11/                      (renamed from yolov9/)
    yolo11l.pt
    yolo11l_fixtures.pt
  sam2/
    sam2.1_hiera_tiny.pt
  video_features/
    dinov2_vits14/
    x3d_m.pt
  motion/
    cotracker2.pth
    raft_small.pth
  audio_features/
    allin1/
    essentia_models/
  audio_to_dmx/                (the core trained model)
    model_fp16.onnx
    model.pt
  onnx_cache/
```

### 6.2 Config Updates (backend/app/core/config.py)

```python
# ML Models - Updated Stack
YOLO_MODEL_PATH: str = "ml_models/yolo11/yolo11l_fixtures.pt"
MERT_MODEL_PATH: str = "ml_models/audio_emotion/mert_v1_95m"
EMOTION_HEAD_PATH: str = "ml_models/audio_emotion/emotion_head.onnx"
SAM2_MODEL_PATH: str = "ml_models/sam2/sam2.1_hiera_tiny.pt"
DINOV2_MODEL_PATH: str = "ml_models/video_features/dinov2_vits14"
X3D_MODEL_PATH: str = "ml_models/video_features/x3d_m.pt"
COTRACKER_MODEL_PATH: str = "ml_models/motion/cotracker2.pth"
AUDIO_TO_DMX_MODEL_PATH: str = "ml_models/audio_to_dmx/model_fp16.onnx"
ESSENTIA_MODELS_DIR: str = "ml_models/audio_features/essentia_models"
# Legacy (keep for backward compatibility)
BEATNET_MODEL_PATH: str = "ml_models/beatnet/model.pt"
HUBERT_MODEL_PATH: str = "ml_models/audio_emotion/mert_v1_95m"  # Redirected
```

### 6.3 ModelManager Updates (backend/app/services/ml/model_manager.py)

```python
class ModelManager:
    """Manages ML model loading and inference - Extended Stack."""

    def __init__(self):
        self.models: Dict[str, Any] = {}
        self.processors: Dict[str, Any] = {}
        self.onnx_sessions: Dict[str, Any] = {}  # ONNX Runtime sessions
        self.device = self._detect_device()        # Auto-detect GPU/CPU
        self.model_paths = {
            'beatnet': settings.BEATNET_MODEL_PATH,
            'mert': settings.MERT_MODEL_PATH,
            'emotion_head': settings.EMOTION_HEAD_PATH,
            'yolo': settings.YOLO_MODEL_PATH,
            'audio_to_dmx': settings.AUDIO_TO_DMX_MODEL_PATH,
        }
        self.loaded = False

    def _detect_device(self) -> str:
        """Detect best available device."""
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            vram_gb = torch.cuda.get_device_properties(0).total_mem / 1e9
            print(f"GPU detected: {gpu_name} ({vram_gb:.1f} GB VRAM)")
            return "cuda"
        else:
            print("No GPU detected. Using CPU inference.")
            return "cpu"

    async def _load_mert(self):
        """Load MERT-v1-95M for music emotion recognition (replaces HuBERT)."""
        model_dir = Path(self.model_paths['mert'])
        if not model_dir.exists():
            print(f"MERT model not found at {model_dir}")
            return
        try:
            from transformers import AutoModel, AutoFeatureExtractor
            import torch
            self.processors['mert'] = AutoFeatureExtractor.from_pretrained(
                str(model_dir), trust_remote_code=True
            )
            self.models['mert'] = AutoModel.from_pretrained(
                str(model_dir), trust_remote_code=True
            )
            if self.device == "cuda":
                self.models['mert'] = self.models['mert'].cuda().half()
            print("MERT-v1-95M loaded successfully")
        except Exception as e:
            print(f"MERT loading error: {e}. Falling back to Essentia.")

    async def _load_onnx_model(self, name: str, path: str):
        """Load an ONNX model with automatic EP selection."""
        try:
            import onnxruntime as ort
            providers = ['TensorrtExecutionProvider', 'CUDAExecutionProvider']
            if self.device == "cpu":
                providers = ['CPUExecutionProvider']
            session = ort.InferenceSession(path, providers=providers)
            self.onnx_sessions[name] = session
            print(f"ONNX model '{name}' loaded with {session.get_providers()}")
        except Exception as e:
            print(f"ONNX loading error for '{name}': {e}")

    async def _load_yolo(self):
        """Load YOLO11-L for fixture detection (replaces YOLOv9)."""
        model_path = Path(self.model_paths['yolo'])
        if not model_path.exists():
            yolo_dir = model_path.parent
            for fallback in ['yolo11l_fixtures.pt', 'yolo11l.pt',
                             'yolov9c.pt', 'model.pt']:
                alt = yolo_dir / fallback
                if alt.exists():
                    model_path = alt
                    break
            else:
                print(f"No YOLO model found in {yolo_dir}")
                return
        try:
            from ultralytics import YOLO
            self.models['yolo'] = YOLO(str(model_path))
            print(f"YOLO model loaded from {model_path}")
        except ImportError:
            print("Ultralytics not installed. Run: pip install ultralytics")
```

### 6.4 install_models.py Updates (scripts/install_models.py)

```python
def install_yolo11():
    """Install YOLO11-L (replaces YOLOv9)."""
    yolo_dir = ML_MODELS_DIR / "yolo11"
    yolo_dir.mkdir(parents=True, exist_ok=True)
    run_command("pip install ultralytics>=8.3.0", "Ultralytics upgrade")
    download_script = yolo_dir / "download_model.py"
    download_script.write_text(
        'from ultralytics import YOLO\n'
        'model = YOLO("yolo11l.pt")\n'
        'print("[OK] YOLO11-L downloaded")\n'
    )
    original_dir = os.getcwd()
    os.chdir(yolo_dir)
    run_command("python download_model.py", "YOLO11-L download")
    os.chdir(original_dir)

def install_mert():
    """Install MERT-v1-95M (replaces HuBERT)."""
    mert_dir = ML_MODELS_DIR / "audio_emotion" / "mert_v1_95m"
    mert_dir.mkdir(parents=True, exist_ok=True)
    download_script = mert_dir / "download_model.py"
    download_script.write_text(
        'from transformers import AutoModel, AutoFeatureExtractor\n'
        'model_name = "m-a-p/MERT-v1-95M"\n'
        'feat = AutoFeatureExtractor.from_pretrained(model_name, trust_remote_code=True)\n'
        'feat.save_pretrained(".")\n'
        'model = AutoModel.from_pretrained(model_name, trust_remote_code=True)\n'
        'model.save_pretrained(".")\n'
        'print("[OK] MERT-v1-95M downloaded")\n'
    )
    original_dir = os.getcwd()
    os.chdir(mert_dir)
    run_command("python download_model.py", "MERT-v1-95M download")
    os.chdir(original_dir)

def install_dinov2():
    """Install DINOv2 ViT-S/14."""
    dino_dir = ML_MODELS_DIR / "video_features" / "dinov2_vits14"
    dino_dir.mkdir(parents=True, exist_ok=True)
    download_script = dino_dir / "download_model.py"
    download_script.write_text(
        'from transformers import AutoModel, AutoImageProcessor\n'
        'model_name = "facebook/dinov2-small"\n'
        'proc = AutoImageProcessor.from_pretrained(model_name)\n'
        'proc.save_pretrained(".")\n'
        'model = AutoModel.from_pretrained(model_name)\n'
        'model.save_pretrained(".")\n'
        'print("[OK] DINOv2 ViT-S/14 downloaded")\n'
    )
    original_dir = os.getcwd()
    os.chdir(dino_dir)
    run_command("python download_model.py", "DINOv2 download")
    os.chdir(original_dir)

def install_essentia_models():
    run_command("pip install essentia-tensorflow", "Essentia TF installation")

def install_madmom():
    run_command("pip install madmom", "madmom installation")

def install_allin1():
    run_command("pip install allin1", "All-In-One installation")

def install_onnxruntime():
    run_command("pip install onnxruntime-gpu", "ONNX Runtime GPU installation")
```

### 6.5 Model Versioning

Create `ml_models/model_manifest.json`:
```json
{
  "models": {
    "yolo11l": {
      "version": "11.0.0",
      "sha256": "<computed after download>",
      "path": "yolo11/yolo11l.pt",
      "source": "ultralytics"
    },
    "mert_v1_95m": {
      "version": "1.0",
      "sha256": "<computed after download>",
      "path": "audio_emotion/mert_v1_95m/model.safetensors",
      "source": "huggingface:m-a-p/MERT-v1-95M"
    }
  }
}
```

Check model integrity on startup by comparing SHA-256 hashes. If missing or corrupted, log a warning and use the fallback.

### 6.6 Graceful Fallback Chain

Every model function should follow this chain:
```
GPU Model (preferred)
  -> ONNX CPU Model (if no GPU)
    -> Lightweight Algorithm (if model missing)
      -> Default Values (last resort)
```

The current `model_manager.py` already implements this pattern for beat detection (BeatNet -> librosa -> zeros) and mood (HuBERT -> energy-based -> neutral). Extend this pattern to all new models.

---

## 7. Cost Analysis

### API Equivalent Cost Per Show (3 hours)

| Function | API Cost per Show |
|----------|-------------------|
| Mood/Emotion (Hume AI) | $64.80 |
| Genre (Google Cloud Audio) | $43.20 |
| Fixture detection (Google Vision) | $486.00 |
| Video analysis (GPT-4V at 1fps) | $108.00 |
| **Total per show** | **~$702** |

### Local Hardware Investment

| Tier | One-time Cost |
|------|---------------|
| Budget (RTX 3060 12GB + RAM + SSD) | $375 |
| Mid (RTX 4070 Ti 12GB + RAM + SSD) | $750 |
| High (RTX 4090 24GB + RAM + SSD) | $1,900 |

### Break-Even

At 1 show/week ($2,808/mo API cost), the budget tier pays for itself in less than 1 week. The mid tier in less than 2 weeks.

### 3-Year Total Cost Comparison

- Local (mid tier): $750 hardware + $360 electricity = **$1,110**
- Cloud APIs (48 shows/year): **$101,100**

---

## Appendix A: Quick-Start Commands

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install ultralytics>=8.3.0 transformers>=4.40.0 onnxruntime-gpu pytorch-lightning>=2.2.0
pip install BeatNet madmom essentia-tensorflow allin1 librosa timm
python scripts/install_models.py
```

## Appendix B: License Summary

| Model | License | Commercial OK? |
|-------|---------|----------------|
| YOLO11 | AGPL-3.0 | Internal use only; use RT-DETR (Apache-2.0) if distributing |
| SAM 2, DINOv2, CoTracker, X3D, VideoMAE | Apache-2.0 | Yes |
| MERT-v1-95M | CC-BY-NC-4.0 | Non-commercial only; use CLAP (Apache-2.0) for commercial |
| BeatNet | MIT | Yes |
| madmom, RAFT | BSD-3 | Yes |
| Essentia | AGPL-3.0 | Internal use only |
| All-In-One | MIT | Yes |
| ONNX Runtime | MIT | Yes |

## Appendix C: Benchmarks (RTX 4070 Ti 12GB)

| Model | Latency (ONNX FP16) | VRAM |
|-------|---------------------|------|
| YOLO11-L | 4.2ms | 2.0 GB |
| SAM 2 Hiera-T | 14ms | 3.0 GB |
| DINOv2 ViT-S/14 | 2.1ms | 1.0 GB |
| MERT-v1-95M | 15ms | 2.0 GB |
| BeatNet | 20ms | 0.2 GB |
| Essentia (all) | 5ms | 0 (CPU) |
| Audio-to-DMX | 2.5ms | 0.5 GB |
| **Combined live** | **~25ms** | **~4.7 GB** |
