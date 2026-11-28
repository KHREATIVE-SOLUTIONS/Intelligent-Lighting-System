"""
Room from a walkthrough video
=============================

backend/app/services/room_scan/video.py and video_jobs.py. docs/ROOM_SCAN.md.

What has to hold: a machine with no photogrammetry tool is told what to
install or what to do instead; blurred and repeated frames are dropped; a
model that comes back tipped over and at no scale is stood up and scaled into
the room the scan reader recognises; an unmeasured scale is called assumed,
loudly; and a job can be stopped and cleans up after itself.

COLMAP is not run here: FakeTools stands in for it (room_video_fakes.py), so
these show the steps are called in order and their files read, not that a real
COLMAP accepts the calls. ffmpeg is run for real where it is installed.
"""

import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from app.services.room_scan import RoomScanError, extract_room, read_scan_file
from app.services.room_scan import video
from app.services.room_scan.video import (
    MIN_FRAMES, Reference, VideoCancelled, VideoCloud, VideoPipelineError, VideoTools,
    align_cloud, cloud_ply, find_colmap, find_tools, read_colmap_images, read_colmap_points,
    reconstruct, run_tool, sample_frames, select_frames, sharpness, shrink,
)
from app.services.room_scan.video_jobs import CANCELLED, DONE, FAILED, JobBusy, VideoJobs
from tests.unit.room_scan_meshes import ROOM, sample_surface, room_mesh, write_ply
from tests.unit.room_video_fakes import (
    CAMERA_HEIGHT, MODEL_SCALE, MODEL_SHIFT, FakeTools, images_txt, points3d_txt, sparse_walkthrough,
    tipped_rotation, walkthrough,
)

FFMPEG = shutil.which("ffmpeg")
READY = VideoTools(ffmpeg="ffmpeg", colmap="colmap")
FAR = time.monotonic() + 3600


def never() -> threading.Event:
    return threading.Event()


def wait_for(job, states=(DONE, FAILED, CANCELLED), seconds=20.0):
    end = time.monotonic() + seconds
    while job.state not in states and time.monotonic() < end:
        time.sleep(0.02)
    return job.state


def synthetic_cloud() -> VideoCloud:
    """The tipped, unscaled walkthrough, stood up by align_cloud."""
    cloud, poses = walkthrough()
    centres = np.array([-r.T @ t for r, t in poses])
    downs = np.array([r[1] for r, _ in poses])
    points, cameras, upright, notes, warnings = align_cloud(cloud, centres, downs)
    return VideoCloud(points=points.astype(np.float32), cameras=cameras.astype(np.float32),
                      upright=upright, notes=notes, warnings=warnings)


def room_of(ply: bytes):
    return extract_room(read_scan_file("walkthrough.ply", ply))


# ---------------------------------------------------------------------------
# What is installed
# ---------------------------------------------------------------------------

class TestTools:

    def test_no_colmap_says_what_to_install_and_what_to_do_instead(self):
        tools = VideoTools(ffmpeg="ffmpeg", colmap=None)
        assert not tools.ready
        message = tools.missing_message()
        assert "COLMAP" in message and "github.com/colmap/colmap" in message
        assert "COLMAP_PATH" in message
        assert "Polycam" in message and "Scaniverse" in message and "OBJ or PLY" in message
        assert tools.to_dict()["message"] == message

    def test_colmap_without_a_frame_reader_asks_for_ffmpeg(self):
        tools = VideoTools(colmap="colmap")
        assert not tools.ready
        assert "ffmpeg" in tools.missing_message()

    def test_ready_with_either_frame_reader(self):
        assert VideoTools(ffmpeg="ffmpeg", colmap="colmap").frame_tool == "ffmpeg"
        opencv = VideoTools(opencv=True, colmap="colmap")
        assert opencv.ready and opencv.frame_tool == "opencv" and opencv.missing_message() is None

    def test_a_configured_folder_file_or_nothing(self, tmp_path):
        folder = tmp_path / "COLMAP-3.9"
        (folder / "bin").mkdir(parents=True)
        (folder / "bin" / "colmap.exe").write_bytes(b"")
        assert find_colmap(str(folder)) == str(folder / "bin" / "colmap.exe")
        # The .bat sets up the libraries, so it is preferred where both are there.
        (folder / "COLMAP.bat").write_bytes(b"")
        assert find_colmap(str(folder)) == str(folder / "COLMAP.bat")
        assert find_colmap(str(folder / "COLMAP.bat")) == str(folder / "COLMAP.bat")
        # A configured path that is wrong is not quietly replaced by whatever PATH has.
        assert find_colmap(str(tmp_path / "missing")) is None

    def test_find_tools_reads_the_configured_path(self, tmp_path):
        (tmp_path / "colmap").write_bytes(b"")
        assert find_tools(colmap_path=str(tmp_path)).colmap == str(tmp_path / "colmap")


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------

