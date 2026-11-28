"""Rig fixture label token

Revision ID: 012
Revises: 011
Create Date: 2026-11-28 00:00:00.000000

Adds `rig_fixtures.label_token`, a random 32 hex digit token printed into each
fixture's label QR (docs/RDM_AND_QR.md). Rig fixture ids are SQLite rowids and
can be handed to a new row after a delete; the token cannot, so the scan route
trusts a label's rig_fixture_id only when its token agrees.

Additive: the column is nullable and every existing row keeps its values. Each
existing row is given its own token here, so labels printed from now on carry
one without the print having to write it.
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '012'
down_revision: Union[str, None] = '011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = 'rig_fixtures'
COLUMN_NAME = 'label_token'


def _has_table() -> bool:
    return sa.inspect(op.get_bind()).has_table(TABLE_NAME)


def _has_column() -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(c['name'] == COLUMN_NAME for c in inspector.get_columns(TABLE_NAME))


def upgrade() -> None:
    if not _has_table():
        return
    if not _has_column():
        op.add_column(TABLE_NAME, sa.Column(COLUMN_NAME, sa.String(length=32), nullable=True))

    bind = op.get_bind()
    ids = [row[0] for row in bind.execute(
        sa.text(f"SELECT id FROM {TABLE_NAME} WHERE {COLUMN_NAME} IS NULL")
    )]
    for rf_id in ids:
        bind.execute(
            sa.text(f"UPDATE {TABLE_NAME} SET {COLUMN_NAME} = :token WHERE id = :id"),
            {"token": uuid4().hex, "id": rf_id},
        )


def downgrade() -> None:
    if not _has_table() or not _has_column():
        return
    with op.batch_alter_table(TABLE_NAME) as batch:
        batch.drop_column(COLUMN_NAME)
