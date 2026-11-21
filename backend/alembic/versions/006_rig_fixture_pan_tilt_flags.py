"""Rig fixture pan/tilt invert and swap

Revision ID: 006
Revises: 005
Create Date: 2026-11-20 00:00:00.000000

Adds the three per-fixture hang flags: pan_invert, tilt_invert, pan_tilt_swap.
Purely additive. The columns are NOT NULL with a database default of false, so
every row that was already in a rig reads back False for all three - the
behaviour that rig had before this revision - and never NULL, which the API's
boolean fields would refuse.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = 'rig_fixtures'
COLUMN_NAMES = ('pan_invert', 'tilt_invert', 'pan_tilt_swap')


def _existing_columns(bind) -> set:
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE_NAME):
        return set()
    return {c['name'] for c in inspector.get_columns(TABLE_NAME)}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE_NAME):
        return

    existing = _existing_columns(bind)
    for name in COLUMN_NAMES:
        if name in existing:
            continue
        op.add_column(
            TABLE_NAME,
            sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing = _existing_columns(bind)
    # Batch mode rebuilds the table on SQLite, which works on every SQLite
    # version rather than only those with a native DROP COLUMN.
    present = [name for name in COLUMN_NAMES if name in existing]
    if not present:
        return
    with op.batch_alter_table(TABLE_NAME) as batch:
        for name in present:
            batch.drop_column(name)
