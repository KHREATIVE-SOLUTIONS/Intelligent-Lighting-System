"""
Soak: continuous music into the real backend, one row of measurements a minute,
and a verdict against the G1 pass line of docs/ASSESSMENT_AND_ROADMAP_2026-11.md:

    eight hours with flat memory, steady 40 fps and no gap over 100 ms.

``run_soak`` produces the rows (and appends each to a JSON-lines file as it is
measured, so a run that is cut short keeps what it saw). ``evaluate`` turns rows into
a verdict and touches nothing else, so it can be unit-tested and re-run on a saved file.

While the music plays the soak also works the two controls an operator leans on: a
short blackout and a grand-master dip in the first minute and every tenth after it,
each judged on the wire. The run ends with ``soak_report.json`` and a one-page
``soak_report.md`` beside it.
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

DEFAULT_MINUTES = 60
MAX_MINUTES = 480

# Control probes, in seconds from the start of a probed minute. Both finish well
# inside the minute, so each is judged from that minute's capture before it is pruned.
PROBE_EVERY_MINUTES = 10
BLACKOUT_AT, BLACKOUT_HOLD_S = 20.0, 3.0
MASTER_AT, MASTER_HOLD_S, MASTER_LEVEL = 35.0, 4.0, 0.3
# The same lines the wire tier holds (tests/wire/test_wire_truth.py).
BLACKOUT_DARK_WITHIN_S = 0.075      # frames already on their way at the ack
MASTER_PEAK_MARGIN = 0.02
MASTER_SETTLE_S = 1.0
FLASHES_PER_SECOND_LIMIT = 3.0


def resolve_minutes(hours: Optional[float] = None, minutes: Optional[int] = None) -> int:
    """The length of a run: one hour unless told otherwise, never over eight."""
    if hours is not None and minutes is not None:
        raise ValueError("give hours or minutes, not both")
    if minutes is None:
        minutes = DEFAULT_MINUTES if hours is None else round(hours * 60)
    if not 1 <= minutes <= MAX_MINUTES:
        raise ValueError(f"a soak runs for 1 to {MAX_MINUTES} minutes (8 hours); asked for {minutes}")
    return int(minutes)


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
    flashes_per_second: float = FLASHES_PER_SECOND_LIMIT   # whole-rig flashes in any one second


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
    off_box = sorted({r["artnet_target"] for r in rows
                      if r.get("artnet_target") and not H.is_loopback(r["artnet_target"])})
    if off_box:
        faults.append(f"the backend reported sending Art-Net off this machine, to {off_box}")
    check("wire_integrity", not faults, "; ".join(faults) if faults else
          "0 send errors, 0 stray channels, 0 malformed packets, 0 sequence breaks")

    reconnects = max((r.get("feed_reconnects") or 0) for r in rows)
    check("audio_feed", reconnects == 0,
          "audio feed held" if not reconnects else f"audio feed reconnected {reconnects} times")

    # flash rate of the whole rig
    flash = [(r["minute"], r.get("rig_flash_worst_1s")) for r in rows]
    seen = [f for _, f in flash if f is not None]
    over = [(m, f) for m, f in flash if f is not None and f > limits.flashes_per_second]
    if not seen:
        check("flash_rate", None, "no flash figures in these rows")
    else:
        check("flash_rate", not over,
              f"worst {max(seen):g} whole-rig flashes in one second (limit {limits.flashes_per_second:g})"
              + (f"; over in {len(over)} minutes, first at minute {over[0][0]}" if over else ""))

    # blackout and grand master, each time they were tried
    for name, label in (("blackout", "blackout"), ("master", "grand master")):
        probes = [(r["minute"], r[name]) for r in rows if r.get(name)]
        bad = [(m, p) for m, p in probes if not p.get("ok")]
        if not probes:
            check(name, None, f"{label} was not tried in these rows")
        else:
            check(name, not bad,
                  f"{label} held in {len(probes) - len(bad)} of {len(probes)} probes"
                  + (f"; first failure at minute {bad[0][0]}: {bad[0][1].get('why')}" if bad else ""))

    passed = all(c["passed"] is True for c in checks.values())
    failed = [name for name, c in checks.items() if c["passed"] is False]
    unjudged = [name for name, c in checks.items() if c["passed"] is None]
    return {
        "passed": passed,
        # "smoke": nothing measured was wrong, but something could not be judged
        # (a run of a few minutes cannot show a memory trend). Not a pass.
        "outcome": "pass" if passed else "fail" if failed else "smoke",
        "failed": failed,
        "unjudged": unjudged,
        "minutes": n,
        "checks": checks,
        "limits": asdict(limits),
    }


def channel_jumps(window: dict, patch: list) -> dict:
    """The largest change between two consecutive frames, in DMX steps (0-255).

    ``any`` is over every channel of every universe; ``pan_tilt`` is over the coarse
    pan and tilt channels, where a large step is a head being thrown, not a flash.
    """
    worst_any, worst_move = 0, 0
    for uni, (times, frames, _) in window.items():
        if frames is None or len(frames) < 2:
            continue
        step = np.abs(np.diff(frames.astype(np.int16), axis=0)).max(axis=0)   # [512]
        worst_any = max(worst_any, int(step.max()))
        for fx in patch:
            if fx["universe"] != uni:
                continue
            for c in fx["channels"]:
                idx = fx["address"] - 1 + c["offset"]
                if c["type"] in ("pan", "tilt") and not c["is_fine"] and 0 <= idx < 512:
                    worst_move = max(worst_move, int(step[idx]))
    return {"any": worst_any, "pan_tilt": worst_move}


def judge_blackout(http_status, restore_status, last_lit_after_ack: float, peak_late: float,
                   first_light: Optional[float], lit_before: bool) -> dict:
    """Did the rig go dark on the next frame, stay dark, and come back?"""
    why = []
    if http_status != 200:
        why.append(f"blackout answered {http_status}")
    if restore_status != 200:
        why.append(f"restore answered {restore_status}")
    if last_lit_after_ack > BLACKOUT_DARK_WITHIN_S:
        why.append(f"still lit {last_lit_after_ack} s after the acknowledgement")
    if peak_late > 0.0:
        why.append(f"light at level {peak_late} while latched")
    # How soon light returns depends on what the music is doing at that moment, so
    # the soak only fails a rig that never came back; the wire tier times the return.
    if lit_before and first_light is None:
        why.append("the rig stayed dark for the rest of the minute after restore")
    return {
        "ok": not why, "why": "; ".join(why) or None,
        "last_lit_s_after_ack": last_lit_after_ack, "peak_while_latched": peak_late,
        "first_light_s_after_restore": first_light, "lit_before": lit_before,
    }


def judge_master(http_status, level: float, fixture_peak: Optional[float]) -> dict:
    """Did no fixture exceed the grand master while it was down?"""
    why = []
    if http_status != 200:
        why.append(f"master answered {http_status}")
    if fixture_peak is None:
        why.append("no frames while the master was down")
    elif fixture_peak > level + MASTER_PEAK_MARGIN:
        why.append(f"a fixture reached {fixture_peak} with the master at {level}")
    return {"ok": not why, "why": "; ".join(why) or None,
            "level_set": level, "fixture_peak": fixture_peak}


def boundary_gap_ms(last_seen: dict, window: dict) -> Optional[float]:
    """The longest wait between the previous minute's last frame and this one's first.

    Gaps are measured inside each minute's window, so without this a stall that
    straddled a minute boundary would never be counted. ``last_seen`` maps a
    universe to the time of its last frame and is updated to this window's.
    A universe that has gone quiet is charged up to the last frame of any universe.
    """
    firsts = {u: float(times[0]) for u, (times, _, _) in window.items() if len(times)}
    newest = max((float(times[-1]) for times, _, _ in window.values() if len(times)), default=None)
    worst = None
    for uni, previous in last_seen.items():
        reached = firsts.get(uni, newest)
        if reached is not None:
            gap = (reached - previous) * 1000.0
            worst = gap if worst is None else max(worst, gap)
    for uni, (times, _, _) in window.items():
        if len(times):
            last_seen[uni] = float(times[-1])
    return None if worst is None else round(worst, 1)


def headline(verdict: dict) -> str:
    outcome = verdict.get("outcome") or ("pass" if verdict["passed"] else "fail")
    minutes = verdict["minutes"]
    if outcome == "pass":
        short = "" if minutes >= MAX_MINUTES else f" (G1 asks for {MAX_MINUTES}; this is not the G1 soak)"
        return f"SOAK PASS over {minutes} minutes{short}"
    if outcome == "smoke":
        return (f"SOAK SMOKE OK over {minutes} minutes: nothing measured was wrong, "
                f"not judged: {', '.join(verdict.get('unjudged', []))}. Not a G1 pass")
    return f"SOAK FAIL over {minutes} minutes"


def format_verdict(verdict: dict) -> str:
    lines = [headline(verdict)]
    for name, c in verdict["checks"].items():
        mark = {True: "ok  ", False: "FAIL", None: "n/a "}[c["passed"]]
        lines.append(f"  {mark} {name}: {c['detail']}")
    return "\n".join(lines)


def _span(rows: list, key: str, unit: str = "") -> str:
    values = [r[key] for r in rows if r.get(key) is not None]
    if not values:
        return "not measured"
    low, high = min(values), max(values)
    return f"{low:g}{unit}" if low == high else f"{low:g} to {high:g}{unit}"


def format_markdown(report: dict) -> str:
    """The one-page report that sits beside soak_report.json."""
    verdict, rows = report["verdict"], report["rows"]
    out = ["# Soak report", "", f"**{headline(verdict)}**", ""]
    out.append(f"- Asked for {report['requested_minutes']} minutes, measured {len(rows)}; "
               f"rig from the \"{report['template']}\" template.")
    out.append(f"- Art-Net captured on {report.get('captured_on', 'loopback')}: "
               f"{report['packets_captured']} packets. Nothing was sent to the network.")
    if report.get("error"):
        out.append(f"- **The run stopped early:** {report['error']}")
    out += ["", "| Check | Result | Detail |", "|---|---|---|"]
    for name, c in verdict["checks"].items():
        mark = {True: "ok", False: "**FAIL**", None: "not judged"}[c["passed"]]
        out.append(f"| {name} | {mark} | {c['detail']} |")
    if rows:
        def total(key):
            return sum((r.get(key) or 0) for r in rows)

        def peak(key):
            return max(((r.get(key) or 0) for r in rows), default=0)

        out += ["", "| Measure | Value |", "|---|---|"]
        out.append(f"| Frame rate, per minute | {_span(rows, 'fps', ' fps')} |")
        out.append(f"| Longest gap between frames, per minute | {_span(rows, 'gap_ms_max', ' ms')} |")
        out.append(f"| 99th-percentile gap | {_span(rows, 'gap_ms_p99', ' ms')} |")
        out.append(f"| Largest channel jump in one frame | {peak('channel_jump_max')} of 255 on any channel, "
                   f"{peak('pan_tilt_jump_max')} on coarse pan or tilt (reported, not judged) |")
        out.append(f"| Flash rate | worst {peak('rig_flash_worst_1s'):g} whole-rig flashes in a second; "
                   f"{total('flash_violations')} minutes over {verdict['limits']['flashes_per_second']:g}; "
                   f"at most {peak('fixtures_flashing_over_limit')} single fixtures over it in a minute |")
        for key, label in (("blackout", "Blackout"), ("master", "Grand master")):
            probes = [r[key] for r in rows if r.get(key)]
            held = sum(1 for p in probes if p.get("ok"))
            out.append(f"| {label} | held in {held} of {len(probes)} probes |")
        out.append(f"| Errors | {peak('send_errors')} send errors, {peak('malformed_packets')} malformed packets, "
                   f"{total('seq_breaks')} sequence breaks, {total('stray_channels')} channels outside the patch, "
                   f"{peak('feed_reconnects')} audio reconnects, "
                   f"{report.get('backend_log_error_lines', 'unknown')} error lines in the backend log |")
        out.append(f"| Memory (backend process tree) | {_span(rows, 'rss_mb', ' MB')} |")
        out.append(f"| Tracks played | {rows[-1].get('tracks_played')} |")
    out += ["", "Every minute is in `soak_rows.jsonl`; the limits used are in `soak_report.json`.", ""]
    return "\n".join(out)


def log_error_lines(log_path: Path) -> Optional[int]:
    """Lines of the backend's console log that report an error or a traceback."""
    try:
        text = Path(log_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return sum(1 for line in text.splitlines() if "Traceback" in line or "ERROR" in line)


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
    error: Optional[str] = None
    start_usage = None
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

        async def probe_controls(t0: float) -> dict:
            """A short blackout, then a grand-master dip, at fixed points of this minute."""
            marks: dict = {}

            async def at(seconds: float) -> float:
                await asyncio.sleep(max(0.0, t0 + seconds - time.perf_counter()))
                return time.perf_counter()

            try:
                marks["bo_cmd"] = await at(BLACKOUT_AT)
                r = await client.post("/api/effects/trigger/blackout")
                marks["bo_ack"], marks["bo_status"] = time.perf_counter(), r.status_code
                marks["rs_cmd"] = await at(BLACKOUT_AT + BLACKOUT_HOLD_S)
                marks["rs_status"] = (await client.post("/api/effects/trigger/restore")).status_code
                marks["gm_cmd"] = await at(MASTER_AT)
                r = await client.post("/api/effects/master", json={"level": MASTER_LEVEL})
                marks["gm_status"] = r.status_code
                marks["gm_end"] = await at(MASTER_AT + MASTER_HOLD_S)
            except Exception as exc:
                marks["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                # Never leave the rig dark or dimmed for the rest of the run.
                try:
                    if "bo_cmd" in marks and "rs_status" not in marks:
                        await client.post("/api/effects/trigger/restore")
                    if "gm_cmd" in marks:
                        await client.post("/api/effects/master", json={"level": 1.0})
                except Exception:
                    pass
            return marks

        def judge_probe(marks: dict, t1: float) -> tuple:
            if "error" in marks:
                failed = {"ok": False, "why": marks["error"]}
                return failed, failed
            before = H.analyse(cap, patch, marks["bo_cmd"] - 5.0, marks["bo_cmd"])
            lit_before = (before.get("level") or {}).get("rig_max", 0.0) > 0.02
            last_after_ack, _ = H.last_lit(cap, patch, marks["bo_ack"], marks["rs_cmd"])
            _, peak_late = H.last_lit(cap, patch, marks["bo_cmd"], marks["rs_cmd"])
            first = H.first_lit(cap, patch, marks["rs_cmd"], t1)
            blackout = judge_blackout(marks["bo_status"], marks["rs_status"],
                                      last_after_ack, peak_late, first, lit_before)
            dipped = H.analyse(cap, patch, marks["gm_cmd"] + MASTER_SETTLE_S, marks["gm_end"])
            master = judge_master(marks["gm_status"], MASTER_LEVEL,
                                  (dipped.get("level") or {}).get("fixture_peak_max"))
            return blackout, master

        last_seen: dict = {}
        feed_task = asyncio.create_task(feeder())
        t_begin = time.perf_counter()
        try:
            for minute in range(1, minutes + 1):
                t0 = t_begin + (minute - 1) * 60.0
                t1 = t0 + 60.0
                probing = minute == 1 or minute % PROBE_EVERY_MINUTES == 0
                marks = await probe_controls(t0) if probing and srv.alive() else None
                # A moment past the minute, so its last packets have been read in.
                await asyncio.sleep(max(0.0, t1 + 0.25 - time.perf_counter()))
                alive = srv.alive()
                a = H.analyse(cap, patch, t0, t1)
                window = cap.window(t0, t1)
                across = boundary_gap_ms(last_seen, window)
                jumps = channel_jumps(window, patch)
                blackout, master = judge_probe(marks, t1) if marks else (None, None)
                cap.prune(t1)
                tx = a["transport"]
                gap_max = max([u["gap_ms_max"] for u in tx.values()]
                              + ([across] if across is not None else []), default=None)
                level, flash = a.get("level", {}), a.get("flash", {})
                row = {
                    "minute": minute,
                    "backend_alive": alive,
                    "fps": min((u["fps"] for u in tx.values()), default=None),
                    "gap_ms_p99": max((u["gap_ms_p99"] for u in tx.values()), default=None),
                    "gap_ms_max": gap_max,
                    "seq_breaks": sum(u["seq_breaks"] for u in tx.values()),
                    "stray_channels": a["nonzero_channels_outside_patch"],
                    "unpatched_universes": a["unpatched_universes_transmitted"],
                    "malformed_packets": int(sum(cap.bad.values())),
                    "rig_mean": level.get("rig_mean"), "rig_max": level.get("rig_max"),
                    "dark_pct": level.get("pct_time_rig_dark"),
                    "rig_flash_worst_1s": flash.get("rig_worst_flashes_in_1s"),
                    "flash_violations": int((flash.get("rig_worst_flashes_in_1s") or 0) > FLASHES_PER_SECOND_LIMIT),
                    "fixtures_flashing_over_limit": flash.get("fixtures_flashing_over_3_per_s"),
                    "channel_jump_max": jumps["any"], "pan_tilt_jump_max": jumps["pan_tilt"],
                    "blackout": blackout, "master": master,
                    "feed_reconnects": state["reconnects"],
                    "tracks_played": state["tracks"],
                    "log_kb": srv.log_path.stat().st_size // 1024,
                    "rss_mb": None, "threads": None, "cpu_s": None,
                    "send_errors": None, "health": None, "artnet_target": None,
                }
                if alive:
                    row["rss_mb"], row["threads"], row["cpu_s"] = H.process_tree_usage(srv.proc.pid)
                    try:
                        h = (await client.get("/api/health")).json()
                        row["health"] = h.get("status")
                        detail = h.get("dmx_detail") or {}
                        row["send_errors"] = detail.get("send_error_count")
                        row["artnet_target"] = detail.get("target_ip")
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
    except Exception as exc:
        # Whatever was measured is still worth a report; the verdict will say "incomplete".
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if client is not None:
            await client.aclose()
        srv.hard_kill()
        cap.close()

    verdict = evaluate(rows, expected_minutes=minutes)
    if error:
        verdict["checks"]["harness"] = {"passed": False, "detail": f"the run stopped early: {error}"}
        verdict.update(passed=False, outcome="fail", failed=verdict.get("failed", []) + ["harness"])
    report = {
        "requested_minutes": minutes, "template": template,
        "captured_on": f"127.0.0.1:{cfg.art_port}",
        "start_rss_threads_cpu": start_usage,
        "capture_anomalies": dict(cap.bad), "packets_captured": cap.total,
        "backend_log_error_lines": log_error_lines(srv.log_path),
        "error": error,
        "verdict": verdict, "rows": rows,
    }
    (cfg.out / "soak_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (cfg.out / "soak_report.md").write_text(format_markdown(report), encoding="utf-8")
    return report
