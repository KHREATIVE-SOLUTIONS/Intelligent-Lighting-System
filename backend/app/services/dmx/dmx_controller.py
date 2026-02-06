"""
DMX Controller Service
======================

Controls DMX output via ArtNet protocol.
"""

import asyncio
import socket
import struct
import time
from typing import Dict, List, Optional, Set, Any
from collections import defaultdict

from app.core.config import settings
from app.schemas.dmx import DMXFrame, DMXUniverse, ArtNetConfig, DMXSceneState, DMXFixtureState


class ArtNetProtocol:
    """ArtNet protocol implementation."""

    ARTNET_HEADER = b'Art-Net\x00'
    OPCODE_DMX = 0x5000
    PROTOCOL_VERSION = 14

    @staticmethod
    def create_dmx_packet(universe: int, data: bytes, sequence: int = 0) -> bytes:
        """Create an ArtNet DMX packet."""
        # Ensure data is 512 bytes
        if len(data) < 512:
            data = data + bytes(512 - len(data))
        elif len(data) > 512:
            data = data[:512]

        # ArtNet header
        packet = bytearray(ArtNetProtocol.ARTNET_HEADER)

        # OpCode (little endian)
        packet.extend(struct.pack('<H', ArtNetProtocol.OPCODE_DMX))

        # Protocol version (big endian)
        packet.extend(struct.pack('>H', ArtNetProtocol.PROTOCOL_VERSION))

        # Sequence (0 = disabled)
        packet.append(sequence)

        # Physical port
        packet.append(0)

        # Universe (little endian)
        packet.extend(struct.pack('<H', universe))

        # Length (big endian)
        packet.extend(struct.pack('>H', len(data)))

        # DMX data
        packet.extend(data)

        return bytes(packet)


