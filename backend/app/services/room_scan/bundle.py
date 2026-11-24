"""
A scan in a zip
===============

Phone scan apps often share a scan as a ZIP: a .gltf with its .bin and its
textures, or an .obj with its .mtl and its textures. This reads one, in memory:
nothing is ever written to disk, so no name in the archive is ever a path.

What is in it is not trusted. Before a byte is unpacked:

    names       an absolute name, or one that climbs out with `..`, refuses the
                whole zip. Nothing would be written there, but such a zip is
                not a scan export, and saying so beats reading round it.
    how many    more than MAX_ZIP_ENTRIES files is refused. The directory's own
                size is checked first, from the end of the file, so a zip that
                lists a million files is refused before the list is read.
    passwords   an encrypted file refuses the whole zip.
    how big     the sizes the zip gives for its files, added up over all of
                them, may not pass the upload limit (mesh.MAX_UPLOAD_BYTES): a
                zip is held to what a file sent on its own would be. A file
                that then unpacks to another size than it gave is refused.

Only the scan and the buffers it names are unpacked. Textures, .mtl files and
whatever else is there are never read.

Which file is the scan: the one model in the zip. Left out of the search are
folders, macOS's `__MACOSX` copies and anything in or named with a leading dot.
A .json counts only when it looks like a RoomPlan room or a glTF, so an app's
own notes about the scan are not taken for it. Where there are several models
they are tried in the order of PREFERENCE (the whole scan in one file first),
then the one nearest the top of the zip, then the first in the archive. The
first that can be read is the scan, and the report says which it was, which
were left alone, and which were tried and could not be read.

A .gltf's buffers are fetched from the zip by their `uri`: relative to the
.gltf's own folder, percent-decoded, and never from outside the zip.

Standard library only.
"""

import io
import posixpath
import re
import struct
import zipfile
import zlib
from pathlib import PurePosixPath
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import unquote

from .gltf import looks_like_gltf, parse_glb, parse_gltf
from .mesh import MAX_UPLOAD_BYTES, RoomScanError, ScanMesh, parse_obj, parse_ply
from .usd import USDC_MAGIC, parse_roomplan_bytes, parse_usda, parse_usdz
from .usdc import parse_usdc

# A scan export is a model, a buffer or two and its textures. A tiled
# photogrammetry export can run to some hundreds of files.
MAX_ZIP_ENTRIES = 2000
# What one file's line in the zip's directory may come to on average. A real
# one is its name and about fifty bytes.
_DIRECTORY_BYTES_PER_ENTRY = 4096

# The order models are tried in, and each one's ending.
PREFERENCE = ("glb", "gltf", "usdz", "usdc", "usda", "obj", "ply", "json")
MODEL_ENDINGS = ", ".join(f".{kind}" for kind in PREFERENCE[:-1]) + " or RoomPlan .json"

ZIP_AGAIN = "Zip the scan's own files again (the model, its .bin or .mtl, its textures) and send that."

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
_DRIVE = re.compile(r"^[A-Za-z]:")
_END_OF_DIRECTORY = b"PK\x05\x06"
_ZIP64_LOCATOR = b"PK\x06\x07"
_ZIP64_END = b"PK\x06\x06"

# Everything zipfile and zlib raise for an archive that does not hold together.
_UNREADABLE = (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, OSError, ValueError, struct.error)


def _shown(name: str) -> str:
    return name if len(name) <= 60 else name[:57] + "..."


def _listed(names: List[str], most: int = 5) -> str:
    """'a', 'b' and 'c', or the first few and how many more."""
    quoted = [f"'{_shown(name)}'" for name in names[:most]]
    if len(names) > most:
        return ", ".join(quoted) + f" and {len(names) - most} more"
    if len(quoted) == 1:
        return quoted[0]
    return ", ".join(quoted[:-1]) + " and " + quoted[-1]


def _too_many(most: int) -> RoomScanError:
    return RoomScanError(
        f"The zip holds more than {most:,} files, which is not a scan export. {ZIP_AGAIN}"
    )


def _directory(content: bytes) -> Optional[Tuple[int, int]]:
    """(files, bytes) of the zip's directory as its last record gives them, or None if that cannot be found.

    Found the way zipfile finds it, so the two agree about which record counts.
    """
    tail_start = max(0, len(content) - (22 + 0xFFFF))
    at = content.rfind(_END_OF_DIRECTORY, tail_start)
    if at < 0 or at + 22 > len(content):
        return None
    files, size = struct.unpack_from("<HI", content, at + 10)
    if files != 0xFFFF and size != 0xFFFFFFFF:
        return files, size
    # Zip64: the numbers are in a longer record, which a locator just before this one points at.
    locator = at - 20
    if locator < 0 or content[locator:locator + 4] != _ZIP64_LOCATOR:
        return None
    (record,) = struct.unpack_from("<Q", content, locator + 8)
    if record + 56 > len(content) or content[record:record + 4] != _ZIP64_END:
        return None
    files, size = struct.unpack_from("<QQ", content, record + 32)
    return files, size


