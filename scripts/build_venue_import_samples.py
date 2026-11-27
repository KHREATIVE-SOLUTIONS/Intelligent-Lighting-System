"""
Write the venue importer's sample files to backend/tests/fixtures/import/.

    backend/venv/Scripts/python scripts/build_venue_import_samples.py

A CSV patch list, a GDTF, an MVR that embeds it and a grandMA2 XML export, each
a subset of the LIV approximate demo preset. All four are generated from the
preset, so edit the preset or app/services/demo/import_samples.py, not the
files. Also the example festival patch sheet with no positions, from
app/services/demo/patch_sheet_samples.py. Touches no database, opens no socket
and sends no DMX.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.demo.import_samples import sample_files  # noqa: E402
from app.services.demo.patch_sheet_samples import sample_files as patch_sheet_files  # noqa: E402


def main() -> int:
    folder = ROOT / "backend" / "tests" / "fixtures" / "import"
    folder.mkdir(parents=True, exist_ok=True)
    for name, data in {**sample_files(), **patch_sheet_files()}.items():
        (folder / name).write_bytes(data)
        print(f"Wrote {(folder / name).relative_to(ROOT)} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
