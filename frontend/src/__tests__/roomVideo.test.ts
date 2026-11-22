import { describe, expect, it } from 'vitest';
import {
  NO_REFERENCE,
  ROOM_VIDEO_ACCEPT,
  cloudFileName,
  elapsedText,
  isVideoFile,
  jobEnded,
  jobStatusText,
  referenceMetres,
  referenceParams,
  referenceProblem,
  roomVideoCloudPath,
  roomVideoJobPath,
  roomVideoPath,
  roomVideoToolsPath,
  scaleIsAssumed,
  toolsText,
  videoProblem,
} from '../utils/roomVideo';
import type { RoomVideoJob, RoomVideoTools } from '../utils/roomVideo';

// What backend/app/api/endpoints/room_scan_video.py answers.
const READY: RoomVideoTools = {
  ready: true,
  frames: { tool: 'ffmpeg', path: 'C:/tools/ffmpeg.exe' },
  photogrammetry: { tool: 'colmap', path: 'C:/COLMAP/COLMAP.bat' },
  dense: { tool: null, path: null },
  message: null,
  max_upload_mb: 500,
};

const NO_COLMAP: RoomVideoTools = {
  ready: false,
  frames: { tool: 'ffmpeg', path: 'C:/tools/ffmpeg.exe' },
  photogrammetry: { tool: null, path: null },
  dense: { tool: null, path: null },
  message: 'No photogrammetry tool is installed on this machine. Install COLMAP, or export OBJ or PLY from Polycam.',
};

const job = (over: Partial<RoomVideoJob>): RoomVideoJob => ({
  job_id: 'abc123', rig_id: 4, state: 'running', ...over,
});

describe('walkthrough video: paths and files', () => {
  it('addresses the job under its rig', () => {
    expect(roomVideoToolsPath).toBe('/room-scan/video/tools');
    expect(roomVideoPath(4)).toBe('/rigs/4/room-scan/video');
    expect(roomVideoJobPath(4, 'abc123')).toBe('/rigs/4/room-scan/video/abc123');
    expect(roomVideoCloudPath(4, 'abc123')).toBe('/rigs/4/room-scan/video/abc123/cloud.ply');
    expect(roomVideoJobPath(4, 'a/b')).toBe('/rigs/4/room-scan/video/a%2Fb');
  });

  it('names the finished cloud as a PLY, which is what the scan reader is sent', () => {
    expect(cloudFileName('abc123')).toBe('walkthrough-abc123.ply');
  });

  it('knows a video by its ending, whatever its case', () => {
    expect(isVideoFile('club walk.MOV')).toBe(true);
    expect(isVideoFile('walk.mp4')).toBe(true);
    expect(isVideoFile('room.obj')).toBe(false);
    expect(ROOM_VIDEO_ACCEPT).toContain('.mp4');
  });

  it('refuses what the server would refuse, before sending it', () => {
    expect(videoProblem({ name: 'walk.mp4', size: 80 * 1024 * 1024 })).toBeNull();
    expect(videoProblem({ name: 'room.obj', size: 10 })).toContain('not a video');
    expect(videoProblem({ name: 'walk.mp4', size: 0 })).toBe('walk.mp4 is empty.');
    const big = videoProblem({ name: 'walk.mp4', size: 700 * 1024 * 1024 });
    expect(big).toContain('700 MB');
    expect(big).toContain('The limit is 500 MB');
    expect(big).toContain('1080p');
    // The server's own limit is used once it has said what it is.
    expect(videoProblem({ name: 'walk.mp4', size: 700 * 1024 * 1024 }, 1024)).toBeNull();
  });
});

