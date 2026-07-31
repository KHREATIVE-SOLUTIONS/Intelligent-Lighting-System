"""Extended channel types

Revision ID: 003
Revises: 002
Create Date: 2026-07-31 00:00:00.000000

Adds the subtractive-colour, beam-shaping and second-gobo channel types needed to
import arbitrary GDTF/OFL profiles.

The enum persists member NAMES, so 'GOBO2_ROTATION' (14 chars) does not fit the
VARCHAR(13) the previous member set produced. The column is widened rather than
just re-declared.

Widening alone would leave the new members unused: every channel already seeded
carries the type the old member set could express, so a CMY spot's cyan flag is
stored as 'other' and the renderer never drives it - which on a subtractive
fixture means the flag stays fully open. The rows whose own name says what they
are are retyped here. Downgrade leaves them: rewriting them back to 'other'
would discard what the upgrade recovered.
"""
import re
from typing import Optional, Sequence, Union

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


# Only a channel whose own name states the mechanism is retyped; anything
# ambiguous ('Color Temp', 'CTC', 'Effect') keeps 'other'.
SUBTRACTIVE_NAME_TYPES = (
    (re.compile(r'\bcyan\b', re.I), 'CYAN'),
    (re.compile(r'\bmagenta\b', re.I), 'MAGENTA'),
    (re.compile(r'\byellow\b', re.I), 'YELLOW'),
)

NAME_TYPES = (
    (re.compile(r'\bcto\b', re.I), 'CTO'),
    (re.compile(r'\bctb\b', re.I), 'CTB'),
    (re.compile(r'\biris\b', re.I), 'IRIS'),
    (re.compile(r'\bfrost\b', re.I), 'FROST'),
    (re.compile(r'\banimation\b', re.I), 'ANIMATION'),
    (re.compile(r'\b(blade|shaper|framing|keystone)\b', re.I), 'FRAMING'),
    (re.compile(r'\blime\b', re.I), 'LIME'),
    (re.compile(r'\bindigo\b', re.I), 'INDIGO'),
)

_UPDATE_CHUNK = 400


def _channel_type_enum(members: Sequence[str]) -> sa.Enum:
    return sa.Enum(*members, name='channeltype')


def _retyped(name: str, subtractive: bool) -> Optional[str]:
    """The member a channel's name names, or None if the name does not say.

    Cyan/magenta/yellow are read as subtractive flags only on a fixture that
    declares CMY mixing: on an RGB+ LED engine those names are additive
    emitters, and driving one as a flag lights it fully at blackout.
    """
    rules = (SUBTRACTIVE_NAME_TYPES + NAME_TYPES) if subtractive else NAME_TYPES
    for pattern, member in rules:
        if pattern.search(name or ''):
            return member
    return None


def _backfill_channel_types(bind) -> None:
    channels = sa.table(
        'fixture_channels',
        sa.column('id', sa.Integer),
        sa.column('mode_id', sa.Integer),
        sa.column('channel_type', _channel_type_enum(CURRENT_CHANNEL_TYPES)),
        sa.column('name', sa.String),
    )
    modes = sa.table(
        'fixture_modes',
        sa.column('id', sa.Integer),
        sa.column('fixture_id', sa.Integer),
    )
    fixtures = sa.table(
        'fixtures',
        sa.column('id', sa.Integer),
        sa.column('has_cmy', sa.Boolean),
    )

    rows = bind.execute(
        sa.select(channels.c.id, channels.c.name, fixtures.c.has_cmy)
        .select_from(
            channels
            .join(modes, channels.c.mode_id == modes.c.id)
            .join(fixtures, modes.c.fixture_id == fixtures.c.id)
        )
        .where(channels.c.channel_type == 'OTHER')
    ).fetchall()

    by_member: dict = {}
    for row_id, name, has_cmy in rows:
        member = _retyped(name, bool(has_cmy))
        if member is not None:
            by_member.setdefault(member, []).append(row_id)

    for member, ids in by_member.items():
        for start in range(0, len(ids), _UPDATE_CHUNK):
            bind.execute(
                channels.update()
                .where(channels.c.id.in_(ids[start:start + _UPDATE_CHUNK]))
                .values(channel_type=member)
            )


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
    else:
        with op.batch_alter_table('fixture_channels') as batch_op:
            batch_op.alter_column(
                'channel_type',
                existing_type=_channel_type_enum(PREVIOUS_CHANNEL_TYPES),
                type_=_channel_type_enum(CURRENT_CHANNEL_TYPES),
                existing_nullable=True,
            )

    _backfill_channel_types(bind)


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
