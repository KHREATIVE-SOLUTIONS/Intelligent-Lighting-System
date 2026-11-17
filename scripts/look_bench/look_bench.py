"""
Look bench: see and score a whole show without a room, a rig or a login.

Plays one or more tracks back to back through the real analyser and the real
engine - one engine and one analyser for the whole sequence, as a DJ set would
run - on a virtual clock, far faster than real time. Every DMX frame the engine
emits is decoded through the rig's own channel map, and the run comes out as:

  * one picture: what each fixture did over time (colour x level), how bright
    the rig was against the music, where each moving head pointed, and which
    section the engine thought it was in against where the music really changed
  * numbers for the things a lighting designer would judge by eye

Usage (from the repository root, with the backend's Python):

    backend/venv/Scripts/python scripts/look_bench/look_bench.py \
        --rig club_night --tracks ibd,dense:30,ibd --out bench_out --label baseline

--rig     a demo preset name (club_night, small_nightclub, pro_beam_room ...)
          or db:<sqlite file>:<rig id> for a rig patched in a database
--tracks  comma separated. Synthetic: ibd (intro/build/drop), dense[:seconds],
          quiet, mix, song, click. Append @<dB> for gain, e.g. ibd@-6.
          Or a path to a WAV/FLAC file for real music.
--armed   also apply what "Start Capture" applies (the venue path). Off by
          default so results line up with audio fed over the WebSocket.
"""
from __future__ import annotations

import argparse
import asyncio
import colorsys
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
# Importing the app must not create a signing key or touch a real database.
os.environ.setdefault("SECRET_KEY", "look-bench-not-persisted")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from tests.musical import metrics as M  # noqa: E402
from tests.musical import synthetic_audio as sa  # noqa: E402
from app.services.audio.audio_analyzer import AudioAnalyzer  # noqa: E402

FPS = 60.0
SECTION_COLOURS = {
    "breakdown": "#3b4a6b", "verse": "#3f6b4f", "buildup": "#b8862b",
    "chorus": "#8a4fa3", "drop": "#c2413b", "unknown": "#444444",
}


# --------------------------------------------------------------------------
# Tracks
# --------------------------------------------------------------------------
@dataclass
class Track:
    name: str
    samples: np.ndarray
    sample_rate: int
    truth: Dict[str, float]            # label -> seconds into the track
    beat_times: Optional[np.ndarray] = None

    @property
    def duration_s(self) -> float:
        return len(self.samples) / float(self.sample_rate)


def load_track(spec: str) -> Track:
    gain_db = 0.0
    if "@" in spec and not Path(spec).exists():
        spec, g = spec.rsplit("@", 1)
        gain_db = float(g)
    name, _, arg = spec.partition(":")
    truth: Dict[str, float] = {}
    path = Path(spec)
    if path.exists():
        import soundfile as sf
        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        return Track(path.stem, data.mean(axis=1), int(sr), {})
    if name == "ibd":
        t = sa.intro_build_drop_track(bpm=128.0)
        bar = 60.0 / 128.0 * 4
        truth = {"build": sa.LEAD_IN_S + 8 * bar, "drop": float(t.drop_time)}
    elif name == "dense":
        t = sa.dense_loud_track(bpm=128.0, duration_s=float(arg or 30.0))
    elif name == "quiet":
        t = sa.sparse_quiet_track()
    elif name == "mix":
        t = sa.dj_mix_track(bpm=126.0, outgoing_bars=16, blend_bars=8, incoming_bars=16)
    elif name == "song":
        t = sa.song_track()
    elif name == "click":
        t = sa.click_track()
    else:
        raise SystemExit(f"unknown track '{spec}'")
    if gain_db:
        t = t.with_gain_db(gain_db)
    label = t.name + (f"@{gain_db:+.0f}dB" if gain_db else "")
    return Track(label, np.asarray(t.samples, dtype=np.float32), int(t.sample_rate), truth,
                 np.asarray(t.beat_times) if len(t.beat_samples) else None)


