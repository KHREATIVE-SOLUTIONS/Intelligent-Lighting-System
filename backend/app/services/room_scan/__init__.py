"""
Room Scan
=========

Reads a phone scan of a room (LiDAR or photogrammetry, exported as OBJ, PLY, a
USD text layer or RoomPlan JSON) and suggests the room shell the 3D view draws:
floor, ceiling height, walls, raised areas and overhead lines. See
docs/ROOM_SCAN.md.

    mesh    = read_scan_file(filename, content)     # detect.py, mesh.py, usd.py
    found   = extract_room(mesh, ScanOptions())     # extract.py
    moves   = suggest_positions(fixtures, shell)    # suggest.py

All of it is pure: nothing here touches the database, the engine or a device.
"""

from .detect import detect_scan_format, read_scan_file
from .extract import RoomExtraction, ScanOptions, extract_room
from .mesh import RoomScanError, ScanMesh
from .suggest import SuggestedMove, suggest_positions

__all__ = [
    "RoomExtraction",
    "RoomScanError",
    "ScanMesh",
    "ScanOptions",
    "SuggestedMove",
    "detect_scan_format",
    "extract_room",
    "read_scan_file",
    "suggest_positions",
]
