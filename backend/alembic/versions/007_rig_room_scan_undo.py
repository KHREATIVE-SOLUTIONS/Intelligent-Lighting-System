"""Rig room scan undo record

Revision ID: 007
Revises: 006
Create Date: 2026-11-22 04:00:00.000000

Adds the nullable record of where a rig's fixtures stood before a room scan
moved them, so the move can be undone (docs/ROOM_SCAN.md). Purely additive:
every existing row keeps its values and reads back NULL, which means "no room
scan moves to undo".
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = 'rigs'
COLUMN_NAME = 'room_scan_undo'


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
