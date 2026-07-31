"""
Live Fixture Test Service
==========================

Provides identify, color cycle, movement, and full test sequences
for individual fixtures using actual DMX output.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple

from app.models.fixture import ChannelType

logger = logging.getLogger(__name__)


class FixtureTestService:
    """Service for running live fixture tests via DMX output."""

    def __init__(self, dmx_controller):
        self.dmx = dmx_controller
        self.active_tests: Dict[int, asyncio.Task] = {}  # rig_fixture_id -> task

    def _build_channel_map(self, mode_channels: List[Any]) -> Dict[str, int]:
        """Build a map of channel_type -> 0-indexed DMX offset.

        mode_channels: list of FixtureChannel model instances or dicts.
        """
        coarse: Dict[str, int] = {}
        fine: Dict[str, int] = {}

        for ch in mode_channels:
            if hasattr(ch, "channel_type"):
                ct = ch.channel_type.value if hasattr(ch.channel_type, "value") else ch.channel_type
                offset = ch.channel_number - 1  # Convert 1-indexed to 0-indexed
                is_fine = bool(getattr(ch, "is_fine", False))
            else:
                ct = ch.get("channel_type", "other")
                offset = ch.get("channel_number", 1) - 1
                is_fine = bool(ch.get("is_fine", False))

            # Only pan and tilt have dedicated fine channel types; every other 16-bit
            # channel repeats its coarse type, so a plain assignment would leave the
            # map pointing at the low byte and the fixture dark during an identify.
            target = fine if is_fine else coarse
            if ct not in target or offset < target[ct]:
                target[ct] = offset

        for ct, offset in fine.items():
            coarse.setdefault(ct, offset)
        return coarse

    async def _set_fixture_channel(
        self, universe: int, base_address: int, offset: int, value: int
    ):
        """Set a single channel on the fixture."""
        channel = base_address + offset  # base_address is 1-indexed DMX
        if 1 <= channel <= 512:
            await self.dmx.set_channel(universe, channel, max(0, min(255, value)))

    async def _set_fixture_channels(
        self,
        universe: int,
        base_address: int,
        channel_values: Dict[int, int],
    ):
        """Set multiple channels on a fixture. channel_values: {offset: value}."""
        for offset, value in channel_values.items():
            await self._set_fixture_channel(universe, base_address, offset, value)

    async def _zero_fixture(
        self, universe: int, base_address: int, channel_count: int
    ):
        """Zero all channels of a fixture."""
        for offset in range(channel_count):
            await self._set_fixture_channel(universe, base_address, offset, 0)

    async def identify(
        self,
        universe: int,
        base_address: int,
        ch_map: Dict[str, int],
        channel_count: int,
    ):
        """Identify test: full white at full brightness for 3 seconds."""
        values = {}
        if "dimmer" in ch_map:
            values[ch_map["dimmer"]] = 255
        if "red" in ch_map:
            values[ch_map["red"]] = 255
        if "green" in ch_map:
            values[ch_map["green"]] = 255
        if "blue" in ch_map:
            values[ch_map["blue"]] = 255
        if "white" in ch_map:
            values[ch_map["white"]] = 255
        if "shutter" in ch_map:
            values[ch_map["shutter"]] = 255  # Open shutter

        await self._set_fixture_channels(universe, base_address, values)
        await asyncio.sleep(3.0)
        await self._zero_fixture(universe, base_address, channel_count)

    async def color_cycle(
        self,
        universe: int,
        base_address: int,
        ch_map: Dict[str, int],
        channel_count: int,
    ):
        """Cycle through colors: R, G, B, Yellow, Magenta, Cyan, White."""
        colors = [
            (255, 0, 0),    # Red
            (0, 255, 0),    # Green
            (0, 0, 255),    # Blue
            (255, 255, 0),  # Yellow
            (255, 0, 255),  # Magenta
            (0, 255, 255),  # Cyan
            (255, 255, 255),  # White
        ]

        # Ensure dimmer and shutter open
        base_values = {}
        if "dimmer" in ch_map:
            base_values[ch_map["dimmer"]] = 255
        if "shutter" in ch_map:
            base_values[ch_map["shutter"]] = 255

        for r, g, b in colors:
            values = dict(base_values)
            if "red" in ch_map:
                values[ch_map["red"]] = r
            if "green" in ch_map:
                values[ch_map["green"]] = g
            if "blue" in ch_map:
                values[ch_map["blue"]] = b
            await self._set_fixture_channels(universe, base_address, values)
            await asyncio.sleep(1.0)

        await self._zero_fixture(universe, base_address, channel_count)

    async def movement_test(
        self,
        universe: int,
        base_address: int,
        ch_map: Dict[str, int],
        channel_count: int,
    ):
        """Movement test: sweep pan 0-255, tilt 0-255, then center."""
        # Turn on light first
        base_values = {}
        if "dimmer" in ch_map:
            base_values[ch_map["dimmer"]] = 255
        if "white" in ch_map:
            base_values[ch_map["white"]] = 200
        elif "red" in ch_map:
            base_values[ch_map["red"]] = 200
            if "green" in ch_map:
                base_values[ch_map["green"]] = 200
            if "blue" in ch_map:
                base_values[ch_map["blue"]] = 200
        if "shutter" in ch_map:
            base_values[ch_map["shutter"]] = 255

        await self._set_fixture_channels(universe, base_address, base_values)
        await asyncio.sleep(0.5)

        # Pan sweep
        if "pan" in ch_map:
            for val in range(0, 256, 8):
                await self._set_fixture_channel(
                    universe, base_address, ch_map["pan"], val
                )
                await asyncio.sleep(0.05)
            # Return to center
            await self._set_fixture_channel(
                universe, base_address, ch_map["pan"], 128
            )
            await asyncio.sleep(0.3)

        # Tilt sweep
        if "tilt" in ch_map:
            for val in range(0, 256, 8):
                await self._set_fixture_channel(
                    universe, base_address, ch_map["tilt"], val
                )
                await asyncio.sleep(0.05)
            # Return to center
            await self._set_fixture_channel(
                universe, base_address, ch_map["tilt"], 128
            )
            await asyncio.sleep(0.3)

        await self._zero_fixture(universe, base_address, channel_count)

    async def _full_test(
        self,
        universe: int,
        base_address: int,
        ch_map: Dict[str, int],
        channel_count: int,
    ):
        """Run all tests sequentially."""
        await self.identify(universe, base_address, ch_map, channel_count)
        await asyncio.sleep(0.5)
        await self.color_cycle(universe, base_address, ch_map, channel_count)
        await asyncio.sleep(0.5)
        await self.movement_test(universe, base_address, ch_map, channel_count)

    async def run_test(
        self,
        rig_fixture_id: int,
        universe: int,
        base_address: int,
        ch_map: Dict[str, int],
        channel_count: int,
        test_type: str = "identify",
    ):
        """Run a test, managing the active test task."""
        # Stop any existing test for this fixture
        await self.stop_test(rig_fixture_id)

        test_funcs = {
            "identify": self.identify,
            "color_cycle": self.color_cycle,
            "movement": self.movement_test,
            "full": self._full_test,
        }

        func = test_funcs.get(test_type)
        if not func:
            raise ValueError(f"Unknown test type: {test_type}")

        async def _run():
            try:
                await func(universe, base_address, ch_map, channel_count)
            except asyncio.CancelledError:
                # Clean up - zero the fixture on cancellation
                await self._zero_fixture(universe, base_address, channel_count)
            finally:
                self.active_tests.pop(rig_fixture_id, None)

        task = asyncio.create_task(_run())
        self.active_tests[rig_fixture_id] = task

    async def stop_test(self, rig_fixture_id: int):
        """Stop an active test for a fixture."""
        task = self.active_tests.pop(rig_fixture_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def set_channels(
        self,
        universe: int,
        base_address: int,
        channel_values: Dict[int, int],
    ):
        """Live fader control - set specific channels on a fixture."""
        await self._set_fixture_channels(universe, base_address, channel_values)
