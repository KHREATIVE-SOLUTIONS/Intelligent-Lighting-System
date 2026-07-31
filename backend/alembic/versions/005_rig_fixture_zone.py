"""Rig fixture zone

Revision ID: 005
Revises: 004
Create Date: 2026-07-31 00:00:00.000000

Adds the nullable zone a rig fixture points at. Purely additive: every existing
row keeps its values and reads back NULL, which the loader treats as "no zone
declared" - the behaviour a rig had before this revision.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = 'rig_fixtures'
COLUMN_NAME = 'zone'


def _has_column(bind) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE_NAME):
        return False
    return COLUMN_NAME in {c['name'] for c in inspector.get_columns(TABLE_NAME)}


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE_NAME) or _has_column(bind):
        return

    op.add_column(TABLE_NAME, sa.Column(COLUMN_NAME, sa.String(length=50), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind):
        return

    op.drop_column(TABLE_NAME, COLUMN_NAME)
