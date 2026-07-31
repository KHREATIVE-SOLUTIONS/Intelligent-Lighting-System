"""
Unit Tests for DMX Controller
=============================
"""

import pytest
import asyncio
from app.services.dmx.dmx_controller import DMXController, ArtNetProtocol
from app.schemas.dmx import DMXFrame, DMXUniverse


@pytest.fixture
def controller():
    """Create a DMX controller instance."""
    return DMXController()


class TestArtNetProtocol:
    """Tests for ArtNet protocol implementation."""

    def test_create_dmx_packet_basic(self):
        """Test creating a basic DMX packet."""
        data = bytes([255] * 512)
        packet = ArtNetProtocol.create_dmx_packet(0, data)

        # Check header
        assert packet[:8] == b'Art-Net\x00'

        # Check opcode (little endian 0x5000)
        assert packet[8:10] == b'\x00\x50'

        # Check data length (big endian 512)
        assert packet[16:18] == b'\x02\x00'

        # Total packet size should be header (18) + data (512)
        assert len(packet) == 18 + 512

    def test_create_dmx_packet_short_data(self):
        """Test packet creation pads short data to 512 bytes."""
        data = bytes([128] * 100)
        packet = ArtNetProtocol.create_dmx_packet(0, data)

        # Should be padded to 512 bytes
        assert len(packet) == 18 + 512

    def test_create_dmx_packet_universe(self):
        """Test universe number is encoded correctly."""
        data = bytes(512)

        # Universe 0
        packet = ArtNetProtocol.create_dmx_packet(0, data)
        assert packet[14:16] == b'\x00\x00'

        # Universe 5
        packet = ArtNetProtocol.create_dmx_packet(5, data)
        assert packet[14:16] == b'\x05\x00'


class TestDMXController:
    """Tests for DMXController class."""

    def test_initialization(self, controller):
        """Test controller initializes correctly."""
        assert controller.is_connected == False
        assert controller.packets_sent == 0
        assert controller.target_fps == 40

    @pytest.mark.asyncio
    async def test_connect_disconnect(self, controller):
        """Test connecting and disconnecting."""
        await controller.connect()
        assert controller.is_connected == True
        # Nothing is transmitted until something drives it. Claiming universe 0 here
        # would put continuous zeros on a Port-Address the rig may not own.
        assert controller.universes == {}

        await controller.disconnect()
        assert controller.is_connected == False

    @pytest.mark.asyncio
    async def test_get_universe(self, controller):
        """Test getting universe state."""
        universe = controller.get_universe(0)

        assert isinstance(universe, DMXUniverse)
        assert universe.universe == 0
        assert len(universe.data) == 512

    @pytest.mark.asyncio
    async def test_set_channel(self, controller):
        """Test setting individual channel."""
        await controller.connect()

        await controller.set_channel(0, 1, 255)

        universe = controller.get_universe(0)
        assert universe.get_channel(1) == 255

        await controller.disconnect()

    @pytest.mark.asyncio
    async def test_set_frame(self, controller):
        """Test setting frame data."""
        await controller.connect()

        frame = DMXFrame(
            universe=0,
            channels={1: 100, 2: 150, 3: 200}
        )
        await controller.set_frame(0, frame)

        universe = controller.get_universe(0)
        assert universe.get_channel(1) == 100
        assert universe.get_channel(2) == 150
        assert universe.get_channel(3) == 200

        await controller.disconnect()

    @pytest.mark.asyncio
    async def test_blackout(self, controller):
        """Test blackout function."""
        await controller.connect()

        # Set some values first
        await controller.set_channel(0, 1, 255)
        await controller.set_channel(0, 2, 128)

        # Blackout
        await controller.blackout()

        universe = controller.get_universe(0)
        assert universe.get_channel(1) == 0
        assert universe.get_channel(2) == 0

        await controller.disconnect()

    @pytest.mark.asyncio
    async def test_blackout_restore(self, controller):
        """Test blackout and restore."""
        await controller.connect()

        # Set initial values
        await controller.set_channel(0, 1, 255)
        await controller.set_channel(0, 5, 100)

        # Blackout
        await controller.blackout()

        # Restore
        await controller.restore()

        universe = controller.get_universe(0)
        assert universe.get_channel(1) == 255
        assert universe.get_channel(5) == 100

        await controller.disconnect()


class TestDMXUniverse:
    """Tests for DMXUniverse schema."""

    def test_get_channel(self):
        """Test getting channel values."""
        universe = DMXUniverse(universe=0)
        universe.data[0] = 100

        assert universe.get_channel(1) == 100
        assert universe.get_channel(512) == 0

    def test_get_channel_bounds(self):
        """Test channel bounds checking."""
        universe = DMXUniverse(universe=0)

        # Out of bounds should return 0
        assert universe.get_channel(0) == 0
        assert universe.get_channel(513) == 0

    def test_set_channel(self):
        """Test setting channel values."""
        universe = DMXUniverse(universe=0)

        universe.set_channel(1, 255)
        assert universe.data[0] == 255

        universe.set_channel(512, 128)
        assert universe.data[511] == 128

    def test_set_channel_clamping(self):
        """Test that values are clamped to 0-255."""
        universe = DMXUniverse(universe=0)

        universe.set_channel(1, 300)  # Should clamp to 255
        assert universe.data[0] == 255

        universe.set_channel(1, -50)  # Should clamp to 0
        assert universe.data[0] == 0


class TestDMXFrame:
    """Tests for DMXFrame schema."""

    def test_to_bytes(self):
        """Test converting frame to bytes."""
        frame = DMXFrame(
            universe=0,
            channels={1: 255, 10: 128, 100: 64}
        )

        data = frame.to_bytes()

        assert len(data) == 512
        assert data[0] == 255
        assert data[9] == 128
        assert data[99] == 64

    def test_to_bytes_clamping(self):
        """Test that to_bytes clamps values."""
        frame = DMXFrame(
            universe=0,
            channels={1: 300, 2: -50}
        )

        data = frame.to_bytes()

        assert data[0] == 255  # Clamped from 300
        assert data[1] == 0    # Clamped from -50
