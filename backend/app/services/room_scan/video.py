"""
Room from a walkthrough video
=============================

Turns a phone video of someone walking round the room into a point cloud the
scan reader (extract.py) can read, using only free tools already on this
machine. Nothing is uploaded anywhere and nothing is installed from here.

    tools  = find_tools(colmap_path)                  # what is installed
    cloud  = reconstruct(video, work_dir, tools, ...)  # frames -> COLMAP -> aligned cloud
    ply    = cloud_ply(cloud, Reference(...))          # scaled, with its caveats in the header

In order:

1. **Frames.** ffmpeg (or OpenCV when ffmpeg is missing) pulls a few frames a
   second. Blurred ones and ones that show the same thing as the frame before
   are dropped, and the sharpest of what is left are kept.
2. **Reconstruction.** COLMAP, as an outside process: features, matching,
   mapping. Optionally a dense cloud (COLMAP's own stereo, which needs CUDA,
   else OpenMVS where it is installed); any failure there falls back to the
   sparse cloud.
3. **Which way is up.** A photogrammetry model has no up. The phone does: the
   average of every frame's "down" is close to gravity, and from there the
   direction is nudged until the floor and ceiling are as thin as they can be.
4. **Scale.** A video has none either. `cloud_ply` sets it from one
   measurement (ceiling height or the longest wall). With none it assumes the
   phone was held 1.5 m above the floor and says, as a warning, that every
   size is a guess.

Steps 3 and 4 are numpy and are tested. Step 2 has never been run against a
real COLMAP in this repository's tests: they drive it with a stand-in process.
See docs/ROOM_SCAN.md.
"""

import importlib.util
import math
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .extract import (
    MAX_CLOUD_POINTS, _wall, dominant_wall_turn, find_floor_and_ceiling, turn_about_vertical,
)
from .mesh import (
    PLY_METRES_PER_UNIT, PLY_NOTE, PLY_UP_AXIS, PLY_WARNING, RoomScanError, parse_ply,
)

VIDEO_SUFFIXES = (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".3gp")

# Frames
MAX_FRAMES = 150                 # kept for reconstruction
CANDIDATES_PER_FRAME = 3         # looked at, for each one kept
MAX_CANDIDATE_FPS = 4.0
MIN_CANDIDATE_FPS = 0.5
FRAME_LONG_SIDE = 1600           # pixels; more only makes COLMAP slower
THUMB = 512                      # the centre crop sharpness is measured on
SMALL = 32                       # the grid two frames are compared on
MIN_FRAMES = 12
BLUR_SHARE = 0.5                 # blurred: under this share of the sharpness of its neighbours
FLAT_SHARPNESS = 2.0             # a lens cap, a black frame
DUPLICATE_DIFF = 1.5             # grey levels (of 255): the same view as the frame before

# Reconstruction
EXHAUSTIVE_UP_TO = 100           # frames; past this every-pair matching takes too long
MIN_TRACK = 3                    # a sparse point seen in fewer frames than this is noise
MIN_SPARSE_POINTS = 300

# Scale
NOMINAL_HEIGHT = 3.0             # metres the cloud is stretched to while the floor is looked for
ASSUMED_CAMERA_HEIGHT = 1.5
ASSUMED_CEILING_HEIGHT = 3.0
REFERENCE_MIN, REFERENCE_MAX = 1.0, 200.0

COLMAP_URL = "https://github.com/colmap/colmap/releases"

Runner = Callable[[Sequence[str], Path, threading.Event, float], int]
Progress = Callable[[str, str], None]


class VideoPipelineError(RoomScanError):
    """The video could not be turned into a room. The message is for the operator."""


class VideoCancelled(Exception):
    """The operator stopped the job."""


# ---------------------------------------------------------------------------
# What is installed
# ---------------------------------------------------------------------------

@dataclass
class VideoTools:
    ffmpeg: Optional[str] = None
    opencv: bool = False
    colmap: Optional[str] = None
    openmvs: Optional[str] = None       # the folder holding DensifyPointCloud and InterfaceCOLMAP

    @property
    def frame_tool(self) -> Optional[str]:
        return "ffmpeg" if self.ffmpeg else "opencv" if self.opencv else None

    @property
    def ready(self) -> bool:
        return bool(self.colmap) and self.frame_tool is not None

    def missing_message(self) -> Optional[str]:
        """What to install, or None when a video can be read here."""
        if self.ready:
            return None
        polycam = (
            "Or skip the video: scan the room with Polycam or Scaniverse (both free), export OBJ or PLY, "
            "and choose that file here instead."
        )
        if not self.colmap:
            return (
                "No photogrammetry tool is installed on this machine, so a video cannot be turned into a room "
                f"here. To use video, install COLMAP (free, BSD licence): download it from {COLMAP_URL}, "
                "unpack it, then either put its folder on PATH or set COLMAP_PATH in backend/.env to that "
                "folder, and restart the backend. " + polycam
            )
        return (
            "COLMAP is installed, but nothing here can read frames out of a video. Install ffmpeg (free) and "
            "put it on PATH, then restart the backend. " + polycam
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ready": self.ready,
            "frames": {"tool": self.frame_tool, "path": self.ffmpeg},
            "photogrammetry": {"tool": "colmap" if self.colmap else None, "path": self.colmap},
            "dense": {"tool": "openmvs" if self.openmvs else None, "path": self.openmvs},
            "message": self.missing_message(),
        }


