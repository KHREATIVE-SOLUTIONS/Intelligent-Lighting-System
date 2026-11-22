"""
Room from a walkthrough video, over HTTP
========================================

POST /api/rigs/{id}/room-scan/video starts a background job, GET polls it, and
its cloud.ply goes into the ordinary room scan preview and apply.
docs/ROOM_SCAN.md.

What has to hold: a machine with no photogrammetry tool gets an answer that
says what to install or do instead, not an error; starting a job does not wait
for it; the result previews and applies as any scan does, with the scale
called assumed unless a measurement was given; a job belongs to its rig; the
size limit acts; and nothing is written to a rig by any route here.

No tool is run: the reconstruction is replaced by one that hands back the
synthetic room, tipped over and unscaled, as COLMAP would
(tests/unit/room_video_fakes.py).
"""

import asyncio
import threading

import pytest
from httpx import AsyncClient

from app.api.endpoints import room_scan_video
from app.core.config import settings
from app.services.room_scan import video_jobs
from app.services.room_scan.video import VideoCancelled, VideoPipelineError, VideoTools
from tests.unit.room_scan_meshes import ROOM
from tests.unit.test_room_video import synthetic_cloud

VIDEO = b"\x00\x00\x00\x18ftypmp42" + b"walkthrough" * 2000
READY = VideoTools(ffmpeg="ffmpeg", colmap="colmap")


@pytest.fixture
def tools_ready(monkeypatch):
    monkeypatch.setattr(room_scan_video, "installed_tools", lambda: READY)


@pytest.fixture
def no_colmap(monkeypatch):
    monkeypatch.setattr(room_scan_video, "installed_tools", lambda: VideoTools(ffmpeg="ffmpeg"))


@pytest.fixture(autouse=True)
def clean_jobs():
    yield
    video_jobs.jobs.shutdown(wait_s=5)
    video_jobs.jobs._jobs.clear()


@pytest.fixture
def instant(monkeypatch):
    """A reconstruction that hands back the synthetic room at once."""
    seen = {}

    def run(video, work, tools, cancel, quality, timeout_s, progress, runner):
        seen["bytes"] = video.read_bytes()
        seen["name"] = video.name
        seen["quality"] = quality
        progress("mapping", "this is the slow step")
        return synthetic_cloud()

    monkeypatch.setattr(video_jobs, "reconstruct", run)
    return seen


@pytest.fixture
def held(monkeypatch):
    """A reconstruction that runs until it is released or stopped."""
    release = threading.Event()

    def run(video, work, tools, cancel, quality, timeout_s, progress, runner):
        progress("features", "40 frames")
        while not release.wait(0.01):
            if cancel.is_set():
                raise VideoCancelled()
        return synthetic_cloud()

    monkeypatch.setattr(video_jobs, "reconstruct", run)
    yield release
    release.set()


async def new_rig(client: AsyncClient, sample_rig_data) -> int:
    rig = await client.post("/api/rigs/", json=sample_rig_data)
    assert rig.status_code == 201, rig.text
    return rig.json()["id"]


async def start(client: AsyncClient, rig_id: int, content: bytes = VIDEO, name: str = "walk.mp4", **params):
    return await client.post(
        f"/api/rigs/{rig_id}/room-scan/video", content=content, params={"filename": name, **params},
        headers={"Content-Type": "video/mp4"},
    )


async def finished(client: AsyncClient, rig_id: int, job_id: str, want=("done", "failed", "cancelled")) -> dict:
    for _ in range(400):
        status = await client.get(f"/api/rigs/{rig_id}/room-scan/video/{job_id}")
        assert status.status_code == 200, status.text
        if status.json()["state"] in want:
            return status.json()
        await asyncio.sleep(0.02)
    raise AssertionError(f"the job never reached {want}: {status.json()}")


