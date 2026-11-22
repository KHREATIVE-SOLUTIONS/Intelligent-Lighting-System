"""
Which reader a scan file goes to
================================

Decided from the file's first bytes, and from its name only when the bytes do
not say: an OBJ has no signature, so a file is taken for one when it is named
`.obj` or its lines look like one.
"""

from pathlib import PurePath

from .mesh import RoomScanError, ScanMesh, parse_obj, parse_ply
from .usd import CONVERT_MESSAGE, USDA_MAGIC, USDC_MAGIC, parse_roomplan_bytes, parse_usda, parse_usdz

SUPPORTED = "OBJ, PLY (ASCII or binary), a USDZ or USDA with a text layer, or RoomPlan JSON"


def detect_scan_format(filename: str, content: bytes) -> str:
    """obj, ply, usdz, usda, usdc, roomplan, glb or '' when nothing fits."""
    head = content[:4096]
    stripped = head.lstrip()
    suffix = PurePath(filename or "").suffix.lower()

    if head.startswith(b"ply"):
        return "ply"
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return "usdz"
    if stripped.startswith(USDA_MAGIC):
        return "usda"
    if head.startswith(USDC_MAGIC):
        return "usdc"
    if head.startswith(b"glTF"):
        return "glb"
    if stripped.startswith(b"{"):
        return "roomplan"
    if suffix == ".obj":
        return "obj"
    if any(line.startswith((b"v ", b"f ")) for line in head.splitlines()):
        return "obj"
    return ""


def read_scan_file(filename: str, content: bytes) -> ScanMesh:
    """Read a scan export into a ScanMesh, or say why it cannot be read."""
    if not content:
        raise RoomScanError("The file is empty.")
    fmt = detect_scan_format(filename, content)
    name = PurePath(filename or "").name

    if fmt == "obj":
        return parse_obj(content, name)
    if fmt == "ply":
        return parse_ply(content, name)
    if fmt == "usdz":
        return parse_usdz(content, name)
    if fmt == "usda":
        return parse_usda(content.decode("utf-8", errors="replace"), name)
    if fmt == "roomplan":
        return parse_roomplan_bytes(content, name)
    if fmt == "usdc":
        raise RoomScanError(CONVERT_MESSAGE.replace("This USDZ holds only", "This file is"))
    if fmt == "glb":
        raise RoomScanError(
            "This is a GLB (binary glTF), which is not read yet. Export the scan as OBJ or PLY instead."
        )
    raise RoomScanError(f"This does not look like a room scan this can read. Send {SUPPORTED}.")