class TestFrameSelection:

    def frames(self, count=30, seed=0):
        rng = np.random.default_rng(seed)
        return rng.integers(0, 255, (count, video.THUMB, video.THUMB), dtype=np.uint8)

    def test_a_smeared_frame_scores_far_below_a_sharp_one(self):
        sharp = self.frames(1)[0]
        smeared = sharp.astype(np.float32).reshape(video.THUMB, video.THUMB // 8, 8).mean(axis=2)
        smeared = np.repeat(smeared, 8, axis=1)
        assert sharpness(smeared) < 0.3 * sharpness(sharp)

    def test_blurred_frames_are_dropped(self):
        grey = self.frames(30)
        sharp = np.array([sharpness(g) for g in grey])
        sharp[[5, 17]] *= 0.1                                   # two frames taken mid-swing
        small = np.stack([shrink(g) for g in grey])
        keep, blurred, repeats = select_frames(sharp, small)
        assert blurred == 2 and repeats == 0
        assert 5 not in keep and 17 not in keep and len(keep) == 28

    def test_a_frame_showing_what_the_last_one_showed_is_dropped(self):
        grey = self.frames(20)
        grey[8] = grey[7]
        grey[9] = grey[7]
        sharp = np.array([sharpness(g) for g in grey])
        keep, blurred, repeats = select_frames(sharp, np.stack([shrink(g) for g in grey]))
        assert repeats == 2 and blurred == 0
        assert 7 in keep and 8 not in keep and 9 not in keep

    def test_a_black_frame_is_dropped(self):
        grey = self.frames(12)
        grey[3] = 0
        sharp = np.array([sharpness(g) for g in grey])
        keep, blurred, _ = select_frames(sharp, np.stack([shrink(g) for g in grey]))
        assert 3 not in keep and blurred == 1

    def test_too_many_are_thinned_evenly_keeping_the_sharpest(self):
        grey = self.frames(60)
        sharp = np.array([sharpness(g) for g in grey])
        sharp[10] *= 1.2
        keep, _, _ = select_frames(sharp, np.stack([shrink(g) for g in grey]), max_frames=20)
        assert len(keep) == 20 and keep == sorted(keep)
        assert 10 in keep
        assert keep[0] < 3 and keep[-1] >= 57                   # from the whole video, not its start

    def test_a_dim_room_is_not_a_phone_standing_still(self):
        """Two frames are compared against their own contrast, not a fixed number of grey levels."""
        grey = self.frames(20)
        sharp = np.array([sharpness(g) for g in grey])
        dim = np.stack([shrink(g) for g in grey]) * 0.05
        keep, blurred, repeats = select_frames(sharp, dim)
        assert repeats == 0 and len(keep) == 20
        dim[8] = dim[7]
        assert select_frames(sharp, dim)[2] == 1

    def test_no_frames(self):
        assert select_frames(np.array([]), np.zeros((0, 32, 32))) == ([], 0, 0)


def make_clip(path: Path, source: str, seconds: int = 6) -> None:
    done = subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", source,
         "-t", str(seconds), "-pix_fmt", "yuv420p", str(path)],
        capture_output=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")


def frame_size(path: Path) -> str:
    """Width x height of a JPEG, as ffmpeg reports it."""
    probe = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, timeout=60)
    return re.search(r", (\d+x\d+)", probe.stderr.decode(errors="replace")).group(1)


def sampler_tools(sampler: str) -> VideoTools:
    if sampler == "opencv":
        pytest.importorskip("cv2")
        return VideoTools(opencv=True, colmap="c")
    return VideoTools(ffmpeg=FFMPEG, colmap="c")


