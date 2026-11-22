"""
Walkthrough video jobs
======================

A reconstruction takes minutes, so it runs on a thread of its own and the API
only starts it and asks how it is doing. One runs at a time: COLMAP takes
every core it is given, and this machine may be running a show.

    job = jobs.start(rig_id, video_path, work_dir, filename, tools)
    jobs.get(job.id).to_dict()            # polled
    jobs.cancel(job.id)

A job's working folder (the video, its frames, COLMAP's database) is deleted
when the job ends, however it ends. What is kept is the finished cloud, in
memory, for a couple of hours: a few megabytes. Nothing survives a restart.
"""

import logging
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .mesh import RoomScanError
from .video import (
    STAGE_LABEL, STAGE_START, VideoCancelled, VideoCloud, VideoTools, reconstruct, run_tool,
)

logger = logging.getLogger(__name__)

KEEP_FINISHED = 4
KEEP_SECONDS = 2 * 3600.0

QUEUED, RUNNING, DONE, FAILED, CANCELLED = "queued", "running", "done", "failed", "cancelled"
ENDED = (DONE, FAILED, CANCELLED)


class JobBusy(Exception):
    """Another reconstruction is already running."""

    def __init__(self, job: "VideoJob"):
        super().__init__("A walkthrough video is already being processed.")
        self.job = job


@dataclass
class VideoJob:
    id: str
    rig_id: int
    filename: str
    work: Path
    tools: VideoTools
    quality: str = "sparse"
    state: str = QUEUED
    stage: str = ""
    detail: str = ""
    error: Optional[str] = None
    cloud: Optional[VideoCloud] = None
    started: float = field(default_factory=time.monotonic)
    ended: Optional[float] = None
    cancel: threading.Event = field(default_factory=threading.Event)
    thread: Optional[threading.Thread] = None

    def to_dict(self) -> Dict[str, Any]:
        cloud = self.cloud
        # A stage's start, not a fraction of it: COLMAP does not say how far through a step it is.
        progress = 1.0 if self.state == DONE else STAGE_START.get(self.stage, 0.0)
        notes: List[str] = list(cloud.notes) if cloud else []
        warnings: List[str] = list(cloud.warnings) if cloud else []
        return {
            "job_id": self.id,
            "rig_id": self.rig_id,
            "file": self.filename,
            "state": self.state,
            "stage": self.stage,
            "stage_label": STAGE_LABEL.get(self.stage, "Waiting to start" if self.state == QUEUED else ""),
            "detail": self.detail,
            "progress": round(progress, 2),
            "elapsed_s": round((self.ended or time.monotonic()) - self.started, 1),
            "quality": self.quality,
            "error": self.error,
            "tools": self.tools.to_dict(),
            "frames": cloud.frames.to_dict() if cloud else None,
            "cloud": cloud.summary() if cloud else None,
            "notes": notes,
            "warnings": warnings,
        }


class VideoJobs:
    """The jobs this process knows about. Safe to call from the event loop: nothing here waits."""

    def __init__(self) -> None:
        self._jobs: Dict[str, VideoJob] = {}
        self._lock = threading.Lock()

    def running(self) -> Optional[VideoJob]:
        with self._lock:
            return next((job for job in self._jobs.values() if job.state not in ENDED), None)

    def get(self, job_id: str) -> Optional[VideoJob]:
        with self._lock:
            self._forget_old()
            return self._jobs.get(job_id)

    def start(
        self, rig_id: int, video: Path, work: Path, filename: str, tools: VideoTools,
        quality: str = "sparse", timeout_s: float = 3600.0,
        run: Optional[Callable[..., VideoCloud]] = None, runner: Callable[..., int] = run_tool,
    ) -> VideoJob:
        """Start reading a video on a thread of its own. Raises JobBusy when one is already running."""
        job = VideoJob(id=uuid.uuid4().hex[:16], rig_id=rig_id, filename=filename, work=work, tools=tools,
                       quality=quality)
        with self._lock:
            busy = next((j for j in self._jobs.values() if j.state not in ENDED), None)
            if busy is not None:
                raise JobBusy(busy)
            self._forget_old()
            self._jobs[job.id] = job
        job.thread = threading.Thread(
            target=self._work, args=(job, video, timeout_s, run or reconstruct, runner),
            name=f"room-video-{job.id}", daemon=True,
        )
        job.thread.start()
        return job

    def _work(self, job: VideoJob, video: Path, timeout_s: float, run: Callable[..., VideoCloud], runner) -> None:
        def progress(stage: str, detail: str) -> None:
            job.stage, job.detail = stage, detail

        job.state = RUNNING
        try:
            cloud = run(
                video, job.work, job.tools, job.cancel,
                quality=job.quality, timeout_s=timeout_s, progress=progress, runner=runner,
            )
            if job.cancel.is_set():
                raise VideoCancelled()
            job.cloud, job.detail, job.state = cloud, "", DONE
            logger.info("Room video %s for rig %s: %s", job.id, job.rig_id, cloud.summary())
        except VideoCancelled:
            job.state, job.error = CANCELLED, "Stopped."
        except RoomScanError as e:
            job.state, job.error = FAILED, str(e)
            logger.info("Room video %s for rig %s failed: %s", job.id, job.rig_id, e)
        except Exception as e:  # a thread must not die without saying so
            job.state, job.error = FAILED, f"The video could not be read: {e}"
            logger.exception("Room video %s for rig %s crashed", job.id, job.rig_id)
        finally:
            job.ended = time.monotonic()
            shutil.rmtree(job.work, ignore_errors=True)

    def cancel(self, job_id: str) -> Optional[VideoJob]:
        """Ask a job to stop. Its tool is killed within a moment; the job says `cancelled` once it has."""
        job = self.get(job_id)
        if job is not None and job.state not in ENDED:
            job.cancel.set()
        return job

    def forget(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None and job.state in ENDED:
                del self._jobs[job_id]

    def _forget_old(self) -> None:
        now = time.monotonic()
        ended = sorted((j for j in self._jobs.values() if j.state in ENDED), key=lambda j: j.ended or 0.0)
        for index, job in enumerate(ended):
            too_many = len(ended) - index > KEEP_FINISHED
            if too_many or now - (job.ended or now) > KEEP_SECONDS:
                del self._jobs[job.id]

    def shutdown(self, wait_s: float = 5.0) -> None:
        """Stop everything: the backend is going down."""
        with self._lock:
            live = [job for job in self._jobs.values() if job.state not in ENDED]
        for job in live:
            job.cancel.set()
        for job in live:
            if job.thread is not None:
                job.thread.join(timeout=wait_s)


jobs = VideoJobs()