class TestRoomVideoTools:

    @pytest.mark.asyncio
    async def test_with_no_photogrammetry_tool_the_answer_says_what_to_do(self, client: AsyncClient, no_colmap):
        answer = await client.get("/api/room-scan/video/tools")
        assert answer.status_code == 200, answer.text
        tools = answer.json()
        assert tools["ready"] is False
        assert tools["photogrammetry"]["tool"] is None and tools["frames"]["tool"] == "ffmpeg"
        assert "COLMAP" in tools["message"] and "Polycam or Scaniverse" in tools["message"]
        assert tools["max_upload_mb"] == settings.ROOM_VIDEO_MAX_MB
        assert ".mp4" in tools["video_types"] and tools["reference_kinds"] == ["ceiling_height", "longest_wall"]

    @pytest.mark.asyncio
    async def test_with_the_tools_there_is_nothing_to_say(self, client: AsyncClient, tools_ready):
        tools = (await client.get("/api/room-scan/video/tools")).json()
        assert tools["ready"] is True and tools["message"] is None
        assert tools["photogrammetry"] == {"tool": "colmap", "path": "colmap"}

    @pytest.mark.asyncio
    async def test_a_video_sent_anyway_is_answered_not_failed(
        self, client: AsyncClient, sample_rig_data, no_colmap, instant,
    ):
        rig_id = await new_rig(client, sample_rig_data)
        answer = await start(client, rig_id)
        assert answer.status_code == 200, answer.text
        body = answer.json()
        assert body["state"] == "unavailable" and body["job_id"] is None
        assert "install COLMAP" in body["error"] and "Polycam or Scaniverse" in body["error"]
        assert instant == {} and video_jobs.jobs.running() is None       # nothing was started