def _exe(name: str) -> List[str]:
    return [name + ".exe", name + ".bat", name] if os.name == "nt" else [name]


def find_colmap(configured: str = "") -> Optional[str]:
    """COLMAP's launcher: the configured file or folder, else whatever PATH has.

    The Windows release is a folder holding COLMAP.bat (which sets up the
    libraries) and bin/colmap.exe. The .bat is preferred where both exist.
    """
    configured = (configured or "").strip().strip('"')
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path)
        if path.is_dir():
            for name in ("COLMAP.bat", "colmap.bat", "colmap.exe", "colmap", "bin/colmap.exe", "bin/colmap"):
                candidate = path / name
                if candidate.is_file():
                    return str(candidate)
        return None
    return shutil.which("colmap") or shutil.which("COLMAP")


def find_openmvs(configured: str = "") -> Optional[str]:
    """The folder holding OpenMVS's DensifyPointCloud and InterfaceCOLMAP, or None."""
    folders: List[Path] = []
    configured = (configured or "").strip().strip('"')
    if configured:
        folders.append(Path(configured).expanduser())
    else:
        found = shutil.which("DensifyPointCloud")
        if found:
            folders.append(Path(found).parent)
    for folder in folders:
        if all(any((folder / n).is_file() for n in _exe(tool)) for tool in ("DensifyPointCloud", "InterfaceCOLMAP")):
            return str(folder)
    return None


def find_tools(colmap_path: str = "", openmvs_path: str = "") -> VideoTools:
    return VideoTools(
        ffmpeg=shutil.which("ffmpeg"),
        # Looked for, not imported: OpenCV is not a dependency of this project.
        opencv=importlib.util.find_spec("cv2") is not None,
        colmap=find_colmap(colmap_path),
        openmvs=find_openmvs(openmvs_path),
    )


# ---------------------------------------------------------------------------
# Running an outside tool
# ---------------------------------------------------------------------------

_LIVE: "set[subprocess.Popen]" = set()
_LIVE_LOCK = threading.Lock()


def _kill_tree(process: subprocess.Popen) -> None:
    """Stop a tool and whatever it started. COLMAP.bat is cmd.exe with colmap.exe under it."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        process.kill()
    except OSError:
        pass


def kill_running_tools() -> None:
    """Stop every tool still running. Called when the backend shuts down."""
    with _LIVE_LOCK:
        live = list(_LIVE)
    for process in live:
        _kill_tree(process)


def run_tool(args: Sequence[str], log_path: Path, cancel: threading.Event, deadline: float) -> int:
    """Run a tool to its end, its output appended to `log_path`. Returns its exit code.

    Runs at low priority with no window: this machine may be running a show.
    """
    kwargs: Dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    else:
        kwargs["start_new_session"] = True
    with open(log_path, "ab") as log:
        log.write(("\n$ " + " ".join(str(a) for a in args) + "\n").encode("utf-8", errors="replace"))
        log.flush()
        try:
            process = subprocess.Popen(
                [str(a) for a in args], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **kwargs,
            )
        except OSError as e:
            raise VideoPipelineError(f"{Path(str(args[0])).name} could not be started: {e}")
        with _LIVE_LOCK:
            _LIVE.add(process)
        try:
            while True:
                try:
                    return process.wait(timeout=0.25)
                except subprocess.TimeoutExpired:
                    pass
                if cancel.is_set():
                    _kill_tree(process)
                    raise VideoCancelled()
                if time.monotonic() > deadline:
                    _kill_tree(process)
                    raise VideoPipelineError(
                        "The reconstruction ran out of time and was stopped. Use a shorter video (one to two "
                        "minutes is enough), or scan the room with Polycam or Scaniverse and export OBJ or PLY."
                    )
        finally:
            _kill_tree(process)
            with _LIVE_LOCK:
                _LIVE.discard(process)


def log_tail(log_path: Path, lines: int = 6, limit: int = 600) -> str:
    """The end of a tool's output, for an error message."""
    try:
        text = log_path.read_bytes()[-8000:].decode("utf-8", errors="replace")
    except OSError:
        return ""
    kept = [line.strip() for line in text.splitlines() if line.strip()][-lines:]
    return " | ".join(kept)[-limit:]


def _check(cancel: threading.Event, deadline: float) -> None:
    if cancel.is_set():
        raise VideoCancelled()
    if time.monotonic() > deadline:
        raise VideoPipelineError("The job ran out of time and was stopped. Use a shorter video.")


# ---------------------------------------------------------------------------
# 1. Frames
# ---------------------------------------------------------------------------

@dataclass
class FrameReport:
    tool: str = ""
    duration_s: Optional[float] = None
    candidates: int = 0
    kept: int = 0
    blurry: int = 0
    duplicates: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool, "duration_s": self.duration_s, "candidates": self.candidates,
            "kept": self.kept, "blurry": self.blurry, "duplicates": self.duplicates,
        }