SAMPLERS = pytest.mark.parametrize("sampler", ["ffmpeg", "opencv"])


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
class TestFramesWithRealFfmpeg:
    """The one stage that can be run for real here."""

    def test_frames_come_out_of_a_moving_clip_in_order(self, tmp_path):
        clip = tmp_path / "walk.mp4"
        make_clip(clip, "testsrc2=size=1280x720:rate=30")
        report = sample_frames(clip, tmp_path, tmp_path / "frames", VideoTools(ffmpeg=FFMPEG, colmap="c"),
                               never(), FAR)
        names = sorted(p.name for p in (tmp_path / "frames").glob("*.jpg"))
        assert report.tool == "ffmpeg"
        assert report.duration_s == pytest.approx(6.0, abs=0.3)
        assert report.kept == len(names) >= MIN_FRAMES
        assert report.candidates >= report.kept
        assert names[0] == "frame_000001.jpg" and names[-1] == f"frame_{len(names):06d}.jpg"
        assert all((tmp_path / "frames" / n).stat().st_size > 1000 for n in names)
        # What was only needed to choose is gone.
        assert not (tmp_path / "candidates").exists() and not (tmp_path / "thumbs.gray").exists()

    @SAMPLERS
    def test_a_portrait_clip_keeps_its_long_side_within_the_limit(self, tmp_path, sampler):
        """Also: this pattern barely changes in its middle. Frames are compared whole, so none is a repeat."""
        clip = tmp_path / "tall.mp4"
        make_clip(clip, "testsrc2=size=1080x1920:rate=30")
        report = sample_frames(clip, tmp_path, tmp_path / "frames", sampler_tools(sampler), never(), FAR)
        assert report.duplicates == 0 and report.kept == report.candidates
        assert frame_size(tmp_path / "frames" / "frame_000001.jpg") == "900x1600"

    @SAMPLERS
    def test_a_video_filmed_upright_comes_out_upright(self, tmp_path, sampler):
        """A phone held upright records sideways pixels and a rotation beside them. Up is guessed
        from which way is down in each frame, so the frames have to be turned as the phone was."""
        flat = tmp_path / "flat.mp4"
        make_clip(flat, "testsrc2=size=1280x720:rate=30")
        turned = tmp_path / "turned.mp4"
        done = subprocess.run(
            [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-display_rotation", "90", "-i", str(flat),
             "-c", "copy", str(turned)], capture_output=True, timeout=120)
        if done.returncode != 0:
            pytest.skip("this ffmpeg cannot write a rotation into a video")
        work = tmp_path / "work"
        work.mkdir()
        sample_frames(turned, work, work / "frames", sampler_tools(sampler), never(), FAR)
        assert frame_size(work / "frames" / "frame_000001.jpg") == "720x1280"

    @SAMPLERS
    def test_a_dark_room_still_gives_its_frames(self, tmp_path, sampler):
        clip = tmp_path / "dark.mp4"
        make_clip(clip, "testsrc2=size=1280x720:rate=30,lutyuv=y=val*0.12")
        report = sample_frames(clip, tmp_path, tmp_path / "frames", sampler_tools(sampler), never(), FAR)
        assert report.blurry == 0 and report.duplicates == 0 and report.kept == report.candidates

    @SAMPLERS
    def test_a_grainy_clip_that_never_moves_is_still_a_clip_that_never_moves(self, tmp_path, sampler):
        clip = tmp_path / "grain.mp4"
        make_clip(clip, "smptebars=size=640x360:rate=30,noise=alls=12:allf=t")
        with pytest.raises(VideoPipelineError) as refused:
            sample_frames(clip, tmp_path, tmp_path / "frames", sampler_tools(sampler), never(), FAR)
        assert "Only 1 usable frames" in str(refused.value)

    def test_a_clip_that_never_moves_is_refused_with_advice(self, tmp_path):
        clip = tmp_path / "still.mp4"
        make_clip(clip, "smptebars=size=640x360:rate=30")
        with pytest.raises(VideoPipelineError) as refused:
            sample_frames(clip, tmp_path, tmp_path / "frames", VideoTools(ffmpeg=FFMPEG, colmap="c"), never(), FAR)
        assert "same view" in str(refused.value) and "walking slowly" in str(refused.value)

    def test_a_file_that_is_not_a_video_is_refused(self, tmp_path):
        fake = tmp_path / "notes.mp4"
        fake.write_bytes(b"this is not a video" * 100)
        with pytest.raises(VideoPipelineError) as refused:
            sample_frames(fake, tmp_path, tmp_path / "frames", VideoTools(ffmpeg=FFMPEG, colmap="c"), never(), FAR)
        assert "MP4 or MOV" in str(refused.value)

    def test_opencv_reads_the_same_clip_when_ffmpeg_is_missing(self, tmp_path):
        pytest.importorskip("cv2")
        clip = tmp_path / "walk.mp4"
        make_clip(clip, "testsrc2=size=1280x720:rate=30")
        report = sample_frames(clip, tmp_path, tmp_path / "frames", VideoTools(opencv=True, colmap="c"),
                               never(), FAR)
        assert report.tool == "opencv"
        assert report.kept == len(list((tmp_path / "frames").glob("frame_*.jpg"))) >= MIN_FRAMES


