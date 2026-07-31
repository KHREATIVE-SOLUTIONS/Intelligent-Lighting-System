"""
Bundled Venue Templates
=======================

The rig templates the gallery offers on a fresh install.

Placements are not written down here: they are generated at seed time by
``WizardService.compute_placement``, the same call the wizard's auto-place step
makes, so a template and the wizard can never describe the same venue
differently. Only the venue itself - stage size, what is rigged and where it is
mounted - is declared.
"""

import hashlib
import json
import logging
from itertools import combinations
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.fixture import Fixture, FixtureMode
from app.models.template import RigTemplate
from app.services.rig.fixture_choice import choose_mode, mode_makes_light
from app.services.rig.wizard_service import WizardService

logger = logging.getLogger(__name__)

# Written to RigTemplate.created_by as "system:<digest of the row as seeded>".
# rig_templates has no updated_at, so re-deriving that digest from the stored
# row is the only way to tell a bundled template nobody has touched from one
# the operator has since edited and must not be overwritten.
SEED_MARKER = "system"

# Used when the library holds no fixture of that type. The template still
# seeds, so the gap shows up in the gallery and in the boot log instead of the
# venue quietly losing a group.
FALLBACK_CHANNEL_COUNTS = {
    "beam": 16,
    "effect": 8,
    "led_bar": 8,
    "led_par": 8,
    "moving_head": 16,
    "spot": 18,
    "strobe": 5,
    "wash": 16,
}

DMX_UNIVERSE_SIZE = 512

