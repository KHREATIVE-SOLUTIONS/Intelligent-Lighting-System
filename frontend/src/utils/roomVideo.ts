// Room from a walkthrough video: what the server answers and how the dialog
// words it. Pure, so it can be tested without a server. The pipeline itself is
// backend/app/services/room_scan/video.py; docs/ROOM_SCAN.md describes it.

/** The video endings the server takes (video.VIDEO_SUFFIXES). */
export const ROOM_VIDEO_SUFFIXES = ['.mp4', '.mov', '.m4v', '.avi', '.mkv', '.webm', '.3gp'];

export const ROOM_VIDEO_ACCEPT = `${ROOM_VIDEO_SUFFIXES.join(',')},video/*`;

/** The server's default limit (settings.ROOM_VIDEO_MAX_MB). Its own answer is used once it has been asked. */
export const ROOM_VIDEO_DEFAULT_MAX_MB = 500;

/** How often a running job is asked how it is doing. */
export const ROOM_VIDEO_POLL_MS = 1500;

export type RoomVideoState = 'queued' | 'running' | 'done' | 'failed' | 'cancelled' | 'unavailable';
export type RoomVideoQuality = 'sparse' | 'dense';

/** GET /api/room-scan/video/tools, and the `tools` of every job. */
export interface RoomVideoTools {
  ready: boolean;
  frames: { tool: 'ffmpeg' | 'opencv' | null; path: string | null };
  photogrammetry: { tool: 'colmap' | null; path: string | null };
  dense: { tool: 'openmvs' | null; path: string | null };
  /** What to install, or what to do instead. Null when a video can be read here. */
  message: string | null;
  max_upload_mb?: number;
  video_types?: string[];
}

/** The answer to starting a job and to each poll. */
export interface RoomVideoJob {
  /** Null only for 'unavailable': no job was started. */
  job_id: string | null;
  rig_id: number;
  state: RoomVideoState;
  file?: string;
  stage?: string;
  stage_label?: string;
  detail?: string;
  /** 0 to 1. The start of the current stage: the tools do not say how far through a step they are. */
  progress?: number;
  elapsed_s?: number;
  quality?: RoomVideoQuality;
  error?: string | null;
  tools?: RoomVideoTools;
  frames?: null | {
    tool: string;
    duration_s: number | null;
    candidates: number;
    kept: number;
    blurry: number;
    duplicates: number;
  };
  cloud?: null | {
    points: number;
    kind: 'sparse' | 'dense';
    upright: boolean;
    images_registered: number;
    images_total: number;
  };
  notes?: string[];
  warnings?: string[];
}

export type ReferenceKind = 'none' | 'ceiling_height' | 'longest_wall';

/** The one thing the operator measured, as typed. */
export interface RoomVideoReference {
  kind: ReferenceKind;
  metres: string;
}

export const NO_REFERENCE: RoomVideoReference = { kind: 'none', metres: '' };

/** The server's own bounds (video.REFERENCE_MIN, REFERENCE_MAX). */
export const REFERENCE_MIN_M = 1;
export const REFERENCE_MAX_M = 200;

export const roomVideoToolsPath = '/room-scan/video/tools';

export function roomVideoPath(rigId: number): string {
  return `/rigs/${rigId}/room-scan/video`;
}

export function roomVideoJobPath(rigId: number, jobId: string): string {
  return `${roomVideoPath(rigId)}/${encodeURIComponent(jobId)}`;
}

export function roomVideoCloudPath(rigId: number, jobId: string): string {
  return `${roomVideoJobPath(rigId, jobId)}/cloud.ply`;
}

/** The name the finished cloud is previewed and applied under. */
export function cloudFileName(jobId: string): string {
  return `walkthrough-${jobId}.ply`;
}

export function isVideoFile(name: string): boolean {
  const lower = name.toLowerCase();
  return ROOM_VIDEO_SUFFIXES.some((suffix) => lower.endsWith(suffix));
}

