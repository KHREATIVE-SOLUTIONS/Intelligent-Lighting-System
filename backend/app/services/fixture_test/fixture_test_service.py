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
from app.services.dmx.channel_ranges import channel_type_name, resolve_channel_ranges

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

    def _build_open_values(self, mode_channels: List[Any]) -> Dict[str, int]:
        """channel_type -> the DMX value that lets light through without strobing.

        Only for shutter and strobe channels whose profile carries value ranges,
        and only for the channel `_build_channel_map` points that type at. A
        type missing from here is driven on the fixed numbers the tests always
        used: 255 on a shutter, and a strobe channel left alone.
        """
        chosen: Dict[str, Tuple[int, Any]] = {}
        for ch in mode_channels:
            if hasattr(ch, "channel_type"):
                ct = channel_type_name(ch.channel_type)
                offset = ch.channel_number - 1
                is_fine = bool(getattr(ch, "is_fine", False))
                ranges = getattr(ch, "value_ranges", None)
            else:
                ct = channel_type_name(ch.get("channel_type", "other"))
                offset = ch.get("channel_number", 1) - 1
                is_fine = bool(ch.get("is_fine", False))
                ranges = ch.get("value_ranges")
            if is_fine or ct not in ("shutter", "strobe"):
                continue
            if ct not in chosen or offset < chosen[ct][0]:
                chosen[ct] = (offset, ranges)

        open_values: Dict[str, int] = {}
        for ct, (_offset, ranges) in chosen.items():
            resolved = resolve_channel_ranges(ct, ranges)
            if resolved is not None:
                open_values[ct] = resolved.open_byte()
        return open_values

    @staticmethod
    def _open_light(
        values: Dict[int, int], ch_map: Dict[str, int], open_values: Optional[Dict[str, int]]
    ) -> None:
        """Put the shutter and strobe channels where the fixture shows light."""
        known = open_values or {}
        if "shutter" in ch_map:
            values[ch_map["shutter"]] = known.get("shutter", 255)  # Open shutter
        # A strobe channel is only touched when the profile names its resting
        # value: on some pars 0 is "closed", and a test on one shows nothing.
        if "strobe" in ch_map and "strobe" in known:
            values[ch_map["strobe"]] = known["strobe"]

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
        open_values: Optional[Dict[str, int]] = None,
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
        self._open_light(values, ch_map, open_values)

        await self._set_fixture_channels(universe, base_address, values)
        await asyncio.sleep(3.0)
        await self._zero_fixture(universe, base_address, channel_count)

    async def color_cycle(
        self,
        universe: int,
        base_address: int,
        ch_map: Dict[str, int],
        channel_count: int,
        open_values: Optional[Dict[str, int]] = None,
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
        self._open_light(base_values, ch_map, open_values)

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
        open_values: Optional[Dict[str, int]] = None,
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
        self._open_light(base_values, ch_map, open_values)

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
        open_values: Optional[Dict[str, int]] = None,
    ):
        """Run all tests sequentially."""
        await self.identify(universe, base_address, ch_map, channel_count, open_values)
        await asyncio.sleep(0.5)
        await self.color_cycle(universe, base_address, ch_map, channel_count, open_values)
        await asyncio.sleep(0.5)
        await self.movement_test(universe, base_address, ch_map, channel_count, open_values)

    async def run_test(
        self,
        rig_fixture_id: int,
        universe: int,
        base_address: int,
        ch_map: Dict[str, int],
        channel_count: int,
        test_type: str = "identify",
        open_values: Optional[Dict[str, int]] = None,
    ):
        """Run a test, managing the active test task.

        `open_values` is `_build_open_values` for the fixture's mode: the bytes
        its profile says open the shutter and rest the strobe channel.
        """
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
                await func(universe, base_address, ch_map, channel_count, open_values)
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
