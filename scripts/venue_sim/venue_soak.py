"""
Soak: continuous music into the real backend, one line a minute, and a verdict
against the G1 pass line (flat memory, steady 40 fps, no gap over 100 ms).

    python scripts/venue_sim/venue_soak.py <backend_dir> <out_dir>               # one hour
    python scripts/venue_sim/venue_soak.py <backend_dir> <out_dir> --hours 8     # the G1 soak
    python scripts/venue_sim/venue_soak.py <backend_dir> <out_dir> --minutes 2   # smoke
    python scripts/venue_sim/venue_soak.py <backend_dir> --evaluate <out_dir>/soak_rows.jsonl

The default is one hour and the longest run is eight. Each minute is appended to
<out_dir>/soak_rows.jsonl as it is measured, so a run that is interrupted keeps what
it saw; --evaluate judges such a file. A finished run leaves soak_report.json and
soak_report.md in <out_dir>.

Exit code: 0 for a complete run in which nothing measured was wrong, 1 otherwise.
A run too short to judge memory (under 8 minutes) says SMOKE OK, not PASS.
Everything stays on 127.0.0.1. Needs psutil.
"""
import argparse
import asyncio
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("backend_dir", type=Path)
    ap.add_argument("out_dir", type=Path, nargs="?")
    length = ap.add_mutually_exclusive_group()
    length.add_argument("--hours", type=float, help="length in hours, up to 8 (default 1)")
    length.add_argument("--minutes", type=int, help="length in minutes, 1 to 480")
    ap.add_argument("--evaluate", type=Path, metavar="ROWS_JSONL",
                    help="judge a saved soak_rows.jsonl instead of running")
    ap.add_argument("--expect-minutes", type=int, default=None,
                    help="with --evaluate: the length the run was meant to reach")
    ap.add_argument("--template", default="Small Club")
    args = ap.parse_args()

    sys.path.insert(0, str(args.backend_dir.resolve()))
    from tests.wire import harness as H
    from tests.wire import soak

    if args.evaluate:
        verdict = soak.evaluate(soak.load_rows(args.evaluate), expected_minutes=args.expect_minutes)
        print(soak.format_verdict(verdict))
        if args.expect_minutes is None:
            print("  note: --expect-minutes was not given, so a run cut short would not show as incomplete")
        return 0 if verdict["outcome"] != "fail" else 1

    if args.out_dir is None:
        ap.error("out_dir is required to run a soak")
    try:
        minutes = soak.resolve_minutes(hours=args.hours, minutes=args.minutes)
    except ValueError as exc:
        ap.error(str(exc))
    cfg = H.WireConfig.create(args.out_dir, backend=args.backend_dir)
    print(f"soak: {minutes} minutes, HTTP 127.0.0.1:{cfg.http_port}, Art-Net 127.0.0.1:{cfg.art_port}, "
          f"rows in {cfg.out / 'soak_rows.jsonl'}", flush=True)

    def show(row: dict) -> None:
        print(f"min {row['minute']:4d}: rss={row['rss_mb']} MB threads={row['threads']} cpu_s={row['cpu_s']} "
              f"fps={row['fps']} gap_p99={row['gap_ms_p99']} gap_max={row['gap_ms_max']} "
              f"seq_breaks={row['seq_breaks']} stray={row['stray_channels']} send_errors={row['send_errors']} "
              f"rig_mean={row['rig_mean']} rig_max={row['rig_max']} dark%={row['dark_pct']} "
              f"flash_worst_1s={row['rig_flash_worst_1s']} jump_max={row['channel_jump_max']} "
              f"pan_tilt_jump={row['pan_tilt_jump_max']} "
              + "".join(f"{key}={'ok' if row[key]['ok'] else 'FAIL'} "
                        for key in ("blackout", "master") if row.get(key))
              + f"tracks={row['tracks_played']} log_kb={row['log_kb']} health={row['health']}", flush=True)

    report = asyncio.run(soak.run_soak(cfg, minutes, on_row=show, template=args.template))
    print(soak.format_verdict(report["verdict"]), flush=True)
    print(f"report: {cfg.out / 'soak_report.md'} and {cfg.out / 'soak_report.json'}", flush=True)
    return 0 if report["verdict"]["outcome"] != "fail" else 1


if __name__ == "__main__":
    sys.exit(main())