# ---------------------------------------------------------------------------
# Running an outside tool
# ---------------------------------------------------------------------------

class TestRunTool:

    def test_output_goes_to_the_log_and_the_exit_code_comes_back(self, tmp_path):
        log = tmp_path / "tool.log"
        assert run_tool([sys.executable, "-c", "print('hello from the tool')"], log, never(), FAR) == 0
        assert run_tool([sys.executable, "-c", "import sys; sys.exit(3)"], log, never(), FAR) == 3
        assert "hello from the tool" in log.read_text(errors="replace")
        assert "hello from the tool" in video.log_tail(log, lines=20)

    def test_a_cancelled_tool_is_killed(self, tmp_path):
        cancel = threading.Event()
        threading.Timer(0.5, cancel.set).start()
        started = time.monotonic()
        with pytest.raises(VideoCancelled):
            run_tool([sys.executable, "-c", "import time; time.sleep(60)"], tmp_path / "t.log", cancel, FAR)
        assert time.monotonic() - started < 15

    def test_a_tool_past_the_deadline_is_killed(self, tmp_path):
        started = time.monotonic()
        with pytest.raises(VideoPipelineError) as stopped:
            run_tool([sys.executable, "-c", "import time; time.sleep(60)"], tmp_path / "t.log", never(),
                     time.monotonic() + 0.5)
        assert "out of time" in str(stopped.value) and time.monotonic() - started < 15

    def test_a_tool_that_is_not_there(self, tmp_path):
        with pytest.raises(VideoPipelineError) as missing:
            run_tool([str(tmp_path / "no-such-tool")], tmp_path / "t.log", never(), FAR)
        assert "could not be started" in str(missing.value)


# ---------------------------------------------------------------------------
# COLMAP's files
# ---------------------------------------------------------------------------

class TestColmapText:

    def test_cameras_are_read_where_they_stood_and_which_way_was_down(self, tmp_path):
        _, poses = walkthrough(cameras=9)
        path = tmp_path / "images.txt"
        path.write_text(images_txt(poses), encoding="utf-8")       # every third frame has an empty points line
        centres, downs = read_colmap_images(path)
        assert len(centres) == 9
        q = tipped_rotation()
        # Back in the room's own axes every camera is 1.5 m up and inside the room.
        world = (centres - MODEL_SHIFT) / MODEL_SCALE @ q
        assert np.allclose(world[:, 1], CAMERA_HEIGHT, atol=1e-5)
        assert np.abs(world[:, 0]).max() < ROOM["width"] / 2 and np.abs(world[:, 2]).max() < ROOM["depth"] / 2
        # Each camera's down is a unit vector pointing mostly at the floor.
        assert np.allclose(np.linalg.norm(downs, axis=1), 1.0, atol=1e-6)
        assert ((downs @ q)[:, 1] < -0.9).all()

    def test_points_seen_in_few_frames_are_left_out_unless_there_is_little_else(self, tmp_path):
        cloud = np.random.default_rng(0).normal(size=(400, 3))
        strong, weak = tmp_path / "strong.txt", tmp_path / "weak.txt"
        strong.write_text(points3d_txt(cloud, track=3) + "9999 50 50 50 1 1 1 0.5 1 2 2 3\n", encoding="utf-8")
        weak.write_text(points3d_txt(cloud[:100], track=2), encoding="utf-8")
        assert len(read_colmap_points(strong)) == 400           # the two-frame point is dropped
        assert len(read_colmap_points(weak)) == 100             # too few to be choosy
        assert np.allclose(read_colmap_points(strong)[:5], cloud[:5], atol=1e-5)

    def test_missing_files_read_as_nothing(self, tmp_path):
        assert len(read_colmap_points(tmp_path / "none.txt")) == 0
        assert len(read_colmap_images(tmp_path / "none.txt")[0]) == 0


