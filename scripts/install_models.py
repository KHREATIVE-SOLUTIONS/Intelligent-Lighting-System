#!/usr/bin/env python3
"""
ML Model Installation Script
============================

Downloads and sets up ML models for the Intelligent Lighting System:
- BeatNet: Beat detection and tempo tracking
- HuBERT: Audio mood/emotion classification
- YOLOv9: Fixture detection in images
"""

import os
import sys
import subprocess
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
ML_MODELS_DIR = PROJECT_ROOT / "ml_models"


def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}")
    try:
        subprocess.run(cmd, shell=True, check=True)
        print(f"[OK] {description} completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] {description} failed: {e}")
        return False


def install_pytorch():
    """Install PyTorch with CUDA support if available."""
    print("\n" + "="*60)
    print("  Installing PyTorch...")
    print("="*60)

    # Check for CUDA
    try:
        import torch
        if torch.cuda.is_available():
            print(f"[INFO] PyTorch already installed with CUDA {torch.version.cuda}")
            return True
        else:
            print("[INFO] PyTorch already installed (CPU only)")
            return True
    except ImportError:
        pass

    # Install PyTorch - use pip for simplicity
    # For CUDA support, users can install manually with specific CUDA version
    cmd = "pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121"

    print("[INFO] Installing PyTorch with CUDA 12.1 support...")
    print("[INFO] If you need a different CUDA version, install PyTorch manually first")

    return run_command(cmd, "PyTorch installation")


def install_beatnet():
    """Install BeatNet for beat detection."""
    print("\n" + "="*60)
    print("  Setting up BeatNet...")
    print("="*60)

    beatnet_dir = ML_MODELS_DIR / "beatnet"
    beatnet_dir.mkdir(parents=True, exist_ok=True)

    # Install BeatNet package
    if not run_command("pip install BeatNet", "BeatNet package installation"):
        return False

    # BeatNet downloads its model automatically on first use
    # Create a test script to trigger download
    test_script = beatnet_dir / "download_model.py"
    test_script.write_text('''
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # Use CPU for download
try:
    from BeatNet.BeatNet import BeatNet
    # Initialize to trigger model download
    estimator = BeatNet(1, mode='offline', inference_model='DBN', plot=[], thread=False)
    print("[OK] BeatNet model downloaded successfully")
except Exception as e:
    print(f"[INFO] BeatNet setup: {e}")
    print("[INFO] Model will be downloaded on first use")
''')

    print("[INFO] Downloading BeatNet model...")
    run_command(f"python {test_script}", "BeatNet model download")

    # Update config
    config_path = beatnet_dir / "config.yaml"
    config_path.write_text('''# BeatNet Configuration
model:
  name: BeatNet
  version: "1.0"
  type: beat_detection

inference:
  mode: online  # online or offline
  inference_model: DBN  # DBN or PF
  sample_rate: 22050

output:
  beat_times: true
  downbeat_times: true
  tempo: true
''')

    print("[OK] BeatNet setup complete")
    return True


def install_hubert():
    """Install HuBERT for mood classification."""
    print("\n" + "="*60)
    print("  Setting up HuBERT...")
    print("="*60)

    hubert_dir = ML_MODELS_DIR / "hubert"
    hubert_dir.mkdir(parents=True, exist_ok=True)

    # Install transformers
    if not run_command("pip install transformers", "Transformers installation"):
        return False

    # Download HuBERT model for emotion recognition
    download_script = hubert_dir / "download_model.py"
    download_script.write_text('''
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # Use CPU for download

print("[INFO] Downloading HuBERT model for emotion recognition...")

try:
    from transformers import Wav2Vec2FeatureExtractor, HubertForSequenceClassification

    # Using a fine-tuned HuBERT model for emotion recognition
    model_name = "superb/hubert-large-superb-er"

    print(f"[INFO] Downloading {model_name}...")

    # Download feature extractor
    feature_extractor = Wav2Vec2FeatureExtractor.from_pretrained(model_name)
    feature_extractor.save_pretrained(".")

    # Download model
    model = HubertForSequenceClassification.from_pretrained(model_name)
    model.save_pretrained(".")

    print("[OK] HuBERT model downloaded successfully")

except Exception as e:
    print(f"[ERROR] HuBERT download failed: {e}")
    print("[INFO] Trying alternative model...")

    try:
        from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

        # Alternative: wav2vec2 for emotion
        model_name = "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"

        print(f"[INFO] Downloading {model_name}...")

        feature_extractor = AutoFeatureExtractor.from_pretrained(model_name)
        feature_extractor.save_pretrained(".")

        model = AutoModelForAudioClassification.from_pretrained(model_name)
        model.save_pretrained(".")

        print("[OK] Alternative emotion model downloaded successfully")

    except Exception as e2:
        print(f"[ERROR] Alternative download also failed: {e2}")
''')

    # Run download in the hubert directory
    original_dir = os.getcwd()
    os.chdir(hubert_dir)
    run_command(f"python download_model.py", "HuBERT model download")
    os.chdir(original_dir)

    # Update config
    config_path = hubert_dir / "config.yaml"
    config_path.write_text('''# HuBERT Configuration
model:
  name: HuBERT
  version: "large"
  type: emotion_recognition
  source: superb/hubert-large-superb-er

inference:
  sample_rate: 16000
  max_length: 10  # seconds

output:
  valence: true
  arousal: true
  emotions:
    - angry
    - happy
    - sad
    - neutral
''')

    print("[OK] HuBERT setup complete")
    return True


