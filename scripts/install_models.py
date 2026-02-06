#!/usr/bin/env python3
"""
ML Model Installation Script
============================

Downloads and sets up ML models for the Intelligent Lighting System:
- MERT-v1-95M: Music emotion recognition (replaces HuBERT)
- BeatNet: Beat detection and tempo tracking
- YOLOv9: Fixture detection in images
- All-In-One: Music structure analysis
- Essentia: Genre classification (CPU)
- madmom: Beat validation and chord detection (CPU)
- ONNX Runtime: Optimized inference

Usage:
    python scripts/install_models.py              # Install all (legacy mode)
    python scripts/install_models.py --all        # Install all new models
    python scripts/install_models.py --mert       # Install MERT only
    python scripts/install_models.py --verify     # Verify installed models
"""

import argparse
import hashlib
import json
import os
import sys
import subprocess
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
ML_MODELS_DIR = PROJECT_ROOT / "data" / "models"
LEGACY_MODELS_DIR = PROJECT_ROOT / "ml_models"
MANIFEST_PATH = ML_MODELS_DIR / "model_manifest.json"


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


def compute_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    """Load or create the model manifest."""
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    return {"models": {}}


def save_manifest(manifest: dict):
    """Save the model manifest."""
    ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)


def install_pytorch():
    """Install PyTorch with CUDA support if available."""
    print("\n" + "="*60)
    print("  Installing PyTorch...")
    print("="*60)

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

    cmd = "pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121"
    print("[INFO] Installing PyTorch with CUDA 12.1 support...")
    return run_command(cmd, "PyTorch installation")


def install_mert():
    """Install MERT-v1-95M from HuggingFace.

    Replaces HuBERT for music emotion recognition.
    ~380 MB download, CC-BY-NC-4.0 license.
    """
    mert_dir = ML_MODELS_DIR / "mert_v1_95m"
    mert_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 60)
    print("Installing MERT-v1-95M (Music Understanding Model)")
    print("Source: huggingface.co/m-a-p/MERT-v1-95M")
    print("Size: ~380 MB | License: CC-BY-NC-4.0")
    print("=" * 60)

    config_file = mert_dir / "config.json"
    if config_file.exists():
        print(f"  MERT model already exists at {mert_dir}")
        return True

    if not run_command("pip install transformers>=4.40.0", "Transformers installation"):
        return False

    download_script = mert_dir / "_download.py"
    download_script.write_text(
        'from transformers import AutoModel, AutoFeatureExtractor\n'
        'model_name = "m-a-p/MERT-v1-95M"\n'
        'print("Downloading MERT-v1-95M feature extractor...")\n'
        'feat = AutoFeatureExtractor.from_pretrained(model_name, trust_remote_code=True)\n'
        f'feat.save_pretrained("{mert_dir.as_posix()}")\n'
        'print("Downloading MERT-v1-95M model weights...")\n'
        'model = AutoModel.from_pretrained(model_name, trust_remote_code=True)\n'
        f'model.save_pretrained("{mert_dir.as_posix()}")\n'
        'print("[OK] MERT-v1-95M downloaded successfully")\n'
    )

    success = run_command(f"{sys.executable} {download_script}", "MERT-v1-95M download")
    download_script.unlink(missing_ok=True)

    if success:
        manifest = load_manifest()
        manifest["models"]["mert_v1_95m"] = {
            "version": "1.0",
            "path": "mert_v1_95m/",
            "source": "huggingface:m-a-p/MERT-v1-95M",
            "license": "CC-BY-NC-4.0",
            "installed": True,
        }
        save_manifest(manifest)

    return success


def install_beatnet():
    """Install BeatNet for beat detection."""
    print("\n" + "="*60)
    print("  Setting up BeatNet...")
    print("  License: MIT")
    print("="*60)

    beatnet_dir = LEGACY_MODELS_DIR / "beatnet"
    beatnet_dir.mkdir(parents=True, exist_ok=True)

    if not run_command("pip install BeatNet", "BeatNet package installation"):
        return False

    test_script = beatnet_dir / "download_model.py"
    test_script.write_text(
        'import os\n'
        'os.environ["CUDA_VISIBLE_DEVICES"] = ""\n'
        'try:\n'
        '    from BeatNet.BeatNet import BeatNet\n'
        '    estimator = BeatNet(1, mode="offline", inference_model="DBN", plot=[], thread=False)\n'
        '    print("[OK] BeatNet model downloaded successfully")\n'
        'except Exception as e:\n'
        '    print(f"[INFO] BeatNet setup: {e}")\n'
        '    print("[INFO] Model will be downloaded on first use")\n'
    )

    run_command(f"{sys.executable} {test_script}", "BeatNet model download")

    manifest = load_manifest()
    manifest["models"]["beatnet"] = {
        "version": "latest",
        "source": "pip:BeatNet",
        "license": "MIT",
        "installed": True,
    }
    save_manifest(manifest)

    return True


