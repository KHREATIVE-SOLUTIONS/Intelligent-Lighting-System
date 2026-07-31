"""Extended channel types

Revision ID: 003
Revises: 002
Create Date: 2026-07-31 00:00:00.000000

Adds the subtractive-colour, beam-shaping and second-gobo channel types needed to
import arbitrary GDTF/OFL profiles.

The enum persists member NAMES, so 'GOBO2_ROTATION' (14 chars) does not fit the
VARCHAR(13) the previous member set produced. The column is widened rather than
just re-declared; existing rows are carried across untouched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PREVIOUS_CHANNEL_TYPES = (
    'DIMMER', 'RED', 'GREEN', 'BLUE', 'WHITE', 'AMBER', 'UV',
    'PAN', 'PAN_FINE', 'TILT', 'TILT_FINE', 'ZOOM', 'FOCUS',
    'GOBO', 'GOBO_ROTATION', 'PRISM', 'COLOR_WHEEL', 'SHUTTER',
    'STROBE', 'SPEED', 'EFFECT', 'MACRO', 'OTHER',
)

ADDED_CHANNEL_TYPES = (
    'LIME', 'INDIGO', 'CYAN', 'MAGENTA', 'YELLOW', 'CTO', 'CTB',
    'IRIS', 'FROST', 'GOBO2', 'GOBO2_ROTATION', 'ANIMATION', 'FRAMING',
)

CURRENT_CHANNEL_TYPES = PREVIOUS_CHANNEL_TYPES + ADDED_CHANNEL_TYPES


def _channel_type_enum(members: Sequence[str]) -> sa.Enum:
    return sa.Enum(*members, name='channeltype')


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == 'postgresql':
        # Native enum: values are added to the type, the column is untouched.
        # ADD VALUE cannot run in the migration's transaction on PostgreSQL < 12.
        with op.get_context().autocommit_block():
            for member in ADDED_CHANNEL_TYPES:
                op.execute(
                    f"ALTER TYPE channeltype ADD VALUE IF NOT EXISTS '{member}'"
                )
        return

    with op.batch_alter_table('fixture_channels') as batch_op:
        batch_op.alter_column(
            'channel_type',
            existing_type=_channel_type_enum(PREVIOUS_CHANNEL_TYPES),
            type_=_channel_type_enum(CURRENT_CHANNEL_TYPES),
            existing_nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == 'postgresql':
        # Dropping enum values would fail against any row already using one, and
        # rewriting those rows would lose the imported channel's meaning.
        return

    with op.batch_alter_table('fixture_channels') as batch_op:
        batch_op.alter_column(
            'channel_type',
            existing_type=_channel_type_enum(CURRENT_CHANNEL_TYPES),
            type_=_channel_type_enum(PREVIOUS_CHANNEL_TYPES),
            existing_nullable=True,
        )
