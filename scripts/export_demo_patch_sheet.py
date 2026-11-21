"""
Write a demo venue preset's patch sheet to docs/venues/.

    backend/venv/Scripts/python scripts/export_demo_patch_sheet.py [preset]

Defaults to the LIV Miami approximate recreation. Touches no database, opens no
socket and sends no DMX: it only reads the preset and writes a CSV.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.demo.patch_sheet import patch_sheet_csv  # noqa: E402
from app.services.demo.venue_presets import VENUE_PRESETS  # noqa: E402


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "liv_miami_approx"
    preset = VENUE_PRESETS.get(name)
    if preset is None:
        print(f"Unknown preset '{name}'. Available: {', '.join(VENUE_PRESETS)}")
        return 1
    target = ROOT / "docs" / "venues" / f"{name}_patch.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(patch_sheet_csv(preset), encoding="utf-8", newline="\n")
    print(f"Wrote {target.relative_to(ROOT)} ({len(preset.fixtures)} fixtures)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
