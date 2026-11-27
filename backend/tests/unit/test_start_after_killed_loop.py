"""/start after a cancelled engine loop must start a new loop (Q15)."""

import asyncio

import pytest

from app.api.endpoints import effects as effects_api
from app.services.effects.effects_engine import EffectsConfig, EffectsEngine


def _counting_engine():
    engine = EffectsEngine(EffectsConfig(fps=40))
    frames = {"n": 0}

    def tick(delta_time=None):
        frames["n"] += 1

    engine.update = tick
    return engine, frames


async def _cancel(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_run_clears_running_when_the_loop_is_cancelled():
    engine, frames = _counting_engine()
    task = asyncio.create_task(engine.run())
    await asyncio.sleep(0.05)
    assert engine.running
    assert frames["n"] > 0

    await _cancel(task)

    assert engine.running is False
    assert engine._run_task is None


@pytest.mark.asyncio
async def test_start_loop_restarts_after_a_cancelled_task():
    engine, frames = _counting_engine()
    first = engine.start_loop()
    await asyncio.sleep(0.05)
    first_count = frames["n"]
    assert first_count > 0

    await _cancel(first)

    second = engine.start_loop()
    assert second is not first
    await asyncio.sleep(0.05)
    try:
        assert engine.running
        assert not second.done()
        assert frames["n"] > first_count
    finally:
        engine.stop()
        await asyncio.wait_for(second, timeout=1.0)


@pytest.mark.asyncio
async def test_start_loop_is_idempotent_while_a_task_is_alive():
    engine, _frames = _counting_engine()
    first = engine.start_loop()
    await asyncio.sleep(0.05)
    try:
        assert engine.start_loop() is first
        assert engine.running
        assert not first.done()
    finally:
        engine.stop()
        await asyncio.wait_for(first, timeout=1.0)


@pytest.mark.asyncio
async def test_start_loop_ignores_a_stale_running_flag():
    """A cancelled loop used to leave running True with no live task."""
    engine, frames = _counting_engine()
    engine.running = True
    engine._run_task = None

    task = engine.start_loop()
    await asyncio.sleep(0.05)
    try:
        assert frames["n"] > 0
        assert engine.running
        assert not task.done()
    finally:
        engine.stop()
        await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_start_endpoint_works_after_a_killed_loop_without_stop():
    engine, frames = _counting_engine()
    previous = effects_api._effects_engine
    effects_api.set_effects_engine(engine)
    first = engine.start_loop()
    await asyncio.sleep(0.05)
    await _cancel(first)

    try:
        result = await effects_api.start_effects()
        assert result["status"] == "started"
        await asyncio.sleep(0.05)
        task = engine._run_task
        assert engine.running
        assert task is not None and not task.done()
        assert frames["n"] > 0
        engine.stop()
        await asyncio.wait_for(task, timeout=1.0)
    finally:
        effects_api.set_effects_engine(previous)
