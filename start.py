#!/usr/bin/env python3
"""
Intelligent Lighting System - the one launcher.

    python start.py              backend + operator UI, health check, Ctrl+C stops both
    python start.py --check      preflight only: what is missing or busy
    python start.py --dry-run    print the exact commands and exit
    python start.py --no-ui      backend only
    python start.py --audio      also feed this machine's audio to the backend

Any Python 3.8+ can run this file; the backend itself runs under backend/venv.
The logic is in scripts/launcher.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

from launcher import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