# ---------------------------------------------------------------------------
# Which way is up, and scale
# ---------------------------------------------------------------------------

class TestAlignAndScale:

    def test_a_tipped_model_is_stood_up(self):
        cloud = synthetic_cloud()
        assert cloud.upright
        y = cloud.points[:, 1].astype(np.float64)
        low, high = np.percentile(y, [0.5, 99.5])
        height = (high - low) / MODEL_SCALE
        assert height == pytest.approx(ROOM["height"], abs=0.08)        # flat floor and ceiling: no smear
        # The floor is below the cameras, not above them: up is up, not down.
        cameras = float(np.median(cloud.cameras[:, 1]))
        assert (cameras - low) / MODEL_SCALE == pytest.approx(CAMERA_HEIGHT, abs=0.1)
        assert any("how the phone was held" in note for note in cloud.notes)

    def test_the_phone_alone_would_have_left_the_room_leaning(self):
        """Why the up direction is refined: the walk in the fake tilts the phone's average down."""
        cloud, poses = walkthrough()
        held = -np.array([r[1] for r, _ in poses]).mean(axis=0)
        held /= np.linalg.norm(held)
        true_up = tipped_rotation() @ np.array([0.0, 1.0, 0.0])
        assert np.degrees(np.arccos(held @ true_up)) > 3.0
        refined = video.refine_up(cloud - np.median(cloud, axis=0), held)
        assert np.degrees(np.arccos(refined @ true_up)) < 0.15

    @pytest.mark.parametrize("count, flat_share, seed", [
        (600, 0.25, 0), (600, 0.10, 2), (1500, 0.10, 0), (3000, 0.25, 1), (3000, 0.10, 2), (5000, 0.10, 1),
    ])
    def test_a_sparse_noisy_cloud_with_strays_is_still_the_room(self, count, flat_share, seed):
        """What COLMAP's sparse cloud looks like: few points, mostly on walls, each a few
        centimetres off, and some percent nowhere near the room. The other tests here use
        60,000 clean points, which no video gives."""
        cloud, centres, downs = sparse_walkthrough(count, flat_share=flat_share, seed=seed)
        points, cameras, upright, notes, _ = align_cloud(cloud, centres, downs)
        assert upright and any("stray points" in note for note in notes)
        made = VideoCloud(points=points.astype(np.float32), cameras=cameras.astype(np.float32), upright=True)

        room = room_of(cloud_ply(made, Reference("ceiling_height", ROOM["height"]))[0]).shell["room"]
        assert room["height"] == pytest.approx(ROOM["height"], abs=0.1)
        assert sorted([room["width"], room["depth"]]) == pytest.approx([ROOM["depth"], ROOM["width"]], abs=0.25)
        # And from the phone's height alone, which is how an unmeasured room is scaled.
        assumed = room_of(cloud_ply(made)[0]).shell["room"]
        assert assumed["height"] == pytest.approx(ROOM["height"], abs=0.2)

    def test_strays_are_dropped_and_the_room_is_kept(self):
        cloud, _, _ = sparse_walkthrough(3000, stray=0.05, seed=4)
        keep = video.drop_strays(cloud)
        world = (cloud - MODEL_SHIFT) / MODEL_SCALE @ tipped_rotation()
        inside = (
            (np.abs(world[:, 0]) < ROOM["width"] / 2 + 0.3) & (np.abs(world[:, 2]) < ROOM["depth"] / 2 + 0.3)
            & (world[:, 1] > -0.3) & (world[:, 1] < ROOM["height"] + 0.3)
        )
        assert keep[inside].mean() > 0.97                # the room stays
        assert keep[~inside].mean() < 0.1                # what is nowhere near it goes
        assert video.drop_strays(cloud[:5]).all()        # too few to judge: nothing is dropped

    def test_no_cameras_means_no_claim_about_up(self):
        cloud, _ = walkthrough(points=5000)
        _, _, upright, _, warnings = align_cloud(cloud, np.zeros((0, 3)), np.zeros((0, 3)))
        assert not upright and any("up axis" in w for w in warnings)

    def test_a_measured_ceiling_gives_the_room_its_real_size(self):
        ply, info = cloud_ply(synthetic_cloud(), Reference("ceiling_height", ROOM["height"]))
        assert info["assumed"] is False and info["basis"] == "ceiling height"
        found = room_of(ply)
        room = found.shell["room"]
        assert room["height"] == pytest.approx(ROOM["height"], abs=0.1)
        assert sorted([room["width"], room["depth"]]) == pytest.approx([ROOM["depth"], ROOM["width"]], abs=0.25)
        assert found.shell["scan"]["units"] == "m" and found.shell["scan"]["up_axis"] == "y"
        said = " ".join(found.assumptions)
        assert "the file says so" in said                                 # units and up axis are not re-guessed
        assert "Scale set from the measurement given: the ceiling is 5 m high." in said
        assert not any("ASSUMED" in w for w in found.warnings)
        # The stage is still where it was: nothing was mirrored on the way.
        assert any(riser["kind"] == "stage" for riser in found.shell["risers"])

    def test_a_measured_wall_gives_the_same_room(self):
        ply, info = cloud_ply(synthetic_cloud(), Reference("longest_wall", ROOM["width"]))
        assert info["basis"] == "longest wall"
        room = room_of(ply).shell["room"]
        assert room["height"] == pytest.approx(ROOM["height"], abs=0.15)
        assert max(room["width"], room["depth"]) == pytest.approx(ROOM["width"], abs=0.15)

    def test_with_no_measurement_the_scale_is_assumed_and_says_so(self):
        ply, info = cloud_ply(synthetic_cloud())
        assert info["assumed"] is True and info["basis"] == "assumed camera height"
        found = room_of(ply)
        assert found.warnings and "The scale is ASSUMED" in found.warnings[0]
        assert "ceiling height or the length of the longest wall" in found.warnings[0]
        # The phone really was 1.5 m up in the fake, so the guess lands close. It is still called a guess.
        assert found.shell["room"]["height"] == pytest.approx(ROOM["height"], abs=0.3)

    def test_with_no_cameras_the_ceiling_is_assumed_instead(self):
        cloud = synthetic_cloud()
        cloud.cameras = np.zeros((0, 3), dtype=np.float32)
        ply, info = cloud_ply(cloud)
        assert info["basis"] == "assumed ceiling height"
        found = room_of(ply)
        assert found.shell["room"]["height"] == pytest.approx(3.0, abs=0.1)
        assert "ASSUMED" in found.warnings[0]

    def test_the_same_cloud_and_measurement_give_the_same_file(self):
        cloud = synthetic_cloud()
        reference = Reference("ceiling_height", 4.2)
        assert cloud_ply(cloud, reference)[0] == cloud_ply(cloud, reference)[0]     # preview and apply agree

    @pytest.mark.parametrize("kind, metres", [("ceiling_height", 0.2), ("ceiling_height", 900.0),
                                              ("ceiling_height", None), ("door_width", 2.0)])
    def test_a_measurement_that_cannot_be_right_is_refused(self, kind, metres):
        with pytest.raises(RoomScanError):
            Reference(kind, metres)

    def test_another_ply_is_read_as_it_always_was(self):
        """Only this system's own header comments are taken up; `comment synthetic room` is not a note."""
        vertices, faces = room_mesh()
        mesh = read_scan_file("cloud.ply", write_ply(sample_surface(vertices, faces, 5000)))
        assert mesh.up_axis is None and mesh.metres_per_unit is None and mesh.warnings == []
        assert mesh.notes == ["The PLY has no faces: it was read as a point cloud."]