# Counts and stage sizes are what these venues actually rig, not one rig scaled
# up and down: a bar gets eight fixtures on a low bar-height truss, a festival
# gets fifty-six over a ten-metre stage.
VENUE_TEMPLATES: List[Dict[str, Any]] = [
    {
        "venue_type": "small_bar",
        "name": "Small Bar",
        "description": (
            "Corner stage in a pub or bar. Eight fixtures on one low truss plus "
            "two uplights - enough for an acoustic act or a duo."
        ),
        "stage_width": 4.0,
        "stage_depth": 3.0,
        "stage_height": 2.8,
        "groups": [
            {"fixture_type": "led_par", "count": 4,
             "group_name": "Front Wash", "mounting": "front_truss", "zone": "stage_center"},
            {"fixture_type": "moving_head", "count": 2,
             "group_name": "Moving Heads", "mounting": "mid_truss"},
            {"fixture_type": "led_par", "count": 2,
             "group_name": "Uplights", "mounting": "floor"},
        ],
    },
    {
        "venue_type": "small_club",
        "name": "Small Club",
        "description": (
            "Live room for 100-200 people. Front wash for the band, four movers "
            "for movement, and uplights to stop the back wall going black."
        ),
        "stage_width": 6.0,
        "stage_depth": 4.0,
        "stage_height": 3.5,
        "groups": [
            {"fixture_type": "led_par", "count": 6,
             "group_name": "Front Wash", "mounting": "front_truss", "zone": "stage_center"},
            {"fixture_type": "moving_head", "count": 4,
             "group_name": "Moving Heads", "mounting": "mid_truss"},
            {"fixture_type": "led_bar", "count": 2,
             "group_name": "Backdrop Bars", "mounting": "back_truss"},
            {"fixture_type": "led_par", "count": 4,
             "group_name": "Floor Uplights", "mounting": "floor"},
        ],
    },
    {
        "venue_type": "medium_club",
        "name": "Medium Club",
        "description": (
            "Touring-size club stage, 300-800 capacity. Full front wash, movers "
            "and beams overhead, wash and strobes upstage behind the band."
        ),
        "stage_width": 10.0,
        "stage_depth": 7.0,
        "stage_height": 5.0,
        "groups": [
            {"fixture_type": "led_par", "count": 8,
             "group_name": "Front Wash", "mounting": "front_truss", "zone": "stage_center"},
            {"fixture_type": "moving_head", "count": 6,
             "group_name": "Moving Heads", "mounting": "mid_truss"},
            {"fixture_type": "beam", "count": 4,
             "group_name": "Beams", "mounting": "mid_truss"},
            {"fixture_type": "wash", "count": 4,
             "group_name": "Back Wash", "mounting": "back_truss"},
            {"fixture_type": "strobe", "count": 2,
             "group_name": "Strobes", "mounting": "back_truss"},
            {"fixture_type": "led_bar", "count": 4,
             "group_name": "Upstage Bars", "mounting": "floor"},
        ],
    },
    {
        "venue_type": "nightclub",
        "name": "Nightclub",
        "description": (
            "DJ booth and dance floor rather than a stage. Movers and wash "
            "cover the floor, effects and beams sit behind the booth."
        ),
        "stage_width": 8.0,
        "stage_depth": 6.0,
        "stage_height": 4.0,
        "groups": [
            {"fixture_type": "moving_head", "count": 6,
             "group_name": "Dance Floor Movers", "mounting": "ceiling", "zone": "dance_floor"},
            {"fixture_type": "led_par", "count": 8,
             "group_name": "Perimeter Wash", "mounting": "floor"},
            {"fixture_type": "led_bar", "count": 4,
             "group_name": "Booth Bars", "mounting": "front_truss", "zone": "dj_booth"},
            {"fixture_type": "strobe", "count": 2,
             "group_name": "Strobes", "mounting": "mid_truss"},
            {"fixture_type": "beam", "count": 2,
             "group_name": "Beams", "mounting": "back_truss"},
            {"fixture_type": "effect", "count": 2,
             "group_name": "Effects", "mounting": "back_truss"},
        ],
    },
    {
        "venue_type": "church",
        "name": "Church / Worship",
        "description": (
            "Wide, shallow platform. Key light on whoever is speaking, even "
            "wash across the platform, and colour on the backdrop."
        ),
        "stage_width": 12.0,
        "stage_depth": 6.0,
        "stage_height": 6.0,
        "groups": [
            {"fixture_type": "spot", "count": 4,
             "group_name": "Key Light", "mounting": "front_truss", "zone": "stage_center"},
            {"fixture_type": "wash", "count": 6,
             "group_name": "Platform Wash", "mounting": "ceiling"},
            {"fixture_type": "led_par", "count": 6,
             "group_name": "Choir Wash", "mounting": "mid_truss", "zone": "upstage_center"},
            {"fixture_type": "led_bar", "count": 4,
             "group_name": "Backdrop Wash", "mounting": "floor"},
            {"fixture_type": "moving_head", "count": 2,
             "group_name": "Accent Movers", "mounting": "back_truss"},
        ],
    },
    {
        "venue_type": "band_stage",
        "name": "Band Stage",
        "description": (
            "House rig for a room that books bands. Front wash so faces read, "
            "backlight beams for depth, and a pair of pars on the drum riser."
        ),
        "stage_width": 8.0,
        "stage_depth": 5.0,
        "stage_height": 4.0,
        "groups": [
            {"fixture_type": "led_par", "count": 6,
             "group_name": "Front Wash", "mounting": "front_truss", "zone": "stage_center"},
            {"fixture_type": "moving_head", "count": 4,
             "group_name": "Moving Heads", "mounting": "mid_truss"},
            {"fixture_type": "wash", "count": 4,
             "group_name": "Back Wash", "mounting": "back_truss"},
            {"fixture_type": "beam", "count": 4,
             "group_name": "Backlight Beams", "mounting": "back_truss"},
            {"fixture_type": "led_par", "count": 2,
             "group_name": "Drum Fill", "mounting": "floor", "zone": "drum_riser"},
        ],
    },
    {
        "venue_type": "mobile_dj",
        "name": "Mobile DJ",
        "description": (
            "Two tripod T-bars and a booth, packed in a car. Twelve fixtures, "
            "no rigging - the smallest setup that still looks like a show."
        ),
        "stage_width": 6.0,
        "stage_depth": 3.0,
        "stage_height": 2.5,
        "groups": [
            {"fixture_type": "moving_head", "count": 4,
             "group_name": "Moving Heads", "mounting": "front_truss"},
            {"fixture_type": "led_par", "count": 4,
             "group_name": "Dance Floor Wash", "mounting": "mid_truss", "zone": "dance_floor"},
            {"fixture_type": "led_bar", "count": 2,
             "group_name": "Booth Bars", "mounting": "floor", "zone": "dj_booth"},
            {"fixture_type": "effect", "count": 2,
             "group_name": "Effects", "mounting": "floor"},
        ],
    },
    {
        "venue_type": "theater",
        "name": "Theatre",
        "description": (
            "Proscenium house. Front of house spots, overhead wash, side light "
            "from both wings and a cyc the full width of the stage."
        ),
        "stage_width": 14.0,
        "stage_depth": 10.0,
        "stage_height": 8.0,
        "groups": [
            {"fixture_type": "spot", "count": 8,
             "group_name": "Front of House", "mounting": "front_truss", "zone": "stage_center"},
            {"fixture_type": "wash", "count": 6,
             "group_name": "Stage Wash", "mounting": "ceiling"},
            {"fixture_type": "spot", "count": 4,
             "group_name": "Side Light Left", "mounting": "side_left", "zone": "stage_left"},
            {"fixture_type": "spot", "count": 4,
             "group_name": "Side Light Right", "mounting": "side_right", "zone": "stage_right"},
            {"fixture_type": "moving_head", "count": 4,
             "group_name": "Moving Heads", "mounting": "mid_truss"},
            {"fixture_type": "led_bar", "count": 6,
             "group_name": "Cyc Bars", "mounting": "back_truss"},
        ],
    },
    {
        "venue_type": "function_room",
        "name": "Function Room",
        "description": (
            "Weddings, parties and awards nights. Ten uplighters round the "
            "room, wash over the dance floor, movers for when the band starts."
        ),
        "stage_width": 10.0,
        "stage_depth": 6.0,
        "stage_height": 3.5,
        "groups": [
            {"fixture_type": "led_par", "count": 10,
             "group_name": "Uplighters", "mounting": "floor"},
            {"fixture_type": "led_par", "count": 4,
             "group_name": "Dance Floor Wash", "mounting": "ceiling", "zone": "dance_floor"},
            {"fixture_type": "moving_head", "count": 4,
             "group_name": "Moving Heads", "mounting": "mid_truss"},
            {"fixture_type": "led_bar", "count": 2,
             "group_name": "Top Table", "mounting": "front_truss", "zone": "stage_center"},
        ],
    },
    {
        "venue_type": "festival_stage",
        "name": "Festival Stage",
        "description": (
            "Outdoor main stage, three trusses deep. Fifty-six fixtures across "
            "two DMX universes - a full production rig for touring acts."
        ),
        "stage_width": 18.0,
        "stage_depth": 12.0,
        "stage_height": 10.0,
        "groups": [
            {"fixture_type": "led_par", "count": 12,
             "group_name": "Front Wash", "mounting": "front_truss", "zone": "stage_center"},
            {"fixture_type": "spot", "count": 8,
             "group_name": "Key Spots", "mounting": "ceiling", "zone": "stage_center"},
            {"fixture_type": "moving_head", "count": 8,
             "group_name": "Moving Heads", "mounting": "mid_truss"},
            {"fixture_type": "strobe", "count": 4,
             "group_name": "Strobes", "mounting": "mid_truss"},
            {"fixture_type": "wash", "count": 8,
             "group_name": "Back Wash", "mounting": "back_truss"},
            {"fixture_type": "beam", "count": 8,
             "group_name": "Beams", "mounting": "back_truss"},
            {"fixture_type": "led_bar", "count": 8,
             "group_name": "Upstage Bars", "mounting": "floor"},
        ],
    },
]


