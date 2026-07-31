"""
DMX Controller Service
======================

Controls DMX output via ArtNet protocol.
"""

import asyncio
import logging
import socket
import struct
import time
from typing import Dict, List, Optional, Set, Any
from collections import defaultdict

from app.core.config import settings
from app.schemas.dmx import DMXFrame, DMXUniverse, ArtNetConfig, DMXSceneState, DMXFixtureState


logger = logging.getLogger(__name__)


class ArtNetProtocol:
    """ArtNet protocol implementation."""

    ARTNET_HEADER = b'Art-Net\x00'
    OPCODE_DMX = 0x5000
    PROTOCOL_VERSION = 14

    @staticmethod
    def encode_port_address(universe: int, net: int = 0, subnet: int = 0) -> int:
        """Encode the Art-Net 4 15-bit Port-Address (Net << 8 | Sub-Net << 4 | Universe).

        A ``universe`` above 15 does not fit the 4-bit Universe field, so it is
        taken to already be a full Port-Address and Net/Sub-Net are ignored.
        """
        if universe > 0x0F:
            return universe & 0x7FFF
        return ((net & 0x7F) << 8) | ((subnet & 0x0F) << 4) | (universe & 0x0F)

    @staticmethod
    def create_dmx_packet(
        universe: int,
        data: bytes,
        sequence: int = 0,
        net: int = 0,
        subnet: int = 0,
    ) -> bytes:
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

        # Port-Address: SubUni (Sub-Net + Universe) then Net
        port_address = ArtNetProtocol.encode_port_address(universe, net, subnet)
        packet.append(port_address & 0xFF)
        packet.append((port_address >> 8) & 0x7F)

        # Length (big endian)
        packet.extend(struct.pack('>H', len(data)))

        # DMX data
        packet.extend(data)

        return bytes(packet)


