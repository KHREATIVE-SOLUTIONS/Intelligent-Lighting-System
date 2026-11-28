"""
sACN sender, Art-Net Port-Address packing and the remembered output target.

Nothing here opens a real socket except one listener bound to 127.0.0.1:
frames go to a recording stand-in, and multicast and broadcast destinations
are only ever compared as strings.

sACN is a wire format behind the G2 output stage, not a second way out. The
packet-format tests below hand the send point a ``StagedFrame`` directly, as
master's own send-point test does; everything about blackout, master level,
flash limit and watchdog is proved through ``_transmit_frame``, the path the
venue's transmitter thread takes.
"""

import asyncio
import json
import struct
import uuid

import pytest
from pydantic import ValidationError

from app.main import app, _restore_output_target
from app.schemas.dmx import OutputTarget, validate_target_ip
from app.services.dmx import output_target, sacn
from app.services.dmx.dmx_controller import ArtNetProtocol, DMXController
from app.services.dmx.output_stage import StagedFrame

from tests.unit.test_output_stage import worst_flashes_per_second

CID = uuid.UUID("0f8fad5b-d9cb-469f-a165-70867728950e").bytes
TARGET_URL = "/api/dmx/output-target"
WIRE_FPS = 40


def staged(data) -> StagedFrame:
    """A payload marked as staged, for tests of the wire format alone."""
    if isinstance(data, int):
        data = bytes(data)
    return StagedFrame(bytes(data))


def payload(packet: bytes) -> bytes:
    """The 512 DMX slots of either protocol's packet."""
    if packet[:8] == b"Art-Net\x00":
        return packet[18:530]
    assert packet[4:16] == sacn.ACN_PACKET_IDENTIFIER
    return packet[126:638]


class RecordingSocket:
    """Stands in for the UDP socket; keeps what would have been sent."""

    def __init__(self):
        self.sent = []

    def sendto(self, packet, destination):
        self.sent.append((bytes(packet), destination))
        return len(packet)

    def close(self):
        pass