def seed_venue_templates() -> Tuple[int, int, int, List[str]]:
    """Insert or refresh the bundled venue templates.

    Idempotent: a template already seeded and untouched is left alone unless
    its generated content changed, in which case it is regenerated in place.
    A template the operator has edited is never overwritten.

    Returns (created, refreshed, total, errors). Blocking - call from a worker
    thread.
    """
    errors: List[str] = []
    warnings: List[str] = []
    created = 0
    refreshed = 0

    session = SessionLocal()
    try:
        channel_counts = _resolve_channel_counts(session, errors)

        existing: Dict[str, RigTemplate] = {}
        for row in session.query(RigTemplate).filter(RigTemplate.is_system.is_(True)):
            if row.venue_type:
                existing[row.venue_type] = row

        for definition in VENUE_TEMPLATES:
            venue_type = definition["venue_type"]
            try:
                payload = build_template_payload(definition, channel_counts)
            except Exception as e:
                errors.append(f"templates: {venue_type}: {e}")
                logger.error("Could not generate venue template %s: %s", venue_type, e)
                continue

            warnings.extend(_placement_warnings(definition, payload))
            digest = _digest(payload)
            row = existing.get(venue_type)

            try:
                if row is None:
                    session.add(RigTemplate(
                        **payload,
                        is_system=True,
                        is_public=True,
                        created_by=f"{SEED_MARKER}:{digest}",
                        usage_count=0,
                    ))
                    created += 1
                else:
                    stored = _digest(_row_payload(row))
                    if row.created_by != f"{SEED_MARKER}:{stored}":
                        continue
                    if stored == digest:
                        continue
                    for key, value in payload.items():
                        setattr(row, key, value)
                    row.created_by = f"{SEED_MARKER}:{digest}"
                    refreshed += 1
                session.commit()
            except Exception as e:
                session.rollback()
                errors.append(f"templates: {venue_type}: {e}")
                logger.error("Could not seed venue template %s: %s", venue_type, e)
                continue

            stats = template_stats(payload)
            logger.debug(
                "Venue template %s: %d fixtures, %d channels, %d universe(s)",
                venue_type, stats["fixtures"], stats["channels"], stats["universes"],
            )

        total = session.query(RigTemplate).count()
    finally:
        session.close()

    for warning in warnings:
        logger.warning("Venue template placement: %s", warning)
    if warnings:
        errors.append(
            f"templates: {len(warnings)} placement warning(s) - see log"
        )

    if created or refreshed:
        logger.info(
            "Venue templates seeded (%d new, %d refreshed; gallery holds %d)",
            created, refreshed, total,
        )
    else:
        logger.info("Venue templates already seeded (gallery holds %d)", total)

    return created, refreshed, total, errors


