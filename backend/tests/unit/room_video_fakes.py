"""
Stand-ins for the walkthrough-video tests
=========================================

The room of room_scan_meshes.py as a photogrammetry tool would hand it back:
in axes of its own (tipped over, not just turned), at no particular scale,
with the cameras that filmed it. And a stand-in for the outside tools, which
writes the files COLMAP and ffmpeg would write without running either.

The stand-in follows COLMAP's documented text format. It shows that the
pipeline calls the steps in order and reads what they write; it cannot show
that a real COLMAP accepts those calls.
"""

import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.services.room_scan.video import THUMB, VideoCancelled
from tests.unit.room_scan_meshes import ROOM, room_mesh, sample_surface

MODEL_SCALE = 0.37                       # model units per metre: a video has no scale
MODEL_SHIFT = np.array([4.0, -2.5, 7.0])
CAMERA_HEIGHT = 1.5


def tipped_rotation(seed: int = 3) -> np.ndarray:
    """A proper rotation that leaves no axis where it was."""
    q, _ = np.linalg.qr(np.random.default_rng(seed).normal(size=(3, 3)))
    if np.linalg.det(q) < 0:
        q[:, 0] = -q[:, 0]
    return q


def rotation_quaternion(r: np.ndarray) -> Tuple[float, float, float, float]:
    """(w, x, y, z) of a rotation matrix."""
    trace = r[0, 0] + r[1, 1] + r[2, 2]
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        return (0.25 * s, (r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s)
    if r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = math.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
        return ((r[2, 1] - r[1, 2]) / s, 0.25 * s, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s)
    if r[1, 1] > r[2, 2]:
        s = math.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
        return ((r[0, 2] - r[2, 0]) / s, (r[0, 1] + r[1, 0]) / s, 0.25 * s, (r[1, 2] + r[2, 1]) / s)
    s = math.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
    return ((r[1, 0] - r[0, 1]) / s, (r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, 0.25 * s)


def walkthrough(
    cameras: int = 30, pitch_deg: float = 12.0, points: int = 60_000,
) -> Tuple[np.ndarray, List[Tuple[np.ndarray, np.ndarray]]]:
    """(the room's points in model axes, [(world-to-camera rotation, translation)] for each frame).

    The phone is carried round the room 1.5 m up, looking the way it is going
    and tilted up a little, and only faces half the compass: so the average of
    its "down" is some degrees off true down, as a real walk's is.
    """
    q = tipped_rotation()
    vertices, faces = room_mesh()
    cloud = sample_surface(vertices, faces, points) @ q.T * MODEL_SCALE + MODEL_SHIFT

    poses = []
    pitch = math.radians(pitch_deg)
    for i in range(cameras):
        along = i / max(cameras - 1, 1)
        yaw = math.radians(-80.0 + 160.0 * along)
        centre = np.array([
            (ROOM["width"] / 2 - 2.0) * math.cos(2 * math.pi * along),
            CAMERA_HEIGHT,
            (ROOM["depth"] / 2 - 2.0) * math.sin(2 * math.pi * along),
        ])
        forward = np.array([math.sin(yaw) * math.cos(pitch), math.sin(pitch), math.cos(yaw) * math.cos(pitch)])
        right = np.cross(np.array([0.0, -1.0, 0.0]), forward)
        right /= np.linalg.norm(right)
        down = np.cross(forward, right)
        to_camera = np.stack([right, down, forward]) @ q.T      # model axes to camera axes
        centre_model = centre @ q.T * MODEL_SCALE + MODEL_SHIFT
        poses.append((to_camera, -to_camera @ centre_model))
    return cloud, poses


def images_txt(poses: Sequence[Tuple[np.ndarray, np.ndarray]]) -> str:
    lines = [
        "# Image list with two lines of data per image:",
        "#   IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME",
        "#   POINTS2D[] as (X, Y, POINT3D_ID)",
        f"# Number of images: {len(poses)}",
    ]
    for number, (rotation, translation) in enumerate(poses, start=1):
        w, x, y, z = rotation_quaternion(rotation)
        tx, ty, tz = translation
        lines.append(f"{number} {w:.9f} {x:.9f} {y:.9f} {z:.9f} {tx:.9f} {ty:.9f} {tz:.9f} 1 frame_{number:06d}.jpg")
        # The second line is the frame's 2D points. One frame in three has none, which is an empty line.
        lines.append("" if number % 3 == 0 else "12.5 40.25 7 300.0 211.5 -1")
    return "\n".join(lines) + "\n"


def points3d_txt(cloud: np.ndarray, track: int = 3) -> str:
    lines = ["# 3D point list with one line of data per point:",
             "#   POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[] as (IMAGE_ID, POINT2D_IDX)"]
    seen = " ".join(f"{image} {image * 2}" for image in range(1, track + 1))
    lines += [f"{n} {x:.6f} {y:.6f} {z:.6f} 128 128 128 0.5 {seen}" for n, (x, y, z) in enumerate(cloud, start=1)]
    return "\n".join(lines) + "\n"


class FakeTools:
    """Stands in for run_tool: writes what ffmpeg and COLMAP would, and records what was asked.

    The mapper "finds" two models: a small stray piece (sparse/0) and the
    room (sparse/1), so picking the larger one is exercised.
    """

    def __init__(
        self, frames: int = 40, needs_cpu_flag: bool = False, fail_step: Optional[str] = None,
        no_model: bool = False, still_video: bool = False, points: int = 60_000,
    ) -> None:
        self.frames = frames
        self.needs_cpu_flag = needs_cpu_flag
        self.fail_step = fail_step
        self.no_model = no_model
        self.still_video = still_video
        self.calls: List[List[str]] = []
        self.cloud, self.poses = walkthrough(points=points)

    def steps(self) -> List[str]:
        return [Path(call[0]).stem.lower() if "ffmpeg" in call[0] else call[1] for call in self.calls]

    def _models(self) -> Dict[str, Tuple[str, str]]:
        return {
            "0": (images_txt(self.poses[:2]), points3d_txt(self.cloud[:50])),
            "1": (images_txt(self.poses), points3d_txt(self.cloud)),
        }

    def __call__(self, args, log_path, cancel, deadline) -> int:
        args = [str(a) for a in args]
        self.calls.append(args)
        if cancel.is_set():
            raise VideoCancelled()
        with open(log_path, "ab") as log:
            log.write(f"fake {args[:2]}\n".encode())

        if "ffmpeg" in args[0]:
            pattern = next(a for a in args if a.endswith("%06d.jpg"))
            thumbs = next(a for a in args if a.endswith("thumbs.gray"))
            rng = np.random.default_rng(1)
            if self.still_video:
                # A phone left on a table: every frame is the one before.
                frame = rng.integers(0, 255, (THUMB, THUMB), dtype=np.uint8)
                grey = np.repeat(frame[None], self.frames, axis=0)
            else:
                grey = rng.integers(0, 255, (self.frames, THUMB, THUMB), dtype=np.uint8)
            grey.tofile(thumbs)
            for number in range(1, self.frames + 1):
                Path(pattern.replace("%06d", f"{number:06d}")).write_bytes(b"\xff\xd8 not a real jpeg")
            return 0

        step = args[1]
        option = {args[i]: args[i + 1] for i in range(2, len(args) - 1, 2)}
        if step == self.fail_step:
            with open(log_path, "ab") as log:
                log.write(b"ERROR: something went wrong in the fake\n")
            return 1
        if step in ("feature_extractor", "exhaustive_matcher", "sequential_matcher"):
            if self.needs_cpu_flag and not any(key.endswith(".use_gpu") for key in option):
                return 1
            return 0
        if step == "mapper":
            if not self.no_model:
                for name in self._models():
                    model = Path(option["--output_path"]) / name
                    model.mkdir(parents=True, exist_ok=True)
                    (model / "points3D.bin").write_bytes(b"binary, never read")
            return 0
        if step == "model_converter":
            images, points = self._models()[Path(option["--input_path"]).name]
            out = Path(option["--output_path"])
            (out / "images.txt").write_text(images, encoding="utf-8")
            (out / "points3D.txt").write_text(points, encoding="utf-8")
            return 0
        return 1    # image_undistorter and the rest: no dense cloud here
