"""Rig custom focus targets

Revision ID: 011
Revises: 010
Create Date: 2026-11-27 00:00:00.000000

Adds `rigs.focus_targets`, the points a person added to focus moving heads on
(a list of {id, name, x, y, z}; docs/FOCUS_PRESETS.md). Nullable and additive:
a rig without it has the default targets only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '011'
down_revision: Union[str, None] = '010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = 'rigs'
COLUMN_NAME = 'focus_targets'


def _has_column() -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE_NAME):
        return True  # nothing to add to: treat as done
    return any(c['name'] == COLUMN_NAME for c in inspector.get_columns(TABLE_NAME))


def upgrade() -> None:
    if _has_column():
        return
    op.add_column(TABLE_NAME, sa.Column(COLUMN_NAME, sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(TABLE_NAME):
        return
    if not any(c['name'] == COLUMN_NAME for c in inspector.get_columns(TABLE_NAME)):
        return
    with op.batch_alter_table(TABLE_NAME) as batch:
        batch.drop_column(COLUMN_NAME)
