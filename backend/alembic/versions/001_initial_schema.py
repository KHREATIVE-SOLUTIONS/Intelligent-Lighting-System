"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Audio fingerprints table
    op.create_table(
        'audio_fingerprints',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('track_name', sa.String(255), nullable=True),
        sa.Column('artist', sa.String(255), nullable=True),
        sa.Column('album', sa.String(255), nullable=True),
        sa.Column('isrc', sa.String(20), nullable=True),
        sa.Column('fingerprint_hash', sa.String(64), nullable=True),
        sa.Column('fingerprint_data', sa.LargeBinary(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('sample_rate', sa.Integer(), nullable=True),
        sa.Column('avg_bpm', sa.Float(), nullable=True),
        sa.Column('key', sa.String(10), nullable=True),
        sa.Column('time_signature', sa.String(10), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_matched', sa.DateTime(), nullable=True),
        sa.Column('match_count', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audio_fingerprints_fingerprint_hash', 'audio_fingerprints', ['fingerprint_hash'], unique=True)
    op.create_index('ix_audio_fingerprints_id', 'audio_fingerprints', ['id'], unique=False)

    # Shows table
    op.create_table(
        'shows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('bpm', sa.Float(), nullable=True),
        sa.Column('status', sa.Enum('DRAFT', 'READY', 'PLAYING', 'PAUSED', 'COMPLETED', name='showstatus'), nullable=True),
        sa.Column('base_valence', sa.Float(), nullable=True),
        sa.Column('base_arousal', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.Column('audio_fingerprint_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['audio_fingerprint_id'], ['audio_fingerprints.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_shows_id', 'shows', ['id'], unique=False)
    op.create_index('ix_shows_name', 'shows', ['name'], unique=False)

    # Show tracks table
    op.create_table(
        'show_tracks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('show_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('track_type', sa.String(50), nullable=True),
        sa.Column('order', sa.Integer(), nullable=True),
        sa.Column('muted', sa.Boolean(), nullable=True),
        sa.Column('solo', sa.Boolean(), nullable=True),
        sa.Column('fixture_ids', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['show_id'], ['shows.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_show_tracks_id', 'show_tracks', ['id'], unique=False)

    # Show cues table
    op.create_table(
        'show_cues',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('show_id', sa.Integer(), nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('cue_type', sa.Enum('STATIC', 'FADE', 'CHASE', 'EFFECT', 'AUDIO_REACTIVE', name='cuetype'), nullable=True),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('fade_in', sa.Float(), nullable=True),
        sa.Column('fade_out', sa.Float(), nullable=True),
        sa.Column('dmx_values', sa.JSON(), nullable=True),
        sa.Column('effect_type', sa.String(50), nullable=True),
        sa.Column('effect_params', sa.JSON(), nullable=True),
        sa.Column('audio_reactive', sa.Boolean(), nullable=True),
        sa.Column('audio_trigger', sa.String(50), nullable=True),
        sa.Column('audio_params', sa.JSON(), nullable=True),
        sa.Column('valence', sa.Float(), nullable=True),
        sa.Column('arousal', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['show_id'], ['shows.id'], ),
        sa.ForeignKeyConstraint(['track_id'], ['show_tracks.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_show_cues_id', 'show_cues', ['id'], unique=False)

    # Fixtures table
    op.create_table(
        'fixtures',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('manufacturer', sa.String(255), nullable=False),
        sa.Column('model', sa.String(255), nullable=False),
        sa.Column('fixture_type', sa.Enum('MOVING_HEAD', 'LED_PAR', 'LED_BAR', 'WASH', 'SPOT', 'BEAM', 'STROBE', 'LASER', 'EFFECT', 'DIMMER', 'OTHER', name='fixturetype'), nullable=True),
        sa.Column('gdtf_id', sa.String(100), nullable=True),
        sa.Column('gdtf_file', sa.String(500), nullable=True),
        sa.Column('weight', sa.Float(), nullable=True),
        sa.Column('power', sa.Float(), nullable=True),
        sa.Column('beam_angle', sa.Float(), nullable=True),
        sa.Column('pan_range', sa.Float(), nullable=True),
        sa.Column('tilt_range', sa.Float(), nullable=True),
        sa.Column('has_rgb', sa.Boolean(), nullable=True),
        sa.Column('has_cmy', sa.Boolean(), nullable=True),
        sa.Column('has_color_wheel', sa.Boolean(), nullable=True),
        sa.Column('color_temp_range', sa.JSON(), nullable=True),
        sa.Column('thumbnail_url', sa.String(500), nullable=True),
        sa.Column('model_3d_url', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_fixtures_id', 'fixtures', ['id'], unique=False)
    op.create_index('ix_fixtures_manufacturer', 'fixtures', ['manufacturer'], unique=False)
    op.create_index('ix_fixtures_model', 'fixtures', ['model'], unique=False)
    op.create_index('ix_fixtures_gdtf_id', 'fixtures', ['gdtf_id'], unique=True)

    # Fixture modes table
    op.create_table(
        'fixture_modes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fixture_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('channel_count', sa.Integer(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['fixture_id'], ['fixtures.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_fixture_modes_id', 'fixture_modes', ['id'], unique=False)

    # Fixture channels table
    op.create_table(
        'fixture_channels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mode_id', sa.Integer(), nullable=False),
        sa.Column('channel_number', sa.Integer(), nullable=False),
        sa.Column('channel_type', sa.Enum('DIMMER', 'RED', 'GREEN', 'BLUE', 'WHITE', 'AMBER', 'UV', 'PAN', 'PAN_FINE', 'TILT', 'TILT_FINE', 'ZOOM', 'FOCUS', 'GOBO', 'GOBO_ROTATION', 'PRISM', 'COLOR_WHEEL', 'SHUTTER', 'STROBE', 'SPEED', 'EFFECT', 'MACRO', 'OTHER', name='channeltype'), nullable=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('default_value', sa.Integer(), nullable=True),
        sa.Column('min_value', sa.Integer(), nullable=True),
        sa.Column('max_value', sa.Integer(), nullable=True),
        sa.Column('is_fine', sa.Boolean(), nullable=True),
        sa.Column('coarse_channel', sa.Integer(), nullable=True),
        sa.Column('value_ranges', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['mode_id'], ['fixture_modes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_fixture_channels_id', 'fixture_channels', ['id'], unique=False)

    # Rigs table
    op.create_table(
        'rigs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('venue', sa.String(255), nullable=True),
        sa.Column('stage_width', sa.Float(), nullable=True),
        sa.Column('stage_depth', sa.Float(), nullable=True),
        sa.Column('stage_height', sa.Float(), nullable=True),
        sa.Column('universes', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rigs_id', 'rigs', ['id'], unique=False)
    op.create_index('ix_rigs_name', 'rigs', ['name'], unique=False)

    # Rig fixtures table
    op.create_table(
        'rig_fixtures',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('rig_id', sa.Integer(), nullable=False),
        sa.Column('fixture_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('fixture_number', sa.Integer(), nullable=True),
        sa.Column('universe', sa.Integer(), nullable=True),
        sa.Column('dmx_address', sa.Integer(), nullable=False),
        sa.Column('mode_id', sa.Integer(), nullable=True),
        sa.Column('position_x', sa.Float(), nullable=True),
        sa.Column('position_y', sa.Float(), nullable=True),
        sa.Column('position_z', sa.Float(), nullable=True),
        sa.Column('rotation_x', sa.Float(), nullable=True),
        sa.Column('rotation_y', sa.Float(), nullable=True),
        sa.Column('rotation_z', sa.Float(), nullable=True),
        sa.Column('group_name', sa.String(100), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('is_inverted', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['fixture_id'], ['fixtures.id'], ),
        sa.ForeignKeyConstraint(['mode_id'], ['fixture_modes.id'], ),
        sa.ForeignKeyConstraint(['rig_id'], ['rigs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rig_fixtures_id', 'rig_fixtures', ['id'], unique=False)

    # Audio analyses table
    op.create_table(
        'audio_analyses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('source', sa.String(50), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('bpm', sa.Float(), nullable=True),
        sa.Column('beat_confidence', sa.Float(), nullable=True),
        sa.Column('beat_positions', sa.JSON(), nullable=True),
        sa.Column('downbeats', sa.JSON(), nullable=True),
        sa.Column('valence', sa.Float(), nullable=True),
        sa.Column('arousal', sa.Float(), nullable=True),
        sa.Column('mood_confidence', sa.Float(), nullable=True),
        sa.Column('detected_emotions', sa.JSON(), nullable=True),
        sa.Column('frequency_bands', sa.JSON(), nullable=True),
        sa.Column('spectral_centroid', sa.Float(), nullable=True),
        sa.Column('spectral_rolloff', sa.Float(), nullable=True),
        sa.Column('spectral_flux', sa.Float(), nullable=True),
        sa.Column('rms_energy', sa.Float(), nullable=True),
        sa.Column('peak_amplitude', sa.Float(), nullable=True),
        sa.Column('detected_genre', sa.String(100), nullable=True),
        sa.Column('genre_confidence', sa.Float(), nullable=True),
        sa.Column('mfcc_features', sa.JSON(), nullable=True),
        sa.Column('chroma_features', sa.JSON(), nullable=True),
        sa.Column('fingerprint_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['fingerprint_id'], ['audio_fingerprints.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audio_analyses_id', 'audio_analyses', ['id'], unique=False)


def downgrade() -> None:
    op.drop_table('audio_analyses')
    op.drop_table('rig_fixtures')
    op.drop_table('rigs')
    op.drop_table('fixture_channels')
    op.drop_table('fixture_modes')
    op.drop_table('fixtures')
    op.drop_table('show_cues')
    op.drop_table('show_tracks')
    op.drop_table('shows')
    op.drop_table('audio_fingerprints')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS showstatus')
    op.execute('DROP TYPE IF EXISTS cuetype')
    op.execute('DROP TYPE IF EXISTS fixturetype')
    op.execute('DROP TYPE IF EXISTS channeltype')
