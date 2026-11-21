"""
Drop bench: how often is the drop caught, and how often is one invented?

The November 2026 assessment (finding D2) measured the drop on the wire: caught
in 8 of 12 single plays and in 2 of 4 back to back in the soak, with the misses
all depending on what had been played before. Those runs need a booted backend
and real time. This is the closest offline equivalent: the same synthetic tracks,
through the real analyser and the real engine, on the look bench's virtual
clock, with nothing downloaded and nothing sent anywhere.

  * 12 single plays. Each is a fresh analyser and engine ("a fresh boot"), an
    optional prelude, then the intro/build/drop track. Only the last drop is
    scored. The preludes are the histories the wire passes used (cold, after
    14 s and 30 s of dense music, after an earlier drop) plus gain changes.
  * 4 back to back. One boot, the soak's playlist: DJ mix, drop track, four
    times over. All four drops are scored.
  * False drops. Every time the engine enters `drop` outside a true drop's
    window, in the plays above and in material that has no drop at all.
  * Other builds. The drop track at other tempos and build lengths, cold and
    after loud music. Not part of the 12 + 4: they are there to show the
    detector was not fitted to one render.

A drop is "caught" by the look bench's own rule: the engine's section reads
`drop` at some frame from 1 s before the true drop to 4 s after it.

Usage (from the repository root, with the backend's Python):

    backend/venv/Scripts/python scripts/look_bench/drop_bench.py
    backend/venv/Scripts/python scripts/look_bench/drop_bench.py --json out.json -v
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import look_bench as LB  # noqa: E402  (sets up sys.path and the environment)

from tests.musical import metrics as M  # noqa: E402
from tests.musical import synthetic_audio as sa  # noqa: E402
from app.services.audio.audio_analyzer import AudioAnalyzer  # noqa: E402

FPS = 60.0
CAUGHT_FROM_S = -1.0      # the look bench's window around the true drop
CAUGHT_TO_S = 4.0

# (label, prelude tracks, the scored drop track)
SINGLE_PLAYS: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    ("cold", (), "ibd"),
    ("cold, -6 dB", (), "ibd@-6"),
    ("cold, +6 dB", (), "ibd@6"),
    ("cold, -12 dB", (), "ibd@-12"),
    ("after 14 s dense", ("dense:14",), "ibd"),
    ("after 30 s dense", ("dense:30",), "ibd"),
    ("after 14 s dense, -6 dB", ("dense:14@-6",), "ibd@-6"),
    ("after 14 s dense at +6 dB", ("dense:14@6",), "ibd"),
    ("after a drop", ("ibd",), "ibd"),
    ("after a drop and 30 s dense", ("ibd", "dense:30"), "ibd"),
    ("after a DJ mix", ("mix",), "ibd"),
    ("after a quiet track", ("quiet",), "ibd"),
)

# venue_soak.py's playlist, cut to the four drops the soak sampled.
BACK_TO_BACK: Tuple[str, ...] = ("soakmix", "ibd") * 4

# Material with no drop in it. Anything labelled `drop` here is false.
NO_DROP: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("dense 60 s", ("dense:60",)),
    ("quiet", ("quiet",)),
    ("DJ mix", ("mix",)),
    ("song", ("song",)),
    ("click", ("click",)),
    ("build that never drops", ("nodrop",)),
    ("build, small hit, breakdown", ("falseimpact",)),
    ("dense then quiet then dense", ("dense:20", "quiet", "dense:20")),
    ("quiet then dense", ("quiet", "dense:30")),
    ("dense at +6 dB then dense", ("dense:20@6", "dense:20")),
    ("dense at -12 dB then dense", ("dense:20@-12", "dense:30")),
    ("dense then song", ("dense:20", "song")),
    ("dense then DJ mix", ("dense:20", "mix")),
    ("dense then click", ("dense:14", "click")),
    ("dense then build that never drops", ("dense:14", "nodrop")),
    ("dense then build, small hit, breakdown", ("dense:14", "falseimpact")),
)

# The drop track rendered differently: `ibdv:<bpm>:<build bars>`. Held out.
OTHER_BUILDS: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    ("140 BPM, 16-bar build, cold", (), "ibdv:140:16"),
    ("140 BPM, 16-bar build, after dense", ("dense:20",), "ibdv:140:16"),
    ("100 BPM, 8-bar build, cold", (), "ibdv:100:8"),
    ("100 BPM, 8-bar build, after dense", ("dense:20",), "ibdv:100:8"),
    ("128 BPM, 4-bar build, cold", (), "ibdv:128:4"),
    ("128 BPM, 4-bar build, after dense", ("dense:20",), "ibdv:128:4"),
    ("174 BPM, 16-bar build, after a DJ mix", ("mix",), "ibdv:174:16"),
    ("120 BPM, 8-bar build, after song", ("song",), "ibdv:120:8"),
)


def load(spec: str) -> LB.Track:
    """look_bench's tracks, plus the ones this bench needs."""
    name, _, gain = spec.partition("@")
    extra = None
    truth: Dict[str, float] = {}
    if name.startswith("ibdv:"):
        _, bpm, build_bars = name.split(":")
        extra = sa.intro_build_drop_track(bpm=float(bpm), build_bars=int(build_bars))
        truth = {"drop": float(extra.drop_time)}
    elif name == "soakmix":
        extra = sa.dj_mix_track(bpm=126.0, outgoing_bars=12, blend_bars=8, incoming_bars=12)
    elif name in ("nodrop", "falseimpact"):
        from tests.musical import test_musical_behaviour as T
        extra = T.build_without_drop_track() if name == "nodrop" else T.build_with_a_false_impact_track()
    if extra is None:
        return LB.load_track(spec)
    if gain:
        extra = extra.with_gain_db(float(gain))
    return LB.Track(extra.name, np.asarray(extra.samples, dtype=np.float32), int(extra.sample_rate), truth)