class TestRoomVideoJob:

    @pytest.mark.asyncio
    async def test_starting_does_not_wait_for_the_reconstruction(
        self, client: AsyncClient, sample_rig_data, tools_ready, held,
    ):
        rig_id = await new_rig(client, sample_rig_data)
        answer = await start(client, rig_id)
        assert answer.status_code == 202, answer.text        # answered while the work is still held
        job = answer.json()
        assert job["state"] in ("queued", "running") and job["rig_id"] == rig_id and job["file"] == "walk.mp4"

        status = await finished(client, rig_id, job["job_id"], want=("running",))
        assert status["stage"] == "features" and status["detail"] == "40 frames"
        assert status["stage_label"].startswith("COLMAP") and 0 < status["progress"] < 1
        assert status["tools"]["frames"]["tool"] == "ffmpeg" and status["cloud"] is None

        held.set()
        status = await finished(client, rig_id, job["job_id"])
        assert status["state"] == "done" and status["progress"] == 1.0
        assert status["cloud"]["points"] == 60_000 and status["cloud"]["upright"] is True

    @pytest.mark.asyncio
    async def test_the_video_reaches_the_job_under_a_name_of_the_servers_own(
        self, client: AsyncClient, sample_rig_data, tools_ready, instant,
    ):
        rig_id = await new_rig(client, sample_rig_data)
        job = (await start(client, rig_id, name="../../evil walk.MOV", quality="dense")).json()
        await finished(client, rig_id, job["job_id"])
        assert instant["bytes"] == VIDEO and instant["name"] == "video.mov" and instant["quality"] == "dense"
        assert job["file"] == "evil walk.MOV"

    @pytest.mark.asyncio
    async def test_the_result_previews_and_applies_as_any_scan_does(
        self, client: AsyncClient, sample_rig_data, tools_ready, instant,
    ):
        rig_id = await new_rig(client, sample_rig_data)
        job = (await start(client, rig_id)).json()
        await finished(client, rig_id, job["job_id"])

        cloud = await client.get(
            f"/api/rigs/{rig_id}/room-scan/video/{job['job_id']}/cloud.ply", params={"ceiling_height": 5.0},
        )
        assert cloud.status_code == 200, cloud.text
        assert cloud.headers["x-room-scale-assumed"] == "false"
        assert cloud.content.startswith(b"ply\n")

        # Nothing so far has touched the rig.
        assert (await client.get(f"/api/rigs/{rig_id}")).json()["room_shell"] is None

        files = {"file": ("walkthrough.ply", cloud.content, "application/octet-stream")}
        preview = await client.post(f"/api/rigs/{rig_id}/room-scan", files=files)
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["applied"] is None and body["format"] == "ply"
        assert body["summary"]["height"] == pytest.approx(ROOM["height"], abs=0.1)
        assert sorted([body["summary"]["width"], body["summary"]["depth"]]) == pytest.approx(
            [ROOM["depth"], ROOM["width"]], abs=0.25)
        assert body["summary"]["units"] == "m" and body["summary"]["up_axis"] == "y"
        assert any("Scale set from the measurement given" in line for line in body["assumptions"])
        assert any("how the phone was held" in line for line in body["assumptions"])
        assert not any("ASSUMED" in line for line in body["warnings"])

        applied = await client.post(f"/api/rigs/{rig_id}/room-scan", files=files, params={"apply": True})
        assert applied.status_code == 200, applied.text
        shell = (await client.get(f"/api/rigs/{rig_id}")).json()["room_shell"]
        assert shell["source"] == "scan" and shell["room"]["height"] == body["summary"]["height"]

    @pytest.mark.asyncio
    async def test_with_no_measurement_the_preview_warns_that_the_scale_is_assumed(
        self, client: AsyncClient, sample_rig_data, tools_ready, instant,
    ):
        rig_id = await new_rig(client, sample_rig_data)
        job = (await start(client, rig_id)).json()
        await finished(client, rig_id, job["job_id"])
        cloud = await client.get(f"/api/rigs/{rig_id}/room-scan/video/{job['job_id']}/cloud.ply")
        assert cloud.status_code == 200 and cloud.headers["x-room-scale-assumed"] == "true"
        preview = await client.post(
            f"/api/rigs/{rig_id}/room-scan", files={"file": ("walkthrough.ply", cloud.content, "application/octet-stream")},
        )
        assert preview.status_code == 200, preview.text
        assert "The scale is ASSUMED" in preview.json()["warnings"][0]

        # A different measurement is a new file from the same job: no second reconstruction.
        wall = await client.get(
            f"/api/rigs/{rig_id}/room-scan/video/{job['job_id']}/cloud.ply", params={"longest_wall": 24.0},
        )
        twice = await client.post(
            f"/api/rigs/{rig_id}/room-scan", files={"file": ("walkthrough.ply", wall.content, "application/octet-stream")},
        )
        assert max(twice.json()["summary"]["width"], twice.json()["summary"]["depth"]) == pytest.approx(24.0, abs=0.3)

    @pytest.mark.asyncio
    async def test_a_failed_job_carries_the_operators_message(
        self, client: AsyncClient, sample_rig_data, tools_ready, monkeypatch,
    ):
        def run(*args, **kwargs):
            raise VideoPipelineError("COLMAP could not put the frames together into a room. Film again more slowly.")

        monkeypatch.setattr(video_jobs, "reconstruct", run)
        rig_id = await new_rig(client, sample_rig_data)
        job = (await start(client, rig_id)).json()
        status = await finished(client, rig_id, job["job_id"])
        assert status["state"] == "failed" and "Film again more slowly" in status["error"]
        cloud = await client.get(f"/api/rigs/{rig_id}/room-scan/video/{job['job_id']}/cloud.ply")
        assert cloud.status_code == 409 and "failed" in cloud.json()["detail"]

    @pytest.mark.asyncio
    async def test_a_running_job_can_be_stopped_and_frees_the_slot(
        self, client: AsyncClient, sample_rig_data, tools_ready, held,
    ):
        rig_id = await new_rig(client, sample_rig_data)
        job = (await start(client, rig_id)).json()

        second = await start(client, rig_id)
        assert second.status_code == 409 and "already being processed" in second.json()["detail"]
        early = await client.get(f"/api/rigs/{rig_id}/room-scan/video/{job['job_id']}/cloud.ply")
        assert early.status_code == 409

        stopped = await client.delete(f"/api/rigs/{rig_id}/room-scan/video/{job['job_id']}")
        assert stopped.status_code == 200 and stopped.json()["stopping"] is True
        status = await finished(client, rig_id, job["job_id"])
        assert status["state"] == "cancelled"

        # Stopped, it can be forgotten, and another may start.
        assert (await client.delete(f"/api/rigs/{rig_id}/room-scan/video/{job['job_id']}")).json()["stopping"] is False
        assert (await client.get(f"/api/rigs/{rig_id}/room-scan/video/{job['job_id']}")).status_code == 404
        assert (await start(client, rig_id)).status_code == 202