# ---------------------------------------------------------------------------
# The whole run, with a stand-in for the tools
# ---------------------------------------------------------------------------

@pytest.fixture
def no_probe(monkeypatch):
    monkeypatch.setattr(video, "probe_duration", lambda ffmpeg, path: 20.0)


class TestReconstruct:

    def test_video_to_an_upright_cloud_of_the_room(self, tmp_path, no_probe):
        tools = FakeTools()
        said = []
        cloud = reconstruct(tmp_path / "walk.mp4", tmp_path, READY, never(), runner=tools,
                            progress=lambda stage, detail: said.append(stage))
        assert tools.steps() == [
            "ffmpeg", "feature_extractor", "exhaustive_matcher", "mapper", "model_converter", "model_converter",
        ]
        assert said[0] == "frames" and said[-1] == "cloud"
        assert [s for i, s in enumerate(said) if i == 0 or s != said[i - 1]] == [
            "frames", "features", "matching", "mapping", "cloud",
        ]
        # The room, not the stray two-frame piece the mapper also wrote.
        assert cloud.images_registered == 30 and len(cloud.points) == 60_000
        assert cloud.kind == "sparse" and cloud.upright and cloud.frames.kept == 40
        assert "40 frames kept of 40 looked at" in cloud.notes[0] and "COLMAP placed 30" in cloud.notes[0]

        room = room_of(cloud_ply(cloud, Reference("ceiling_height", ROOM["height"]))[0]).shell["room"]
        assert room["height"] == pytest.approx(ROOM["height"], abs=0.1)
        assert sorted([room["width"], room["depth"]]) == pytest.approx([ROOM["depth"], ROOM["width"]], abs=0.25)

    def test_frames_are_handed_to_colmap_as_one_camera_in_name_order(self, tmp_path, no_probe):
        tools = FakeTools()
        reconstruct(tmp_path / "walk.mp4", tmp_path, READY, never(), runner=tools)
        extract = tools.calls[1]
        assert extract[extract.index("--ImageReader.single_camera") + 1] == "1"
        frames = Path(extract[extract.index("--image_path") + 1])
        assert sorted(p.name for p in frames.glob("*.jpg"))[:2] == ["frame_000001.jpg", "frame_000002.jpg"]

    def test_a_long_walk_is_matched_frame_to_neighbour(self, tmp_path, no_probe):
        tools = FakeTools(frames=130)
        reconstruct(tmp_path / "walk.mp4", tmp_path, READY, never(), runner=tools)
        assert "sequential_matcher" in tools.steps() and "exhaustive_matcher" not in tools.steps()

    def test_no_usable_graphics_card_falls_back_to_the_cpu(self, tmp_path, no_probe):
        tools = FakeTools(needs_cpu_flag=True)
        reconstruct(tmp_path / "walk.mp4", tmp_path, READY, never(), runner=tools)
        extract = [call for call in tools.calls if call[1] == "feature_extractor"]
        assert len(extract) == 2 and extract[1][-2:] == ["--SiftExtraction.use_gpu", "0"]

    def test_a_failed_step_says_which_and_what_to_do_instead(self, tmp_path, no_probe):
        with pytest.raises(VideoPipelineError) as failed:
            reconstruct(tmp_path / "walk.mp4", tmp_path, READY, never(), runner=FakeTools(fail_step="mapper"))
        message = str(failed.value)
        assert "COLMAP's mapper step failed (exit 1)" in message
        assert "something went wrong in the fake" in message                # the tool's own last words
        assert "Polycam or Scaniverse" in message

    def test_frames_that_cannot_be_joined_say_how_to_film_again(self, tmp_path, no_probe):
        with pytest.raises(VideoPipelineError) as failed:
            reconstruct(tmp_path / "walk.mp4", tmp_path, READY, never(), runner=FakeTools(no_model=True))
        assert "could not put the frames together" in str(failed.value)
        assert "more slowly" in str(failed.value)

    def test_too_few_points_is_not_called_a_room(self, tmp_path, no_probe):
        with pytest.raises(VideoPipelineError) as failed:
            reconstruct(tmp_path / "walk.mp4", tmp_path, READY, never(), runner=FakeTools(points=120))
        assert "only 120 points" in str(failed.value)

    def test_a_phone_left_on_a_table(self, tmp_path, no_probe):
        tools = FakeTools(still_video=True)
        with pytest.raises(VideoPipelineError) as failed:
            reconstruct(tmp_path / "walk.mp4", tmp_path, READY, never(), runner=tools)
        assert "Only 1 usable frames" in str(failed.value)
        assert tools.steps() == ["ffmpeg"]                                   # COLMAP was never started

    def test_dense_falls_back_to_sparse_and_says_so(self, tmp_path, no_probe):
        tools = FakeTools()
        cloud = reconstruct(tmp_path / "walk.mp4", tmp_path, READY, never(), runner=tools, quality="dense")
        assert "image_undistorter" in tools.steps()
        assert cloud.kind == "sparse"
        assert any("sparse cloud was used" in note for note in cloud.notes)

    def test_cancelled_before_it_starts(self, tmp_path, no_probe):
        cancel = threading.Event()
        cancel.set()
        with pytest.raises(VideoCancelled):
            reconstruct(tmp_path / "walk.mp4", tmp_path, READY, cancel, runner=FakeTools())

    def test_without_a_tool_nothing_is_run(self, tmp_path):
        tools = FakeTools()
        with pytest.raises(VideoPipelineError) as refused:
            reconstruct(tmp_path / "walk.mp4", tmp_path, VideoTools(ffmpeg="ffmpeg"), never(), runner=tools)
        assert "install COLMAP" in str(refused.value) and tools.calls == []


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