def _unsafe(name: str) -> bool:
    """Whether a name in the zip is absolute, or climbs out of it."""
    plain = name.replace("\\", "/")
    return plain.startswith("/") or bool(_DRIVE.match(plain)) or ".." in plain.split("/")


def _junk(path: str) -> bool:
    """macOS's resource copies, and anything hidden: never the scan and never part of it."""
    return any(part == "__MACOSX" or part.startswith(".") for part in path.split("/"))


class _Zip:
    """An archive that has passed the checks, and the little of it that is unpacked."""

    def __init__(self, content: bytes, max_bytes: int, max_entries: int):
        declared = _directory(content)
        if declared is not None and (
            declared[0] > max_entries or declared[1] > max_entries * _DIRECTORY_BYTES_PER_ENTRY
        ):
            raise _too_many(max_entries)
        try:
            self.archive = zipfile.ZipFile(io.BytesIO(content))
            infos = self.archive.infolist()
        except NotImplementedError:
            raise RoomScanError(f"The zip is of a kind this cannot open (it may be in several parts). {ZIP_AGAIN}")
        except _UNREADABLE:
            raise RoomScanError(
                "The zip is damaged or cut short: it cannot be opened. Send it again, or zip the scan's files again."
            )
        if len(infos) > max_entries:
            raise _too_many(max_entries)

        self.max_bytes = max_bytes
        self.left = max_bytes
        self.files: List[Tuple[str, zipfile.ZipInfo]] = []      # (path, entry), junk and folders left out
        self._by_path: Dict[str, zipfile.ZipInfo] = {}
        self._by_lower: Dict[str, zipfile.ZipInfo] = {}
        self._read: Dict[int, bytes] = {}

        total = 0
        for info in infos:
            for name in {info.filename, info.orig_filename}:
                if _unsafe(name):
                    raise RoomScanError(
                        f"The zip holds a file named '{_shown(name)}', which points outside the zip. "
                        f"A scan app does not write that, so nothing in it was read. {ZIP_AGAIN}"
                    )
            if info.is_dir():
                continue
            if info.flag_bits & 0x1:
                raise RoomScanError(
                    f"The zip is locked with a password ('{_shown(info.filename)}' is encrypted). "
                    "Zip the scan again without a password and send that."
                )
            total += info.file_size
            if total > max_bytes:
                raise RoomScanError(
                    f"The zip unpacks to more than {self._megabytes()}, the most that is read. "
                    "Export the scan at a lower detail, or zip the model without its textures."
                )
            path = posixpath.normpath(info.filename.replace("\\", "/"))
            if _junk(path):
                continue
            self.files.append((path, info))
            self._by_path.setdefault(path, info)
            self._by_lower.setdefault(path.lower(), info)

    def _megabytes(self) -> str:
        size = self.max_bytes / (1024 * 1024)
        return f"{size:.0f} MB" if size >= 1 else f"{self.max_bytes:,} bytes"

    def find(self, path: str) -> Optional[zipfile.ZipInfo]:
        """The file at a path in the zip. Capitals are let off when no name matches exactly."""
        return self._by_path.get(path) or self._by_lower.get(path.lower())

    def read(self, info: zipfile.ZipInfo) -> bytes:
        """One file unpacked, once, and never more of it than the zip said it holds."""
        key = info.header_offset
        if key in self._read:
            return self._read[key]
        name = _shown(info.filename)
        if info.file_size > self.left:
            raise RoomScanError(f"The zip unpacks to more than {self._megabytes()}, the most that is read.")
        try:
            with self.archive.open(info) as handle:
                data = handle.read(info.file_size + 1)
        except NotImplementedError:
            raise RoomScanError(
                f"'{name}' is packed in the zip in a way this cannot unpack. "
                "Zip the scan again with ordinary (deflate) compression and send that."
            )
        except MemoryError:
            raise RoomScanError(f"'{name}' is too large to unpack. Export the scan at a lower detail.")
        except _UNREADABLE:
            raise RoomScanError(
                f"The zip is damaged: '{name}' could not be unpacked. Send it again, or zip the scan's files again."
            )
        if len(data) != info.file_size:
            raise RoomScanError(
                f"The zip is damaged: '{name}' does not unpack to the size the zip gives for it. "
                "Send it again, or zip the scan's files again."
            )
        self.left -= len(data)
        self._read[key] = data
        return data

    def resolver(self, model_path: str) -> Callable[[str], bytes]:
        """How a glTF at `model_path` gets the file one of its buffers names."""
        folder = posixpath.dirname(model_path)

        def resolve(uri: str) -> bytes:
            if _SCHEME.match(uri) or uri.startswith(("/", "\\")):
                raise RoomScanError(
                    f"It keeps its mesh at '{_shown(uri)}', which is not a file in the zip. "
                    "Export the scan as .glb, which is the whole scan in one file, or export OBJ."
                )
            outside = False
            # As a URI is meant to be read, then as it is written: some apps do not encode a name.
            for spelling in (unquote(uri), uri):
                path = posixpath.normpath(posixpath.join(folder, spelling.replace("\\", "/")))
                if path == ".." or path.startswith(("../", "/")):
                    outside = True
                    continue
                info = self.find(path)
                if info is not None:
                    return self.read(info)
            if outside:
                raise RoomScanError(
                    f"It keeps its mesh at '{_shown(uri)}', which is outside the zip. "
                    "Zip the .gltf together with its .bin and send that, or export the scan as .glb."
                )
            raise RoomScanError(
                f"It needs '{_shown(unquote(uri))}', and that file is not in the zip. "
                "Zip the .gltf together with its .bin and send that, or export the scan as .glb, "
                "which is the whole scan in one file."
            )

        return resolve