def install_hubert():
    """Install HuBERT for mood classification (legacy, replaced by MERT)."""
    print("\n" + "="*60)
    print("  Setting up HuBERT (legacy)...")
    print("  NOTE: MERT-v1-95M is recommended instead. Use --mert")
    print("="*60)

    hubert_dir = LEGACY_MODELS_DIR / "hubert"
    hubert_dir.mkdir(parents=True, exist_ok=True)

    if not run_command("pip install transformers", "Transformers installation"):
        return False

    download_script = hubert_dir / "download_model.py"
    download_script.write_text(
        'import os\n'
        'os.environ["CUDA_VISIBLE_DEVICES"] = ""\n'
        'print("[INFO] Downloading HuBERT model for emotion recognition...")\n'
        'try:\n'
        '    from transformers import AutoFeatureExtractor, AutoModelForAudioClassification\n'
        '    model_name = "ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition"\n'
        '    print(f"[INFO] Downloading {model_name}...")\n'
        '    feature_extractor = AutoFeatureExtractor.from_pretrained(model_name)\n'
        '    feature_extractor.save_pretrained(".")\n'
        '    model = AutoModelForAudioClassification.from_pretrained(model_name)\n'
        '    model.save_pretrained(".")\n'
        '    print("[OK] HuBERT model downloaded successfully")\n'
        'except Exception as e:\n'
        '    print(f"[ERROR] HuBERT download failed: {e}")\n'
    )

    original_dir = os.getcwd()
    os.chdir(hubert_dir)
    run_command(f"{sys.executable} download_model.py", "HuBERT model download")
    os.chdir(original_dir)

    return True


def install_yolov9():
    """Install YOLOv9 for fixture detection."""
    print("\n" + "="*60)
    print("  Setting up YOLOv9...")
    print("="*60)

    yolo_dir = LEGACY_MODELS_DIR / "yolov9"
    yolo_dir.mkdir(parents=True, exist_ok=True)

    if not run_command("pip install ultralytics", "Ultralytics installation"):
        return False

    download_script = yolo_dir / "download_model.py"
    download_script.write_text(
        'import os\n'
        'os.environ["CUDA_VISIBLE_DEVICES"] = ""\n'
        'print("[INFO] Downloading YOLOv9 model...")\n'
        'try:\n'
        '    from ultralytics import YOLO\n'
        '    model = YOLO("yolov9c.pt")\n'
        '    import shutil\n'
        '    if os.path.exists("yolov9c.pt"):\n'
        '        shutil.move("yolov9c.pt", "model.pt")\n'
        '    print("[OK] YOLOv9 model downloaded successfully")\n'
        'except Exception as e:\n'
        '    print(f"[ERROR] YOLOv9 download failed: {e}")\n'
    )

    original_dir = os.getcwd()
    os.chdir(yolo_dir)
    run_command(f"{sys.executable} download_model.py", "YOLOv9 model download")
    os.chdir(original_dir)

    return True


def install_allin1():
    """Install All-In-One Music Structure Analyzer."""
    print("\n" + "=" * 60)
    print("Installing All-In-One Music Structure Analyzer")
    print("Source: github.com/mir-aidj/all-in-one | License: MIT")
    print("=" * 60)

    success = run_command(f"{sys.executable} -m pip install allin1", "All-In-One installation")
    if success:
        manifest = load_manifest()
        manifest["models"]["allin1"] = {
            "version": "latest",
            "source": "pip:allin1",
            "license": "MIT",
            "installed": True,
        }
        save_manifest(manifest)
    return success


def install_essentia():
    """Install Essentia models for genre/mood classification (CPU)."""
    print("\n" + "=" * 60)
    print("Installing Essentia Models (Genre/Mood, CPU)")
    print("License: AGPL-3.0")
    print("=" * 60)

    success = run_command(
        f"{sys.executable} -m pip install essentia-tensorflow",
        "Essentia installation"
    )
    if success:
        manifest = load_manifest()
        manifest["models"]["essentia"] = {
            "version": "latest",
            "source": "pip:essentia-tensorflow",
            "license": "AGPL-3.0",
            "installed": True,
        }
        save_manifest(manifest)
    return success


def install_madmom():
    """Install madmom for beat tracking validation and chord detection."""
    print("\n" + "=" * 60)
    print("Installing madmom (Beat/Chord, CPU)")
    print("License: BSD-3")
    print("=" * 60)

    success = run_command(f"{sys.executable} -m pip install madmom", "madmom installation")
    if success:
        manifest = load_manifest()
        manifest["models"]["madmom"] = {
            "version": "latest",
            "source": "pip:madmom",
            "license": "BSD-3",
            "installed": True,
        }
        save_manifest(manifest)
    return success


