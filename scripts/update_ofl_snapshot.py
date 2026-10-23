#!/usr/bin/env python3
"""
Refresh the offline Open Fixture Library snapshot
=================================================

A venue patches its rig at load-in, often before the house network is up. The
app therefore ships a copy of the whole Open Fixture Library (OFL) so a fixture
can be found and patched by make and model with no internet at all. This script
rebuilds that copy from the OFL repository.

The snapshot is the OFL fixture JSON exactly as published (minus the `$schema`
pointer), keyed "manufacturer/fixture", plus the manufacturer names and the
rename redirects. Conversion into our profile format happens at import time with
the same converter the online path uses, so a converter fix never needs a new
snapshot.

OFL is MIT licensed; its licence travels with the snapshot in
data/fixtures/ofl/LICENSE.OFL.md.

Usage
-----
    python scripts/update_ofl_snapshot.py                    # clone OFL, write snapshot
    python scripts/update_ofl_snapshot.py --source ./ofl     # use an existing checkout

Needs git and network access only when --source is not given.
"""

import argparse
import gzip
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

OFL_REPO = "https://github.com/OpenLightingProject/open-fixture-library.git"
REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = REPO_ROOT / "data" / "fixtures" / "ofl" / "ofl_snapshot.json.gz"


def _clone(target: Path) -> Path:
    checkout = target / "ofl"
    subprocess.run(
        ["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", OFL_REPO, str(checkout)],
        check=True,
    )
    subprocess.run(["git", "-C", str(checkout), "sparse-checkout", "set", "fixtures"], check=True)
    return checkout


def _commit(checkout: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_snapshot(checkout: Path) -> dict:
    fixtures_dir = checkout / "fixtures"
    manufacturers_raw = json.loads((fixtures_dir / "manufacturers.json").read_text(encoding="utf-8"))
    manufacturers = {
        key: {k: v for k, v in value.items() if k in ("name", "website", "rdmId")}
        for key, value in manufacturers_raw.items()
        if not key.startswith("$") and isinstance(value, dict)
    }

    fixtures = {}
    redirects = {}
    for path in sorted(fixtures_dir.glob("*/*.json")):
        key = f"{path.parent.name}/{path.stem}"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("$schema", None)
        if "redirectTo" in data:
            redirects[key] = data["redirectTo"]
            continue
        fixtures[key] = data

    return {
        "source": OFL_REPO,
        "commit": _commit(checkout),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "license": "MIT, see LICENSE.OFL.md",
        "manufacturers": manufacturers,
        "redirects": redirects,
        "fixtures": fixtures,
    }


def write_snapshot(snapshot: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    # mtime=0 keeps the archive byte-identical when OFL has not changed.
    with open(path, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as gz:
            gz.write(payload.encode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, help="existing OFL checkout (skips the clone)")
    parser.add_argument("--output", type=Path, default=SNAPSHOT_PATH)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="ofl-") as tmp:
        checkout = args.source or _clone(Path(tmp))
        snapshot = build_snapshot(checkout)
        write_snapshot(snapshot, args.output)

    print(
        f"Wrote {len(snapshot['fixtures'])} fixtures from {len(snapshot['manufacturers'])} "
        f"manufacturers (OFL {snapshot['commit'][:10]}) to {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
