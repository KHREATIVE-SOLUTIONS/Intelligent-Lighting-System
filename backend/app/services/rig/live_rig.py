"""
Live Rig
========

The one way a rig gets onto the running show, and the check a patched rig has
to pass first.

Everything here is synchronous on purpose. The effects engine renders a frame
inside one `update()` call on the event loop, so a swap made without an
`await` can only land between two frames: the engine never renders half of
one rig and half of another.
"""

import time
from typing import Any, Dict, List, Optional

from app.services.rig.rig_loader import DMX_UNIVERSE_SIZE, get_rig_diagnostics

NOT_ACTIVE_REASON = "fixture is not active"


def live_rig_version(app) -> int:
    """A number that changes every time the engine is given a rig.

    Compare it for equality only. It starts from the clock, so a restarted
    backend never hands out a number an open page has already seen.
    """
    return int(getattr(app.state, "live_rig_version", 0) or 0)


def bump_live_rig_version(app) -> int:
    version = max(live_rig_version(app) + 1, int(time.time() * 1000))
    app.state.live_rig_version = version
    return version


def _sync_output_hold(app) -> None:
    """Tell the engine whether the demo's output hold is on (the output stage reads it)."""
    engine = getattr(app.state, "effects_engine", None)
    hold = getattr(engine, "set_output_held", None) if engine is not None else None
    if callable(hold):
        hold(bool(getattr(app.state, "dmx_output_held", False)))


def swap_fixture_manager(app, manager) -> int:
    """Hand the engine a fixture manager. Returns the new live rig version."""
    engine = getattr(app.state, "effects_engine", None)
    _sync_output_hold(app)
    if engine is not None:
        setter = getattr(engine, "set_fixture_manager", None)
        if callable(setter):
            setter(manager)
        else:
            engine.fixtures = manager
    app.state.fixture_manager = manager
    return bump_live_rig_version(app)


def record_live_rig(app, *, rig_id: Optional[int], name: Optional[str], demo: bool, fixtures: int) -> None:
    """What /api/effects/status reports as the rig on stage."""
    app.state.live_rig = {"id": rig_id, "name": name, "demo": demo, "fixtures": fixtures}


def install_patched_rig(app, manager, *, rig_id: Optional[int], name: Optional[str]) -> int:
    """Put a rig from the database on stage and release the demo's output hold."""
    version = swap_fixture_manager(app, manager)
    app.state.dmx_output_held = False
    _sync_output_hold(app)
    record_live_rig(
        app, rig_id=rig_id, name=name or "active rig", demo=False,
        fixtures=len(getattr(manager, "fixtures", None) or {}),
    )
    return version


async def new_rig_is_active(db) -> bool:
    """Whether a rig being created should carry the active mark.

    Only when no rig holds it: the first rig of a fresh install is the one a
    restart boots on, as before. After that the mark moves only through
    Activate. Every way of making a rig used to stamp it active, so every rig
    in the list read "Active", the Activate control never showed, and a restart
    booted whichever rig was touched last, checked or not.
    """
    from sqlalchemy import select

    from app.models.rig import Rig

    taken = (await db.execute(select(Rig.id).where(Rig.is_active == True).limit(1))).first()  # noqa: E712
    return taken is None


def _label(entry: Dict[str, Any]) -> str:
    name = entry.get("name")
    return f"'{name}'" if name else f"fixture {entry.get('rig_fixture_id')}"


def _footprint(fixture) -> int:
    span = getattr(fixture, "channel_span", None)
    if not span:
        span = max((fixture.channels or {}).values(), default=0) + 1
    return max(1, int(span))


def rig_problems(manager) -> List[str]:
    """Reasons a rig built by the rig loader must not go on stage.

    Read from the loader's own account of the build, so this judges the rig
    the engine would drive: its modes, its footprints, its skipped patches.
    An empty list means the rig is safe to run.
    """
    problems: List[str] = []
    diagnostics = get_rig_diagnostics(manager)
    if diagnostics is not None:
        for entry in diagnostics.skipped:
            if entry.get("reason") == NOT_ACTIVE_REASON:
                continue
            problems.append(f"{_label(entry)}: {entry.get('reason')}")
        for entry in diagnostics.truncated:
            start = entry.get("dmx_address")
            count = entry.get("channel_count")
            problems.append(
                f"{_label(entry)}: {count} channels from address {start} run past channel "
                f"{DMX_UNIVERSE_SIZE} of universe {entry.get('universe')}"
            )
        problems.extend(diagnostics.errors)

    by_universe: Dict[int, List[Any]] = {}
    for fixture in (getattr(manager, "fixtures", None) or {}).values():
        by_universe.setdefault(int(fixture.universe), []).append(fixture)
    for universe, fixtures in sorted(by_universe.items()):
        fixtures.sort(key=lambda f: f.dmx_address)
        # Against the furthest channel claimed so far, not only the neighbour:
        # one long fixture can cover several short ones.
        holder = None
        holder_end = 0
        for fixture in fixtures:
            end = fixture.dmx_address + _footprint(fixture) - 1
            if holder is not None and fixture.dmx_address <= holder_end:
                problems.append(
                    f"'{fixture.name}' at {fixture.dmx_address}-{end} overlaps '{holder.name}' at "
                    f"{holder.dmx_address}-{holder_end} on universe {universe}"
                )
            if end > holder_end:
                holder, holder_end = fixture, end
    return problems