# --------------------------------------------------------------------------
# Rig
# --------------------------------------------------------------------------
async def load_rig(spec: str):
    if spec.startswith("db:"):
        # The rig id is after the last colon; a Windows path has one of its own.
        path, rig_id = spec[3:].rsplit(":", 1)
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        import app.models  # noqa: F401
        from app.services.rig.rig_loader import build_manager_for_rig_id
        db = create_async_engine(f"sqlite+aiosqlite:///{Path(path).as_posix()}")
        async with AsyncSession(db) as session:
            manager = await build_manager_for_rig_id(session, int(rig_id))
        await db.dispose()
        return manager, f"db rig {rig_id}"
    from app.services.demo.venue_presets import create_venue_rig
    manager, preset = create_venue_rig(spec)
    if manager is None:
        raise SystemExit(f"unknown rig preset '{spec}'")
    return manager, preset.display_name


@dataclass
class Tap:
    fid: str
    group: str
    x: float
    y: float
    z: float
    universe: int
    base: int
    ch: Dict[str, int]
    pan_range: float
    tilt_range: float

    @property
    def moves(self) -> bool:
        return "pan" in self.ch and "tilt" in self.ch and self.pan_range > 0


def build_taps(manager) -> List[Tap]:
    fixtures = list(manager.fixtures.values())
    prefixes = {f.id: re.sub(r"[_-]?\d+$", "", str(f.id)) for f in fixtures}
    use_prefix = 2 <= len(set(prefixes.values())) <= 14
    taps = []
    for f in fixtures:
        group = prefixes[f.id] if use_prefix else str(f.fixture_type)
        taps.append(Tap(str(f.id), group, float(f.x), float(f.y), float(f.z), int(f.universe or 0),
                        int(f.dmx_address) - 1, dict(f.channels or {}),
                        float(f.pan_range or 0.0), float(f.tilt_range or 0.0)))
    # Rows read top to bottom as: upstage to downstage, left to right.
    order: Dict[str, Tuple[float, float]] = {}
    for t in taps:
        zs = [u.z for u in taps if u.group == t.group]
        order[t.group] = (0 if any(u.moves for u in taps if u.group == t.group) else 1, float(np.mean(zs)))
    taps.sort(key=lambda t: (order[t.group], t.group, t.z, t.x))
    return taps


def decode(taps: List[Tap], frames: Dict[int, List[int]]):
    n = len(taps)
    level = np.zeros(n, dtype=np.float32)
    rgb = np.ones((n, 3), dtype=np.float32)
    pan = np.full(n, np.nan, dtype=np.float32)
    tilt = np.full(n, np.nan, dtype=np.float32)
    for i, t in enumerate(taps):
        frame = frames.get(t.universe)
        if frame is None:
            continue

        def get(name):
            off = t.ch.get(name)
            if off is None:
                return None
            idx = t.base + off
            return frame[idx] if 0 <= idx < 512 else None

        colour = [get("red"), get("green"), get("blue")]
        white = get("white") or 0
        dim = get("dimmer")
        if all(c is not None for c in colour):
            # A white emitter adds to all three; shown as a lift toward white.
            rgb[i] = np.minimum(1.0, (np.array(colour, dtype=np.float32) + white) / 255.0)
            peak = float(rgb[i].max())
            level[i] = (dim / 255.0 if dim is not None else 1.0) * peak
            if peak > 0:
                rgb[i] = rgb[i] / peak
        else:
            level[i] = dim / 255.0 if dim is not None else 0.0
        if t.moves:
            p, pf = get("pan"), get("pan_fine") or 0
            q, qf = get("tilt"), get("tilt_fine") or 0
            if p is not None and q is not None:
                pan[i] = (p * 256 + pf) / 65535.0
                tilt[i] = (q * 256 + qf) / 65535.0
    return level, rgb, pan, tilt


# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------
async def run(rig_spec: str, track_specs: List[str], armed: bool):
    manager, rig_name = await load_rig(rig_spec)
    engine = M.build_venue_engine()
    engine.set_fixture_manager(manager)
    if armed:
        from app.api.endpoints.audio import arm_show_for_live_audio
        arm_show_for_live_audio(engine)
    analyzer = AudioAnalyzer()
    taps = build_taps(manager)

    captured: Dict[int, List[int]] = {}
    engine.set_dmx_callback(lambda universe, frame: captured.__setitem__(int(universe), frame))

    times, levels, rgbs, pans, tilts, sections = [], [], [], [], [], []
    chunk_t, chunk_e = [], []
    bounds = []                                    # (name, start, end, truth, beats)
    clock = M._Clock()
    dt = 1.0 / FPS
    engine_time = 0.0
    offset = 0.0

    with M.virtual_clock(clock):
        for spec in track_specs:
            track = load_track(spec)
            analyzer.sample_rate = track.sample_rate
            n = (len(track.samples) // sa.CHUNK_SIZE) * sa.CHUNK_SIZE
            for start in range(0, n, sa.CHUNK_SIZE):
                chunk_end = offset + (start + sa.CHUNK_SIZE) / float(track.sample_rate)
                clock.t = chunk_end
                analysis = await analyzer.process_chunk(track.samples[start:start + sa.CHUNK_SIZE])
                kwargs = M.analysis_to_engine_kwargs(analysis)
                engine.update_audio(**kwargs)
                chunk_t.append(chunk_end)
                chunk_e.append(kwargs["energy"])
                while engine_time + dt <= chunk_end + 1e-9:
                    engine_time += dt
                    clock.t = engine_time
                    captured.clear()
                    engine.update(delta_time=dt)
                    lv, c, p, q = decode(taps, captured)
                    times.append(engine_time)
                    levels.append(lv)
                    rgbs.append(c)
                    pans.append(p)
                    tilts.append(q)
                    sections.append(M._engine_section(engine))
            end = offset + n / float(track.sample_rate)
            bounds.append((track.name, offset, end, track.truth,
                           None if track.beat_times is None else track.beat_times + offset))
            offset = end

    return {
        "rig_name": rig_name, "taps": taps, "t": np.array(times),
        "level": np.vstack(levels), "rgb": np.stack(rgbs),
        "pan": np.vstack(pans), "tilt": np.vstack(tilts), "sections": sections,
        "chunk_t": np.array(chunk_t), "chunk_e": np.array(chunk_e), "bounds": bounds,
    }


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------
def luminance_peaks(rig: np.ndarray, prominence: float = 0.2, reach: int = 12, merge: int = 5) -> np.ndarray:
    """Frames where total rig brightness peaks by at least `prominence`.

    A peak is the top of its neighbourhood (`merge` frames either side), and a
    plateau counts once, at its first frame. Without that, a held level whose
    frames differ in the third decimal place - which a change of colour is
    enough to cause - was counted as two or three peaks, and the count moved by
    one for reasons that had nothing to do with flashing.
    """
    idx = []
    n = len(rig)
    for i in range(1, n - 1):
        lo, hi = max(0, i - merge), min(n, i + merge + 1)
        if rig[i] < rig[lo:hi].max() - 1e-9:
            continue
        if i > lo and np.any(rig[lo:i] >= rig[i] - 1e-9):
            continue
        left = rig[max(0, i - reach):i + 1].min()
        right = rig[i:i + reach + 1].min()
        if rig[i] - max(left, right) >= prominence:
            idx.append(i)
    return np.array(idx, dtype=int)


def worst_per_second(times: np.ndarray) -> int:
    return max((int(np.sum((times >= x) & (times < x + 1.0))) for x in times), default=0)


def timeline(t: np.ndarray, sections: List[str]) -> List[Tuple[float, str]]:
    out, prev = [], None
    for ti, s in zip(t, sections):
        if s != prev:
            out.append((round(float(ti), 1), s))
            prev = s
    return out


def mirror_pairs(taps: List[Tap]) -> List[Tuple[int, int]]:
    pairs = []
    for i, a in enumerate(taps):
        if not a.moves or a.x >= -0.05:
            continue
        for j, b in enumerate(taps):
            if b.moves and b.group == a.group and abs(b.z - a.z) < 0.3 and abs(b.x + a.x) < 0.3:
                pairs.append((i, j))
                break
    return pairs


def corr(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    if a.std() < 1e-4 or b.std() < 1e-4:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def measure(res: dict, lo: float, hi: float) -> dict:
    t, taps = res["t"], res["taps"]
    m = (t >= lo) & (t < hi)
    level, rgb, pan, tilt = res["level"][m], res["rgb"][m], res["pan"][m], res["tilt"][m]
    sections = [s for s, keep in zip(res["sections"], m) if keep]
    rig = level.mean(axis=1)
    out: dict = {"seconds": round(hi - lo, 1), "sections": timeline(t[m] - lo, sections)}

    out["level"] = {
        "rig_mean": round(float(rig.mean()), 3), "rig_p5": round(float(np.percentile(rig, 5)), 3),
        "rig_p95": round(float(np.percentile(rig, 95)), 3),
        "fixture_peak": round(float(level.max()), 3),
        "pct_time_dark": round(float((rig < 0.01).mean() * 100), 1),
    }
    by_section = {}
    for name in sorted(set(sections)):
        sm = np.array([s == name for s in sections])
        by_section[name] = round(float(rig[sm].mean()), 3)
    out["level_by_section"] = by_section

    groups = sorted({tp.group for tp in taps})
    gl = {g: level[:, [i for i, tp in enumerate(taps) if tp.group == g]].mean(axis=1) for g in groups}
    out["group_mean_level"] = {g: round(float(v.mean()), 3) for g, v in gl.items()}
    # Do the fixture families do different things, or one thing at different sizes?
    diffs = []
    for a in range(len(groups)):
        for b in range(a + 1, len(groups)):
            c = corr(gl[groups[a]], gl[groups[b]])
            if c is not None:
                diffs.append(c)
    out["group_level_correlation_mean"] = round(float(np.mean(diffs)), 3) if diffs else None
    # Within a family: is there a chase, or is every fixture identical?
    spread = {}
    for g in groups:
        cols = [i for i, tp in enumerate(taps) if tp.group == g]
        if len(cols) > 1:
            spread[g] = round(float((level[:, cols].max(axis=1) - level[:, cols].min(axis=1)).mean()), 3)
    out["within_group_spread"] = spread

    lit = level > 0.03
    if lit.any():
        px = rgb[lit]
        mx, mn = px.max(axis=1), px.min(axis=1)
        sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
        hues = np.array([colorsys.rgb_to_hsv(*p)[0] for p in px[:: max(1, len(px) // 4000)]])
        ang = hues * 2 * np.pi
        resultant = float(np.hypot(np.cos(ang).mean(), np.sin(ang).mean()))
        mean_hue = float((np.arctan2(np.sin(ang).mean(), np.cos(ang).mean()) % (2 * np.pi)) / (2 * np.pi) * 360)
        out["colour"] = {
            "saturation_mean": round(float(sat.mean()), 3),
            "mean_hue_deg": round(mean_hue),
            # 0 = one hue all night, 1 = hues all round the wheel.
            "hue_variety": round(1.0 - resultant, 3),
        }

    movers = [i for i, tp in enumerate(taps) if tp.moves]
    if movers:
        pan_deg = (pan[:, movers] - 0.5) * np.array([taps[i].pan_range for i in movers])
        tilt_deg = (tilt[:, movers] - 0.5) * np.array([taps[i].tilt_range for i in movers])
        pan_pp = np.nanmax(pan_deg, axis=0) - np.nanmin(pan_deg, axis=0)
        tilt_pp = np.nanmax(tilt_deg, axis=0) - np.nanmin(tilt_deg, axis=0)
        step = np.maximum(np.abs(np.diff(pan_deg, axis=0)), np.abs(np.diff(tilt_deg, axis=0)))
        lit_step = np.where(level[1:, movers] > 0.1, step, 0.0)
        pc, tc = [], []
        for i, j in mirror_pairs(taps):
            a = corr(pan[:, i] - 0.5, -(pan[:, j] - 0.5))
            b = corr(tilt[:, i], tilt[:, j])
            if a is not None:
                pc.append(a)
            if b is not None:
                tc.append(b)
        out["movement"] = {
            "movers": len(movers),
            "pan_sweep_deg_median": round(float(np.median(pan_pp)), 1),
            "tilt_sweep_deg_median": round(float(np.median(tilt_pp)), 1),
            "biggest_step_deg_in_one_frame": round(float(np.nanmax(step)), 1),
            "biggest_step_deg_while_lit": round(float(np.nanmax(lit_step)), 1),
            "frames_stepping_over_8deg_while_lit": int((lit_step > 8.0).any(axis=1).sum()),
            # +1 = left and right mirror each other, 0 = unrelated, -1 = all heads move as one.
            "mirror_symmetry_pan": round(float(np.mean(pc)), 2) if pc else None,
            "mirror_symmetry_tilt": round(float(np.mean(tc)), 2) if tc else None,
        }

    peaks = luminance_peaks(rig)
    white = (level > 0.88) & (rgb.min(axis=2) > 0.97)
    flash = white.mean(axis=1) > 0.5
    edges = np.where(flash[1:] & ~flash[:-1])[0] + 1
    tt = t[m]
    out["flash"] = {
        "luminance_peaks": int(len(peaks)), "worst_luminance_peaks_in_1s": worst_per_second(tt[peaks]),
        "full_white_flashes": int(len(edges)), "worst_white_flashes_in_1s": worst_per_second(tt[edges]),
    }
    return out


def summarise(res: dict) -> dict:
    report = {"rig": res["rig_name"], "fixtures": len(res["taps"]), "tracks": []}
    for name, lo, hi, truth, _ in res["bounds"]:
        entry = {"track": name, "starts_s": round(lo, 1), **measure(res, lo, hi)}
        if "drop" in truth:
            t, rig = res["t"], res["level"].mean(axis=1)
            d = lo + truth["drop"]
            pre = rig[(t >= d - 8) & (t < d)].mean()
            post = rig[(t >= d) & (t < d + 8)].mean()
            names = [s for ti, s in zip(t, res["sections"]) if d - 1.0 <= ti < d + 4.0]
            hit = next((ti for ti, s in zip(t, res["sections"]) if ti >= d - 1.0 and s == "drop" and ti < d + 4.0), None)
            entry["drop"] = {
                "true_s": round(truth["drop"], 1),
                "labelled_drop_at_s": None if hit is None else round(float(hit - lo), 1),
                "caught": "drop" in names,
                "level_8s_before": round(float(pre), 3), "level_8s_after": round(float(post), 3),
            }
        report["tracks"].append(entry)
    return report


# --------------------------------------------------------------------------
# Picture
# --------------------------------------------------------------------------
def draw(res: dict, report: dict, path: Path, label: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t, taps = res["t"], res["taps"]
    level, rgb, pan, tilt = res["level"], res["rgb"], res["pan"], res["tilt"]
    rig = level.mean(axis=1)
    total = float(t[-1])
    movers = [i for i, tp in enumerate(taps) if tp.moves]

    plt.rcParams.update({"font.size": 9, "text.color": "#dddddd", "axes.labelcolor": "#bbbbbb",
                         "xtick.color": "#999999", "ytick.color": "#999999", "axes.edgecolor": "#444444"})
    heights = [0.5, max(2.6, 0.13 * len(taps)), 1.5, 1.6, 1.6] if movers else [0.5, max(2.6, 0.13 * len(taps)), 1.5]
    fig, axes = plt.subplots(len(heights), 1, figsize=(max(14.0, min(40.0, total / 6.0)), sum(heights) + 1.6),
                             sharex=True, gridspec_kw={"height_ratios": heights, "hspace": 0.12},
                             facecolor="#101012")
    for ax in axes:
        ax.set_facecolor("#08080a")

    def marks(ax, text=False):
        for name, lo, hi, truth, _ in res["bounds"]:
            ax.axvline(lo, color="#888888", lw=0.8)
            for key, at in truth.items():
                ax.axvline(lo + at, color="#ffffff", lw=0.9, ls=(0, (4, 3)))
                if text:
                    ax.text(lo + at, 1.02, f"true {key}", transform=ax.get_xaxis_transform(),
                            ha="center", va="bottom", fontsize=8, color="#ffffff")
            if text:
                ax.text(lo + 0.3, 1.5, name, transform=ax.get_xaxis_transform(), ha="left", va="bottom",
                        fontsize=9, color="#9fc5ff")

    # 1. what the engine called each moment
    ax = axes[0]
    for (start, name), nxt in zip(timeline(t, res["sections"]), timeline(t, res["sections"])[1:] + [(total, "")]):
        ax.axvspan(start, nxt[0], color=SECTION_COLOURS.get(name, "#444444"))
        if nxt[0] - start > total * 0.02:
            ax.text((start + nxt[0]) / 2, 0.5, name, ha="center", va="center", fontsize=8, color="#ffffff")
    ax.set_yticks([])
    ax.set_ylabel("section", rotation=0, ha="right", va="center")
    marks(ax, text=True)

    # 2. the show: one row per fixture, colour x level, gamma-lifted so low levels read
    ax = axes[1]
    bins = np.arange(0.0, total, 0.05)
    idx = np.clip(np.searchsorted(t, bins), 0, len(t) - 1)
    img = (rgb[idx] * level[idx][:, :, None]) ** (1 / 2.2)
    ax.imshow(np.transpose(img, (1, 0, 2)), aspect="auto", interpolation="nearest",
              extent=(0, total, len(taps), 0))
    ticks, names, prev = [], [], None
    for row, tp in enumerate(taps):
        if tp.group != prev:
            if prev is not None:
                ax.axhline(row, color="#101012", lw=2.0)
            rows = [r for r, u in enumerate(taps) if u.group == tp.group]
            ticks.append(np.mean(rows) + 0.5)
            names.append(f"{tp.group} ({len(rows)})")
            prev = tp.group
    ax.set_yticks(ticks)
    ax.set_yticklabels(names)
    marks(ax)

    # 3. how bright against how loud
    ax = axes[2]
    ax.fill_between(res["chunk_t"], 0, res["chunk_e"], color="#2f3a4a", lw=0, label="music energy")
    ax.plot(t, rig, color="#ffffff", lw=0.8, label="rig level")
    ax.set_ylim(0, 1.02)
    ax.set_ylabel("level")
    ax.legend(loc="upper right", fontsize=7, frameon=False, ncol=2)
    marks(ax)

    # 4/5. where the heads point: left of centre drawn cool, right of centre warm
    if movers:
        xs = np.array([taps[i].x for i in movers])
        span = max(1e-6, float(np.abs(xs).max()))
        cmap = plt.get_cmap("coolwarm")
        for ax, data, ranges, name in (
            (axes[3], pan, [taps[i].pan_range for i in movers], "pan  deg"),
            (axes[4], tilt, [taps[i].tilt_range for i in movers], "tilt  deg"),
        ):
            for k, i in enumerate(movers):
                ax.plot(t, (data[:, i] - 0.5) * ranges[k], lw=0.6, color=cmap(0.5 + 0.5 * xs[k] / span), alpha=0.85)
            ax.axhline(0, color="#444444", lw=0.6)
            ax.set_ylabel(name)
            marks(ax)
    axes[-1].set_xlabel("seconds")
    axes[-1].set_xlim(0, total)

    lines = [f"{label}   |   rig: {res['rig_name']} ({len(taps)} fixtures)   |   left heads blue, right heads red"]
    for tr in report["tracks"]:
        mv = tr.get("movement", {})
        col = tr.get("colour", {})
        drop = tr.get("drop")
        lines.append(
            f"{tr['track']}: level {tr['level']['rig_mean']:.2f} (dark {tr['level']['pct_time_dark']:.0f}%)  "
            f"sat {col.get('saturation_mean', 0):.2f}  hue variety {col.get('hue_variety', 0):.2f}  "
            f"pan sweep {mv.get('pan_sweep_deg_median', 0):.0f} deg  tilt {mv.get('tilt_sweep_deg_median', 0):.0f} deg  "
            f"mirror pan/tilt {mv.get('mirror_symmetry_pan')}/{mv.get('mirror_symmetry_tilt')}  "
            f"lit step {mv.get('biggest_step_deg_while_lit', 0):.0f} deg  "
            f"peaks/s {tr['flash']['worst_luminance_peaks_in_1s']}"
            + ("" if not drop else f"  drop {'caught' if drop['caught'] else 'MISSED'} "
                                   f"({drop['level_8s_before']:.2f}->{drop['level_8s_after']:.2f})")
        )
    fig.suptitle("\n".join(lines), x=0.01, ha="left", fontsize=9, color="#dddddd", y=0.995, va="top")
    fig.subplots_adjust(top=1 - (0.5 + 0.2 * len(lines)) / (sum(heights) + 1.6), left=0.07, right=0.995, bottom=0.06)
    fig.savefig(path, dpi=110, facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rig", default="club_night")
    ap.add_argument("--tracks", default="ibd,dense:30,ibd")
    ap.add_argument("--out", default="look_bench_out")
    ap.add_argument("--label", default="run")
    ap.add_argument("--armed", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    res = asyncio.run(run(args.rig, [s.strip() for s in args.tracks.split(",") if s.strip()], args.armed))
    report = summarise(res)
    report["label"] = args.label
    (out / f"{args.label}.json").write_text(json.dumps(report, indent=1))
    draw(res, report, out / f"{args.label}.png", args.label)
    for tr in report["tracks"]:
        print(json.dumps({k: tr[k] for k in tr if k not in ("group_mean_level", "within_group_spread")}))
    print(f"picture: {out / (args.label + '.png')}")


if __name__ == "__main__":
    main()
