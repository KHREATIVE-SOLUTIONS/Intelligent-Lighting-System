"""Operator credential

Revision ID: 004
Revises: 003
Create Date: 2026-07-31 00:00:00.000000

Adds the single-row table holding the operator password hash. Purely additive:
no existing table or row is touched, and a box upgraded past this point is still
in first-run state until someone completes /api/auth/setup.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = 'operator_credential'


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table(TABLE_NAME):
        return

    op.create_table(
        TABLE_NAME,
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f(f'ix_{TABLE_NAME}_id'), TABLE_NAME, ['id'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(TABLE_NAME):
        return

    op.drop_index(op.f(f'ix_{TABLE_NAME}_id'), table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