def build_template_payload(
    definition: Dict[str, Any],
    channel_counts: Dict[str, int],
) -> Dict[str, Any]:
    """Turn a venue declaration into a RigTemplate column payload.

    Positions come from the wizard's placement call so that a template and the
    wizard's auto-place step cannot disagree.
    """
    groups = definition["groups"]
    stage = {
        "stage_width": definition["stage_width"],
        "stage_depth": definition["stage_depth"],
        "stage_height": definition["stage_height"],
    }

    placements = WizardService.compute_placement(
        stage_width=stage["stage_width"],
        stage_depth=stage["stage_depth"],
        stage_height=stage["stage_height"],
        fixtures=[_wizard_group(g, channel_counts) for g in groups],
    )

    expected = sum(g["count"] for g in groups)
    if len(placements) != expected:
        raise ValueError(
            f"placement returned {len(placements)} positions for {expected} fixtures"
        )

    slots: List[Dict[str, Any]] = []
    cursor = 0
    for group in groups:
        if group["count"] < 1:
            raise ValueError(f"group '{group['group_name']}' declares no fixtures")
        chunk = placements[cursor:cursor + group["count"]]
        cursor += group["count"]
        if any(p.get("group_name") != group["group_name"] for p in chunk):
            raise ValueError(
                f"placements for '{group['group_name']}' came back out of order"
            )
        slots.append({
            "fixture_type": group["fixture_type"],
            "count": group["count"],
            "group_name": group["group_name"],
            # What the placement call resolved, not what was asked for.
            "mounting": chunk[0].get("mounting_position", group["mounting"]),
            "zone": group.get("zone"),
            "mode_channel_count": _channel_count(group["fixture_type"], channel_counts),
            "positions": [_slot_position(group["group_name"], p) for p in chunk],
        })

    return {
        "name": definition["name"],
        "description": definition["description"],
        "venue_type": definition["venue_type"],
        "fixture_slots": slots,
        "thumbnail_url": None,
        **stage,
    }