def install_onnxruntime():
    """Install ONNX Runtime with GPU support for optimized inference."""
    print("\n" + "=" * 60)
    print("Installing ONNX Runtime (Optimized Inference)")
    print("License: MIT")
    print("=" * 60)

    success = run_command(
        f"{sys.executable} -m pip install onnxruntime-gpu",
        "ONNX Runtime GPU"
    )
    if not success:
        success = run_command(
            f"{sys.executable} -m pip install onnxruntime",
            "ONNX Runtime CPU (fallback)"
        )
    if success:
        manifest = load_manifest()
        manifest["models"]["onnxruntime"] = {
            "version": "latest",
            "source": "pip:onnxruntime",
            "license": "MIT",
            "installed": True,
        }
        save_manifest(manifest)
    return success


def verify_models():
    """Verify all installed models."""
    print("\n" + "=" * 60)
    print("Verifying Installed Models")
    print("=" * 60)

    manifest = load_manifest()
    for name, info in manifest.get("models", {}).items():
        path = info.get("path", "")
        if path:
            full_path = ML_MODELS_DIR / path
            if full_path.exists():
                print(f"  [OK] {name}: {info.get('source', 'unknown')}")
            else:
                print(f"  [MISSING] {name}: expected at {full_path}")
        else:
            print(f"  [OK] {name}: {info.get('source', 'pip package')}")

    packages = {
        "BeatNet": "beat detection",
        "transformers": "MERT/HuBERT",
        "onnxruntime": "ONNX inference",
        "allin1": "music structure",
    }
    for pkg, desc in packages.items():
        try:
            __import__(pkg.lower().replace("-", "_"))
            print(f"  [OK] {pkg} ({desc})")
        except ImportError:
            print(f"  [MISSING] {pkg} ({desc})")


def main():
    """Main installation function."""
    parser = argparse.ArgumentParser(
        description="Install ML models for Intelligent Lighting System"
    )
    parser.add_argument("--all", action="store_true", help="Install all models (new stack)")
    parser.add_argument("--mert", action="store_true", help="Install MERT-v1-95M")
    parser.add_argument("--beatnet", action="store_true", help="Install BeatNet")
    parser.add_argument("--essentia", action="store_true", help="Install Essentia")
    parser.add_argument("--allin1", action="store_true", help="Install All-In-One")
    parser.add_argument("--madmom", action="store_true", help="Install madmom")
    parser.add_argument("--onnx", action="store_true", help="Install ONNX Runtime")
    parser.add_argument("--verify", action="store_true", help="Verify installed models")
    parser.add_argument("--legacy", action="store_true", help="Install legacy models (HuBERT, YOLOv9)")

    args = parser.parse_args()

    # If no args, run legacy installer for backward compatibility
    has_new_args = any([args.all, args.mert, args.beatnet, args.essentia,
                        args.allin1, args.madmom, args.onnx, args.verify,
                        args.legacy])

    if not has_new_args:
        # Legacy behavior: install everything
        print("""
================================================================
     Intelligent Lighting System - ML Model Installer
================================================================
  This script will download and set up:
  - MERT-v1-95M  - Music emotion recognition (~380MB)
  - BeatNet      - Beat detection (~500MB)
  - YOLOv9       - Object detection (~100MB)
  - PyTorch      - Deep learning framework (~2GB)
================================================================
        """)

        if sys.version_info < (3, 9):
            print("[ERROR] Python 3.9 or higher is required")
            sys.exit(1)

        LEGACY_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)

        results = {}
        results['pytorch'] = install_pytorch()
        if not results['pytorch']:
            print("\n[ERROR] PyTorch installation failed.")
            sys.exit(1)

        results['beatnet'] = install_beatnet()
        results['mert'] = install_mert()
        results['hubert'] = install_hubert()
        results['yolov9'] = install_yolov9()

        print("\n" + "="*60)
        print("  Installation Summary")
        print("="*60)
        for name, success in results.items():
            status = "[OK]" if success else "[FAILED]"
            print(f"  {status} {name}")
        return 0 if all(results.values()) else 1

    # New-style installation
    ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)

    if args.verify:
        verify_models()
        return 0

    print("=" * 60)
    print("Intelligent Lighting System - Model Installer")
    print(f"Model directory: {ML_MODELS_DIR}")
    print("=" * 60)

    results = {}

    if args.all or args.onnx:
        results["onnxruntime"] = install_onnxruntime()
    if args.all or args.mert:
        results["mert"] = install_mert()
    if args.all or args.beatnet:
        results["beatnet"] = install_beatnet()
    if args.all or args.essentia:
        results["essentia"] = install_essentia()
    if args.all or args.allin1:
        results["allin1"] = install_allin1()
    if args.all or args.madmom:
        results["madmom"] = install_madmom()
    if args.legacy:
        results["hubert"] = install_hubert()
        results["yolov9"] = install_yolov9()

    print("\n" + "=" * 60)
    print("Installation Summary")
    print("=" * 60)
    for name, success in results.items():
        status = "[OK]" if success else "[FAIL]"
        print(f"  {status} {name}")

    if all(results.values()):
        print("\nAll installations completed successfully.")
    else:
        print("\nSome installations failed. Check the output above.")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