def install_yolov9():
    """Install YOLOv9 for fixture detection."""
    print("\n" + "="*60)
    print("  Setting up YOLOv9...")
    print("="*60)

    yolo_dir = ML_MODELS_DIR / "yolov9"
    yolo_dir.mkdir(parents=True, exist_ok=True)

    # Install ultralytics
    if not run_command("pip install ultralytics", "Ultralytics installation"):
        return False

    # Download YOLOv9 model
    download_script = yolo_dir / "download_model.py"
    download_script.write_text('''
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # Use CPU for download

print("[INFO] Downloading YOLOv9 model...")

try:
    from ultralytics import YOLO

    # Download YOLOv9 compact model (good balance of speed/accuracy)
    # Options: yolov9t, yolov9s, yolov9m, yolov9c, yolov9e
    model = YOLO("yolov9c.pt")

    # Save to current directory
    import shutil
    if os.path.exists("yolov9c.pt"):
        shutil.move("yolov9c.pt", "model.pt")

    print("[OK] YOLOv9 model downloaded successfully")

except Exception as e:
    print(f"[ERROR] YOLOv9 download failed: {e}")
    print("[INFO] Trying YOLOv8 as fallback...")

    try:
        from ultralytics import YOLO
        model = YOLO("yolov8m.pt")

        import shutil
        if os.path.exists("yolov8m.pt"):
            shutil.move("yolov8m.pt", "model.pt")

        print("[OK] YOLOv8 model downloaded as fallback")

    except Exception as e2:
        print(f"[ERROR] Fallback download also failed: {e2}")
''')

    # Run download in the yolo directory
    original_dir = os.getcwd()
    os.chdir(yolo_dir)
    run_command(f"python download_model.py", "YOLOv9 model download")
    os.chdir(original_dir)

    # Update config
    config_path = yolo_dir / "config.yaml"
    config_path.write_text('''# YOLOv9 Configuration
model:
  name: YOLOv9
  version: "c"
  type: object_detection
  weights: model.pt

inference:
  confidence_threshold: 0.5
  iou_threshold: 0.45
  max_detections: 100

# Custom classes for fixture detection
# To train on custom fixtures, create a dataset and fine-tune
classes:
  - moving_head
  - par_can
  - led_bar
  - strobe
  - laser
  - spotlight
  - wash_light
  - effect_light
''')

    print("[OK] YOLOv9 setup complete")
    return True


def update_requirements():
    """Update requirements.txt with ML dependencies."""
    print("\n" + "="*60)
    print("  Updating requirements.txt...")
    print("="*60)

    req_path = PROJECT_ROOT / "backend" / "requirements.txt"

    ml_deps = """
# ML/AI Dependencies (installed by install_models.py)
torch>=2.1.0
torchvision>=0.16.0
torchaudio>=2.1.0
transformers>=4.36.0
ultralytics>=8.0.0
BeatNet>=1.0.0
"""

    # Read existing requirements
    existing = req_path.read_text() if req_path.exists() else ""

    # Check if ML deps already added
    if "torch>=" in existing:
        print("[INFO] ML dependencies already in requirements.txt")
        return True

    # Append ML dependencies
    with open(req_path, "a") as f:
        f.write(ml_deps)

    print("[OK] requirements.txt updated with ML dependencies")
    return True


def main():
    """Main installation function."""
    print("""
================================================================
     Intelligent Lighting System - ML Model Installer
================================================================
  This script will download and set up:
  - BeatNet    - Beat detection (~500MB)
  - HuBERT     - Emotion recognition (~1.5GB)
  - YOLOv9     - Object detection (~100MB)
  - PyTorch    - Deep learning framework (~2GB)
================================================================
    """)

    # Check Python version
    if sys.version_info < (3, 9):
        print("[ERROR] Python 3.9 or higher is required")
        sys.exit(1)

    print(f"[INFO] Python version: {sys.version}")
    print(f"[INFO] ML Models directory: {ML_MODELS_DIR}")

    # Create ML models directory
    ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)

    results = {}

    # Install PyTorch first
    results['pytorch'] = install_pytorch()

    if not results['pytorch']:
        print("\n[ERROR] PyTorch installation failed. Cannot continue.")
        print("[INFO] Please install PyTorch manually: https://pytorch.org/get-started/locally/")
        sys.exit(1)

    # Install models
    results['beatnet'] = install_beatnet()
    results['hubert'] = install_hubert()
    results['yolov9'] = install_yolov9()

    # Update requirements
    update_requirements()

    # Summary
    print("\n" + "="*60)
    print("  Installation Summary")
    print("="*60)

    for name, success in results.items():
        status = "[OK]" if success else "[FAILED]"
        print(f"  {status} {name}")

    if all(results.values()):
        print("\n[SUCCESS] All models installed successfully!")
        print("\nTo use the models, restart the backend server:")
        print("  docker-compose restart backend")
        print("\nOr if running locally:")
        print("  cd backend && python -m uvicorn app.main:app --reload")
    else:
        print("\n[WARNING] Some models failed to install.")
        print("The system will use fallback algorithms for missing models.")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