def run(coroutine):
    """Run a coroutine on a private loop, leaving the suite's own loop alone."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def wired_controller() -> tuple:
    """A controller that believes it is connected, sending into a recorder."""
    controller = DMXController()
    sock = RecordingSocket()
    controller.socket = sock
    controller.is_connected = True
    controller.sacn_cid = CID
    return controller, sock


def apply(controller: DMXController, **fields) -> OutputTarget:
    target = OutputTarget(**fields)
    # Not connected to a real socket, so the stop-swap-start has nothing to restart.
    connected, controller.is_connected = controller.is_connected, False
    run(controller.apply_output_target(target))
    controller.is_connected = connected
    return target


@pytest.fixture
def target_dir(tmp_path, monkeypatch):
    """Keep remembered targets out of the data dir the rest of the suite boots from."""
    monkeypatch.setattr(output_target, "default_data_dir", lambda: tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# E1.31 packet
# ---------------------------------------------------------------------------

class TestSACNPacket:
    def packet(self, **overrides) -> bytes:
        fields = dict(universe=1, data=bytes(range(256)) * 2, sequence=0, cid=CID)
        fields.update(overrides)
        return sacn.create_data_packet(**fields)

    def test_length_is_638_for_a_full_universe(self):
        assert len(self.packet()) == 638 == sacn.PACKET_LENGTH

    def test_root_layer(self):
        packet = self.packet()
        assert packet[0:2] == b"\x00\x10"            # preamble size
        assert packet[2:4] == b"\x00\x00"            # postamble size
        assert packet[4:16] == b"ASC-E1.17\x00\x00\x00"
        assert struct.unpack(">H", packet[16:18])[0] == 0x7000 | (638 - 16) == 0x726E
        assert struct.unpack(">I", packet[18:22])[0] == 0x00000004
        assert packet[22:38] == CID

    def test_framing_layer(self):
        packet = self.packet(universe=1, sequence=7, source_name="Front of house")
        assert struct.unpack(">H", packet[38:40])[0] == 0x7000 | (638 - 38) == 0x7258
        assert struct.unpack(">I", packet[40:44])[0] == 0x00000002
        name = packet[44:108]
        assert len(name) == 64
        assert name.rstrip(b"\x00") == b"Front of house"
        assert packet[108] == 100                    # default priority
        assert packet[109:111] == b"\x00\x00"        # no synchronization universe
        assert packet[111] == 7                      # sequence
        assert packet[112] == 0                      # options
        assert packet[113:115] == b"\x00\x01"        # universe, big endian

    def test_dmp_layer_start_code_and_slots(self):
        data = bytes((i * 7) % 256 for i in range(512))
        packet = self.packet(data=data)
        assert struct.unpack(">H", packet[115:117])[0] == 0x7000 | (638 - 115) == 0x720B
        assert packet[117] == 0x02                   # set property
        assert packet[118] == 0xA1                   # address and data type
        assert packet[119:121] == b"\x00\x00"        # first property address
        assert packet[121:123] == b"\x00\x01"        # address increment
        assert struct.unpack(">H", packet[123:125])[0] == 513  # start code + 512 slots
        assert packet[125] == 0x00                   # DMX null start code
        assert packet[126:638] == data

    def test_flags_are_0x7_on_every_layer(self):
        packet = self.packet()
        for offset in (16, 38, 115):
            assert packet[offset] >> 4 == 0x7

    @pytest.mark.parametrize("universe", [1, 255, 256, 4660, 63999])
    def test_universe_is_big_endian(self, universe):
        packet = self.packet(universe=universe)
        assert struct.unpack(">H", packet[113:115])[0] == universe

    @pytest.mark.parametrize("universe", [0, -1, 64000, 65535, True, "1", 1.0])
    def test_universe_outside_1_to_63999_is_refused(self, universe):
        with pytest.raises(ValueError):
            self.packet(universe=universe)

    def test_priority(self):
        assert self.packet(priority=0)[108] == 0
        assert self.packet(priority=200)[108] == 200
        for bad in (-1, 201):
            with pytest.raises(ValueError):
                self.packet(priority=bad)

    def test_short_frame_is_padded_and_long_frame_cut_to_512_slots(self):
        short = self.packet(data=b"\xff" * 10)
        assert len(short) == 638
        assert short[126:136] == b"\xff" * 10
        assert short[136:638] == bytes(502)
        assert len(self.packet(data=b"\x01" * 600)) == 638

    def test_long_source_name_keeps_its_terminator(self):
        packet = self.packet(source_name="x" * 200)
        assert packet[44:107] == b"x" * 63
        assert packet[107] == 0
        # A multi-byte character must not be cut in half.
        name = self.packet(source_name="é" * 40)[44:108].rstrip(b"\x00")
        assert name.decode("utf-8") == "é" * 31

    def test_cid_must_be_16_bytes(self):
        with pytest.raises(ValueError):
            self.packet(cid=b"short")

    def test_stream_terminated_option(self):
        assert self.packet(stream_terminated=True)[112] == 0x40

    def test_multicast_group_comes_from_the_universe(self):
        assert sacn.multicast_address(1) == "239.255.0.1"
        assert sacn.multicast_address(256) == "239.255.1.0"
        assert sacn.multicast_address(63999) == "239.255.249.255"
        with pytest.raises(ValueError):
            sacn.multicast_address(0)


# ---------------------------------------------------------------------------
# Art-Net Port-Address
# ---------------------------------------------------------------------------

class TestArtNetPortAddress:
    @pytest.mark.parametrize("net, subnet, universe, expected", [
        (0, 0, 0, 0x0000),
        (0, 0, 15, 0x000F),
        (0, 1, 0, 0x0010),
        (0, 15, 15, 0x00FF),
        (1, 0, 0, 0x0100),
        (2, 3, 4, 0x0234),
        (127, 15, 15, 0x7FFF),
    ])
    def test_pack(self, net, subnet, universe, expected):
        assert ArtNetProtocol.pack_port_address(net, subnet, universe) == expected
        assert ArtNetProtocol.unpack_port_address(expected) == (net, subnet, universe)

    @pytest.mark.parametrize("net, subnet, universe", [
        (128, 0, 0), (-1, 0, 0), (0, 16, 0), (0, -1, 0), (0, 0, 16), (0, 0, -1),
        (True, 0, 0), (0, 0, "1"),
    ])
    def test_pack_refuses_what_does_not_fit(self, net, subnet, universe):
        with pytest.raises(ValueError):
            ArtNetProtocol.pack_port_address(net, subnet, universe)

    def test_unpack_refuses_more_than_15_bits(self):
        for bad in (-1, 0x8000):
            with pytest.raises(ValueError):
                ArtNetProtocol.unpack_port_address(bad)

    def test_port_address_on_the_wire(self):
        controller, sock = wired_controller()
        apply(controller, protocol="artnet", ip_address="127.0.0.1", net=2, subnet=3, universe=4)
        controller._send_universe(0, staged(512))
        controller._send_universe(1, staged(512))
        first, second = (packet for packet, _ in sock.sent)
        assert first[14] == 0x34 and first[15] == 0x02   # SubUni, then Net
        assert second[14] == 0x35 and second[15] == 0x02
        assert controller.artnet_port_address(0) == 0x0234

    def test_untouched_controller_still_sends_engine_universe_as_is(self):
        controller, sock = wired_controller()
        controller.config.ip_address = "127.0.0.1"
        controller.config.net, controller.config.subnet = 1, 2
        for universe in (0, 5, 300):
            controller._send_universe(universe, staged(512))
        addresses = [packet[14] | (packet[15] << 8) for packet, _ in sock.sent]
        assert addresses == [0x0120, 0x0125, 300]


# ---------------------------------------------------------------------------
# Routing through the controller
# ---------------------------------------------------------------------------

class TestProtocolRouting:
    def test_artnet_is_the_default_sender(self):
        controller, sock = wired_controller()
        controller.config.ip_address = "127.0.0.1"
        controller._send_universe(0, staged([9] * 512))
        packet, destination = sock.sent[0]
        assert packet[:8] == b"Art-Net\x00"
        assert destination == ("127.0.0.1", 6454)

    def test_sacn_target_sends_e131_to_the_node_on_5568(self):
        controller, sock = wired_controller()
        apply(controller, protocol="sacn", ip_address="127.0.0.1", universe=7, priority=150)
        controller._send_universe(0, staged([9] * 512))
        packet, destination = sock.sent[0]
        assert destination == ("127.0.0.1", 5568)
        assert packet[4:16] == sacn.ACN_PACKET_IDENTIFIER
        assert packet[22:38] == CID
        assert packet[108] == 150
        assert struct.unpack(">H", packet[113:115])[0] == 7
        assert packet[126:638] == bytes([9] * 512)
        assert controller.get_transmit_status()["protocol"] == "sacn"
        assert controller.get_transmit_status()["port"] == 5568
        assert controller.is_broadcast is False

    def test_switching_protocol_switches_sender(self):
        controller, sock = wired_controller()
        apply(controller, protocol="sacn", ip_address="127.0.0.1", universe=1)
        controller._send_universe(0, staged(512))
        apply(controller, protocol="artnet", ip_address="127.0.0.2")
        controller._send_universe(0, staged(512))
        apply(controller, protocol="sacn", ip_address="127.0.0.3", universe=2)
        controller._send_universe(0, staged(512))

        kinds = ["artnet" if p[:8] == b"Art-Net\x00" else "sacn" for p, _ in sock.sent]
        assert kinds == ["sacn", "artnet", "sacn"]
        assert [d for _, d in sock.sent] == [
            ("127.0.0.1", 5568), ("127.0.0.2", 6454), ("127.0.0.3", 5568),
        ]

    def test_engine_universes_follow_on_from_the_target_universe(self):
        controller, sock = wired_controller()
        apply(controller, protocol="sacn", ip_address="127.0.0.1", universe=10)
        for engine_universe in (0, 1, 2):
            controller._send_universe(engine_universe, staged(512))
        assert [struct.unpack(">H", p[113:115])[0] for p, _ in sock.sent] == [10, 11, 12]

    def test_sacn_sequence_counts_per_universe_and_wraps_through_zero(self):
        controller, sock = wired_controller()
        apply(controller, protocol="sacn", ip_address="127.0.0.1", universe=1)
        for _ in range(258):
            controller._send_universe(0, staged(512))
        sequences = [p[111] for p, _ in sock.sent]
        assert sequences[:3] == [0, 1, 2]
        assert sequences[255:258] == [255, 0, 1]

        controller._send_universe(1, staged(512))
        assert sock.sent[-1][0][111] == 0, "each universe keeps its own sequence"

    def test_multicast_goes_to_each_universes_own_group(self):
        controller, sock = wired_controller()
        apply(controller, protocol="sacn", multicast=True, universe=300)
        controller._send_universe(0, staged(512))
        controller._send_universe(1, staged(512))
        assert [d for _, d in sock.sent] == [("239.255.1.44", 5568), ("239.255.1.45", 5568)]
        assert controller.get_transmit_status()["multicast"] is True

    def test_universe_past_63999_is_an_error_not_a_wrong_universe(self):
        controller, sock = wired_controller()
        apply(controller, protocol="sacn", ip_address="127.0.0.1", universe=63999)
        with pytest.raises(ValueError):
            controller._send_universe(1, staged(512))
        assert sock.sent == []

    def test_written_frames_reach_sacn_through_the_same_universe_store(self):
        """write_universe is the one way in, whatever protocol carries it out."""
        controller, sock = wired_controller()
        apply(controller, protocol="sacn", ip_address="127.0.0.1", universe=1)
        controller.write_universe(0, [200] * 512)
        run(controller.blackout())
        # Through the output stage, the way the transmitter thread sends.
        controller._transmit_frame(0.0)
        packet, _ = sock.sent[0]
        assert packet[4:16] == sacn.ACN_PACKET_IDENTIFIER
        assert packet[126:638] == bytes(512), "the blackout applies to sACN output too"

    def test_blackout_on_stop_speaks_the_chosen_protocol(self):
        controller, sock = wired_controller()
        controller.target_fps = 1000
        apply(controller, protocol="sacn", ip_address="127.0.0.1", universe=5)
        controller.write_universe(0, [255] * 512)
        controller._send_final_blackout(sock)
        assert len(sock.sent) == controller.FINAL_BLACKOUT_REPEATS
        for packet, destination in sock.sent:
            assert destination == ("127.0.0.1", 5568)
            assert struct.unpack(">H", packet[113:115])[0] == 5
            assert packet[126:638] == bytes(512)

    def test_replacing_artnet_config_does_not_switch_protocol_back(self):
        from app.schemas.dmx import ArtNetConfig

        controller, sock = wired_controller()
        apply(controller, protocol="sacn", ip_address="127.0.0.1", universe=1)
        controller.config = ArtNetConfig()   # what PUT /config does; default is broadcast
        controller._send_universe(0, staged(512))
        assert sock.sent[0][1] == ("127.0.0.1", 5568)


# ---------------------------------------------------------------------------
# sACN goes through the G2 output stage
# ---------------------------------------------------------------------------

def sacn_controller(universe: int = 1) -> tuple:
    controller, sock = wired_controller()
    apply(controller, protocol="sacn", ip_address="127.0.0.1", universe=universe)
    return controller, sock


class TestSACNThroughTheOutputStage:
    def test_the_send_point_refuses_an_unstaged_frame_for_sacn(self):
        controller, sock = sacn_controller()
        for raw in (bytes(512), bytearray([255] * 512), [255] * 512):
            with pytest.raises(TypeError):
                controller._put_on_wire(sock, 0, raw)
            with pytest.raises(TypeError):
                controller._send_universe(0, raw)
        assert sock.sent == []

    def test_a_latched_blackout_gives_zeros_on_sacn(self):
        controller, sock = sacn_controller()
        controller.output_stage.blackout()
        controller.write_universe(0, [255] * 512)
        controller.write_universe(1, [200] * 512)
        for n in range(10):
            controller._transmit_frame(n / WIRE_FPS)
        assert len(sock.sent) == 20
        for packet, destination in sock.sent:
            assert destination == ("127.0.0.1", 5568)
            assert payload(packet) == bytes(512), "lit through a latched blackout on sACN"

        controller.output_stage.restore()
        controller._transmit_frame(1.0)
        assert max(payload(sock.sent[-2][0])) == 255, "restore must let sACN light again"

    def test_the_master_level_scales_sacn(self):
        controller, sock = sacn_controller()
        controller.output_stage.set_master(0.5)
        controller.write_universe(0, [255] * 512)
        controller._transmit_frame(0.0)
        data = payload(sock.sent[-1][0])
        assert 0 < max(data) <= 127

    def test_the_strobe_rate_limit_applies_to_sacn(self):
        controller, sock = sacn_controller()
        controller.output_stage.set_flash_policy(False, 2.0)
        times, asked = [], []
        for n in range(6 * WIRE_FPS):
            t = n / WIRE_FPS
            value = 255 if (t * 8.0) % 1.0 < 0.5 else 0       # an 8 Hz full-on flicker
            controller.write_universe(0, [value] * 512)
            asked.append(value / 255.0)
            controller._transmit_frame(t)
            times.append(t)
        sent = [payload(p)[0] / 255.0 for p, _ in sock.sent]

        assert all(p[4:16] == sacn.ACN_PACKET_IDENTIFIER for p, _ in sock.sent)
        assert worst_flashes_per_second(times, asked) >= 8, "the input does not strobe"
        assert max(sent) == 1.0, "the limit must thin flashes out, not just go dark"
        assert worst_flashes_per_second(times, sent) <= 2

    def test_the_watchdog_fades_sacn_to_black(self):
        controller, sock = sacn_controller()
        stage = controller.output_stage
        stage.set_watchdog_seconds(1.0)
        controller.write_universe(0, [255] * 512)
        stage.heartbeat()
        assert stage.watchdog_armed
        # The engine goes silent: no more heartbeats, the buffer stays lit.
        # The watchdog times silence on the transmitter's own clock alone.
        for n in range(3 * WIRE_FPS):
            controller._transmit_frame(n / WIRE_FPS)
        assert max(payload(sock.sent[0][0])) == 255, "the watchdog must not fire early"
        assert payload(sock.sent[-1][0]) == bytes(512), "sACN held its last frame"

    def test_blackout_on_stop_skips_an_unroutable_universe_not_the_rig(self):
        controller, sock = sacn_controller(universe=63999)
        controller.target_fps = 1000
        controller.write_universe(0, [255] * 512)     # sACN universe 63999
        controller.write_universe(1, [255] * 512)     # would be 64000: unroutable
        controller._send_final_blackout(sock)
        assert len(sock.sent) == controller.FINAL_BLACKOUT_REPEATS
        for packet, _ in sock.sent:
            assert struct.unpack(">H", packet[113:115])[0] == 63999
            assert payload(packet) == bytes(512)


class TestSwitchingTargetKeepsTheStage:
    def test_the_stage_and_its_state_survive_artnet_sacn_artnet(self):
        controller, sock = wired_controller()
        controller.config.ip_address = "127.0.0.1"
        stage = controller.output_stage
        stage.set_master(0.5)
        controller.write_universe(0, [255] * 512)

        controller._transmit_frame(0.0)
        apply(controller, protocol="sacn", ip_address="127.0.0.1", universe=1)
        assert controller.output_stage is stage
        controller._transmit_frame(0.025)
        apply(controller, protocol="artnet", ip_address="127.0.0.2")
        assert controller.output_stage is stage
        controller._transmit_frame(0.05)

        kinds = ["artnet" if p[:8] == b"Art-Net\x00" else "sacn" for p, _ in sock.sent]
        assert kinds == ["artnet", "sacn", "artnet"]
        for packet, _ in sock.sent:
            assert 0 < max(payload(packet)) <= 127, "the master must carry over a switch"
        assert stage.master == 0.5

        stage.blackout()
        apply(controller, protocol="sacn", ip_address="127.0.0.1", universe=1)
        controller._transmit_frame(0.075)
        assert stage.blackout_active, "a switch must not release a latched blackout"
        apply(controller, protocol="artnet", ip_address="127.0.0.2")
        controller._transmit_frame(0.1)
        assert [kind for kind in
                ("artnet" if p[:8] == b"Art-Net\x00" else "sacn" for p, _ in sock.sent[-2:])
                ] == ["sacn", "artnet"]
        for packet, _ in sock.sent[-2:]:
            assert payload(packet) == bytes(512)

    def test_the_flash_limit_holds_across_a_switch_mid_strobe(self):
        controller, sock = wired_controller()
        controller.config.ip_address = "127.0.0.1"
        controller.output_stage.set_flash_policy(False, 2.0)
        times, sent = [], []
        for n in range(6 * WIRE_FPS):
            t = n / WIRE_FPS
            if n % WIRE_FPS == 0:   # change protocol every second, mid-flicker
                if (n // WIRE_FPS) % 2:
                    apply(controller, protocol="sacn", ip_address="127.0.0.1", universe=1)
                else:
                    apply(controller, protocol="artnet", ip_address="127.0.0.1")
            value = 255 if (t * 8.0) % 1.0 < 0.5 else 0
            controller.write_universe(0, [value] * 512)
            controller._transmit_frame(t)
            times.append(t)
        sent = [payload(p)[0] / 255.0 for p, _ in sock.sent]
        assert {p[:8] == b"Art-Net\x00" for p, _ in sock.sent} == {True, False}
        assert worst_flashes_per_second(times, sent) <= 2


class TestArtNetUnchanged:
    def test_default_port_address_matches_masters_encoding(self):
        controller, _ = wired_controller()
        for net, subnet in ((0, 0), (1, 2), (127, 15)):
            controller.config.net, controller.config.subnet = net, subnet
            for universe in (0, 1, 7, 15, 16, 300, 32767):
                assert controller.artnet_port_address(universe) == (
                    ArtNetProtocol.encode_port_address(universe, net, subnet)
                )

    def test_artnet_packet_is_byte_identical_to_masters(self):
        controller, sock = wired_controller()
        controller.config.ip_address = "127.0.0.1"
        controller.config.net, controller.config.subnet = 1, 2
        frame = staged(bytes(range(256)) * 2)
        controller._send_universe(3, frame)
        expected = ArtNetProtocol.create_dmx_packet(3, frame, 1, net=1, subnet=2)
        assert sock.sent == [(expected, ("127.0.0.1", 6454))]


# ---------------------------------------------------------------------------
# Target validation
# ---------------------------------------------------------------------------

class TestTargetValidation:
    @pytest.mark.parametrize("ip", ["192.168.1.50", "10.0.0.1", "2.0.0.10", "127.0.0.1"])
    def test_unicast_addresses_pass(self, ip):
        assert validate_target_ip(ip) == ip

    @pytest.mark.parametrize("ip", [
        "255.255.255.255", "192.168.1.255", "2.255.255.255",
    ])
    def test_broadcast_needs_asking_for(self, ip):
        with pytest.raises(ValueError):
            validate_target_ip(ip)
        assert validate_target_ip(ip, allow_broadcast=True) == ip

    @pytest.mark.parametrize("ip", [
        "", "0.0.0.0", "not-an-ip", "192.168.1", "192.168.1.256", "239.255.0.1",
        "240.0.0.1", "::1", "192.168.1.50/24",
    ])
    def test_everything_else_is_refused_even_with_broadcast_allowed(self, ip):
        with pytest.raises(ValueError):
            validate_target_ip(ip, allow_broadcast=True)

    def test_defaults_per_protocol(self):
        artnet = OutputTarget(ip_address="10.0.0.5")
        assert (artnet.protocol, artnet.universe, artnet.resolved_port) == ("artnet", 0, 6454)
        e131 = OutputTarget(protocol="sacn", ip_address="10.0.0.5")
        assert (e131.universe, e131.priority, e131.resolved_port) == (1, 100, 5568)

    @pytest.mark.parametrize("fields", [
        dict(protocol="artnet"),                                     # no IP
        dict(protocol="artnet", ip_address="255.255.255.255"),       # broadcast, not asked for
        dict(protocol="artnet", ip_address="10.0.0.5", universe=16),
        dict(protocol="artnet", ip_address="10.0.0.5", net=128),
        dict(protocol="artnet", ip_address="10.0.0.5", subnet=16),
        dict(protocol="artnet", ip_address="10.0.0.5", multicast=True),
        dict(protocol="sacn"),                                       # neither IP nor multicast
        dict(protocol="sacn", ip_address="10.0.0.5", universe=0),
        dict(protocol="sacn", ip_address="10.0.0.5", universe=64000),
        dict(protocol="sacn", ip_address="10.0.0.5", priority=201),
        dict(protocol="sacn", ip_address="239.255.0.1"),
        dict(protocol="dmx512", ip_address="10.0.0.5"),
    ])
    def test_bad_targets_are_refused(self, fields):
        with pytest.raises(ValidationError):
            OutputTarget(**fields)

    def test_broadcast_target_when_explicitly_allowed(self):
        controller, sock = wired_controller()
        apply(controller, ip_address="255.255.255.255", allow_broadcast=True)
        assert controller.config.broadcast is True
        assert controller.is_broadcast is True

    def test_unicast_target_does_not_ask_the_socket_for_broadcast(self):
        controller, _ = wired_controller()
        apply(controller, ip_address="10.0.0.5")
        assert controller.config.broadcast is False
        assert controller.is_broadcast is False
        assert controller.target_ip == "10.0.0.5"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_nothing_saved_means_nothing_remembered(self, tmp_path):
        assert output_target.load(tmp_path) is None

    @pytest.mark.parametrize("fields", [
        dict(protocol="artnet", ip_address="192.168.1.50", net=1, subnet=2, universe=3),
        dict(protocol="sacn", ip_address="192.168.1.50", universe=12, priority=120,
             source_name="Demo box"),
        dict(protocol="sacn", multicast=True, universe=4),
    ])
    def test_round_trip(self, tmp_path, fields):
        target = OutputTarget(**fields)
        assert output_target.save(target, tmp_path) is True
        assert output_target.load(tmp_path) == target

    def test_unreadable_or_invalid_file_is_ignored(self, tmp_path):
        path = output_target.settings_path(tmp_path)
        path.write_text("{not json")
        assert output_target.load(tmp_path) is None
        # A hand-edited broadcast address needs the same explicit flag the API does.
        path.write_text(json.dumps({"protocol": "artnet", "ip_address": "255.255.255.255"}))
        assert output_target.load(tmp_path) is None

    def test_cid_is_created_once_and_kept(self, tmp_path):
        first = output_target.load_or_create_cid(tmp_path)
        assert len(first) == 16
        assert output_target.load_or_create_cid(tmp_path) == first
        output_target.save(OutputTarget(protocol="sacn", ip_address="10.0.0.5"), tmp_path)
        assert output_target.load_or_create_cid(tmp_path) == first, (
            "changing the target must not mint a new sACN identity"
        )

    def test_startup_restores_the_remembered_target_before_connecting(self, target_dir):
        output_target.save(
            OutputTarget(protocol="sacn", ip_address="127.0.0.1", universe=9), target_dir
        )
        controller = DMXController()
        run(_restore_output_target(controller))
        assert controller.is_connected is False
        assert controller.protocol == "sacn"
        assert controller.target_ip == "127.0.0.1"
        assert controller.sacn_universe == 9
        assert controller.sacn_cid == output_target.load_or_create_cid(target_dir)

    def test_startup_without_a_remembered_target_keeps_the_settings_default(self, target_dir):
        controller = DMXController()
        before = controller.config.model_copy()
        run(_restore_output_target(controller))
        assert controller.protocol == "artnet"
        assert controller.config == before


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest.fixture
def api_controller(target_dir, monkeypatch):
    """An unconnected controller on app.state: targets are applied, nothing is sent."""
    controller = DMXController()
    monkeypatch.setattr(app.state, "dmx_controller", controller, raising=False)
    return controller


class TestOutputTargetAPI:
    async def test_get_before_anything_is_remembered(self, client, api_controller):
        response = await client.get(TARGET_URL)
        assert response.status_code == 200
        body = response.json()
        assert body["remembered"] is False
        assert body["target"] is None
        assert body["active"]["protocol"] == "artnet"

    async def test_put_artnet_unicast_is_applied_and_remembered(
        self, client, api_controller, target_dir
    ):
        response = await client.put(TARGET_URL, json={
            "protocol": "artnet", "ip_address": "192.168.1.50",
            "net": 1, "subnet": 2, "universe": 3,
        })
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["remembered"] is True
        assert body["active"]["destination"] == "192.168.1.50"
        assert body["active"]["broadcast"] is False
        assert body["active"]["port_address"] == 0x0123

        assert api_controller.target_ip == "192.168.1.50"
        assert api_controller.is_broadcast is False
        assert output_target.load(target_dir).ip_address == "192.168.1.50"

        again = (await client.get(TARGET_URL)).json()
        assert again["remembered"] is True
        assert again["target"]["net"] == 1

    async def test_put_sacn_switches_protocol(self, client, api_controller, target_dir):
        response = await client.put(TARGET_URL, json={
            "protocol": "sacn", "ip_address": "192.168.1.60", "universe": 5,
        })
        assert response.status_code == 200, response.text
        active = response.json()["active"]
        assert (active["protocol"], active["destination"], active["port"]) == (
            "sacn", "192.168.1.60", 5568
        )
        assert active["priority"] == 100
        assert api_controller.protocol == "sacn"
        assert output_target.load(target_dir).protocol == "sacn"

    @pytest.mark.parametrize("payload", [
        {"protocol": "artnet", "ip_address": "255.255.255.255"},
        {"protocol": "artnet", "ip_address": "192.168.1.255"},
        {"protocol": "sacn", "ip_address": "255.255.255.255"},
        {"protocol": "artnet", "ip_address": "nonsense"},
        {"protocol": "artnet", "ip_address": "0.0.0.0"},
        {"protocol": "artnet"},
        {"protocol": "artnet", "ip_address": "192.168.1.50", "universe": 16},
        {"protocol": "artnet", "ip_address": "192.168.1.50", "net": 128},
        {"protocol": "sacn", "ip_address": "192.168.1.50", "universe": 0},
        {"protocol": "sacn", "ip_address": "192.168.1.50", "universe": 64000},
        {"protocol": "sacn", "ip_address": "192.168.1.50", "priority": 201},
        {"protocol": "kinet", "ip_address": "192.168.1.50"},
    ])
    async def test_invalid_targets_are_refused_and_nothing_changes(
        self, client, api_controller, target_dir, payload
    ):
        before = api_controller.config.model_copy()
        response = await client.put(TARGET_URL, json=payload)
        assert response.status_code == 422, response.text
        assert api_controller.protocol == "artnet"
        assert api_controller.config == before
        assert output_target.load(target_dir) is None

    async def test_broadcast_is_accepted_only_when_asked_for(
        self, client, api_controller, target_dir
    ):
        response = await client.put(TARGET_URL, json={
            "protocol": "artnet", "ip_address": "255.255.255.255", "allow_broadcast": True,
        })
        assert response.status_code == 200, response.text
        assert response.json()["active"]["broadcast"] is True

    async def test_put_without_a_controller_still_remembers(
        self, client, target_dir, monkeypatch
    ):
        monkeypatch.setattr(app.state, "dmx_controller", None, raising=False)
        response = await client.put(TARGET_URL, json={"ip_address": "192.168.1.50"})
        assert response.status_code == 200, response.text
        assert response.json()["active"] is None
        assert output_target.load(target_dir).ip_address == "192.168.1.50"

    async def test_requires_an_operator_session(
        self, unauthenticated_client, operator_token, api_controller, target_dir
    ):
        response = await unauthenticated_client.put(
            TARGET_URL, json={"ip_address": "192.168.1.50"}
        )
        assert response.status_code == 401
        assert api_controller.target_ip != "192.168.1.50"
        assert output_target.load(target_dir) is None


# ---------------------------------------------------------------------------
# The real transmitter thread, over loopback
# ---------------------------------------------------------------------------

async def test_live_output_thread_sends_sacn_to_a_loopback_listener():
    import socket

    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(("127.0.0.1", 0))
    receiver.settimeout(3.0)
    controller = DMXController()
    controller.sacn_cid = CID
    try:
        await controller.apply_output_target(OutputTarget(
            protocol="sacn", ip_address="127.0.0.1", universe=3,
            port=receiver.getsockname()[1],
        ))
        await controller.connect()
        controller.write_universe(0, [42] * 512)
        loop = asyncio.get_running_loop()
        first, _ = await loop.run_in_executor(None, receiver.recvfrom, 2048)
        second, _ = await loop.run_in_executor(None, receiver.recvfrom, 2048)
    finally:
        await controller.disconnect()
        receiver.close()

    assert len(first) == 638
    assert first[4:16] == sacn.ACN_PACKET_IDENTIFIER
    assert first[22:38] == CID
    assert struct.unpack(">H", first[113:115])[0] == 3
    assert first[126:638] == bytes([42] * 512)
    assert second[111] == (first[111] + 1) % 256
    assert controller.get_transmit_status()["send_error_count"] == 0