async def play(specs: Tuple[str, ...]) -> dict:
    """One boot: these tracks back to back through one analyser and one engine."""
    engine = M.build_venue_engine()
    engine.set_dmx_callback(lambda universe, frame: None)
    analyzer = AudioAnalyzer()
    clock = M._Clock()
    dt = 1.0 / FPS
    engine_time = 0.0
    offset = 0.0
    times: List[float] = []
    sections: List[str] = []
    drops: List[float] = []          # true drop times on the run's clock
    with M.virtual_clock(clock):
        for spec in specs:
            track = load(spec)
            analyzer.sample_rate = track.sample_rate
            n = (len(track.samples) // sa.CHUNK_SIZE) * sa.CHUNK_SIZE
            for start in range(0, n, sa.CHUNK_SIZE):
                chunk_end = offset + (start + sa.CHUNK_SIZE) / float(track.sample_rate)
                clock.t = chunk_end
                analysis = await analyzer.process_chunk(track.samples[start:start + sa.CHUNK_SIZE])
                engine.update_audio(**M.analysis_to_engine_kwargs(analysis))
                while engine_time + dt <= chunk_end + 1e-9:
                    engine_time += dt
                    clock.t = engine_time
                    engine.update(delta_time=dt)
                    times.append(engine_time)
                    sections.append(M._engine_section(engine))
            if "drop" in track.truth:
                drops.append(offset + track.truth["drop"])
            offset += n / float(track.sample_rate)
    return {"t": np.array(times), "sections": sections, "drops": drops}


def score(run: dict) -> dict:
    """Per true drop: caught and how late. Plus every drop entered outside one."""
    t, sections, drops = run["t"], run["sections"], run["drops"]
    is_drop = np.array([s == "drop" for s in sections])
    entries = t[np.where(is_drop[1:] & ~is_drop[:-1])[0] + 1] if len(t) > 1 else np.array([])
    results = []
    for d in drops:
        window = (t >= d + CAUGHT_FROM_S) & (t < d + CAUGHT_TO_S)
        hit = t[window & is_drop]
        results.append({
            "true_s": round(float(d), 2),
            "caught": bool(len(hit)),
            "late_ms": None if not len(hit) else round(float(hit[0] - d) * 1000.0),
        })
    false = [
        round(float(e), 2) for e in entries
        if not any(d + CAUGHT_FROM_S <= e < d + CAUGHT_TO_S for d in drops)
    ]
    timeline = LB.timeline(t, sections)
    return {"drops": results, "false_drops_at_s": false, "sections": timeline}


async def bench(verbose: bool = False) -> dict:
    report: dict = {"single": [], "back_to_back": None, "no_drop": [], "other_builds": []}

    def note(label: str, scored: dict) -> None:
        if verbose:
            print(f"    {label}: {scored['sections']}", flush=True)

    for label, prelude, track in SINGLE_PLAYS:
        scored = score(await play(prelude + (track,)))
        last = scored["drops"][-1]
        report["single"].append({
            "play": label, "tracks": list(prelude + (track,)), "caught": last["caught"],
            "late_ms": last["late_ms"], "false_drops_at_s": scored["false_drops_at_s"],
        })
        note(label, scored)

    scored = score(await play(BACK_TO_BACK))
    report["back_to_back"] = {
        "tracks": list(BACK_TO_BACK), "drops": scored["drops"],
        "false_drops_at_s": scored["false_drops_at_s"],
    }
    note("back to back", scored)

    for label, tracks in NO_DROP:
        scored = score(await play(tracks))
        report["no_drop"].append({
            "play": label, "tracks": list(tracks), "false_drops_at_s": scored["false_drops_at_s"],
        })
        note(label, scored)

    for label, prelude, track in OTHER_BUILDS:
        scored = score(await play(prelude + (track,)))
        last = scored["drops"][-1]
        report["other_builds"].append({
            "play": label, "tracks": list(prelude + (track,)), "caught": last["caught"],
            "late_ms": last["late_ms"], "false_drops_at_s": scored["false_drops_at_s"],
        })
        note(label, scored)

    b2b = report["back_to_back"]
    report["totals"] = {
        "single_caught": sum(1 for p in report["single"] if p["caught"]),
        "single_plays": len(report["single"]),
        "back_to_back_caught": sum(1 for d in b2b["drops"] if d["caught"]),
        "back_to_back_drops": len(b2b["drops"]),
        "false_drops_in_drop_plays": sum(len(p["false_drops_at_s"]) for p in report["single"])
        + len(b2b["false_drops_at_s"]),
        "false_drops_in_no_drop_material": sum(len(p["false_drops_at_s"]) for p in report["no_drop"]),
        "other_builds_caught": sum(1 for p in report["other_builds"] if p["caught"]),
        "other_builds_plays": len(report["other_builds"]),
        "false_drops_in_other_builds": sum(len(p["false_drops_at_s"]) for p in report["other_builds"]),
    }
    return report


def show(report: dict) -> None:
    def late(ms: Optional[int]) -> str:
        return "" if ms is None else f"{ms:+d} ms"

    print("\nSingle plays (fresh boot each; the last drop is scored)")
    for p in report["single"]:
        extra = f"   false drops at {p['false_drops_at_s']}" if p["false_drops_at_s"] else ""
        print(f"  {'HIT ' if p['caught'] else 'MISS'}  {p['play']:<40} {late(p['late_ms']):>9}{extra}")
    b2b = report["back_to_back"]
    print("\nBack to back (one boot: DJ mix, drop track, four times)")
    for i, d in enumerate(b2b["drops"], 1):
        print(f"  {'HIT ' if d['caught'] else 'MISS'}  drop {i} at {d['true_s']:>6.1f} s {late(d['late_ms']):>19}")
    if b2b["false_drops_at_s"]:
        print(f"        false drops at {b2b['false_drops_at_s']}")
    print("\nMaterial with no drop")
    for p in report["no_drop"]:
        n = len(p["false_drops_at_s"])
        print(f"  {'ok   ' if not n else 'FALSE'} {p['play']:<40} {p['false_drops_at_s'] if n else ''}")
    print("\nOther builds (held out; not part of the 12 + 4)")
    for p in report["other_builds"]:
        extra = f"   false drops at {p['false_drops_at_s']}" if p["false_drops_at_s"] else ""
        print(f"  {'HIT ' if p['caught'] else 'MISS'}  {p['play']:<40} {late(p['late_ms']):>9}{extra}")
    t = report["totals"]
    print(
        f"\nTOTAL  single {t['single_caught']}/{t['single_plays']}   "
        f"back to back {t['back_to_back_caught']}/{t['back_to_back_drops']}   "
        f"false drops: {t['false_drops_in_drop_plays']} in drop plays, "
        f"{t['false_drops_in_no_drop_material']} in no-drop material\n"
        f"       other builds {t['other_builds_caught']}/{t['other_builds_plays']}, "
        f"{t['false_drops_in_other_builds']} false"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", help="also write the full report here")
    ap.add_argument("-v", "--verbose", action="store_true", help="print each play's section timeline")
    args = ap.parse_args()
    report = asyncio.run(bench(args.verbose))
    show(report)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