class TestJobs:

    def start(self, jobs, tmp_path, run, rig_id=1, name="work"):
        work = tmp_path / name
        work.mkdir()
        (work / "video.mp4").write_bytes(b"video")
        return jobs.start(rig_id, work / "video.mp4", work, "walk.mp4", READY, run=run)

    def test_a_job_runs_off_the_calling_thread_and_cleans_up(self, tmp_path):
        seen = {}

        def run(video_path, work, tools, cancel, quality, timeout_s, progress, runner):
            seen["thread"] = threading.current_thread().name
            seen["video_was_there"] = video_path.is_file()
            progress("mapping", "this is the slow step")
            return synthetic_cloud()

        jobs = VideoJobs()
        job = self.start(jobs, tmp_path, run)
        assert wait_for(job) == DONE
        job.thread.join(5)
        assert seen["thread"].startswith("room-video-") and seen["video_was_there"]
        assert not (tmp_path / "work").exists()                 # the video and frames are gone
        status = jobs.get(job.id).to_dict()
        assert status["state"] == "done" and status["progress"] == 1.0 and status["error"] is None
        assert status["cloud"]["points"] == 60_000 and status["tools"]["photogrammetry"]["tool"] == "colmap"

    def test_only_one_runs_at_a_time(self, tmp_path):
        release = threading.Event()

        def run(video_path, work, tools, cancel, **kwargs):
            release.wait(10)
            return synthetic_cloud()

        jobs = VideoJobs()
        first = self.start(jobs, tmp_path, run)
        with pytest.raises(JobBusy) as busy:
            self.start(jobs, tmp_path, run, name="second")
        assert busy.value.job is first and jobs.running() is first
        release.set()
        assert wait_for(first) == DONE and jobs.running() is None

    def test_a_job_can_be_stopped(self, tmp_path):
        def run(video_path, work, tools, cancel, progress, **kwargs):
            progress("mapping", "")
            while not cancel.wait(0.01):
                pass
            raise VideoCancelled()

        jobs = VideoJobs()
        job = self.start(jobs, tmp_path, run)
        jobs.cancel(job.id)
        assert wait_for(job) == CANCELLED
        status = job.to_dict()
        assert status["stage"] == "mapping" and status["cloud"] is None
        job.thread.join(5)
        assert not (tmp_path / "work").exists()

    def test_a_failure_keeps_the_operators_message(self, tmp_path):
        def run(*args, **kwargs):
            raise VideoPipelineError("COLMAP's mapper step failed (exit 1).")

        jobs = VideoJobs()
        job = self.start(jobs, tmp_path, run)
        assert wait_for(job) == FAILED and job.to_dict()["error"] == "COLMAP's mapper step failed (exit 1)."

    def test_a_crash_is_a_failed_job_not_a_dead_thread(self, tmp_path):
        def run(*args, **kwargs):
            raise ZeroDivisionError("oops")

        jobs = VideoJobs()
        job = self.start(jobs, tmp_path, run)
        assert wait_for(job) == FAILED and "could not be read" in job.error

    def test_old_results_are_forgotten(self, tmp_path):
        jobs = VideoJobs()
        made = []
        for n in range(6):
            job = self.start(jobs, tmp_path, lambda *a, **k: synthetic_cloud(), name=f"w{n}")
            assert wait_for(job) == DONE
            made.append(job.id)
        assert jobs.get(made[0]) is None and jobs.get(made[-1]) is not None

    def test_shutdown_stops_what_is_running(self, tmp_path):
        def run(video_path, work, tools, cancel, **kwargs):
            cancel.wait(30)
            raise VideoCancelled()

        jobs = VideoJobs()
        job = self.start(jobs, tmp_path, run)
        jobs.shutdown(wait_s=5)
        assert job.state == CANCELLED
