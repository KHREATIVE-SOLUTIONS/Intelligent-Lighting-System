"""
The soak as a test: tracks back to back in one boot, judged a minute at a time.

Without --soak-minutes this is a three-minute smoke of the soak machinery and of the
section 4 "smoke soak" row, with a relaxed gap limit and no memory verdict (three
samples cannot show a trend). With --soak-minutes N it is the G1 soak and the full
pass line applies: flat memory, steady 40 fps, no gap over 100 ms.

    pytest tests/wire/test_wire_soak.py --wire                      # smoke
    pytest tests/wire/test_wire_soak.py --wire --soak-minutes 480   # the eight hours

A run that long is easier to leave going with scripts/venue_sim/venue_soak.py,
which prints each minute as it is measured.
"""
import asyncio

import pytest

from . import soak

pytestmark = pytest.mark.wire

SMOKE_MINUTES = 3
SMOKE_GAP_MS = 250.0


def test_soak(request, wire_config):
    requested = request.config.getoption("--soak-minutes")
    minutes = requested or SMOKE_MINUTES

    report = asyncio.run(soak.run_soak(
        wire_config, minutes,
        on_row=lambda row: print(f"\nsoak minute {row['minute']}: {row}", end="")))
    rows = report["rows"]

    if requested:
        verdict = report["verdict"]
        assert verdict["passed"], soak.format_verdict(verdict)
        return

    verdict = soak.evaluate(rows, expected_minutes=minutes,
                            limits=soak.SoakLimits(gap_ms_max=SMOKE_GAP_MS))
    failed = {name: c["detail"] for name, c in verdict["checks"].items() if c["passed"] is False}
    assert not failed, soak.format_verdict(verdict)
    # Tracks really did follow one another, and the rig really was lit by them.
    assert rows[-1]["tracks_played"] >= 2
    assert all(row["rig_mean"] and row["rig_mean"] > 0.02 for row in rows), rows
