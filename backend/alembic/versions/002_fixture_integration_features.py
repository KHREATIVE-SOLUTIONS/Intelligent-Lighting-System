"""Fixture integration features

Revision ID: 002
Revises: 001
Create Date: 2026-02-06 00:00:00.000000

Adds columns and tables for all 10 fixture integration features:
- Fixture library source tracking (3.1)
- Rig import source (3.7)
- Address locking and identification (3.3, 3.10)
- Rig templates (3.6)
- RDM devices (3.9)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Fixture library source tracking (Feature 3.1) --
    op.add_column('fixtures', sa.Column('source', sa.String(50), nullable=True))
    op.add_column('fixtures', sa.Column('source_id', sa.String(255), nullable=True))
    op.add_column('fixtures', sa.Column('categories', sa.JSON(), nullable=True))
    op.add_column('fixtures', sa.Column('popularity_score', sa.Integer(), server_default='0'))
    op.add_column('fixtures', sa.Column('is_bundled', sa.Boolean(), server_default='false'))

    # -- Rig import source (Feature 3.7) --
    op.add_column('rigs', sa.Column('source_format', sa.String(50), nullable=True))
    op.add_column('rigs', sa.Column('source_file', sa.String(500), nullable=True))

    # -- Address locking and identification (Features 3.3, 3.10) --
    op.add_column('rig_fixtures', sa.Column('is_address_locked', sa.Boolean(), server_default='false'))
    op.add_column('rig_fixtures', sa.Column('serial_number', sa.String(100), nullable=True))
    op.add_column('rig_fixtures', sa.Column('qr_code_data', sa.String(500), nullable=True))

    # -- Rig templates table (Feature 3.6) --
    op.create_table(
        'rig_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('venue_type', sa.String(100), nullable=True),
        sa.Column('stage_width', sa.Float(), nullable=True),
        sa.Column('stage_depth', sa.Float(), nullable=True),
        sa.Column('stage_height', sa.Float(), nullable=True),
        sa.Column('fixture_slots', sa.JSON(), nullable=True),
        sa.Column('thumbnail_url', sa.String(500), nullable=True),
        sa.Column('is_system', sa.Boolean(), server_default='false'),
        sa.Column('is_public', sa.Boolean(), server_default='true'),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('usage_count', sa.Integer(), server_default='0'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rig_templates_id', 'rig_templates', ['id'], unique=False)
    op.create_index('ix_rig_templates_name', 'rig_templates', ['name'], unique=False)

    # -- RDM devices table (Feature 3.9) --
    op.create_table(
        'rdm_devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('uid_manufacturer', sa.Integer(), nullable=False),
        sa.Column('uid_device', sa.Integer(), nullable=False),
        sa.Column('manufacturer_label', sa.String(255), nullable=True),
        sa.Column('model_description', sa.String(255), nullable=True),
        sa.Column('device_label', sa.String(255), nullable=True),
        sa.Column('dmx_footprint', sa.Integer(), nullable=True),
        sa.Column('current_personality', sa.Integer(), nullable=True),
        sa.Column('personality_count', sa.Integer(), nullable=True),
        sa.Column('personalities', sa.JSON(), nullable=True),
        sa.Column('dmx_address', sa.Integer(), nullable=True),
        sa.Column('universe', sa.Integer(), server_default='0'),
        sa.Column('supported_parameters', sa.JSON(), nullable=True),
        sa.Column('matched_fixture_id', sa.Integer(), nullable=True),
        sa.Column('is_imported', sa.Boolean(), server_default='false'),
        sa.Column('discovered_at', sa.DateTime(), nullable=True),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rdm_devices_id', 'rdm_devices', ['id'], unique=False)


def downgrade() -> None:
    # Drop new tables
    op.drop_table('rdm_devices')
    op.drop_table('rig_templates')

    # Remove columns from rig_fixtures
    op.drop_column('rig_fixtures', 'qr_code_data')
    op.drop_column('rig_fixtures', 'serial_number')
    op.drop_column('rig_fixtures', 'is_address_locked')

    # Remove columns from rigs
    op.drop_column('rigs', 'source_file')
    op.drop_column('rigs', 'source_format')

    # Remove columns from fixtures
    op.drop_column('fixtures', 'is_bundled')
    op.drop_column('fixtures', 'popularity_score')
    op.drop_column('fixtures', 'categories')
    op.drop_column('fixtures', 'source_id')
    op.drop_column('fixtures', 'source')