def _kind(path: str) -> str:
    """Which of PREFERENCE a file is by its ending, or '' for anything else."""
    ending = PurePosixPath(path).suffix.lower().lstrip(".")
    if ending == "usd":
        # USD lets a layer of either form be called .usd; most are binary. _parse goes by its first bytes.
        return "usdc"
    return ending if ending in PREFERENCE else ""


def _is_a_model(data: bytes) -> bool:
    """Whether a .json is a scan (RoomPlan's room, or a glTF under another name) and not an app's notes."""
    return b'"walls"' in data or looks_like_gltf(data)


def _parse(kind: str, data: bytes, source_file: str, resolve: Callable[[str], bytes]) -> ScanMesh:
    """One file of the zip through its own reader. Never back through the zip reader."""
    if not data:
        raise RoomScanError("The file is empty.")
    if kind == "glb":
        return parse_glb(data, source_file, resolve)
    if kind == "gltf" or (kind == "json" and looks_like_gltf(data)):
        return parse_gltf(data, source_file, resolve)
    if kind == "usdz":
        return parse_usdz(data, source_file)
    if kind in ("usdc", "usda"):
        # A layer is binary or text by its first bytes, whatever it is called.
        if data[:len(USDC_MAGIC)] == USDC_MAGIC:
            return parse_usdc(data, source_file)
        return parse_usda(data.decode("utf-8", errors="replace"), source_file)
    if kind == "obj":
        return parse_obj(data, source_file)
    if kind == "ply":
        return parse_ply(data, source_file)
    return parse_roomplan_bytes(data, source_file)


def parse_zip(
    content: bytes,
    source_file: str = "",
    max_bytes: int = MAX_UPLOAD_BYTES,
    max_entries: int = MAX_ZIP_ENTRIES,
) -> ScanMesh:
    """The scan inside a zip, read like the same file sent on its own."""
    bundle = _Zip(content, max_bytes, max_entries)
    with bundle.archive:
        models: List[Tuple[int, int, int, str, str, zipfile.ZipInfo]] = []
        for place, (path, info) in enumerate(bundle.files):
            kind = _kind(path)
            if not kind:
                continue
            if kind == "json":
                try:
                    if not _is_a_model(bundle.read(info)):
                        continue
                except RoomScanError:
                    continue            # a .json that cannot be unpacked is not the scan
            models.append((PREFERENCE.index(kind), path.count("/"), place, kind, path, info))
        if not models:
            if not bundle.files:
                raise RoomScanError("The zip is empty: there is no scan in it.")
            raise RoomScanError(
                f"The zip holds no scan this can read: no {MODEL_ENDINGS} was found in it "
                f"(it holds {_listed([path for path, _ in bundle.files], most=3)}). "
                "Zip the model the app exported, with its .bin or .mtl, and send that."
            )
        models.sort(key=lambda model: model[:3])

        failed: List[Tuple[str, RoomScanError]] = []
        for number, (_, _, _, kind, path, info) in enumerate(models):
            try:
                mesh = _parse(kind, bundle.read(info), source_file, bundle.resolver(path))
            except RoomScanError as error:
                failed.append((path, error))
                continue

            notes = [f"Read '{_shown(path)}' from the zip."]
            for name, error in failed:
                notes.append(f"'{_shown(name)}' in the zip was tried first and could not be read. {error}")
            others = [other[4] for other in models[number + 1:]]
            if others:
                notes.append(
                    f"The zip also holds {_listed(others)}, which {'was' if len(others) == 1 else 'were'} "
                    "not read: one scan is read from a zip. Check the room against the venue."
                )
            mesh.notes[:0] = notes
            return mesh

    name, error = failed[0]
    raise RoomScanError(f"'{_shown(name)}' in the zip could not be read. {error}")
