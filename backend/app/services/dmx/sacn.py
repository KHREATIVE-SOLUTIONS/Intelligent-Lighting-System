"""
sACN (ANSI E1.31) Data Packets
==============================

Builds the E1.31 data packet a streaming-ACN receiver (a grandMA2 node, most
Ethernet-DMX nodes) accepts. This module only makes bytes; the DMX controller
owns the socket and the output thread, so sACN leaves through exactly the same
path as Art-Net.

A full 512-slot packet is 638 bytes in three nested layers, each opening with a
"flags and length" word: 0x7 in the top nibble, then the byte count from that
word to the end of the packet.

    0   root layer     preamble, ACN id, flags+length, vector, CID
    38  framing layer  flags+length, vector, source name, priority, sync
                       address, sequence, options, universe
    115 DMP layer      flags+length, vector, address type, first address,
                       increment, property count, start code, 512 slots
"""

import struct
import uuid

SACN_PORT = 5568
DEFAULT_PRIORITY = 100
MIN_UNIVERSE = 1
MAX_UNIVERSE = 63999
MAX_PRIORITY = 200
SOURCE_NAME_LENGTH = 64
DEFAULT_SOURCE_NAME = "Intelligent Lighting System"

ACN_PACKET_IDENTIFIER = b"ASC-E1.17\x00\x00\x00"
VECTOR_ROOT_E131_DATA = 0x00000004
VECTOR_E131_DATA_PACKET = 0x00000002
VECTOR_DMP_SET_PROPERTY = 0x02

ROOT_LAYER_OFFSET = 16      # root flags+length; the preamble before it is not counted
FRAMING_LAYER_OFFSET = 38
DMP_LAYER_OFFSET = 115
START_CODE_OFFSET = 125
SLOTS_OFFSET = 126
PACKET_LENGTH = SLOTS_OFFSET + 512

OPTION_STREAM_TERMINATED = 0x40


def validate_universe(universe: int) -> int:
    """An E1.31 universe number, or ValueError. Universe 0 does not exist in sACN."""
    if isinstance(universe, bool) or not isinstance(universe, int):
        raise ValueError("sACN universe must be an integer 1-63999")
    if not MIN_UNIVERSE <= universe <= MAX_UNIVERSE:
        raise ValueError(f"sACN universe must be 1-63999, got {universe}")
    return universe


def multicast_address(universe: int) -> str:
    """The universe's multicast group: 239.255.<high byte>.<low byte>."""
    validate_universe(universe)
    return f"239.255.{(universe >> 8) & 0xFF}.{universe & 0xFF}"


def encode_source_name(name: str) -> bytes:
    """Source name as the 64-byte NUL-padded UTF-8 field (at most 63 bytes of text)."""
    raw = (name or "").encode("utf-8")[:SOURCE_NAME_LENGTH - 1]
    # A cut through the middle of a multi-byte character is not valid UTF-8.
    raw = raw.decode("utf-8", errors="ignore").encode("utf-8")
    return raw.ljust(SOURCE_NAME_LENGTH, b"\x00")


def _flags_and_length(packet_length: int, layer_offset: int) -> int:
    return 0x7000 | ((packet_length - layer_offset) & 0x0FFF)


def create_data_packet(
    universe: int,
    data: bytes,
    sequence: int,
    cid: bytes,
    source_name: str = DEFAULT_SOURCE_NAME,
    priority: int = DEFAULT_PRIORITY,
    stream_terminated: bool = False,
) -> bytes:
    """Build one E1.31 data packet carrying a null-start-code DMX frame."""
    validate_universe(universe)
    if len(cid) != 16:
        raise ValueError("sACN CID must be 16 bytes")
    if not 0 <= priority <= MAX_PRIORITY:
        raise ValueError(f"sACN priority must be 0-200, got {priority}")

    if len(data) < 512:
        data = bytes(data) + bytes(512 - len(data))
    elif len(data) > 512:
        data = bytes(data[:512])

    packet = bytearray()

    # Root layer
    packet += struct.pack(">HH", 0x0010, 0x0000)          # preamble, postamble sizes
    packet += ACN_PACKET_IDENTIFIER
    packet += struct.pack(">H", _flags_and_length(PACKET_LENGTH, ROOT_LAYER_OFFSET))
    packet += struct.pack(">I", VECTOR_ROOT_E131_DATA)
    packet += cid

    # Framing layer
    packet += struct.pack(">H", _flags_and_length(PACKET_LENGTH, FRAMING_LAYER_OFFSET))
    packet += struct.pack(">I", VECTOR_E131_DATA_PACKET)
    packet += encode_source_name(source_name)
    packet.append(priority)
    packet += struct.pack(">H", 0)                        # synchronization address: none
    packet.append(sequence & 0xFF)
    packet.append(OPTION_STREAM_TERMINATED if stream_terminated else 0)
    packet += struct.pack(">H", universe)

    # DMP layer
    packet += struct.pack(">H", _flags_and_length(PACKET_LENGTH, DMP_LAYER_OFFSET))
    packet.append(VECTOR_DMP_SET_PROPERTY)
    packet.append(0xA1)                                   # address type and data type
    packet += struct.pack(">HHH", 0x0000, 0x0001, 513)    # first address, increment, count
    packet.append(0x00)                                   # DMX null start code
    packet += data

    return bytes(packet)


def new_cid() -> bytes:
    return uuid.uuid4().bytes
