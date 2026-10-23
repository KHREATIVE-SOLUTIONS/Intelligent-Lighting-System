#!/usr/bin/env python3
"""
Fetch the club genre model's weights
====================================

EfficientAT `mn10_as` (MIT licence, Copyright (c) 2022 Florian Schmid), the
AudioSet-trained tagger behind GENRE_MODEL_ENABLED. About 20 MB, from the
project's own GitHub release. The file is checked against a pinned SHA-256
before it is put in place, so a truncated or substituted download is refused.

Usage:
    python scripts/download_genre_model.py            # into backend/data/models/efficientat/
    python scripts/download_genre_model.py --dest PATH

Then set GENRE_MODEL_ENABLED=true (and GENRE_MODEL_PATH if you used --dest).
"""

import argparse
import hashlib
import sys
import tempfile
import urllib.request
from pathlib import Path

URL = "https://github.com/fschmid56/EfficientAT/releases/download/v0.0.1/mn10_as_mAP_471.pt"
SHA256 = "0bd7dc2443af498c289a2e739f02ebb515d6aa3fd3ab9db539c86123ae368a4e"
SIZE = 19_708_753

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = PROJECT_ROOT / "backend" / "data" / "models" / "efficientat" / "mn10_as_mAP_471.pt"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="where to put the weights")
    args = parser.parse_args()
    dest: Path = args.dest

    if dest.is_file() and sha256(dest) == SHA256:
        print(f"[OK] Already in place: {dest}")
        return 0

    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {URL}")
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False, suffix=".part") as tmp:
        tmp_path = Path(tmp.name)
        try:
            with urllib.request.urlopen(URL, timeout=60) as response:
                while True:
                    block = response.read(1 << 20)
                    if not block:
                        break
                    tmp.write(block)
        except Exception as e:
            tmp.close()
            tmp_path.unlink(missing_ok=True)
            print(f"[ERROR] Download failed: {e}")
            return 1

    size = tmp_path.stat().st_size
    digest = sha256(tmp_path)
    if size != SIZE or digest != SHA256:
        tmp_path.unlink(missing_ok=True)
        print(f"[ERROR] Refusing the download: {size} bytes, sha256 {digest}; expected {SIZE} bytes, {SHA256}")
        return 1

    tmp_path.replace(dest)
    print(f"[OK] Saved {dest}")
    print("Set GENRE_MODEL_ENABLED=true to use it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
