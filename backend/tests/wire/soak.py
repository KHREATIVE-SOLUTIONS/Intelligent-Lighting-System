"""
Soak: continuous music into the real backend, one row of measurements a minute,
and a verdict against the G1 pass line of docs/ASSESSMENT_AND_ROADMAP_2026-11.md:

    eight hours with flat memory, steady 40 fps and no gap over 100 ms.

``run_soak`` produces the rows (and appends each to a JSON-lines file as it is
measured, so a run that is cut short keeps what it saw). ``evaluate`` turns rows into
a verdict and touches nothing else, so it can be unit-tested and re-run on a saved file.
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from . import harness as H


@dataclass
class SoakLimits:
    """The pass line. Changing a number here changes what "passed the soak" means."""

    fps_target: float = 40.0
    fps_tolerance: float = 0.5          # every minute must average within this of target
    gap_ms_max: float = 100.0           # no gap between frames longer than this
    # "Flat memory": the last quarter of the run against the first quarter after
    # warm-up may differ by the larger of these two.
    mem_growth_mb: float = 20.0
    mem_growth_fraction: float = 0.05
    warmup_minutes: int = 10            # capped at a fifth of the run
    min_minutes_for_memory: int = 8     # fewer samples than this cannot show a trend


def _median(values) -> float:
    return float(np.median(np.asarray(values, dtype=float)))


def evaluate(rows: list, expected_minutes: Optional[int] = None,
             limits: Optional[SoakLimits] = None) -> dict:
    """Judge soak rows. ``passed`` is True only if every check passed.

    A check whose evidence is missing reports ``passed: None`` and fails the run:
    an unmeasured soak has not passed.
    """
    limits = limits or SoakLimits()
    checks: dict = {}
    n = len(rows)

    def check(name: str, passed, detail: str) -> None:
        checks[name] = {"passed": passed, "detail": detail}

    if n == 0:
        check("complete", False, "no rows were recorded")
        return {"passed": False, "minutes": 0, "checks": checks, "limits": asdict(limits)}

    if expected_minutes is not None:
        check("complete", n >= expected_minutes,
              f"{n} of {expected_minutes} minutes recorded")

    dead = [r["minute"] for r in rows if not r.get("backend_alive", True)]
    check("backend_alive", not dead,
          "backend ran throughout" if not dead else f"backend was down at minute {dead[0]}")

    # steady frame rate, every minute
    fps = [(r["minute"], r.get("fps")) for r in rows]
    off = [(m, f) for m, f in fps
           if f is None or abs(f - limits.fps_target) > limits.fps_tolerance]
    measured = [f for _, f in fps if f is not None]
    span = f"{min(measured)}-{max(measured)} fps" if measured else "no frames"
    check("frame_rate", not off,
          f"{span} over {n} minutes" + (f"; outside {limits.fps_target}±{limits.fps_tolerance} "
                                        f"in {len(off)} minutes, first at minute {off[0][0]}" if off else ""))

    # no long gap
    gaps = [(r["minute"], r.get("gap_ms_max")) for r in rows]
    long_gaps = [(m, g) for m, g in gaps if g is None or g > limits.gap_ms_max]
    worst = max((g for _, g in gaps if g is not None), default=None)
    check("frame_gap", not long_gaps,
          f"longest gap {worst} ms" + (f"; over {limits.gap_ms_max} ms in {len(long_gaps)} "
                                       f"minutes, first at minute {long_gaps[0][0]}" if long_gaps else ""))

    # flat memory
    rss = [r.get("rss_mb") for r in rows]
    if any(v is None for v in rss) or n < limits.min_minutes_for_memory:
        check("memory_flat", None,
              f"{n} samples; at least {limits.min_minutes_for_memory} are needed to judge a trend")
    else:
        warm = min(limits.warmup_minutes, n // 5)
        body = rss[warm:]
        q = max(1, len(body) // 4)
        early, late = _median(body[:q]), _median(body[-q:])
        allowed = max(limits.mem_growth_mb, early * limits.mem_growth_fraction)
        slope_mb_per_h = float(np.polyfit(np.arange(len(body)), np.asarray(body, dtype=float), 1)[0] * 60.0)
        check("memory_flat", (late - early) <= allowed,
              f"{early:.1f} MB early, {late:.1f} MB late ({late - early:+.1f} MB, "
              f"allowed +{allowed:.1f}); trend {slope_mb_per_h:+.2f} MB/h; peak {max(rss):.1f} MB")

    # the wire stayed honest
    faults = []
    send_errors = max((r.get("send_errors") or 0) for r in rows)
    if send_errors:
        faults.append(f"{send_errors} send errors")
    stray = sum((r.get("stray_channels") or 0) for r in rows)
    if stray:
        faults.append(f"{stray} non-zero channels outside the patch")
    foreign = sorted({u for r in rows for u in (r.get("unpatched_universes") or [])})
    if foreign:
        faults.append(f"unpatched universes transmitted: {foreign}")
    malformed = max((r.get("malformed_packets") or 0) for r in rows)
    if malformed:
        faults.append(f"{malformed} malformed packets")
    breaks = sum((r.get("seq_breaks") or 0) for r in rows)
    if breaks:
        faults.append(f"{breaks} sequence breaks (a frame lost, repeated or reordered)")
    check("wire_integrity", not faults, "; ".join(faults) if faults else
          "0 send errors, 0 stray channels, 0 malformed packets, 0 sequence breaks")

    reconnects = max((r.get("feed_reconnects") or 0) for r in rows)
    check("audio_feed", reconnects == 0,
          "audio feed held" if not reconnects else f"audio feed reconnected {reconnects} times")

    return {
        "passed": all(c["passed"] is True for c in checks.values()),
        "minutes": n,
        "checks": checks,
        "limits": asdict(limits),
    }


def format_verdict(verdict: dict) -> str:
    lines = [f"SOAK {'PASS' if verdict['passed'] else 'FAIL'} over {verdict['minutes']} minutes"]
    for name, c in verdict["checks"].items():
        mark = {True: "ok  ", False: "FAIL", None: "n/a "}[c["passed"]]
        lines.append(f"  {mark} {name}: {c['detail']}")
    return "\n".join(lines)


def load_rows(path: Path) -> list:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


async def run_soak(cfg: H.WireConfig, minutes: int, rows_path: Optional[Path] = None,
                   on_row: Optional[Callable[[dict], None]] = None,
                   template: str = "Small Club") -> dict:
    """Boot a fresh backend, play music for ``minutes``, return rows and a verdict."""
    sa = H.synthetic_audio(cfg.backend)
    if cfg.db_path.exists():
        cfg.db_path.unlink()
    rows_path = Path(rows_path) if rows_path else cfg.out / "soak_rows.jsonl"
    rows_path.write_text("")
    rows: list = []
    cap = H.Capture(cfg.art_port)
    srv = H.Server(cfg, "soak")
    client = None
    try:
        srv.wait_http()
        client, token, _ = await H.first_run_setup(cfg, srv)
        rig_id = await H.rig_from_template(client, template, rig_name="Soak")
        patch = H.read_patch(cfg.db_path, rig_id)

        # As a DJ plays them: a two-record mix, then a track with a build and a drop.
        playlist = [
            H.pcm_chunks(sa.dj_mix_track(bpm=126.0, outgoing_bars=12, blend_bars=8, incoming_bars=12).samples,
                         sa.CHUNK_SIZE),
            H.pcm_chunks(sa.intro_build_drop_track(bpm=128.0).samples, sa.CHUNK_SIZE),
        ]
        state = {"reconnects": 0, "tracks": 0, "ws_msgs": 0, "stop": False}
        start_usage = H.process_tree_usage(srv.proc.pid)

        async def feeder() -> None:
            while not state["stop"] and srv.alive():
                try:
                    async with H.AudioFeed(cfg, token, sa.SAMPLE_RATE, sa.CHUNK_SIZE) as feed:
                        while not state["stop"]:
                            await feed.play(playlist[state["tracks"] % len(playlist)])
                            state["tracks"] += 1
                            state["ws_msgs"] += len(feed.seen)
                            feed.seen.clear()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if state["stop"]:
                        return
                    state["reconnects"] += 1
                    await asyncio.sleep(1.0)

        feed_task = asyncio.create_task(feeder())
        t_begin = time.perf_counter()
        try:
            for minute in range(1, minutes + 1):
                t0 = t_begin + (minute - 1) * 60.0
                t1 = t0 + 60.0
                # A moment past the minute, so its last packets have been read in.
                await asyncio.sleep(max(0.0, t1 + 0.25 - time.perf_counter()))
                alive = srv.alive()
                a = H.analyse(cap, patch, t0, t1)
                cap.prune(t1)
                tx = a["transport"]
                level, flash = a.get("level", {}), a.get("flash", {})
                row = {
                    "minute": minute,
                    "backend_alive": alive,
                    "fps": min((u["fps"] for u in tx.values()), default=None),
                    "gap_ms_p99": max((u["gap_ms_p99"] for u in tx.values()), default=None),
                    "gap_ms_max": max((u["gap_ms_max"] for u in tx.values()), default=None),
                    "seq_breaks": sum(u["seq_breaks"] for u in tx.values()),
                    "stray_channels": a["nonzero_channels_outside_patch"],
                    "unpatched_universes": a["unpatched_universes_transmitted"],
                    "malformed_packets": int(sum(cap.bad.values())),
                    "rig_mean": level.get("rig_mean"), "rig_max": level.get("rig_max"),
                    "dark_pct": level.get("pct_time_rig_dark"),
                    "rig_flash_worst_1s": flash.get("rig_worst_flashes_in_1s"),
                    "feed_reconnects": state["reconnects"],
                    "tracks_played": state["tracks"],
                    "log_kb": srv.log_path.stat().st_size // 1024,
                    "rss_mb": None, "threads": None, "cpu_s": None,
                    "send_errors": None, "health": None,
                }
                if alive:
                    row["rss_mb"], row["threads"], row["cpu_s"] = H.process_tree_usage(srv.proc.pid)
                    try:
                        h = (await client.get("/api/health")).json()
                        row["health"] = h.get("status")
                        row["send_errors"] = (h.get("dmx_detail") or {}).get("send_error_count")
                    except Exception as exc:
                        row["health"] = f"unreachable: {type(exc).__name__}"
                rows.append(row)
                with rows_path.open("a") as f:
                    f.write(json.dumps(row) + "\n")
                if on_row:
                    on_row(row)
                if not alive:
                    break
        finally:
            state["stop"] = True
            feed_task.cancel()
            await asyncio.gather(feed_task, return_exceptions=True)
    finally:
        if client is not None:
            await client.aclose()
        srv.hard_kill()
        cap.close()

    verdict = evaluate(rows, expected_minutes=minutes)
    report = {
        "requested_minutes": minutes, "template": template,
        "start_rss_threads_cpu": start_usage if rows else None,
        "capture_anomalies": dict(cap.bad), "packets_captured": cap.total,
        "verdict": verdict, "rows": rows,
    }
    (cfg.out / "soak_report.json").write_text(json.dumps(report, indent=1))
    return report