/** Why a video cannot be sent at all, or null when it can. */
export function videoProblem(file: { name: string; size: number }, maxMb = ROOM_VIDEO_DEFAULT_MAX_MB): string | null {
  if (!isVideoFile(file.name)) {
    return `${file.name} is not a video this reads. Choose ${ROOM_VIDEO_SUFFIXES.join(', ')}.`;
  }
  if (file.size === 0) return `${file.name} is empty.`;
  if (file.size > maxMb * 1024 * 1024) {
    return `${file.name} is ${(file.size / (1024 * 1024)).toFixed(0)} MB. The limit is ${maxMb} MB: `
      + 'film at 1080p rather than 4K, or trim it. One to two minutes round the room is enough.';
  }
  return null;
}

/** The measurement as a number, or null when nothing usable is typed. */
export function referenceMetres(reference: RoomVideoReference): number | null {
  if (reference.kind === 'none') return null;
  const text = reference.metres.trim().replace(',', '.');
  if (!/^\d+(\.\d+)?$/.test(text)) return null;
  const value = Number(text);
  return value >= REFERENCE_MIN_M && value <= REFERENCE_MAX_M ? value : null;
}

/** What is wrong with the measurement as typed, or null. Nothing typed yet is not a problem. */
export function referenceProblem(reference: RoomVideoReference): string | null {
  if (reference.kind === 'none' || reference.metres.trim() === '') return null;
  return referenceMetres(reference) === null
    ? `Give the measurement in metres, between ${REFERENCE_MIN_M} and ${REFERENCE_MAX_M}.`
    : null;
}

/**
 * Query parameters for the cloud. With no usable measurement none is sent, and
 * the server assumes a scale and says so in the preview's warnings.
 */
export function referenceParams(reference: RoomVideoReference): Record<string, number> {
  const metres = referenceMetres(reference);
  if (metres === null) return {};
  return reference.kind === 'ceiling_height' ? { ceiling_height: metres } : { longest_wall: metres };
}

/** Whether the scale will be the server's assumption rather than a measurement. */
export function scaleIsAssumed(reference: RoomVideoReference): boolean {
  return referenceMetres(reference) === null;
}

export function jobEnded(job: Pick<RoomVideoJob, 'state'>): boolean {
  return job.state === 'done' || job.state === 'failed' || job.state === 'cancelled' || job.state === 'unavailable';
}

/** "2 min 05 s". */
export function elapsedText(seconds: number | undefined): string {
  const total = Math.max(0, Math.round(seconds ?? 0));
  if (total < 60) return `${total} s`;
  return `${Math.floor(total / 60)} min ${String(total % 60).padStart(2, '0')} s`;
}

/** Which tools are doing the work: "Frames: ffmpeg. Reconstruction: COLMAP." */
export function toolsText(tools: RoomVideoTools | undefined | null): string {
  if (!tools) return '';
  const frames = tools.frames.tool === 'opencv' ? 'OpenCV' : tools.frames.tool === 'ffmpeg' ? 'ffmpeg' : 'none found';
  const reconstruction = tools.photogrammetry.tool === 'colmap' ? 'COLMAP' : 'none found';
  const dense = tools.dense.tool === 'openmvs' ? ' Dense: OpenMVS where COLMAP cannot.' : '';
  return `Frames: ${frames}. Reconstruction: ${reconstruction}.${dense} All free, all on this machine.`;
}

/** One line on where a job stands. */
export function jobStatusText(job: RoomVideoJob): string {
  const took = elapsedText(job.elapsed_s);
  switch (job.state) {
    case 'queued':
      return 'Waiting to start.';
    case 'running': {
      const detail = job.detail ? ` (${job.detail})` : '';
      return `${job.stage_label || 'Working'}${detail}. ${took} so far; a room takes several minutes.`;
    }
    case 'done': {
      const cloud = job.cloud;
      if (!cloud) return `Finished in ${took}.`;
      return `Finished in ${took}: ${cloud.points.toLocaleString('en-GB')} points (${cloud.kind}) from `
        + `${cloud.images_registered} of ${cloud.images_total} frames.`;
    }
    case 'cancelled':
      return 'Stopped. Nothing was stored.';
    case 'unavailable':
      return job.error || 'No tool is installed on this machine to read a video with.';
    default:
      return job.error || 'The video could not be turned into a room.';
  }
}
