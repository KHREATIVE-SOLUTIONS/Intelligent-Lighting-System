#!/usr/bin/env python3
"""
Score a genre night check
=========================

Reads a night's log (genre_check/<night>/log.jsonl in the box's data folder,
next to the database) and prints
how the club genre model did against what the operator marked. The same
numbers the dashboard shows when a check is stopped.

Usage:
    python scripts/genre_night_report.py                 # every night, oldest first
    python scripts/genre_night_report.py 2026-10-24_2200 # one night
    python scripts/genre_night_report.py --dir PATH      # a copied genre_check folder
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.ml.genre_night_check import _root, read_log, score  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("night", nargs="?", help="night folder name; all nights when left out")
    parser.add_argument("--dir", type=Path, default=None, help="the genre_check folder")
    args = parser.parse_args()
    if args.dir is None:
        args.dir = _root()

    if not args.dir.is_dir():
        print(f"No night checks in {args.dir}")
        return 1
    nights = [args.night] if args.night else sorted(
        p.name for p in args.dir.iterdir() if (p / "log.jsonl").is_file()
    )
    if not nights:
        print(f"No night checks in {args.dir}")
        return 1

    for night in nights:
        print(f"== {night}")
        print(json.dumps(score(read_log(args.dir / night)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
