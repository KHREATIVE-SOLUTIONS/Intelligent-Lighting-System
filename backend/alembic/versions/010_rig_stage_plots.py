"""Rig stage plot underlay

Revision ID: 010
Revises: 009
Create Date: 2026-11-27 00:00:00.000000

Adds the table that keeps a rig's stage plot image and its calibration, one
row per rig (docs/STAGE_PLOT.md). Purely additive: no existing table changes,
and a rig without a row has no stage plot.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = 'rig_stage_plots'


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table(TABLE_NAME) or not inspector.has_table('rigs'):
        return

    op.create_table(
        TABLE_NAME,
        sa.Column('rig_id', sa.Integer(), sa.ForeignKey('rigs.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('filename', sa.String(length=255), nullable=True),
        sa.Column('content_type', sa.String(length=50), nullable=False),
        sa.Column('byte_size', sa.Integer(), nullable=False),
        sa.Column('width_px', sa.Integer(), nullable=False),
        sa.Column('height_px', sa.Integer(), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('calibration', sa.JSON(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE_NAME):
        return

    op.drop_table(TABLE_NAME)