class TestRoomVideoRefusals:

    @pytest.mark.asyncio
    async def test_a_job_belongs_to_its_rig(self, client: AsyncClient, sample_rig_data, tools_ready, instant):
        rig_id = await new_rig(client, sample_rig_data)
        other = await new_rig(client, {**sample_rig_data, "name": "Another Rig"})
        job = (await start(client, rig_id)).json()
        await finished(client, rig_id, job["job_id"])
        for request in (
            client.get(f"/api/rigs/{other}/room-scan/video/{job['job_id']}"),
            client.get(f"/api/rigs/{other}/room-scan/video/{job['job_id']}/cloud.ply"),
            client.delete(f"/api/rigs/{other}/room-scan/video/{job['job_id']}"),
        ):
            assert (await request).status_code == 404
        assert (await client.get(f"/api/rigs/{rig_id}/room-scan/video/{job['job_id']}")).status_code == 200

    @pytest.mark.asyncio
    async def test_no_such_rig_or_job(self, client: AsyncClient, sample_rig_data, tools_ready, instant):
        assert (await start(client, 999_999)).status_code == 404
        rig_id = await new_rig(client, sample_rig_data)
        missing = await client.get(f"/api/rigs/{rig_id}/room-scan/video/nope")
        assert missing.status_code == 404 and "send the video again" in missing.json()["detail"]

    @pytest.mark.asyncio
    async def test_a_file_that_is_not_a_video_by_name_or_is_empty(
        self, client: AsyncClient, sample_rig_data, tools_ready, instant,
    ):
        rig_id = await new_rig(client, sample_rig_data)
        wrong = await start(client, rig_id, name="room.obj")
        assert wrong.status_code == 400 and ".mp4" in wrong.json()["detail"]
        empty = await start(client, rig_id, content=b"")
        assert empty.status_code == 400 and "empty" in empty.json()["detail"]
        assert (await client.post(f"/api/rigs/{rig_id}/room-scan/video", content=VIDEO)).status_code == 422
        assert (await start(client, rig_id, quality="ultra")).status_code == 422
        assert instant == {}

    @pytest.mark.asyncio
    async def test_a_video_over_the_limit_is_refused_and_nothing_starts(
        self, client: AsyncClient, sample_rig_data, tools_ready, instant, monkeypatch,
    ):
        monkeypatch.setattr(settings, "ROOM_VIDEO_MAX_MB", 1)
        rig_id = await new_rig(client, sample_rig_data)
        big = await start(client, rig_id, content=b"x" * (1024 * 1024 + 1))
        assert big.status_code == 413
        assert "larger than 1 MB" in big.json()["detail"] and "1080p" in big.json()["detail"]

        # The same when the size is not declared up front: the limit acts as the bytes arrive.
        async def chunks():
            for _ in range(5):
                yield b"x" * (300 * 1024)

        streamed = await client.post(
            f"/api/rigs/{rig_id}/room-scan/video", content=chunks(), params={"filename": "walk.mp4"},
        )
        assert streamed.status_code == 413
        assert instant == {} and video_jobs.jobs.running() is None
        assert (await start(client, rig_id, content=b"x" * (1024 * 1024))).status_code == 202

    @pytest.mark.asyncio
    async def test_measurements_that_cannot_be_used(self, client: AsyncClient, sample_rig_data, tools_ready, instant):
        rig_id = await new_rig(client, sample_rig_data)
        job = (await start(client, rig_id)).json()
        await finished(client, rig_id, job["job_id"])
        url = f"/api/rigs/{rig_id}/room-scan/video/{job['job_id']}/cloud.ply"
        both = await client.get(url, params={"ceiling_height": 5, "longest_wall": 12})
        assert both.status_code == 400 and "one measurement" in both.json()["detail"]
        tiny = await client.get(url, params={"ceiling_height": 0.1})
        assert tiny.status_code == 400 and "between 1 and 200 metres" in tiny.json()["detail"]
        assert (await client.get(url, params={"ceiling_height": "tall"})).status_code == 422

    @pytest.mark.asyncio
    async def test_the_routes_are_behind_the_login(self, unauthenticated_client: AsyncClient):
        assert (await unauthenticated_client.get("/api/room-scan/video/tools")).status_code == 401
        sent = await unauthenticated_client.post(
            "/api/rigs/1/room-scan/video", content=VIDEO, params={"filename": "walk.mp4"},
        )
        assert sent.status_code == 401
        assert (await unauthenticated_client.get("/api/rigs/1/room-scan/video/abc")).status_code == 401
        assert (await unauthenticated_client.get("/api/rigs/1/room-scan/video/abc/cloud.ply")).status_code == 401
        assert (await unauthenticated_client.delete("/api/rigs/1/room-scan/video/abc")).status_code == 401
