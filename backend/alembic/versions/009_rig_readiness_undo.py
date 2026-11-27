"""Rig readiness fix undo record

Revision ID: 009
Revises: 008
Create Date: 2026-11-27 00:00:00.000000

Adds the nullable record of what the last venue readiness fix (Make groups or
Re-address) changed, so it can be undone as one step (docs/READINESS.md).
Purely additive: every existing row reads back NULL, which means "no readiness
fix to undo".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = 'rigs'
COLUMN_NAME = 'readiness_undo'


def _has_column(bind) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE_NAME):
        return False
    return COLUMN_NAME in {c['name'] for c in inspector.get_columns(TABLE_NAME)}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE_NAME) or _has_column(bind):
        return

    op.add_column(TABLE_NAME, sa.Column(COLUMN_NAME, sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind):
        return

    op.drop_column(TABLE_NAME, COLUMN_NAME)
