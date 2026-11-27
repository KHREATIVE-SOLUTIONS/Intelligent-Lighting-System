"""
Stage plot underlay: reading the image and laying it onto the room
==================================================================

Pure functions, no database: what kind of image a file is (from its first
bytes, never from its name or what the client said), how big it is in pixels
(from its header, so no imaging library is needed), and the transform that
puts its pixels onto the rig's plan from what the operator calibrated.
docs/STAGE_PLOT.md.

The conventions, written down once (frontend/src/utils/stagePlot.ts follows them):

- Image pixels: u to the right, v down, (0, 0) the top-left corner.
- The plan: metres, x across, z downstage (toward the audience, down the plan,
  as StageView2D draws it). So with no rotation the image's down is downstage.
- Rotation: degrees, positive turns the image clockwise as seen on the plan.
- room = s * R(rotation) * (pixel - origin), with s the metres per pixel from
  the two points and the distance between them. The origin pixel lands on
  (0, 0), the middle of the stage.
- `matrix` is that as an SVG matrix(a b c d e f):
  x = a*u + c*v + e,  z = b*u + d*v + f.
"""

import math
import struct
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

MAX_STAGE_PLOT_BYTES = 15 * 1024 * 1024

PNG = "image/png"
JPEG = "image/jpeg"
WEBP = "image/webp"
PDF = "application/pdf"
IMAGE_TYPES = (PNG, JPEG, WEBP)

# The longest a measured distance may be: a stadium is well inside this, and
# a slip of the keyboard (4000 for 4.000) is caught.
MAX_DISTANCE_M = 1000.0
# Two points closer than this on the image cannot give a scale worth having.
MIN_POINT_GAP_PX = 2.0


class StagePlotError(ValueError):
    """Something about the file or the calibration, said in a sentence for the operator."""


def sniff(content: bytes) -> Optional[str]:
    """The file's type from its first bytes: one of IMAGE_TYPES, PDF, or None."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if content.startswith(b"\xff\xd8\xff"):
        return JPEG
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return WEBP
    if content.startswith(b"%PDF-"):
        return PDF
    return None


def _png_size(content: bytes) -> Optional[Tuple[int, int]]:
    # The IHDR chunk is always first: length, "IHDR", width, height (big-endian).
    if len(content) < 24 or content[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", content[16:24])


# Start-of-frame markers carry the size; C4 (huffman), C8 (reserved) and CC (arithmetic) do not.
_JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _jpeg_size(content: bytes) -> Optional[Tuple[int, int]]:
    at = 2
    while at + 4 <= len(content):
        if content[at] != 0xFF:
            return None
        marker = content[at + 1]
        if marker == 0xFF:  # fill byte
            at += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # no length
            at += 2
            continue
        (length,) = struct.unpack(">H", content[at + 2:at + 4])
        if marker in _JPEG_SOF:
            if at + 9 > len(content):
                return None
            height, width = struct.unpack(">HH", content[at + 5:at + 9])
            return width, height
        at += 2 + length
    return None


def _webp_size(content: bytes) -> Optional[Tuple[int, int]]:
    chunk = content[12:16]
    if chunk == b"VP8X" and len(content) >= 30:
        width = 1 + int.from_bytes(content[24:27], "little")
        height = 1 + int.from_bytes(content[27:30], "little")
        return width, height
    if chunk == b"VP8 " and len(content) >= 30:
        width, height = struct.unpack("<HH", content[26:30])
        return width & 0x3FFF, height & 0x3FFF
    if chunk == b"VP8L" and len(content) >= 25:
        bits = int.from_bytes(content[21:25], "little")
        return 1 + (bits & 0x3FFF), 1 + ((bits >> 14) & 0x3FFF)
    return None


def image_size(content: bytes, content_type: str) -> Tuple[int, int]:
    """Width and height in pixels, read from the header. StagePlotError where it cannot be read."""
    reader = {PNG: _png_size, JPEG: _jpeg_size, WEBP: _webp_size}.get(content_type)
    size = reader(content) if reader else None
    if not size or size[0] <= 0 or size[1] <= 0:
        raise StagePlotError("The image's size could not be read: the file looks damaged. Export it again.")
    return int(size[0]), int(size[1])


@dataclass(frozen=True)
class Calibration:
    """What the operator set, in image pixels and metres."""
    point_a: Tuple[float, float]
    point_b: Tuple[float, float]
    distance_m: float
    origin: Tuple[float, float]
    rotation_deg: float = 0.0
    opacity: float = 0.5


def _finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise StagePlotError(f"{name} must be a finite number.")
    return float(value)


def normalise_rotation(degrees: float) -> float:
    """The same turn, within (-180, 180]."""
    turned = math.fmod(degrees, 360.0)
    if turned > 180.0:
        turned -= 360.0
    elif turned <= -180.0:
        turned += 360.0
    return turned


def checked(calibration: Calibration) -> Calibration:
    """The calibration with every number finite and in range, rotation normalised. StagePlotError otherwise."""
    ax, ay = (_finite("Point A", v) for v in calibration.point_a)
    bx, by = (_finite("Point B", v) for v in calibration.point_b)
    ox, oy = (_finite("The origin", v) for v in calibration.origin)
    distance = _finite("The distance", calibration.distance_m)
    rotation = _finite("The rotation", calibration.rotation_deg)
    opacity = _finite("The opacity", calibration.opacity)
    if math.hypot(bx - ax, by - ay) < MIN_POINT_GAP_PX:
        raise StagePlotError("The two points are on top of each other. Click two points further apart.")
    if not 0.0 < distance <= MAX_DISTANCE_M:
        raise StagePlotError(f"The distance must be more than 0 and at most {MAX_DISTANCE_M:g} metres.")
    if not 0.0 <= opacity <= 1.0:
        raise StagePlotError("The opacity must be between 0 and 1.")
    return Calibration((ax, ay), (bx, by), distance, (ox, oy), normalise_rotation(rotation), opacity)


def transform(calibration: Calibration) -> Dict[str, Any]:
    """The image-to-room transform: scale, rotation, offset, and the SVG matrix (see the module doc)."""
    c = checked(calibration)
    (ax, ay), (bx, by), (ox, oy) = c.point_a, c.point_b, c.origin
    scale = c.distance_m / math.hypot(bx - ax, by - ay)
    theta = math.radians(c.rotation_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    a, b = scale * cos_t, scale * sin_t
    cc, d = -scale * sin_t, scale * cos_t
    e = -(a * ox + cc * oy)
    f = -(b * ox + d * oy)
    return {
        "scale_m_per_px": scale,
        "rotation_deg": c.rotation_deg,
        # Where the image's top-left pixel lands on the plan.
        "offset_x": e,
        "offset_z": f,
        "matrix": [a, b, cc, d, e, f],
    }


def to_room(matrix, u: float, v: float) -> Tuple[float, float]:
    """A pixel of the image on the plan, by a transform's matrix."""
    a, b, c, d, e, f = matrix
    return a * u + c * v + e, b * u + d * v + f


def calibration_dict(calibration: Calibration) -> Dict[str, Any]:
    """The calibration as stored and sent: what the operator set, checked."""
    c = checked(calibration)
    return {
        "point_a": {"x": c.point_a[0], "y": c.point_a[1]},
        "point_b": {"x": c.point_b[0], "y": c.point_b[1]},
        "distance_m": c.distance_m,
        "origin": {"x": c.origin[0], "y": c.origin[1]},
        "rotation_deg": c.rotation_deg,
        "opacity": c.opacity,
    }
