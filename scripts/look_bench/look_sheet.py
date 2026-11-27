"""
Look sheet: where every beam lands, before a look reaches a rig.

For one rig, draws every look in the library twice - from above and from the
front - at its starting position, with the path each beam's landing point
traces over one cycle. Beside each look are the numbers a lighting designer
would check by eye: is it mirror-symmetric, are the beams evenly spaced, does
anything lean too far, does any head have to move faster than it can.

Usage (from the repository root, with the backend's Python):

    backend/venv/Scripts/python scripts/look_bench/look_sheet.py \
        --rigs club_night,small_nightclub,pro_beam_room --out look_sheets

Nothing here runs the engine: it calls the same pure functions the engine
calls, so it is instant and it is the looks themselves being judged.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("SECRET_KEY", "look-sheet-not-persisted")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.services.demo.venue_presets import VENUE_PRESETS, create_venue_rig  # noqa: E402
from app.services.effects import live_library  # noqa: E402
from app.services.effects import live_looks as LL  # noqa: E402
from app.services.effects import live_moves  # noqa: E402

STEPS = 96          # samples across one cycle
BPM = 128.0
FPS = 60.0


def movers_of(manager) -> list:
    return [f for f in manager.fixtures.values()
            if "pan" in f.channels and "tilt" in f.channels and float(f.pan_range or 0) > 0]


def trace(look: str, rig: LL.Rig, motion: LL.SectionMotion) -> Dict[str, np.ndarray]:
    """Pan, tilt and landing point for every head across one cycle."""
    # A fly-out takes two of the section's cycles; sample the whole of it.
    span_beats = motion.cycle_beats * (2.0 if LL.LOOKS[look].motion == "fly" else 1.0)
    beats = np.linspace(0.0, span_beats, STEPS, endpoint=False)
    pan = np.zeros((STEPS, len(rig.heads)))
    tilt = np.zeros_like(pan)
    land = np.full((STEPS, len(rig.heads), 2), np.nan)
    for i, b in enumerate(beats):
        for k, head in enumerate(rig.heads):
            p, t = LL.head_pan_tilt(look, head, rig, float(b), motion)
            pan[i, k], tilt[i, k] = p, t
            spot = LL.landing(head, p, t)
            if spot is not None:
                land[i, k] = (spot[0], spot[2])
    return {"beats": beats, "pan": pan, "tilt": tilt, "land": land}


def measure(rig: LL.Rig, tr: Dict[str, np.ndarray], motion: LL.SectionMotion, bounds) -> dict:
    heads = rig.heads
    pan, tilt, land = tr["pan"], tr["tilt"], tr["land"]

    # Mirror error: a head's landing against the reflection of its partner's.
    worst_mirror = 0.0
    pairs = 0
    for i, a in enumerate(heads):
        if a.u >= -1e-6:
            continue
        for j, b in enumerate(heads):
            # The partner is the head at the mirrored place AND the same height:
            # two trusses can share a depth.
            if b.row == a.row and abs(b.u + a.u) < 1e-6 and abs(b.y - a.y) < 1e-6:
                pairs += 1
                mirrored = land[:, j].copy()
                mirrored[:, 0] = 2 * rig.x_mid - mirrored[:, 0]
                worst_mirror = max(worst_mirror, float(np.nanmax(np.linalg.norm(land[:, i] - mirrored, axis=1))))
                break

    # Evenness: on each truss, how regular the gaps between neighbouring landings are.
    uneven = []
    for row in sorted({h.row for h in heads}):
        idx = [k for k, h in enumerate(heads) if h.row == row]
        if len(idx) < 3:
            continue
        xs = land[0, idx, 0]
        gaps = np.abs(np.diff(xs))
        if np.nanmean(gaps) > 0.05:
            uneven.append(float(np.nanstd(gaps) / np.nanmean(gaps)))

    x_lo, x_hi, z_lo, z_hi = bounds
    outside = int(np.sum((land[..., 0] < x_lo) | (land[..., 0] > x_hi) | (land[..., 1] < z_lo) | (land[..., 1] > z_hi)))

    # How fast a head has to turn to follow the look in real time.
    seconds_per_step = (float(tr["beats"][1] - tr["beats"][0]) * 60.0 / BPM)
    pan_rate = float(np.abs(np.diff(pan, axis=0, append=pan[:1])).max() / seconds_per_step)
    tilt_rate = float(np.abs(np.diff(tilt, axis=0, append=tilt[:1])).max() / seconds_per_step)

    return {
        "mirror_error_m": round(worst_mirror, 4), "mirror_pairs": pairs,
        "uneven_spacing": round(float(np.mean(uneven)), 3) if uneven else None,
        "max_lean_deg": round(float(np.abs(tilt).max()), 1),
        "max_pan_deg": round(float(np.abs(pan).max()), 1),
        "landings_outside_room": outside,
        "pan_rate_deg_s": round(pan_rate), "tilt_rate_deg_s": round(tilt_rate),
        "too_fast": pan_rate > live_moves.MAX_PAN_DEG_PER_S or tilt_rate > live_moves.MAX_TILT_DEG_PER_S,
    }


def sheet(rig_name: str, section: str, out: Path, looks: List[str]) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    manager, preset = create_venue_rig(rig_name)
    rig = LL.build_rig(movers_of(manager))
    motion = LL.SECTION_MOTION[section]
    heads = rig.heads
    hx = np.array([h.x for h in heads])
    hy = np.array([h.y for h in heads])
    hz = np.array([h.z for h in heads])
    half_w, half_d = preset.stage.width / 2.0, preset.stage.depth / 2.0
    # Beams landing a little way up the walls are normal; well beyond is not.
    margin = max(hy.max() * 1.0, 2.0)
    bounds = (-half_w - margin, half_w + margin, -half_d - margin, half_d + margin)

    plt.rcParams.update({"font.size": 8, "text.color": "#dddddd", "axes.labelcolor": "#bbbbbb",
                         "xtick.color": "#888888", "ytick.color": "#888888", "axes.edgecolor": "#444444"})
    cols = 3
    rows = math.ceil(len(looks) / cols)
    fig = plt.figure(figsize=(cols * 6.4, rows * 5.2 + 0.7), facecolor="#101012")
    outer = fig.add_gridspec(rows, cols, hspace=0.28, wspace=0.12, left=0.03, right=0.99, top=0.95, bottom=0.03)
    cmap = plt.get_cmap("coolwarm")
    span = max(1e-6, float(np.abs(hx - rig.x_mid).max()))
    report = {"rig": rig_name, "section": section, "movers": len(heads),
              "focus": [round(v, 2) for v in rig.focus], "looks": {}}

    for n, look in enumerate(looks):
        tr = trace(look, rig, motion)
        numbers = measure(rig, tr, motion, bounds)
        report["looks"][look] = numbers
        inner = outer[n // cols, n % cols].subgridspec(2, 1, height_ratios=[3.0, 1.5], hspace=0.08)
        top, front = fig.add_subplot(inner[0]), fig.add_subplot(inner[1])
        for ax in (top, front):
            ax.set_facecolor("#08080a")
            ax.tick_params(length=2)

        # From above: X across, Z down the page toward the audience.
        top.add_patch(plt.Rectangle((-half_w, -half_d), 2 * half_w, 2 * half_d, fill=False, ec="#3a3a3a", lw=0.8))
        top.axvline(rig.x_mid, color="#2c2c2c", lw=0.6)
        for k, head in enumerate(heads):
            colour = cmap(0.5 + 0.5 * (head.x - rig.x_mid) / span)
            path = tr["land"][:, k]
            top.plot(path[:, 0], path[:, 1], color=colour, lw=0.7, alpha=0.55)
            top.plot([head.x, path[0, 0]], [head.z, path[0, 1]], color=colour, lw=1.1, alpha=0.95)
            top.plot(path[0, 0], path[0, 1], "o", color=colour, ms=3.2)
        top.plot(hx, hz, "s", color="#e0e0e0", ms=3.2)
        top.plot(rig.focus[0], rig.focus[2], "+", color="#ffd866", ms=9, mew=1.2)
        top.set_xlim(bounds[0], bounds[1])
        top.set_ylim(bounds[3], bounds[2])          # upstage at the top
        top.set_aspect("equal", adjustable="box")
        top.set_xticks([])
        top.set_ylabel("upstage  <-  Z  ->  audience", fontsize=7)

        # From the front: X across, height up.
        front.axhline(0, color="#3a3a3a", lw=0.8)
        for k, head in enumerate(heads):
            colour = cmap(0.5 + 0.5 * (head.x - rig.x_mid) / span)
            front.plot([head.x, tr["land"][0, k, 0]], [head.y, 0.0], color=colour, lw=1.0, alpha=0.9)
        front.plot(hx, hy, "s", color="#e0e0e0", ms=3.0)
        front.set_xlim(bounds[0], bounds[1])
        front.set_ylim(-0.3, hy.max() * 1.12)
        front.set_ylabel("height", fontsize=7)

        flags = []
        if numbers["mirror_error_m"] > 0.01:
            flags.append("NOT MIRRORED")
        if numbers["too_fast"]:
            flags.append("TOO FAST")
        if numbers["landings_outside_room"]:
            flags.append("LANDS OUTSIDE")
        spacing = "-" if numbers["uneven_spacing"] is None else f"{numbers['uneven_spacing']:.2f}"
        cfg = LL.LOOKS[look]
        top.set_title(
            f"{look}   ({cfg.position} + {cfg.motion}{' -> ' + cfg.to if cfg.to else ''}, {cfg.phase})\n"
            f"mirror err {numbers['mirror_error_m']:.3f} m   uneven {spacing}   lean {numbers['max_lean_deg']:.0f} deg"
            f"   pan {numbers['max_pan_deg']:.0f} deg   {numbers['pan_rate_deg_s']}/{numbers['tilt_rate_deg_s']} deg/s"
            + ("   " + "  ".join(flags) if flags else ""),
            fontsize=8, color="#ff7b72" if flags else "#dddddd", loc="left")

    fig.suptitle(
        f"Look sheet - {preset.display_name} ({len(heads)} moving heads), sized for a {section} at {BPM:.0f} BPM.   "
        "Squares are heads; a line runs from each head to where its beam lands at the start of the look; the faint "
        "path is that landing point over one cycle.  Left heads blue, right heads red.  + is the point the rig plays to.",
        x=0.03, ha="left", fontsize=9, color="#dddddd")
    path = out / f"sheet_{rig_name}_{section}.png"
    fig.savefig(path, dpi=92, facecolor=fig.get_facecolor())
    plt.close(fig)
    report["picture"] = str(path)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rigs", default="club_night")
    ap.add_argument("--section", default="chorus", choices=sorted(LL.SECTION_MOTION))
    ap.add_argument("--out", default="look_sheets")
    ap.add_argument("--looks", default="library",
                    help="'library' (the movements the look library uses, the default), 'all' (every "
                         "generated combination), or a comma-separated list of movement names")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    names = list(VENUE_PRESETS) if args.rigs == "all" else [r.strip() for r in args.rigs.split(",") if r.strip()]
    if args.looks == "library":
        looks = sorted(set(live_library.MOVEMENT_TO_LOOK.values()))
    elif args.looks == "all":
        looks = list(LL.LOOKS)
    else:
        looks = [l.strip() for l in args.looks.split(",") if l.strip()]
    for name in names:
        report = sheet(name, args.section, out, looks)
        (out / f"sheet_{name}_{args.section}.json").write_text(json.dumps(report, indent=1))
        bad = {k: v for k, v in report["looks"].items()
               if v["mirror_error_m"] > 0.01 or v["too_fast"] or v["landings_outside_room"]}
        print(f"{name}: {report['movers']} heads, focus {report['focus']}, "
              f"{len(report['looks']) - len(bad)}/{len(report['looks'])} looks clean"
              + (f"; flagged: {json.dumps(bad)}" if bad else ""))
        print(f"  picture: {report['picture']}")


if __name__ == "__main__":
    main()