def sharpness(grey: np.ndarray) -> float:
    """Variance of the Laplacian: high for a sharp frame, low for a smeared one."""
    g = grey.astype(np.float32)
    laplacian = g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:] - 4.0 * g[1:-1, 1:-1]
    return float(laplacian.var())


def shrink(grey: np.ndarray) -> np.ndarray:
    """A THUMB-square frame as SMALL by SMALL block means, to compare two frames on."""
    block = THUMB // SMALL
    return grey.astype(np.float32).reshape(SMALL, block, SMALL, block).mean(axis=(1, 3))


def select_frames(sharp: np.ndarray, small: np.ndarray, max_frames: int = MAX_FRAMES) -> Tuple[List[int], int, int]:
    """(indices of the frames to keep, how many were blurred, how many were repeats).

    A frame is blurred against its neighbours, not against a fixed number:
    how sharp a sharp frame is depends on the room. A repeat is a frame that
    shows what the last kept frame showed (the phone was standing still).
    """
    count = len(sharp)
    if count == 0:
        return [], 0, 0
    padded = np.pad(np.asarray(sharp, dtype=np.float64), 4, mode="edge")
    local = np.median(np.lib.stride_tricks.sliding_window_view(padded, 9), axis=1)
    blurred = (sharp < BLUR_SHARE * local) | (sharp < FLAT_SHARPNESS)

    keep: List[int] = []
    repeats = 0
    for i in range(count):
        if blurred[i]:
            continue
        if keep and float(np.abs(small[i] - small[keep[-1]]).mean()) < DUPLICATE_DIFF:
            repeats += 1
            continue
        keep.append(i)
    if len(keep) > max_frames:
        keep = [int(part[np.argmax(sharp[part])]) for part in np.array_split(np.array(keep), max_frames)]
    return keep, int(blurred.sum()), repeats


def probe_duration(ffmpeg: str, video: Path) -> Optional[float]:
    """The video's length in seconds, or None when ffmpeg does not say. Raises when it holds no video."""
    try:
        done = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostdin", "-i", str(video)],
            capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as e:
        raise VideoPipelineError(f"ffmpeg could not open the video: {e}")
    text = done.stderr.decode("utf-8", errors="replace")
    if not re.search(r"Stream #.*Video:", text):
        raise VideoPipelineError(
            "This file holds no video that ffmpeg can read. Send the walkthrough as MP4 or MOV, "
            "straight from the phone."
        )
    found = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not found:
        return None
    return int(found.group(1)) * 3600 + int(found.group(2)) * 60 + float(found.group(3))


def _candidate_fps(duration: Optional[float], max_frames: int) -> float:
    if not duration or duration <= 0:
        return 2.0
    return float(np.clip(max_frames * CANDIDATES_PER_FRAME / duration, MIN_CANDIDATE_FPS, MAX_CANDIDATE_FPS))


