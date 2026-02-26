"""
Programming-practice audit helpers for rig patching.

Implements a console-agnostic patch hygiene pass aligned with
professional programming workflows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from .patching_service import PatchingService


_MOTION_TYPES = {"moving_head", "wash", "spot", "beam"}


def _severity_weight(severity: str) -> int:
    if severity == "error":
        return 10
    if severity == "warning":
        return 3
    return 1


def _issue(
    severity: str,
    code: str,
    message: str,
    fixture_id: int | None = None,
    fixture_name: str | None = None,
    universe: int | None = None,
    address: int | None = None,
) -> Dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "fixture_id": fixture_id,
        "fixture_name": fixture_name,
        "universe": universe,
        "dmx_address": address,
    }


def build_programming_audit(fixtures_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create a patch hygiene audit report for a rig."""
    issues: List[Dict[str, Any]] = []
    patch_rows: List[Dict[str, Any]] = []

    conflicts = PatchingService.find_conflicts(fixtures_data)
    for c in conflicts:
        issues.append(
            _issue(
                severity="error",
                code="address_overlap",
                message=f"Fixture {c['fixture_a_id']} overlaps fixture {c['fixture_b_id']}",
                universe=c.get("universe"),
                address=c.get("overlap_start"),
            )
        )

    for f in fixtures_data:
        fixture_id = f.get("id")
        name = f.get("name")
        universe = int(f.get("universe", 0) or 0)
        start = int(f.get("dmx_address", 1) or 1)
        ch_count = int(f.get("channel_count", 1) or 1)
        end = start + ch_count - 1
        fixture_type = str(f.get("fixture_type") or "other").lower()
        has_mode = bool(f.get("has_mode"))
        mode_name = f.get("mode_name")
        channel_types = {str(x).lower() for x in (f.get("channel_types") or [])}

        patch_rows.append(
            {
                "fixture_id": fixture_id,
                "name": name,
                "fixture_type": fixture_type,
                "universe": universe,
                "dmx_address": start,
                "channel_count": ch_count,
                "address_end": end,
                "range_ok": start >= 1 and end <= 512,
                "mode_name": mode_name,
                "has_mode": has_mode,
            }
        )

        if not name:
            issues.append(
                _issue(
                    "warning",
                    "missing_label",
                    "Fixture has no label/name; patch labeling is incomplete.",
                    fixture_id=fixture_id,
                    universe=universe,
                    address=start,
                )
            )

        if not has_mode:
            issues.append(
                _issue(
                    "warning",
                    "missing_mode",
                    "Fixture has no mode assigned; channel mapping may be ambiguous.",
                    fixture_id=fixture_id,
                    fixture_name=name,
                    universe=universe,
                    address=start,
                )
            )

        if start < 1 or end > 512:
            issues.append(
                _issue(
                    "error",
                    "address_out_of_range",
                    f"Fixture footprint {start}-{end} exceeds DMX universe bounds (1-512).",
                    fixture_id=fixture_id,
                    fixture_name=name,
                    universe=universe,
                    address=start,
                )
            )

        if fixture_type in _MOTION_TYPES:
            has_pan = "pan" in channel_types or "pan_fine" in channel_types
            has_tilt = "tilt" in channel_types or "tilt_fine" in channel_types
            if not (has_pan and has_tilt):
                issues.append(
                    _issue(
                        "error",
                        "motion_channels_missing",
                        "Motion-capable fixture is missing pan/tilt channel definitions.",
                        fixture_id=fixture_id,
                        fixture_name=name,
                        universe=universe,
                        address=start,
                    )
                )

            if "pan_fine" in channel_types and "pan" not in channel_types:
                issues.append(
                    _issue(
                        "warning",
                        "pan_fine_without_pan",
                        "Pan fine channel exists without coarse pan channel.",
                        fixture_id=fixture_id,
                        fixture_name=name,
                        universe=universe,
                        address=start,
                    )
                )
            if "tilt_fine" in channel_types and "tilt" not in channel_types:
                issues.append(
                    _issue(
                        "warning",
                        "tilt_fine_without_tilt",
                        "Tilt fine channel exists without coarse tilt channel.",
                        fixture_id=fixture_id,
                        fixture_name=name,
                        universe=universe,
                        address=start,
                    )
                )

    penalty = sum(_severity_weight(i["severity"]) for i in issues)
    score = max(0, 100 - penalty)

    sorted_rows = sorted(patch_rows, key=lambda r: (r["universe"], r["dmx_address"], r["fixture_id"] or 0))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixture_count": len(fixtures_data),
        "score": score,
        "issues": issues,
        "patch_report": sorted_rows,
        "ownership_policy": {
            "intensity": {
                "blend": "HTP",
                "owners": ["base_wash", "dimmer_effects", "strobe_overlay", "key_light"],
            },
            "color_position_beam": {
                "blend": "LTP",
                "owners": ["palette_base", "movement_layer", "effect_overrides", "manual_operator"],
            },
        },
        "recommended_artifacts": [
            "patch_report",
            "palette_index",
            "effect_library_sheet",
            "safety_policy_log",
            "ownership_priority_map",
        ],
    }
