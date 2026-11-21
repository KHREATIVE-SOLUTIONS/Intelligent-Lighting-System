"""Map retired is_inverted onto tilt_invert

Revision ID: 007
Revises: 006
Create Date: 2026-11-20 00:00:00.000000

is_inverted was a status flag on rig_fixtures that the engine never read and
the patch UI never drove. The hang flags (pan_invert, tilt_invert,
pan_tilt_swap) replaced it.

A true is_inverted is treated as a hung-inverted unit: mid-tilt should still
point toward the floor, which is tilt_invert. This revision copies that data
onto tilt_invert when tilt_invert is still false.

It does not drop is_inverted, overwrite a tilt_invert that is already true,
or change pan_invert or pan_tilt_swap.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "rig_fixtures"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(TABLE_NAME):
        return
    columns = {c["name"] for c in inspector.get_columns(TABLE_NAME)}
    if "is_inverted" not in columns or "tilt_invert" not in columns:
        return
    op.execute(
        sa.text(
            "UPDATE rig_fixtures SET tilt_invert = 1 "
            "WHERE is_inverted = 1 AND (tilt_invert = 0 OR tilt_invert IS NULL)"
        )
    )


def downgrade() -> None:
    # Do not un-set tilt_invert. It may have been set on purpose, and reversing
    # the copy would delete hang data.
    return