def template_stats(payload: Dict[str, Any]) -> Dict[str, int]:
    """Fixture, channel and universe totals for a generated template.

    Mirrors the sequential addressing the apply endpoint performs, so the
    universe count is the one the operator will actually end up patching.
    """
    fixtures = 0
    channels = 0
    universe = 0
    address = 1

    for slot in payload.get("fixture_slots", []):
        count = slot.get("count", 0)
        width = slot.get("mode_channel_count") or 0
        for _ in range(count):
            if address + width - 1 > DMX_UNIVERSE_SIZE:
                universe += 1
                address = 1
            address += width
            channels += width
            fixtures += 1

    return {"fixtures": fixtures, "channels": channels, "universes": universe + 1}


_PLACEMENT_KEYS = ("position_x", "position_y", "position_z", "rotation_y")


def _slot_position(group_name: str, placement: Dict[str, Any]) -> Dict[str, float]:
    """One position, refusing to invent a coordinate the placement call omitted.

    Defaulting a missing key to 0.0 turns a renamed output field into ten venues
    whose every fixture is stacked on the stage origin, seeded with nothing worse
    than a warning. Missing geometry is a broken template, not a placed one.
    """
    missing = [key for key in _PLACEMENT_KEYS if placement.get(key) is None]
    if missing:
        raise ValueError(
            f"placement for '{group_name}' is missing {', '.join(missing)}"
        )
    return {
        "x": float(placement["position_x"]),
        "y": float(placement["position_y"]),
        "z": float(placement["position_z"]),
        "rotation_y": float(placement["rotation_y"]),
    }


def _wizard_group(
    group: Dict[str, Any],
    channel_counts: Dict[str, int],
) -> Dict[str, Any]:
    """Shape one declared group into the wizard's placement input."""
    return {
        "fixture_id": None,
        "mode_id": None,
        "count": group["count"],
        "group_name": group["group_name"],
        "mounting": group["mounting"],
        "mounting_position": group["mounting"],
        "mode_channel_count": _channel_count(group["fixture_type"], channel_counts),
    }


def _channel_count(fixture_type: str, channel_counts: Dict[str, int]) -> int:
    return channel_counts.get(
        fixture_type, FALLBACK_CHANNEL_COUNTS.get(fixture_type, 16)
    )


def _resolve_channel_counts(session: Session, errors: List[str]) -> Dict[str, int]:
    """Look up the channel width the apply endpoint will pick per fixture type.

    Matched the same way the endpoint matches - first fixture of the type, its
    first mode - so a template's addressing survives being applied.
    """
    counts: Dict[str, int] = {}
    wanted = sorted({
        group["fixture_type"]
        for definition in VENUE_TEMPLATES
        for group in definition["groups"]
    })

    for fixture_type in wanted:
        fixture, mode = pick_profile_sync(session, fixture_type)
        if fixture is None:
            counts[fixture_type] = FALLBACK_CHANNEL_COUNTS.get(fixture_type, 16)
            errors.append(
                f"templates: no '{fixture_type}' fixture in the library - "
                "templates using it will patch short"
            )
            logger.warning(
                "No '%s' fixture in the library; venue templates using it "
                "cannot be applied in full", fixture_type,
            )
            continue

        if mode is None or not mode_makes_light(mode.channels):
            # A group patched on a mode nothing can raise is a fixture the owner
            # will spend their evening deciding is broken.
            errors.append(
                f"templates: the only '{fixture_type}' profile in the library has "
                "no mode with a dimmer or a colour channel - fixtures of that "
                "type would patch and never light"
            )
            logger.error(
                "No drivable '%s' mode in the library; venue templates using it "
                "would seed fixtures that cannot be turned on", fixture_type,
            )

        counts[fixture_type] = (
            mode.channel_count if mode and mode.channel_count
            else FALLBACK_CHANNEL_COUNTS.get(fixture_type, 16)
        )

    return counts