def _ffmpeg_candidates(
    ffmpeg: str, video: Path, work: Path, max_frames: int,
    cancel: threading.Event, deadline: float, runner: Runner, report: FrameReport,
) -> Tuple[List[Path], np.ndarray]:
    """(candidate frames in order, their grey centre crops as an (N, THUMB, THUMB) array)."""
    report.duration_s = probe_duration(ffmpeg, video)
    fps = _candidate_fps(report.duration_s, max_frames)
    limit = max_frames * CANDIDATES_PER_FRAME
    candidates = work / "candidates"
    candidates.mkdir(parents=True, exist_ok=True)
    thumbs = work / "thumbs.gray"
    side = FRAME_LONG_SIDE
    # One pass, two outputs off the same frames: the frame itself, and a grey
    # crop of its centre at full detail to judge it by. ffmpeg turns a portrait
    # video upright by itself, which the "up" guess later relies on.
    graph = (
        f"[0:v]fps={fps:.4f},"
        f"scale='if(gte(iw,ih),min({side},iw),-2)':'if(gte(iw,ih),-2,min({side},ih))',split[full][t];"
        f"[t]crop='min({THUMB},iw)':'min({THUMB},ih)',scale={THUMB}:{THUMB},format=gray[thumb]"
    )
    log = work / "ffmpeg.log"
    code = runner(
        [
            ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", "-i", str(video),
            "-filter_complex", graph,
            "-map", "[full]", "-frames:v", str(limit), "-q:v", "2", str(candidates / "%06d.jpg"),
            "-map", "[thumb]", "-frames:v", str(limit), "-f", "rawvideo", "-pix_fmt", "gray", str(thumbs),
        ],
        log, cancel, deadline,
    )
    files = sorted(candidates.glob("*.jpg"))
    if code != 0 or not files or not thumbs.is_file():
        raise VideoPipelineError(
            "ffmpeg could not read frames out of this video. Send the walkthrough as MP4 or MOV, straight "
            f"from the phone. ({log_tail(log) or f'exit {code}'})"
        )
    grey = np.fromfile(thumbs, dtype=np.uint8)
    grey = grey[: (len(grey) // (THUMB * THUMB)) * THUMB * THUMB].reshape(-1, THUMB, THUMB)
    count = min(len(files), len(grey))
    return files[:count], grey[:count]


def _opencv_candidates(
    video: Path, work: Path, max_frames: int, cancel: threading.Event, deadline: float, report: FrameReport,
) -> Tuple[List[Path], np.ndarray]:
    import cv2  # not a dependency: only reached when ffmpeg is missing and OpenCV is there

    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise VideoPipelineError("OpenCV could not open this video. Send it as MP4 or MOV, or install ffmpeg.")
    try:
        # Turn a portrait video upright, as ffmpeg does, where this OpenCV can.
        if hasattr(cv2, "CAP_PROP_ORIENTATION_AUTO"):
            capture.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
        source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0) or 30.0
        total = float(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        report.duration_s = round(total / source_fps, 2) if total > 0 else None
        every = max(1, int(round(source_fps / _candidate_fps(report.duration_s, max_frames))))
        limit = max_frames * CANDIDATES_PER_FRAME
        candidates = work / "candidates"
        candidates.mkdir(parents=True, exist_ok=True)
        files: List[Path] = []
        greys: List[np.ndarray] = []
        index = 0
        while len(files) < limit and capture.grab():
            index += 1
            if (index - 1) % every:
                continue
            _check(cancel, deadline)
            ok, frame = capture.retrieve()
            if not ok or frame is None:
                continue
            height, width = frame.shape[:2]
            longest = max(height, width)
            if longest > FRAME_LONG_SIDE:
                ratio = FRAME_LONG_SIDE / longest
                frame = cv2.resize(frame, (int(width * ratio) // 2 * 2, int(height * ratio) // 2 * 2),
                                   interpolation=cv2.INTER_AREA)
                height, width = frame.shape[:2]
            grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            ch, cw = min(THUMB, height), min(THUMB, width)
            top, left = (height - ch) // 2, (width - cw) // 2
            crop = grey[top:top + ch, left:left + cw]
            if crop.shape != (THUMB, THUMB):
                crop = cv2.resize(crop, (THUMB, THUMB), interpolation=cv2.INTER_LINEAR)
            path = candidates / f"{len(files) + 1:06d}.jpg"
            if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                continue
            files.append(path)
            greys.append(crop)
    finally:
        capture.release()
    if not files:
        raise VideoPipelineError("OpenCV read no frames out of this video. Send it as MP4 or MOV, or install ffmpeg.")
    return files, np.stack(greys)


def sample_frames(
    video: Path, work: Path, frames_dir: Path, tools: VideoTools,
    cancel: threading.Event, deadline: float,
    max_frames: int = MAX_FRAMES, runner: Runner = run_tool,
) -> FrameReport:
    """Write the frames worth reconstructing from into `frames_dir`, named in order."""
    report = FrameReport(tool=tools.frame_tool or "")
    if tools.ffmpeg:
        files, grey = _ffmpeg_candidates(tools.ffmpeg, video, work, max_frames, cancel, deadline, runner, report)
    elif tools.opencv:
        files, grey = _opencv_candidates(video, work, max_frames, cancel, deadline, report)
    else:
        raise VideoPipelineError(tools.missing_message() or "Nothing here can read frames out of a video.")
    _check(cancel, deadline)

    sharp = np.array([sharpness(g) for g in grey])
    small = np.stack([shrink(g) for g in grey])
    keep, blurred, repeats = select_frames(sharp, small, max_frames)
    report.candidates, report.blurry, report.duplicates, report.kept = len(files), blurred, repeats, len(keep)
    if len(keep) < MIN_FRAMES:
        raise VideoPipelineError(
            f"Only {len(keep)} usable frames came out of the video ({len(files)} looked at, {blurred} blurred, "
            f"{repeats} showing the same view as the one before); at least {MIN_FRAMES} are needed. Film for "
            "a minute or two, walking slowly round the whole room with the lights up."
        )
    frames_dir.mkdir(parents=True, exist_ok=True)
    for number, index in enumerate(keep, start=1):
        shutil.move(str(files[index]), str(frames_dir / f"frame_{number:06d}.jpg"))
    shutil.rmtree(work / "candidates", ignore_errors=True)
    (work / "thumbs.gray").unlink(missing_ok=True)
    return report


# ---------------------------------------------------------------------------
# 2. Reconstruction (COLMAP, as an outside process)
# ---------------------------------------------------------------------------

def _colmap_step(
    colmap: str, step: str, args: Sequence[str], log: Path,
    cancel: threading.Event, deadline: float, runner: Runner,
    retries: Sequence[Sequence[str]] = (),
) -> None:
    """Run one COLMAP command. Each of `retries` is a set of extra flags tried if it fails."""
    code = runner([colmap, step, *args], log, cancel, deadline)
    for extra in retries:
        if code == 0:
            break
        code = runner([colmap, step, *args, *extra], log, cancel, deadline)
    if code != 0:
        raise VideoPipelineError(
            f"COLMAP's {step} step failed (exit {code}). {log_tail(log)} "
            "If this keeps happening, scan the room with Polycam or Scaniverse and export OBJ or PLY instead."
        )


def quaternion_rotation(qw: float, qx: float, qy: float, qz: float) -> np.ndarray:
    """The rotation matrix of a unit quaternion (w, x, y, z), as COLMAP writes one."""
    n = math.sqrt(qw * qw + qx * qx + qy * qy + qz * qz) or 1.0
    w, x, y, z = qw / n, qx / n, qy / n, qz / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def read_colmap_images(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """(camera centres, each camera's image-down direction), both (N, 3), in the model's axes.

    images.txt holds two lines for each image: its pose, then its 2D points
    (which may be empty). The pose takes a world point into the camera,
    x_cam = R x_world + t, so the camera stands at -R^T t and its image-down
    axis, seen from the world, is the second row of R.
    """
    centres: List[np.ndarray] = []
    downs: List[np.ndarray] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return np.zeros((0, 3)), np.zeros((0, 3))
    body = [line for line in lines if not line.startswith("#")]
    for pose in body[0::2]:
        words = pose.split()
        if len(words) < 10:
            continue
        try:
            qw, qx, qy, qz, tx, ty, tz = (float(w) for w in words[1:8])
        except ValueError:
            continue
        rotation = quaternion_rotation(qw, qx, qy, qz)
        centres.append(-rotation.T @ np.array([tx, ty, tz]))
        downs.append(rotation[1])
    if not centres:
        return np.zeros((0, 3)), np.zeros((0, 3))
    return np.array(centres), np.array(downs)


def read_colmap_points(path: Path, min_track: int = MIN_TRACK) -> np.ndarray:
    """The sparse points of points3D.txt: `ID X Y Z R G B ERROR (IMAGE_ID POINT2D_IDX)...`."""
    points: List[Tuple[float, float, float]] = []
    weak: List[Tuple[float, float, float]] = []
    try:
        handle = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return np.zeros((0, 3))
    with handle:
        for line in handle:
            if line.startswith("#"):
                continue
            words = line.split()
            if len(words) < 8:
                continue
            try:
                xyz = (float(words[1]), float(words[2]), float(words[3]))
            except ValueError:
                continue
            (points if (len(words) - 8) // 2 >= min_track else weak).append(xyz)
    # Points seen in only two frames are mostly noise; they are used only when there is little else.
    if len(points) < MIN_SPARSE_POINTS:
        points += weak
    return np.array(points, dtype=np.float64).reshape(-1, 3)


def _best_model(
    colmap: str, sparse: Path, work: Path, log: Path,
    cancel: threading.Event, deadline: float, runner: Runner,
) -> Tuple[Path, Path, np.ndarray, np.ndarray]:
    """(the model's own folder, its text copy, camera centres, camera downs) of the largest model.

    The mapper writes one folder for each piece it could not join to the
    rest. The one holding the most frames is the room.
    """
    best: Optional[Tuple[Path, Path, np.ndarray, np.ndarray]] = None
    for model in sorted(p for p in sparse.iterdir() if p.is_dir()) if sparse.is_dir() else []:
        text = work / "text" / model.name
        text.mkdir(parents=True, exist_ok=True)
        code = runner(
            [colmap, "model_converter", "--input_path", str(model), "--output_path", str(text),
             "--output_type", "TXT"],
            log, cancel, deadline,
        )
        if code != 0:
            continue
        centres, downs = read_colmap_images(text / "images.txt")
        if best is None or len(centres) > len(best[2]):
            best = (model, text, centres, downs)
    if best is None or not len(best[2]):
        raise VideoPipelineError(
            "COLMAP could not put the frames together into a room. Film again more slowly, with the lights "
            "up, keeping some of what you just filmed in view as you turn, and avoid blank walls filling the "
            "picture. Or scan the room with Polycam or Scaniverse and export OBJ or PLY. "
            + log_tail(log, lines=2, limit=240)
        )
    return best


def _dense_cloud(
    tools: VideoTools, frames_dir: Path, model: Path, work: Path, log: Path,
    cancel: threading.Event, deadline: float, runner: Runner, notes: List[str],
) -> Optional[np.ndarray]:
    """A dense cloud in the sparse model's axes, or None (with a note saying why)."""
    colmap = tools.colmap or ""
    dense = work / "dense"
    code = runner(
        [colmap, "image_undistorter", "--image_path", str(frames_dir), "--input_path", str(model),
         "--output_path", str(dense), "--output_type", "COLMAP"],
        log, cancel, deadline,
    )
    if code != 0:
        notes.append("The dense step could not be prepared, so the sparse cloud was used.")
        return None

    fused = dense / "fused.ply"
    code = runner([colmap, "patch_match_stereo", "--workspace_path", str(dense)], log, cancel, deadline)
    if code == 0:
        code = runner(
            [colmap, "stereo_fusion", "--workspace_path", str(dense), "--output_path", str(fused)],
            log, cancel, deadline,
        )
    found: Optional[Path] = fused if code == 0 and fused.is_file() else None
    used = "COLMAP"

    if found is None and tools.openmvs:
        folder = Path(tools.openmvs)

        def tool(name: str) -> str:
            return next((str(folder / n) for n in _exe(name) if (folder / n).is_file()), name)

        scene = dense / "scene.mvs"
        code = runner(
            [tool("InterfaceCOLMAP"), "-i", str(dense), "-o", str(scene), "--image-folder", str(dense / "images")],
            log, cancel, deadline,
        )
        if code == 0:
            code = runner([tool("DensifyPointCloud"), str(scene), "-w", str(dense)], log, cancel, deadline)
        clouds = sorted(dense.glob("*dense*.ply"), key=lambda p: p.stat().st_size, reverse=True)
        if code == 0 and clouds:
            found, used = clouds[0], "OpenMVS"

    if found is None:
        notes.append(
            "A dense cloud was asked for but could not be made (COLMAP's dense step needs an NVIDIA card "
            "with CUDA, and OpenMVS was not found or failed), so the sparse cloud was used."
        )
        return None
    try:
        points = parse_ply(found.read_bytes(), found.name).vertices
    except (OSError, RoomScanError):
        notes.append("The dense cloud could not be read back, so the sparse cloud was used.")
        return None
    notes.append(f"Dense cloud made with {used}: {len(points):,} points.")
    return points


# ---------------------------------------------------------------------------
# 3. Which way is up
# ---------------------------------------------------------------------------

def _layering(points: np.ndarray, direction: np.ndarray, step: float) -> float:
    """How much the cloud piles up into thin layers across `direction`."""
    along = points @ direction
    cells = np.floor((along - along.min()) / step).astype(np.int64)
    counts = np.bincount(cells)
    return float(np.dot(counts, counts))


def refine_up(points: np.ndarray, up: np.ndarray, reach_deg: float = 24.0) -> np.ndarray:
    """The direction within `reach_deg` of `up` that the floor and ceiling are flattest across."""
    up = up / np.linalg.norm(up)
    if len(points) > 40_000:
        points = points[:: len(points) // 40_000 + 1]
    spans = np.percentile(points, 99.5, axis=0) - np.percentile(points, 0.5, axis=0)
    step = max(float(spans.max()), 1e-9) / 250.0

    for reach, grid in ((reach_deg, 3.0), (3.0, 0.5), (0.5, 0.1)):
        helper = np.array([1.0, 0.0, 0.0]) if abs(up[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        e1 = np.cross(up, helper)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(up, e1)
        offsets = np.tan(np.radians(np.arange(-reach, reach + grid / 2.0, grid)))
        best, best_score = up, -1.0
        for a in offsets:
            for b in offsets:
                candidate = up + a * e1 + b * e2
                candidate /= np.linalg.norm(candidate)
                score = _layering(points, candidate, step)
                if score > best_score:
                    best, best_score = candidate, score
        up = best
    return up


def rotation_to_y_up(up: np.ndarray) -> np.ndarray:
    """A rotation (never a mirror) whose rows take `up` to +Y."""
    up = up / np.linalg.norm(up)
    helper = np.array([1.0, 0.0, 0.0]) if abs(up[0]) < 0.9 else np.array([0.0, 0.0, 1.0])
    x = np.cross(up, helper)
    x /= np.linalg.norm(x)
    z = np.cross(x, up)
    return np.stack([x, up, z])


@dataclass
class VideoCloud:
    """What a video gave: a cloud that is upright but has no scale yet."""

    points: np.ndarray                              # (N, 3) float32, Y up where `upright`
    cameras: np.ndarray                             # (M, 3) camera centres in the same axes
    upright: bool = True
    kind: str = "sparse"                            # sparse or dense
    frames: FrameReport = field(default_factory=FrameReport)
    images_registered: int = 0
    notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        return {
            "points": int(len(self.points)), "kind": self.kind, "upright": self.upright,
            "images_registered": self.images_registered, "images_total": self.frames.kept,
        }


def align_cloud(
    points: np.ndarray, centres: np.ndarray, downs: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, bool, List[str], List[str]]:
    """(points, camera centres, whether up was found, notes, warnings), turned so up is +Y."""
    notes: List[str] = []
    warnings: List[str] = []
    origin = np.median(points, axis=0)
    points = points - origin
    centres = centres - origin if len(centres) else centres

    mean_down = downs.mean(axis=0) if len(downs) else np.zeros(3)
    if np.linalg.norm(mean_down) < 0.2:
        warnings.append(
            "Which way is up could not be told from how the phone was held. If the room comes out on its "
            "side, set the up axis by hand."
        )
        return points, centres, False, notes, warnings

    held = -mean_down / np.linalg.norm(mean_down)
    up = refine_up(points, held)
    tilt = math.degrees(math.acos(float(np.clip(np.dot(up, held), -1.0, 1.0))))
    notes.append(
        "Up was taken from how the phone was held, then squared to the floor and ceiling "
        f"({tilt:.1f} degrees from the phone's own)."
    )
    rotation = rotation_to_y_up(up)
    return points @ rotation.T, (centres @ rotation.T if len(centres) else centres), True, notes, warnings


# ---------------------------------------------------------------------------
# The whole run
# ---------------------------------------------------------------------------

# (key, what the operator is told, where the bar stands when it starts)
STAGES = (
    ("frames", "Picking sharp frames out of the video", 0.02),
    ("features", "COLMAP: finding features in each frame", 0.15),
    ("matching", "COLMAP: matching frames to each other", 0.35),
    ("mapping", "COLMAP: working out where the camera went and building the cloud", 0.55),
    ("dense", "Filling the cloud in (dense)", 0.80),
    ("cloud", "Finding which way is up", 0.95),
)
STAGE_LABEL = {key: label for key, label, _ in STAGES}
STAGE_START = {key: start for key, _, start in STAGES}


def reconstruct(
    video: Path, work: Path, tools: VideoTools, cancel: threading.Event,
    quality: str = "sparse", timeout_s: float = 3600.0,
    progress: Optional[Progress] = None, runner: Runner = run_tool, max_frames: int = MAX_FRAMES,
) -> VideoCloud:
    """Video to an upright, unscaled cloud. Blocking and slow: run it on a thread of its own."""
    if not tools.ready:
        raise VideoPipelineError(tools.missing_message() or "No tool is installed to read a video with.")
    colmap = tools.colmap or ""
    deadline = time.monotonic() + timeout_s
    say = progress or (lambda stage, detail: None)
    log = work / "colmap.log"
    frames_dir = work / "frames"

    say("frames", "")
    report = sample_frames(video, work, frames_dir, tools, cancel, deadline, max_frames, runner)
    say("frames", f"{report.kept} of {report.candidates} frames kept")

    database = work / "database.db"
    say("features", f"{report.kept} frames")
    _colmap_step(
        colmap, "feature_extractor",
        ["--database_path", str(database), "--image_path", str(frames_dir), "--ImageReader.single_camera", "1"],
        log, cancel, deadline, runner,
        # No graphics card COLMAP can use: ask for the CPU. The flag's name depends on COLMAP's version.
        retries=(["--SiftExtraction.use_gpu", "0"], ["--FeatureExtraction.use_gpu", "0"]),
    )

    matcher = "exhaustive_matcher" if report.kept <= EXHAUSTIVE_UP_TO else "sequential_matcher"
    say("matching", "every frame against every other" if matcher == "exhaustive_matcher" else "neighbouring frames")
    _colmap_step(
        colmap, matcher, ["--database_path", str(database)], log, cancel, deadline, runner,
        retries=(["--SiftMatching.use_gpu", "0"], ["--FeatureMatching.use_gpu", "0"]),
    )

    sparse = work / "sparse"
    sparse.mkdir(parents=True, exist_ok=True)
    say("mapping", "this is the slow step")
    _colmap_step(
        colmap, "mapper",
        ["--database_path", str(database), "--image_path", str(frames_dir), "--output_path", str(sparse)],
        log, cancel, deadline, runner,
    )
    model, text, centres, downs = _best_model(colmap, sparse, work, log, cancel, deadline, runner)

    notes: List[str] = [
        f"Made from a walkthrough video: {report.kept} frames kept of {report.candidates} looked at "
        f"({report.blurry} blurred, {report.duplicates} repeats), read with {report.tool}; "
        f"COLMAP placed {len(centres)} of them."
    ]
    warnings: List[str] = []
    if len(centres) < max(MIN_FRAMES, 0.5 * report.kept):
        warnings.append(
            f"COLMAP could only place {len(centres)} of the {report.kept} frames, so part of the room is "
            "probably missing. Film again more slowly, keeping what you just filmed in view as you turn."
        )

    points: Optional[np.ndarray] = None
    kind = "sparse"
    if quality == "dense":
        say("dense", "")
        points = _dense_cloud(tools, frames_dir, model, work, log, cancel, deadline, runner, notes)
        kind = "dense" if points is not None else "sparse"
    if points is None:
        points = read_colmap_points(text / "points3D.txt")
    points = points[np.isfinite(points).all(axis=1)]
    if len(points) < MIN_SPARSE_POINTS:
        raise VideoPipelineError(
            f"The reconstruction holds only {len(points)} points, which is not enough to find a room in. "
            "Film again with the lights up and more of the room in each frame, or scan the room with "
            "Polycam or Scaniverse and export OBJ or PLY."
        )
    if len(points) > MAX_CLOUD_POINTS:
        points = points[np.random.default_rng(0).choice(len(points), MAX_CLOUD_POINTS, replace=False)]
    if kind == "sparse":
        notes.append(
            f"The cloud is sparse ({len(points):,} points): it shows the room's size and big shapes, "
            "and will miss small ones. Bare walls and floors give few points."
        )

    _check(cancel, deadline)
    say("cloud", f"{len(points):,} points")
    points, centres, upright, more_notes, more_warnings = align_cloud(points, centres, downs)
    return VideoCloud(
        points=points.astype(np.float32), cameras=centres.astype(np.float32), upright=upright, kind=kind,
        frames=report, images_registered=int(len(centres)),
        notes=notes + more_notes, warnings=warnings + more_warnings,
    )


# ---------------------------------------------------------------------------
# 4. Scale, and the PLY the scan reader is handed
# ---------------------------------------------------------------------------

REFERENCE_KINDS = ("ceiling_height", "longest_wall")


@dataclass
class Reference:
    """One thing the operator measured in the room, in metres."""

    kind: Optional[str] = None          # one of REFERENCE_KINDS, or None: nothing was measured
    metres: Optional[float] = None

    def __post_init__(self) -> None:
        if self.kind is None:
            return
        if self.kind not in REFERENCE_KINDS:
            raise RoomScanError("The measurement must be a ceiling height or the longest wall.")
        if self.metres is None or not REFERENCE_MIN <= self.metres <= REFERENCE_MAX:
            raise RoomScanError(
                f"The measurement must be between {REFERENCE_MIN:g} and {REFERENCE_MAX:g} metres."
            )


def scale_cloud(cloud: VideoCloud, reference: Reference) -> Tuple[np.ndarray, Dict[str, Any], List[str], List[str]]:
    """(points in metres, what the scale rests on, notes, warnings)."""
    points = cloud.points.astype(np.float64)
    notes: List[str] = []
    warnings: List[str] = []
    y = points[:, 1]
    low, high = np.percentile(y, [0.5, 99.5])
    if not high - low > 0:
        raise RoomScanError("The reconstruction is flat: there is no room in it.")
    # extract.py looks for the floor in 2 cm steps, so stretch the cloud to a
    # room-sized height first and look for the floor in that.
    nominal = NOMINAL_HEIGHT / float(high - low)
    unused: List[str] = []
    floor, ceiling = find_floor_and_ceiling(y * nominal, None, unused)
    height = max(ceiling - floor, 1e-6)

    info: Dict[str, Any] = {"assumed": False, "reference": reference.kind, "metres": reference.metres}
    if reference.kind == "ceiling_height":
        scale = nominal * float(reference.metres) / height
        notes.append(f"Scale set from the measurement given: the ceiling is {reference.metres:g} m high.")
        info["basis"] = "ceiling height"
    elif reference.kind == "longest_wall":
        stretched = points * nominal
        upright = (stretched[:, 1] > floor + 0.3) & (stretched[:, 1] < ceiling - 0.3)
        if upright.sum() < 200:
            upright = np.ones(len(stretched), dtype=bool)
        turned = turn_about_vertical(stretched, dominant_wall_turn(stretched[upright, 0], stretched[upright, 2]))
        sides = [_wall(turned[upright, column], side)[0] for column in (0, 2) for side in (-1, 1)]
        longest = max(sides[1] - sides[0], sides[3] - sides[2], 1e-6)
        scale = nominal * float(reference.metres) / longest
        notes.append(f"Scale set from the measurement given: the longest wall is {reference.metres:g} m.")
        info["basis"] = "longest wall"
    else:
        info["assumed"] = True
        camera = None
        if cloud.upright and len(cloud.cameras):
            camera = float(np.median(cloud.cameras[:, 1].astype(np.float64))) * nominal - floor
        if camera is not None and 0.1 * height < camera < 0.95 * height:
            scale = nominal * ASSUMED_CAMERA_HEIGHT / camera
            guess = f"the phone was taken to be held {ASSUMED_CAMERA_HEIGHT:g} m above the floor"
            info["basis"] = "assumed camera height"
        else:
            scale = nominal * ASSUMED_CEILING_HEIGHT / height
            guess = f"the ceiling was taken to be {ASSUMED_CEILING_HEIGHT:g} m high"
            info["basis"] = "assumed ceiling height"
        warnings.append(
            f"The scale is ASSUMED. A video carries no real size, so {guess}. Every size here is a guess "
            "until you give the ceiling height or the length of the longest wall."
        )
    info["scale"] = float(scale)
    info["ceiling_height"] = round(float(height / nominal * scale), 2)
    return points * scale, info, notes, warnings


def _comment(key: str, text: str) -> str:
    """One PLY header comment. The header is ASCII and a comment is one line."""
    plain = " ".join(str(text).split()).encode("ascii", errors="replace").decode("ascii")
    return f"comment {key} {plain}"


def cloud_ply(cloud: VideoCloud, reference: Optional[Reference] = None) -> Tuple[bytes, Dict[str, Any]]:
    """(the cloud as a binary PLY in metres with its caveats in the header, what the scale rests on)."""
    points, info, notes, warnings = scale_cloud(cloud, reference or Reference())
    header = ["ply", "format binary_little_endian 1.0", "comment room scan from a walkthrough video"]
    header.append(_comment(PLY_METRES_PER_UNIT, "1"))
    if cloud.upright:
        header.append(_comment(PLY_UP_AXIS, "y"))
    header += [_comment(PLY_NOTE, note) for note in cloud.notes + notes]
    header += [_comment(PLY_WARNING, warning) for warning in warnings + cloud.warnings]
    header += [f"element vertex {len(points)}", "property float x", "property float y", "property float z",
               "end_header"]
    return ("\n".join(header) + "\n").encode("ascii") + points.astype("<f4").tobytes(), info


__all__ = [
    "FrameReport", "REFERENCE_KINDS", "Reference", "STAGES", "VIDEO_SUFFIXES", "VideoCancelled", "VideoCloud",
    "VideoPipelineError", "VideoTools", "align_cloud", "cloud_ply", "find_tools", "kill_running_tools",
    "reconstruct", "run_tool", "sample_frames", "scale_cloud", "select_frames",
]
