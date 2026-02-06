#!/usr/bin/env python
"""
Database initialization script.

Creates initial database schema and seeds sample data.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base, engine
from app.models import Fixture, FixtureMode, FixtureChannel, Show, Rig, RigFixture


def load_json(filepath: str) -> dict:
    """Load JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def create_tables():
    """Create all database tables."""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")


def seed_fixtures(session: Session):
    """Seed fixture library from JSON files."""
    print("Seeding fixture library...")

    fixtures_dir = Path(__file__).parent.parent / "data" / "fixtures"

    for fixture_file in fixtures_dir.glob("*.json"):
        data = load_json(str(fixture_file))

        # Create fixture
        fixture = Fixture(
            manufacturer=data["manufacturer"],
            model=data["model"],
            fixture_type=data["fixture_type"],
            weight=data.get("weight"),
            power=data.get("power"),
            beam_angle=data.get("beam_angle"),
            pan_range=data.get("pan_range", 0),
            tilt_range=data.get("tilt_range", 0),
            has_rgb=data.get("has_rgb", False),
            has_cmy=data.get("has_cmy", False),
            has_color_wheel=data.get("has_color_wheel", False),
        )
        session.add(fixture)
        session.flush()

        # Create modes
        for mode_data in data.get("modes", []):
            mode = FixtureMode(
                fixture_id=fixture.id,
                name=mode_data["name"],
                channel_count=mode_data["channel_count"],
            )
            session.add(mode)
            session.flush()

            # Create channels
            for channel_data in mode_data.get("channels", []):
                channel = FixtureChannel(
                    mode_id=mode.id,
                    channel_number=channel_data["channel_number"],
                    channel_type=channel_data["channel_type"],
                    name=channel_data["name"],
                    default_value=channel_data.get("default_value", 0),
                )
                session.add(channel)

        print(f"  Added fixture: {fixture.manufacturer} {fixture.model}")

    session.commit()


def seed_sample_data(session: Session):
    """Seed sample shows and rigs."""
    print("Seeding sample data...")

    # Get fixture IDs
    fixtures = session.query(Fixture).all()
    fixture_map = {f"{f.manufacturer} {f.model}": f.id for f in fixtures}

    # Load and create sample rig
    rig_file = Path(__file__).parent.parent / "data" / "rigs" / "sample_rig.json"
    if rig_file.exists():
        rig_data = load_json(str(rig_file))

        rig = Rig(
            name=rig_data["name"],
            description=rig_data.get("description"),
            venue=rig_data.get("venue"),
            stage_width=rig_data.get("stage_width", 10),
            stage_depth=rig_data.get("stage_depth", 8),
            stage_height=rig_data.get("stage_height", 6),
            universes=rig_data.get("universes", []),
            is_active=True,
        )
        session.add(rig)
        session.flush()

        # Add fixtures to rig
        for rf_data in rig_data.get("fixtures", []):
            # Map fixture_id to actual fixture
            fixture_id = rf_data.get("fixture_id")
            if fixtures and fixture_id <= len(fixtures):
                actual_fixture_id = fixtures[fixture_id - 1].id
            else:
                actual_fixture_id = fixtures[0].id if fixtures else 1

            rig_fixture = RigFixture(
                rig_id=rig.id,
                fixture_id=actual_fixture_id,
                name=rf_data.get("name"),
                fixture_number=rf_data.get("fixture_number"),
                universe=rf_data.get("universe", 0),
                dmx_address=rf_data["dmx_address"],
                position_x=rf_data.get("position_x", 0),
                position_y=rf_data.get("position_y", 0),
                position_z=rf_data.get("position_z", 0),
                rotation_x=rf_data.get("rotation_x", 0),
                rotation_y=rf_data.get("rotation_y", 0),
                rotation_z=rf_data.get("rotation_z", 0),
                group_name=rf_data.get("group_name"),
                tags=rf_data.get("tags", []),
            )
            session.add(rig_fixture)

        print(f"  Added rig: {rig.name}")

    # Load and create sample show
    show_file = Path(__file__).parent.parent / "data" / "shows" / "sample_show.json"
    if show_file.exists():
        show_data = load_json(str(show_file))

        show = Show(
            name=show_data["name"],
            description=show_data.get("description"),
            duration=show_data.get("duration"),
            bpm=show_data.get("bpm"),
            base_valence=show_data.get("base_valence", 0.5),
            base_arousal=show_data.get("base_arousal", 0.5),
        )
        session.add(show)
        session.flush()

        print(f"  Added show: {show.name}")

    session.commit()


def main():
    """Main initialization function."""
    print("Initializing database...")
    print(f"Database URL: {os.getenv('DATABASE_URL', 'default')}")

    create_tables()

    with Session(engine) as session:
        # Check if already seeded
        existing_fixtures = session.query(Fixture).count()
        if existing_fixtures > 0:
            print(f"Database already contains {existing_fixtures} fixtures. Skipping seed.")
            return

        seed_fixtures(session)
        seed_sample_data(session)

    print("\nDatabase initialization complete!")


if __name__ == "__main__":
    main()