def pick_profile_sync(session: Session, fixture_type: str):
    """The library profile and mode a template of this type will patch onto.

    Mirrors what the apply endpoint does, so a template's channel widths and
    addressing survive being applied. Both prefer a mode that can make light
    over the merely-first one.
    """
    fixtures = (
        session.query(Fixture)
        .filter(Fixture.fixture_type == fixture_type)
        .order_by(Fixture.id)
        .all()
    )
    if not fixtures:
        return None, None

    fallback = None
    for fixture in fixtures:
        modes = (
            session.query(FixtureMode)
            .filter(FixtureMode.fixture_id == fixture.id)
            .order_by(FixtureMode.id)
            .all()
        )
        mode = choose_mode(modes)
        if mode is not None and mode_makes_light(mode.channels):
            return fixture, mode
        if fallback is None:
            fallback = (fixture, mode)

    return fallback


def _placement_warnings(
    definition: Dict[str, Any],
    payload: Dict[str, Any],
) -> List[str]:
    """Report placements that would look broken to the person using them."""
    warnings: List[str] = []
    name = definition["name"]
    slots = payload.get("fixture_slots", [])

    # Side mounts legitimately share a height and depth with each other, so two
    # mounting positions only look unread when their fixtures also overlap in X.
    lines: Dict[Tuple[float, float], Dict[str, List[float]]] = {}
    for slot in slots:
        for position in slot["positions"]:
            line = lines.setdefault((position["y"], position["z"]), {})
            line.setdefault(slot["mounting"], []).append(position["x"])
    for (y, z), by_mounting in lines.items():
        spans = {m: (min(xs), max(xs)) for m, xs in by_mounting.items()}
        for first, second in combinations(sorted(spans), 2):
            low_a, high_a = spans[first]
            low_b, high_b = spans[second]
            if low_a <= high_b and low_b <= high_a:
                warnings.append(
                    f"{name}: '{first}' and '{second}' both landed on y={y}, "
                    f"z={z} - the placement call is not separating mounting "
                    "positions"
                )

    occupied: Dict[Tuple[float, float, float], str] = {}
    for slot in slots:
        for position in slot["positions"]:
            key = (position["x"], position["y"], position["z"])
            clash = occupied.get(key)
            if clash is not None:
                warnings.append(
                    f"{name}: '{slot['group_name']}' sits on top of '{clash}' at "
                    f"{key}"
                )
            else:
                occupied[key] = slot["group_name"]

    if slots and all(
        position["rotation_y"] == 0.0
        for slot in slots
        for position in slot["positions"]
    ):
        warnings.append(
            f"{name}: every fixture has rotation_y 0 - nothing is aimed at the "
            "performance area"
        )

    return warnings


def _row_payload(row: RigTemplate) -> Dict[str, Any]:
    """Read back the columns seeding owns, in the shape it writes them."""
    return {
        "name": row.name,
        "description": row.description,
        "venue_type": row.venue_type,
        "stage_width": row.stage_width,
        "stage_depth": row.stage_depth,
        "stage_height": row.stage_height,
        "fixture_slots": row.fixture_slots,
        "thumbnail_url": row.thumbnail_url,
    }


def _digest(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
