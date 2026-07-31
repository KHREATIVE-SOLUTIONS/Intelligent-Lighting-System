"""
Database Startup
================

Schema provisioning and bundled fixture seeding, executed once at boot.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import Base, SessionLocal, engine
from app.db.venue_templates import seed_venue_templates
from app.models.fixture import (
    ChannelType, Fixture, FixtureChannel, FixtureMode, FixtureType
)

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
ALEMBIC_SCRIPTS = BACKEND_DIR / "alembic"

FIXTURE_DIR = BACKEND_DIR.parent / "data" / "fixtures"
BUNDLED_FIXTURE_DIR = FIXTURE_DIR / "bundled"
DEFAULT_POPULARITY = 50

# Revision that introduced fixtures.source_id - used to place a pre-Alembic
# database at the right point in the migration history.
FIXTURE_SOURCE_REVISION = "002"
BASE_REVISION = "001"


async def init_database() -> Dict[str, Any]:
    """Ensure the schema exists and the bundled fixture library is seeded."""
    summary: Dict[str, Any] = {
        "schema": "unknown",
        "fixtures_seeded": 0,
        "fixtures_total": 0,
        "templates_seeded": 0,
        "templates_refreshed": 0,
        "templates_total": 0,
        "errors": [],
    }

    try:
        summary["schema"] = await asyncio.to_thread(_upgrade_schema)
    except Exception as e:
        summary["errors"].append(f"alembic: {e}")
        logger.warning(
            "ALEMBIC MIGRATION FAILED (%s) - falling back to create_all; "
            "the database is NOT under migration control",
            e,
            exc_info=True,
        )
        try:
            await asyncio.to_thread(_create_all)
            summary["schema"] = "create_all"
        except Exception as e:
            summary["schema"] = "failed"
            summary["errors"].append(f"create_all: {e}")
            logger.error("Could not create database schema: %s", e, exc_info=True)
            return summary

    try:
        seeded, total, errors = await asyncio.to_thread(_seed_fixture_library)
        summary["fixtures_seeded"] = seeded
        summary["fixtures_total"] = total
        summary["errors"].extend(errors)
    except Exception as e:
        summary["errors"].append(f"fixtures: {e}")
        logger.error("Fixture library seeding failed: %s", e, exc_info=True)

    # Templates resolve each slot's channel width from the library, so they can
    # only be generated once the library is in place.
    try:
        created, refreshed, total, errors = await asyncio.to_thread(seed_venue_templates)
        summary["templates_seeded"] = created
        summary["templates_refreshed"] = refreshed
        summary["templates_total"] = total
        summary["errors"].extend(errors)
    except Exception as e:
        summary["errors"].append(f"templates: {e}")
        logger.error("Venue template seeding failed: %s", e, exc_info=True)

    return summary


def _upgrade_schema() -> str:
    """Run Alembic to head. Blocking - call from a worker thread."""
    from alembic import command
    from alembic.config import Config

    # alembic/env.py resolves the database from the environment, not from settings.
    os.environ.setdefault("DATABASE_URL", settings.DATABASE_URL)

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_SCRIPTS))
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    # env.py calls fileConfig() whenever a config file is attached, which would
    # replace the handlers installed by configure_logging().
    config.config_file_name = None

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    stamped = False
    if tables and "alembic_version" not in tables:
        baseline = BASE_REVISION
        if "fixtures" in tables:
            columns = {c["name"] for c in inspector.get_columns("fixtures")}
            if "source_id" in columns:
                baseline = FIXTURE_SOURCE_REVISION
        command.stamp(config, baseline)
        stamped = True
        logger.info("Adopted pre-existing schema at Alembic revision %s", baseline)

    try:
        command.upgrade(config, "head")
    except Exception:
        # A stamp that survives a failed upgrade wedges the database: every later
        # boot replays the same migration against a schema it does not describe.
        if stamped:
            _discard_adoption_stamp()
        raise

    logger.info("Database schema at Alembic head")
    return "alembic"


def _discard_adoption_stamp() -> None:
    """Drop the version table written by a failed schema adoption."""
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    except Exception as e:
        logger.error("Could not roll back the Alembic adoption stamp: %s", e)


def _create_all() -> None:
    """Create any missing tables straight from the model metadata."""
    Base.metadata.create_all(bind=engine)
    logger.warning("Schema created from model metadata (no migration history)")


def _seed_fixture_library() -> Tuple[int, int, List[str]]:
    """Insert bundled fixture definitions missing from the library.

    Idempotent: fixtures already present (matched on source_id) are skipped.
    Blocking - call from a worker thread.
    """
    paths: List[Path] = []
    for directory in (BUNDLED_FIXTURE_DIR, FIXTURE_DIR):
        if directory.is_dir():
            paths.extend(sorted(directory.glob("*.json")))

    if not paths:
        logger.warning("No bundled fixture definitions found under %s", FIXTURE_DIR)
        return 0, 0, [f"fixtures: no definitions under {FIXTURE_DIR}"]

    errors: List[str] = []
    seeded = 0
    session = SessionLocal()
    try:
        existing = {sid for (sid,) in session.query(Fixture.source_id).all() if sid}

        for path in paths:
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, ValueError) as e:
                errors.append(f"{path.name}: {e}")
                logger.error("Could not read fixture definition %s: %s", path.name, e)
                continue

            source_id = data.get("source_id") or path.stem
            if source_id in existing:
                continue

            try:
                _insert_fixture(session, data, source_id)
                session.commit()
            except Exception as e:
                session.rollback()
                errors.append(f"{path.name}: {e}")
                logger.error("Could not seed fixture %s: %s", path.name, e)
                continue

            existing.add(source_id)
            seeded += 1

        total = session.query(Fixture).count()
    finally:
        session.close()

    if seeded:
        logger.info("Seeded %d bundled fixtures (library holds %d)", seeded, total)
    else:
        logger.info("Fixture library already seeded (%d fixtures)", total)

    return seeded, total, errors


def _insert_fixture(session: Session, data: Dict[str, Any], source_id: str) -> None:
    """Create a fixture with its modes and channels from a bundled definition."""
    fixture = Fixture(
        manufacturer=data["manufacturer"],
        model=data["model"],
        fixture_type=_coerce_enum(FixtureType, data.get("fixture_type"), FixtureType.OTHER),
        weight=data.get("weight"),
        power=data.get("power"),
        beam_angle=data.get("beam_angle"),
        pan_range=data.get("pan_range", 540.0),
        tilt_range=data.get("tilt_range", 270.0),
        has_rgb=data.get("has_rgb", False),
        has_cmy=data.get("has_cmy", False),
        has_color_wheel=data.get("has_color_wheel", False),
        color_temp_range=data.get("color_temp_range"),
        thumbnail_url=data.get("thumbnail_url"),
        source=data.get("source", "bundled"),
        source_id=source_id,
        categories=data.get("categories"),
        popularity_score=data.get("popularity_score", DEFAULT_POPULARITY),
        is_bundled=data.get("is_bundled", True),
    )
    session.add(fixture)
    session.flush()

    for mode_data in data.get("modes", []):
        channels_data = mode_data.get("channels", [])
        mode = FixtureMode(
            fixture_id=fixture.id,
            name=mode_data["name"],
            channel_count=mode_data.get("channel_count", len(channels_data)),
            description=mode_data.get("description"),
        )
        session.add(mode)
        session.flush()

        for ch_data in channels_data:
            session.add(FixtureChannel(
                mode_id=mode.id,
                channel_number=ch_data["channel_number"],
                channel_type=_coerce_enum(
                    ChannelType, ch_data.get("channel_type"), ChannelType.OTHER
                ),
                name=ch_data.get("name", f"Channel {ch_data['channel_number']}"),
                default_value=ch_data.get("default_value", 0),
                min_value=ch_data.get("min_value", 0),
                max_value=ch_data.get("max_value", 255),
                is_fine=ch_data.get("is_fine", False),
                coarse_channel=ch_data.get("coarse_channel"),
                value_ranges=ch_data.get("value_ranges"),
            ))


def _coerce_enum(enum_cls, value, default):
    """Map a JSON string onto an enum member, falling back when unrecognised."""
    try:
        return enum_cls(value)
    except ValueError:
        return default