class DMXController:
    """DMX controller with ArtNet output support."""

    BROADCAST_ADDRESS = '255.255.255.255'
    UNSPECIFIED_ADDRESSES = ('', '0.0.0.0')
    # Frames leave at DMX_FPS, so a gap this long means the output loop stopped.
    TRANSMIT_STALE_AFTER = 1.0

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
        # Universes that exist only to carry a test pattern, and the pending tasks
        # that hand them back once their blackout frame has gone out.
        self._borrowed_universes: Set[int] = set()
        self._release_tasks: Dict[int, asyncio.Task] = {}
        self.pre_blackout_state: Dict[int, List[int]] = {}

        # Output state
        self.sequence = 0
        self.target_fps = settings.DMX_FPS
        self.current_fps = 0.0
        self.frames_sent = 0
        self.send_error_count = 0
        self.last_send_error: Optional[str] = None
        self.last_send_time = 0.0
        self._send_error_logged = False

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

    @property
    def packets_sent(self) -> int:
        """Number of ArtDmx packets handed to the socket without error."""
        return self.frames_sent

    @property
    def target_ip(self) -> str:
        """Resolved destination address.

        An unset or wildcard address is not routable as a destination, so it
        falls back to limited broadcast - the standard ArtNet default.
        """
        ip_address = (self.config.ip_address or '').strip()
        if self.config.broadcast or ip_address in self.UNSPECIFIED_ADDRESSES:
            return self.BROADCAST_ADDRESS
        return ip_address

    @property
    def is_broadcast(self) -> bool:
        """Whether the resolved destination is a broadcast address."""
        target = self.target_ip
        return target == self.BROADCAST_ADDRESS or target.endswith('.255')

    async def connect(self):
        """Connect to the ArtNet interface."""
        if self.is_connected:
            return

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            if self.is_broadcast:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # BUG-018 fix: keep socket blocking for synchronous sendto()
            self.socket.setblocking(True)
            self._send_error_logged = False

            # Universes are created on demand by whatever drives them. Pre-seeding
            # here would transmit continuous zeros on a Port-Address this box does
            # not own, which fights any other console already merging on it.
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

            # Snapshot: _send_universe awaits, and other tasks add or drop universes.
            for universe_num, universe in list(self.universes.items()):
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
        packet = ArtNetProtocol.create_dmx_packet(
            universe,
            data,
            self.sequence,
            net=self.config.net,
            subnet=self.config.subnet,
        )

        # Send packet
        target = (self.target_ip, self.config.port)
        try:
            self.socket.sendto(packet, target)
            self.frames_sent += 1
            self.last_send_time = time.time()
            self.last_send_error = None
            self._send_error_logged = False
        except OSError as e:
            # BUG-017 fix: log send errors instead of silencing them
            self.send_error_count += 1
            self.last_send_error = str(e)
            if not self._send_error_logged:
                logger.warning(
                    f"ArtNet send error to {target[0]}:{target[1]} (suppressing repeats): {e}"
                )
                self._send_error_logged = True

    def get_config(self) -> ArtNetConfig:
        """Get current configuration."""
        return self.config

    def get_transmit_status(self) -> Dict[str, Any]:
        """Report actual ArtNet output health."""
        last_send_time = self.last_send_time or None
        stalled = (
            last_send_time is None
            or (time.time() - last_send_time) > self.TRANSMIT_STALE_AFTER
        )
        return {
            "connected": self.is_connected,
            "transmitting": (
                self.is_connected and not stalled and self.last_send_error is None
            ),
            "target_ip": self.target_ip,
            "port": self.config.port,
            "broadcast": self.is_broadcast,
            "frames_sent": self.frames_sent,
            "send_error_count": self.send_error_count,
            "last_send_error": self.last_send_error,
            "last_send_time": last_send_time,
        }

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

        # A release from a previous run on this universe may still be pending. Let it
        # fire and it would pop the entry out from under this run mid-pattern.
        pending_release = self._release_tasks.pop(universe, None)
        if pending_release is not None:
            pending_release.cancel()

        if universe not in self.universes:
            self.universes[universe] = DMXUniverse(universe=universe)
            self._borrowed_universes.add(universe)
        borrowed = universe in self._borrowed_universes

        async def bounded_pattern():
            try:
                await asyncio.wait_for(
                    self._run_pattern(universe, pattern),
                    timeout=max_duration
                )
            except asyncio.TimeoutError:
                pass
            finally:
                # Every pattern can end on a full-on frame - by operator stop, by the
                # duration timeout firing unattended, or by simply running to
                # completion. Nothing else writes this universe, so without an
                # explicit blackout the rig stays latched at 255 forever.
                entry = self.universes.get(universe)
                if entry is not None:
                    entry.data = [0] * 512
                if borrowed:
                    try:
                        self._release_tasks[universe] = asyncio.get_running_loop().create_task(
                            self._release_borrowed_universe(universe)
                        )
                    except RuntimeError:
                        self.universes.pop(universe, None)
                        self._borrowed_universes.discard(universe)

        self.test_pattern_task = asyncio.create_task(bounded_pattern())

    async def _release_borrowed_universe(self, universe: int):
        """Stop transmitting a universe that only existed to carry a test pattern.

        Delayed so the blackout frame actually reaches the wire first; a fixture left
        holding its last value is exactly what the blackout is there to prevent.
        """
        try:
            await asyncio.sleep(0.25)
            entry = self.universes.get(universe)
            if entry is not None and not any(entry.data):
                self.universes.pop(universe, None)
                self._borrowed_universes.discard(universe)
        finally:
            self._release_tasks.pop(universe, None)

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
                self.universes[universe].data = [255] * 512
                # Hold rather than return, so max_duration bounds how long the rig
                # sits at full and the caller's cleanup gets to run afterwards.
                while True:
                    await asyncio.sleep(0.1)
            elif pattern == "all_off":
                self.universes[universe].data = [0] * 512
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