class DMXController:
    """DMX controller with ArtNet output support."""

    def __init__(self):
        """Initialize the DMX controller."""
        self.is_connected = False
        self.socket: Optional[socket.socket] = None

        # Configuration
        self.config = ArtNetConfig(
            ip_address=settings.ARTNET_IP,
            port=settings.ARTNET_PORT,
            universes=[settings.DMX_UNIVERSE],
        )

        # Universe data
        self.universes: Dict[int, DMXUniverse] = {}
        self.pre_blackout_state: Dict[int, List[int]] = {}

        # Output state
        self.sequence = 0
        self.target_fps = settings.DMX_FPS
        self.current_fps = 0.0
        self.packets_sent = 0
        self.last_send_time = 0.0

        # Fade engine
        self.fade_tasks: Dict[str, asyncio.Task] = {}

        # Subscribers for updates
        self.subscribers: Set[asyncio.Queue] = set()

        # Output loop
        self.output_task: Optional[asyncio.Task] = None
        self.test_pattern_task: Optional[asyncio.Task] = None

    @property
    def active_universes(self) -> List[int]:
        """Get list of active universe numbers."""
        return list(self.universes.keys())

    async def connect(self):
        """Connect to the ArtNet interface."""
        if self.is_connected:
            return

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # BUG-018 fix: keep socket blocking for synchronous sendto()
            self.socket.setblocking(True)

            # Initialize universes
            for universe in self.config.universes:
                self.universes[universe] = DMXUniverse(universe=universe)

            self.is_connected = True

            # Start output loop
            self.output_task = asyncio.create_task(self._output_loop())

        except Exception as e:
            self.is_connected = False
            raise Exception(f"Failed to connect to ArtNet: {e}")

    async def disconnect(self):
        """Disconnect from the ArtNet interface."""
        self.is_connected = False

        if self.output_task:
            self.output_task.cancel()
            try:
                await self.output_task
            except asyncio.CancelledError:
                pass

        if self.socket:
            self.socket.close()
            self.socket = None

    async def _output_loop(self):
        """Main output loop sending DMX frames at target FPS."""
        frame_time = 1.0 / self.target_fps
        fps_counter = 0
        fps_start_time = time.time()

        while self.is_connected:
            loop_start = time.time()

            # Send all universes
            for universe_num, universe in self.universes.items():
                await self._send_universe(universe_num, bytes(universe.data))

            # FPS tracking
            fps_counter += 1
            elapsed = time.time() - fps_start_time
            if elapsed >= 1.0:
                self.current_fps = fps_counter / elapsed
                fps_counter = 0
                fps_start_time = time.time()

            # Wait for next frame
            elapsed = time.time() - loop_start
            sleep_time = max(0, frame_time - elapsed)
            await asyncio.sleep(sleep_time)

    async def _send_universe(self, universe: int, data: bytes):
        """Send a single universe of DMX data."""
        if not self.socket or not self.is_connected:
            return

        # Create packet
        self.sequence = (self.sequence + 1) % 256
        packet = ArtNetProtocol.create_dmx_packet(universe, data, self.sequence)

        # Send packet
        try:
            target = (
                self.config.ip_address if not self.config.broadcast else '255.255.255.255',
                self.config.port
            )
            self.socket.sendto(packet, target)
            self.packets_sent += 1
            self.last_send_time = time.time()
        except OSError as e:
            # BUG-017 fix: log send errors instead of silencing them
            if self.packets_sent % 1000 == 0:
                import logging
                logging.getLogger(__name__).warning(f"ArtNet send error: {e}")

    def get_config(self) -> ArtNetConfig:
        """Get current configuration."""
        return self.config

    async def update_config(self, config: ArtNetConfig):
        """Update configuration."""
        was_connected = self.is_connected

        if was_connected:
            await self.disconnect()

        self.config = config

        if was_connected:
            await self.connect()

    def get_universe(self, universe: int) -> DMXUniverse:
        """Get the current state of a universe."""
        if universe not in self.universes:
            self.universes[universe] = DMXUniverse(universe=universe)
        return self.universes[universe]

    async def set_frame(self, universe: int, frame: DMXFrame):
        """Set DMX values from a frame."""
        if universe not in self.universes:
            self.universes[universe] = DMXUniverse(universe=universe)

        for channel, value in frame.channels.items():
            self.universes[universe].set_channel(channel, value)

        # Notify subscribers
        await self._notify_subscribers({
            "type": "frame",
            "universe": universe,
            "channels": frame.channels,
        })

    async def set_channel(self, universe: int, channel: int, value: int):
        """Set a single DMX channel value."""
        if universe not in self.universes:
            self.universes[universe] = DMXUniverse(universe=universe)

        self.universes[universe].set_channel(channel, value)

        # Notify subscribers
        await self._notify_subscribers({
            "type": "channel",
            "universe": universe,
            "channel": channel,
            "value": value,
        })

    async def blackout(self, universes: Optional[List[int]] = None, fade_time: float = 0.0):
        """Blackout specified universes."""
        target_universes = universes or list(self.universes.keys())

        # Save current state
        for universe in target_universes:
            if universe in self.universes:
                self.pre_blackout_state[universe] = list(self.universes[universe].data)

        if fade_time > 0:
            # Fade to black
            await self._fade_universes(target_universes, [0] * 512, fade_time)
        else:
            # Instant blackout
            for universe in target_universes:
                if universe in self.universes:
                    self.universes[universe].data = [0] * 512

        await self._notify_subscribers({
            "type": "blackout",
            "universes": target_universes,
        })

    async def restore(self, fade_time: float = 0.0):
        """Restore from blackout."""
        for universe, data in self.pre_blackout_state.items():
            if fade_time > 0:
                await self._fade_universe(universe, data, fade_time)
            else:
                if universe in self.universes:
                    self.universes[universe].data = data

        self.pre_blackout_state.clear()

        await self._notify_subscribers({"type": "restore"})

    async def _fade_universes(
        self,
        universes: List[int],
        target_data: List[int],
        duration: float
    ):
        """Fade multiple universes to target values."""
        tasks = [
            self._fade_universe(universe, target_data, duration)
            for universe in universes
        ]
        await asyncio.gather(*tasks)

    async def _fade_universe(
        self,
        universe: int,
        target_data: List[int],
        duration: float
    ):
        """Fade a single universe to target values."""
        if universe not in self.universes:
            return

        start_data = list(self.universes[universe].data)
        steps = int(duration * self.target_fps)

        if steps <= 0:
            # Duration too short for any intermediate steps - apply immediately
            for i in range(512):
                self.universes[universe].data[i] = target_data[i]
            return

        for step in range(steps + 1):
            progress = step / steps
            for i in range(512):
                current = int(start_data[i] + (target_data[i] - start_data[i]) * progress)
                self.universes[universe].data[i] = current
            await asyncio.sleep(1.0 / self.target_fps)

    async def execute_cue(self, cue, fade_time: float = 0.0, delay: float = 0.0):
        """Execute a show cue."""
        if delay > 0:
            await asyncio.sleep(delay)

        # Apply DMX values from cue
        for channel_str, value in cue.dmx_values.items():
            # Parse channel string (format: "universe:channel" or just "channel")
            if ':' in channel_str:
                universe, channel = map(int, channel_str.split(':'))
            else:
                universe = 0
                channel = int(channel_str)

            if fade_time > 0:
                # Start fade (BUG-011 fix: store task reference for cleanup)
                task_key = f"cue_{universe}_{channel}"
                # Cancel any existing fade on this channel
                if task_key in self.fade_tasks:
                    self.fade_tasks[task_key].cancel()
                task = asyncio.create_task(
                    self._fade_channel(universe, channel, value, fade_time)
                )
                self.fade_tasks[task_key] = task
                task.add_done_callback(lambda t, k=task_key: self.fade_tasks.pop(k, None))
            else:
                await self.set_channel(universe, channel, value)

    async def _fade_channel(
        self,
        universe: int,
        channel: int,
        target: int,
        duration: float
    ):
        """Fade a single channel to target value."""
        if universe not in self.universes:
            return

        start_value = self.universes[universe].get_channel(channel)
        steps = int(duration * self.target_fps)

        if steps <= 0:
            # Duration too short for any intermediate steps - apply immediately
            self.universes[universe].set_channel(channel, target)
            return

        for step in range(steps + 1):
            progress = step / steps
            value = int(start_value + (target - start_value) * progress)
            self.universes[universe].set_channel(channel, value)
            await asyncio.sleep(1.0 / self.target_fps)

    async def set_fixture_state(self, rig_fixture_id: int, state: DMXFixtureState):
        """Set the state of a specific fixture.

        BUG-044 fix: actually write channel values to DMX universe instead of no-op.
        Maps channel_values dict entries to sequential DMX channels starting at start_address.
        """
        universe = state.universe
        start_address = state.start_address

        if universe not in self.universes:
            self.universes[universe] = DMXUniverse(universe=universe)

        # Map channel names to sequential offsets from start_address
        for offset, (channel_name, value) in enumerate(state.channel_values.items()):
            channel = start_address + offset
            if 1 <= channel <= 512:
                self.universes[universe].set_channel(channel, value)

        # Notify subscribers
        await self._notify_subscribers({
            "type": "fixture",
            "rig_fixture_id": rig_fixture_id,
            "universe": universe,
            "start_address": start_address,
        })

    def get_scene_state(self) -> DMXSceneState:
        """Get the current scene state.

        BUG-045 fix: return actual universe data as fixture states instead of empty list.
        """
        fixtures = []
        for universe_num, universe in self.universes.items():
            fixtures.append(DMXFixtureState(
                fixture_id=universe_num,
                rig_fixture_id=universe_num,
                universe=universe_num,
                start_address=1,
                channel_values={str(i + 1): universe.data[i] for i in range(512) if universe.data[i] > 0},
            ))
        return DMXSceneState(
            timestamp=time.time(),
            fixtures=fixtures,
            master_intensity=1.0,
        )

    async def run_test_pattern(self, universe: int, pattern: str, max_duration: float = 60.0):
        """Run a test pattern on a universe.

        BUG-034 fix: patterns auto-stop after max_duration to prevent unbounded tasks.
        """
        # Cancel any existing test pattern
        await self.stop_test_pattern()

        if universe not in self.universes:
            self.universes[universe] = DMXUniverse(universe=universe)

        async def bounded_pattern():
            try:
                await asyncio.wait_for(
                    self._run_pattern(universe, pattern),
                    timeout=max_duration
                )
            except asyncio.TimeoutError:
                pass

        self.test_pattern_task = asyncio.create_task(bounded_pattern())

    async def _run_pattern(self, universe: int, pattern: str):
        """Internal pattern runner."""
        try:
            if pattern == "chase":
                await self._chase_pattern(universe)
            elif pattern == "rainbow":
                await self._rainbow_pattern(universe)
            elif pattern == "strobe":
                await self._strobe_pattern(universe)
            elif pattern == "fade":
                await self._fade_pattern(universe)
            elif pattern == "all_on":
                for i in range(512):
                    self.universes[universe].data[i] = 255
            elif pattern == "all_off":
                for i in range(512):
                    self.universes[universe].data[i] = 0
        except asyncio.CancelledError:
            pass

    async def _chase_pattern(self, universe: int):
        """Chase pattern across all channels."""
        while True:
            for i in range(512):
                self.universes[universe].data = [0] * 512
                self.universes[universe].data[i] = 255
                await asyncio.sleep(0.02)

    async def _rainbow_pattern(self, universe: int):
        """Rainbow color cycle (assumes RGB fixtures)."""
        import math
        hue = 0.0
        while True:
            for i in range(0, 512, 3):
                # Simple HSV to RGB
                h = (hue + i / 512) % 1.0
                r, g, b = self._hsv_to_rgb(h, 1.0, 1.0)
                self.universes[universe].data[i] = int(r * 255)
                self.universes[universe].data[i + 1] = int(g * 255)
                self.universes[universe].data[i + 2] = int(b * 255)
            hue = (hue + 0.01) % 1.0
            await asyncio.sleep(0.03)

    def _hsv_to_rgb(self, h: float, s: float, v: float):
        """Convert HSV to RGB."""
        import colorsys
        return colorsys.hsv_to_rgb(h, s, v)

    async def _strobe_pattern(self, universe: int):
        """Strobe pattern."""
        while True:
            self.universes[universe].data = [255] * 512
            await asyncio.sleep(0.05)
            self.universes[universe].data = [0] * 512
            await asyncio.sleep(0.05)

    async def _fade_pattern(self, universe: int):
        """Fade up/down pattern."""
        while True:
            # Fade up
            for v in range(0, 256, 5):
                self.universes[universe].data = [v] * 512
                await asyncio.sleep(0.02)
            # Fade down
            for v in range(255, -1, -5):
                self.universes[universe].data = [v] * 512
                await asyncio.sleep(0.02)

    async def stop_test_pattern(self):
        """Stop any running test pattern."""
        if self.test_pattern_task:
            self.test_pattern_task.cancel()
            try:
                await self.test_pattern_task
            except asyncio.CancelledError:
                pass
            self.test_pattern_task = None

    def subscribe(self, queue: asyncio.Queue):
        """Subscribe to DMX updates."""
        self.subscribers.add(queue)

    def unsubscribe(self, queue: asyncio.Queue):
        """Unsubscribe from DMX updates."""
        self.subscribers.discard(queue)

    async def _notify_subscribers(self, update: Dict[str, Any]):
        """Notify all subscribers of an update."""
        for queue in self.subscribers:
            try:
                queue.put_nowait(update)
            except asyncio.QueueFull:
                pass  # Skip if queue is full
