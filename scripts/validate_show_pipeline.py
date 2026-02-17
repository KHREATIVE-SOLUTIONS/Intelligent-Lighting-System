#!/usr/bin/env python3
"""
Validation harness for beam/spot section behavior and live payload contracts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import List
from urllib.error import URLError
from urllib.request import urlopen


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.services.effects.decision_engine import LightingState
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine
from app.services.effects.strobe_controller import StrobeMode


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _fetch_json(url: str, timeout: float = 1.5) -> dict:
    with urlopen(url, timeout=timeout) as resp:  # nosec B310 (trusted local URLs only)
        return json.loads(resp.read().decode("utf-8"))


def check_section_intensity_and_strobe() -> CheckResult:
    engine = EffectsEngine(EffectsConfig(strobe_enabled=True))
    engine._pro_lighting_enabled = False
    engine.decision._genre = "edm"

    engine.decision.state = LightingState.INTRO
    engine._apply_section_template()
    intro_scale = engine._current_section_intensity_scale
    intro_mode = engine.strobe.params.mode

    engine.decision.state = LightingState.PEAK
    engine._apply_section_template()
    peak_scale = engine._current_section_intensity_scale
    peak_mode = engine.strobe.params.mode

    if peak_scale <= intro_scale:
        return CheckResult(
            "section_scaling",
            False,
            f"peak_scale ({peak_scale:.2f}) <= intro_scale ({intro_scale:.2f})",
        )
    if intro_mode != StrobeMode.OFF:
        return CheckResult("strobe_restraint", False, f"intro strobe is {intro_mode.value}, expected off")
    if peak_mode == StrobeMode.OFF:
        return CheckResult("strobe_restraint", False, "peak strobe remained off")

    return CheckResult(
        "section_scaling_and_strobe",
        True,
        f"intro_scale={intro_scale:.2f}, peak_scale={peak_scale:.2f}, peak_strobe={peak_mode.value}",
    )


def check_backend_mib() -> CheckResult:
    engine = EffectsEngine(EffectsConfig(mib_enabled=True, mib_transition_ms=450, mib_pan_tilt_threshold=20.0))
    fixture = next((f for f in engine.fixtures.fixtures.values() if f.fixture_type != "bar"), None)
    if fixture is None:
        return CheckResult("backend_mib", False, "no mover fixture found")

    fixture.pan = 120
    fixture.tilt = 120
    engine.time = 1.0
    _ = engine._apply_mib_transition(fixture, 0.9)

    fixture.pan = 220
    fixture.tilt = 200
    engine.time = 1.02
    during = engine._apply_mib_transition(fixture, 0.9)

    engine.time = 2.0
    after = engine._apply_mib_transition(fixture, 0.9)

    if during > 0.03:
        return CheckResult("backend_mib", False, f"during transition dimmer={during:.3f}, expected near black")
    if after < 0.5:
        return CheckResult("backend_mib", False, f"post transition dimmer={after:.3f}, expected restore")
    return CheckResult("backend_mib", True, f"during={during:.3f}, after={after:.3f}")


def check_live_endpoints(backend_url: str, visualizer_url: str) -> List[CheckResult]:
    results: List[CheckResult] = []

    try:
        payload = _fetch_json(f"{backend_url}/api/effects/look-spec")
        required = ("section", "genre", "energy", "bpm", "beam", "spot", "color", "transition", "fixture_capabilities")
        for key in required:
            if key not in payload:
                return [CheckResult("live_backend_look_spec", False, f"missing key {key}")]
        results.append(CheckResult("live_backend_look_spec", True, "backend look-spec endpoint OK"))
    except URLError as exc:
        results.append(CheckResult("live_backend_look_spec", False, f"unreachable: {exc}"))

    try:
        payload = _fetch_json(f"{visualizer_url}/api/audio")
        data = payload.get("data") if isinstance(payload, dict) else None
        if data is None:
            results.append(CheckResult("live_visualizer_audio", False, "no audio payload yet"))
        else:
            has_look_spec = "look_spec" in data
            has_settings = "visualizer_settings" in data
            ok = has_look_spec and has_settings
            results.append(
                CheckResult(
                    "live_visualizer_audio",
                    ok,
                    f"look_spec={has_look_spec}, visualizer_settings={has_settings}",
                )
            )
    except URLError as exc:
        results.append(CheckResult("live_visualizer_audio", False, f"unreachable: {exc}"))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ILS section + beam/spot + MIB integration.")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8014")
    parser.add_argument("--visualizer-url", default="http://127.0.0.1:8080")
    parser.add_argument("--skip-live", action="store_true", help="Skip live HTTP endpoint checks.")
    args = parser.parse_args()

    checks = [
        check_section_intensity_and_strobe(),
        check_backend_mib(),
    ]
    if not args.skip_live:
        checks.extend(check_live_endpoints(args.backend_url, args.visualizer_url))

    failed = [c for c in checks if not c.ok]
    for c in checks:
        prefix = "[OK]" if c.ok else "[FAIL]"
        print(f"{prefix} {c.name}: {c.detail}")

    print(f"\nSummary: {len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
