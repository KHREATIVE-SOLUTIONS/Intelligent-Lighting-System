"""
Which reader a scan file goes to
================================

Decided from the file's first bytes, and from its name only when the bytes do
not say: an OBJ has no signature, so a file is taken for one when it is named
`.obj` or its lines look like one. A USD file is text (`#usda`) or binary
(`PXR-USDC`) whatever it is called; both are read, alone or inside a USDZ.

A USDZ is a ZIP, and so is the zip a scan app shares a .gltf and its .bin in,
so those two are told apart by name: an archive named `.usdz` goes to the USDZ
reader, as it always has, and any other archive is read as a zip that holds a
scan (bundle.py), which reads a USD layer inside it as well.
"""

from pathlib import PurePath

from .bundle import parse_zip
from .gltf import GLB_MAGIC, looks_like_gltf, parse_glb, parse_gltf
from .mesh import RoomScanError, ScanMesh, parse_obj, parse_ply
from .usd import USDA_MAGIC, USDC_MAGIC, parse_roomplan_bytes, parse_usda, parse_usdz
from .usdc import parse_usdc

SUPPORTED = (
    "OBJ, PLY (ASCII or binary), glTF (.glb, or a .gltf with its data inside it), "
    "USDZ, USD (USDA text or USDC binary), RoomPlan JSON, or a zip of one of those with the files "
    "that go with it (a .gltf and its .bin, an .obj and its textures)"
)


def detect_scan_format(filename: str, content: bytes) -> str:
    """obj, ply, usdz, zip, usda, usdc, roomplan, glb, gltf or '' when nothing fits.

    A .gltf is JSON, as RoomPlan's file is. It is told apart by its name, or
    by the `asset` every glTF must carry when it is named something else.
    """
    head = content[:4096]
    stripped = head.lstrip()
    suffix = PurePath(filename or "").suffix.lower()

    if head.startswith(b"ply"):
        return "ply"
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return "usdz" if suffix == ".usdz" else "zip"
    if stripped.startswith(USDA_MAGIC):
        return "usda"
    if head.startswith(USDC_MAGIC):
        return "usdc"
    if head.startswith(GLB_MAGIC):
        return "glb"
    if stripped.startswith(b"{") or head.startswith(b"\xef\xbb\xbf{"):
        if suffix in (".gltf", ".glb") or looks_like_gltf(content):
            return "gltf"
        return "roomplan"
    if suffix == ".obj":
        return "obj"
    if suffix == ".glb":
        return "glb"
    if suffix == ".gltf":
        return "gltf"
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
    if fmt == "zip":
        return parse_zip(content, name)
    if fmt == "usda":
        return parse_usda(content.decode("utf-8", errors="replace"), name)
    if fmt == "roomplan":
        return parse_roomplan_bytes(content, name)
    if fmt == "usdc":
        return parse_usdc(content, name)
    if fmt == "glb":
        return parse_glb(content, name)
    if fmt == "gltf":
        return parse_gltf(content, name)
    raise RoomScanError(f"This does not look like a room scan this can read. Send {SUPPORTED}.")