describe('walkthrough video: the one measurement', () => {
  it('sends nothing when nothing was measured, and says the scale is then assumed', () => {
    expect(referenceParams(NO_REFERENCE)).toEqual({});
    expect(scaleIsAssumed(NO_REFERENCE)).toBe(true);
    expect(referenceParams({ kind: 'ceiling_height', metres: '' })).toEqual({});
    expect(scaleIsAssumed({ kind: 'ceiling_height', metres: '' })).toBe(true);
    expect(referenceProblem({ kind: 'ceiling_height', metres: '' })).toBeNull();
  });

  it('sends the measurement under the name the server reads', () => {
    expect(referenceParams({ kind: 'ceiling_height', metres: '4.2' })).toEqual({ ceiling_height: 4.2 });
    expect(referenceParams({ kind: 'longest_wall', metres: ' 18 ' })).toEqual({ longest_wall: 18 });
    expect(scaleIsAssumed({ kind: 'longest_wall', metres: '18' })).toBe(false);
  });

  it('reads a decimal comma', () => {
    expect(referenceMetres({ kind: 'ceiling_height', metres: '4,2' })).toBe(4.2);
  });

  it('does not send a measurement that cannot be right', () => {
    for (const metres of ['0.3', '900', 'tall', '-4', '4m', '1e2']) {
      const reference = { kind: 'ceiling_height' as const, metres };
      expect(referenceMetres(reference)).toBeNull();
      expect(referenceParams(reference)).toEqual({});
      expect(referenceProblem(reference)).toContain('between 1 and 200');
    }
  });
});

describe('walkthrough video: what the operator is told', () => {
  it('names the tools doing the work', () => {
    expect(toolsText(READY)).toBe('Frames: ffmpeg. Reconstruction: COLMAP. All free, all on this machine.');
    expect(toolsText({ ...READY, frames: { tool: 'opencv', path: null } })).toContain('Frames: OpenCV.');
    expect(toolsText({ ...READY, dense: { tool: 'openmvs', path: 'C:/OpenMVS' } })).toContain('Dense: OpenMVS');
    expect(toolsText(NO_COLMAP)).toContain('Reconstruction: none found.');
    expect(toolsText(null)).toBe('');
  });

  it('says how long a job has run', () => {
    expect(elapsedText(0)).toBe('0 s');
    expect(elapsedText(59.4)).toBe('59 s');
    expect(elapsedText(125)).toBe('2 min 05 s');
    expect(elapsedText(undefined)).toBe('0 s');
  });

  it('knows when a job is over', () => {
    expect(jobEnded(job({ state: 'queued' }))).toBe(false);
    expect(jobEnded(job({ state: 'running' }))).toBe(false);
    for (const state of ['done', 'failed', 'cancelled', 'unavailable'] as const) {
      expect(jobEnded(job({ state }))).toBe(true);
    }
  });

  it('describes a running job by its stage', () => {
    const text = jobStatusText(job({
      stage: 'mapping',
      stage_label: 'COLMAP: working out where the camera went and building the cloud',
      detail: 'this is the slow step',
      elapsed_s: 185,
    }));
    expect(text).toBe(
      'COLMAP: working out where the camera went and building the cloud (this is the slow step). '
      + '3 min 05 s so far; a room takes several minutes.',
    );
    expect(jobStatusText(job({ state: 'queued' }))).toBe('Waiting to start.');
  });

  it('describes a finished job by what it made', () => {
    const text = jobStatusText(job({
      state: 'done',
      elapsed_s: 412,
      cloud: { points: 48210, kind: 'sparse', upright: true, images_registered: 118, images_total: 140 },
    }));
    expect(text).toBe('Finished in 6 min 52 s: 48,210 points (sparse) from 118 of 140 frames.');
  });

  it("uses the server's own words for a failure and for a missing tool", () => {
    expect(jobStatusText(job({ state: 'failed', error: 'COLMAP could not put the frames together into a room.' })))
      .toBe('COLMAP could not put the frames together into a room.');
    expect(jobStatusText(job({ state: 'failed' }))).toBe('The video could not be turned into a room.');
    expect(jobStatusText({ job_id: null, rig_id: 4, state: 'unavailable', error: NO_COLMAP.message }))
      .toContain('Install COLMAP');
    expect(jobStatusText(job({ state: 'cancelled' }))).toBe('Stopped. Nothing was stored.');
  });
});
