/**
 * Room scan: read a phone scan of the room, show what it suggests, and only
 * then store it (docs/ROOM_SCAN.md).
 *
 * Choosing a file asks the server for a preview, which writes nothing. Apply
 * sends the same file again with the same options, so what is stored is what
 * was shown. Everything on screen here is a suggestion: the room is scenery
 * for the 3D view, and the only fixtures that move are template guesses nobody
 * has confirmed. They stay unconfirmed afterwards.
 *
 * A walkthrough video goes the long way round: the server turns it into a
 * point cloud as a background job (free tools on that machine), this dialog
 * asks how it is doing, and the finished cloud is then previewed and applied
 * as a scan file like any other. A video has no scale, so the operator gives
 * one measurement; without it the preview warns that every size is assumed.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { UploadFile as UploadFileIcon, Videocam as VideocamIcon } from '@mui/icons-material';
import axios from 'axios';
import { roomScanApi, roomVideoApi } from '../../services/api';
import {
  DEFAULT_SCAN_OPTIONS,
  ROOM_SCAN_ACCEPT,
  fileProblem,
  fixtureMoveText,
  foundLines,
  moveText,
  roomScanErrorText,
  roomSizeText,
} from '../../utils/roomScan';
import {
  NO_REFERENCE,
  ROOM_VIDEO_ACCEPT,
  ROOM_VIDEO_DEFAULT_MAX_MB,
  ROOM_VIDEO_POLL_MS,
  jobEnded,
  jobStatusText,
  referenceMetres,
  referenceProblem,
  scaleIsAssumed,
  toolsText,
  videoProblem,
} from '../../utils/roomVideo';
import type {
  ReferenceKind,
  RoomVideoJob,
  RoomVideoReference,
  RoomVideoTools,
} from '../../utils/roomVideo';
import type {
  RoomScanOptions,
  RoomScanPreview,
  ScanRotate,
  ScanUnits,
  ScanUpAxis,
} from '../../utils/roomScan';

interface RoomScanDialogProps {
  open: boolean;
  rigId: number;
  rigName: string;
  /** Whether the rig already has a room stored on it. */
  hasRoom: boolean;
  onClose: () => void;
  /** Called once a scan has been applied or the stored room removed: the rig has changed. */
  onChanged: () => void;
  /** Opens the 3D view, where the stored room is drawn. */
  onView3D?: () => void;
}

type Busy = 'preview' | 'apply' | 'remove' | null;

function errorText(err: unknown): string {
  if (axios.isAxiosError(err)) return roomScanErrorText(err.response?.status, err.response?.data?.detail);
  return roomScanErrorText(undefined, undefined);
}

/** The same, for a request that asked for a file: a refusal's words arrive as a blob. */
async function blobErrorText(err: unknown): Promise<string> {
  if (axios.isAxiosError(err) && err.response?.data instanceof Blob) {
    try {
      const body = JSON.parse(await err.response.data.text()) as { detail?: unknown };
      return roomScanErrorText(err.response.status, body.detail);
    } catch {
      return roomScanErrorText(err.response.status, undefined);
    }
  }
  return errorText(err);
}

const wait = (ms: number) => new Promise<void>((resolve) => { window.setTimeout(resolve, ms); });

/** A measurement as one comparable value, to tell when it has changed since the cloud was scaled. */
const referenceKey = (reference: RoomVideoReference) => `${reference.kind}:${referenceMetres(reference) ?? ''}`;

export default function RoomScanDialog({
  open,
  rigId,
  rigName,
  hasRoom,
  onClose,
  onChanged,
  onView3D,
}: RoomScanDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [options, setOptions] = useState<RoomScanOptions>(DEFAULT_SCAN_OPTIONS);
  const [preview, setPreview] = useState<RoomScanPreview | null>(null);
  const [applied, setApplied] = useState<RoomScanPreview | null>(null);
  const [moveFixtures, setMoveFixtures] = useState(true);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // A walkthrough video: the server's tools, the job, and the one measurement.
  const [tools, setTools] = useState<RoomVideoTools | null>(null);
  const [videoName, setVideoName] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<number | null>(null);
  const [job, setJob] = useState<RoomVideoJob | null>(null);
  const [dense, setDense] = useState(false);
  const [reference, setReference] = useState<RoomVideoReference>(NO_REFERENCE);
  /** The measurement the cloud on screen was scaled by (referenceKey). */
  const [scaledBy, setScaledBy] = useState<string | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);
  const videoInputRef = useRef<HTMLInputElement>(null);
  // Only the newest video may land, and a job is stopped when the dialog leaves it.
  const videoRequestRef = useRef(0);
  const jobRef = useRef<{ rigId: number; jobId: string } | null>(null);
  // A job outlives the render that started it: it reads what is set now, not what was set then.
  const referenceRef = useRef(reference);
  referenceRef.current = reference;
  const optionsRef = useRef(options);
  optionsRef.current = options;
  // Only the newest preview may land: changing the units while one is in
  // flight must not show the old reading under the new setting.
  const requestRef = useRef(0);

  // A dialog opened again starts clean, and a reply to a closed one is dropped.
  useEffect(() => {
    requestRef.current += 1;
    if (!open) return;
    setFile(null);
    setOptions(DEFAULT_SCAN_OPTIONS);
    setPreview(null);
    setApplied(null);
    setMoveFixtures(true);
    setBusy(null);
    setError(null);
    setNotice(null);
  }, [open, rigId]);

  // The same for a video, and a job left behind is stopped: it would keep the
  // server's processor busy for an hour with nobody to hand its result to.
  useEffect(() => {
    videoRequestRef.current += 1;
    const left = jobRef.current;
    jobRef.current = null;
    if (left) void roomVideoApi.stop(left.rigId, left.jobId).catch(() => undefined);
    if (!open) return;
    setVideoName(null);
    setUploaded(null);
    setJob(null);
    setDense(false);
    setReference(NO_REFERENCE);
    setScaledBy(null);
    setVideoError(null);
    setTools(null);
    const request = videoRequestRef.current;
    roomVideoApi.tools()
      .then((found) => { if (videoRequestRef.current === request) setTools(found); })
      .catch(() => undefined);
  }, [open, rigId]);

  useEffect(() => () => {
    const left = jobRef.current;
    if (left) void roomVideoApi.stop(left.rigId, left.jobId).catch(() => undefined);
  }, []);

  const runPreview = useCallback(async (chosen: File, using: RoomScanOptions) => {
    const request = requestRef.current + 1;
    requestRef.current = request;
    setPreview(null);
    setApplied(null);
    setNotice(null);
    setError(null);
    setBusy('preview');
    try {
      const result = await roomScanApi.preview(rigId, chosen, using);
      if (requestRef.current !== request) return;
      setPreview(result);
    } catch (err) {
      if (requestRef.current !== request) return;
      setError(errorText(err));
    } finally {
      if (requestRef.current === request) setBusy(null);
    }
  }, [rigId]);

  /** Fetch the finished cloud scaled by the measurement, and preview it as the scan file. */
  const loadCloud = useCallback(async (jobId: string, using: RoomVideoReference, request: number) => {
    try {
      const cloud = await roomVideoApi.cloud(rigId, jobId, using);
      if (videoRequestRef.current !== request) return;
      setScaledBy(referenceKey(using));
      setFile(cloud);
      void runPreview(cloud, optionsRef.current);
    } catch (err) {
      const text = await blobErrorText(err);
      if (videoRequestRef.current !== request) return;
      setVideoError(text);
    }
  }, [rigId, runPreview]);

  /** Let go of the video job, stopping it on the server if it is still running. */
  const dropVideoJob = () => {
    videoRequestRef.current += 1;
    const running = jobRef.current;
    jobRef.current = null;
    setUploaded(null);
    if (running) void roomVideoApi.stop(running.rigId, running.jobId).catch(() => undefined);
    return videoRequestRef.current;
  };

  const handleVideo = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const chosen = event.target.files?.[0] ?? null;
    event.target.value = '';
    if (!chosen) return;
    const request = dropVideoJob();
    setJob(null);
    setScaledBy(null);
    setVideoName(chosen.name);
    setVideoError(null);

    // Nothing is sent to a server that has no tool to read it with: its own
    // words say what to install, or to export OBJ or PLY from a scanning app.
    if (tools && !tools.ready) {
      setVideoError(tools.message);
      return;
    }
    const problem = videoProblem(chosen, tools?.max_upload_mb ?? ROOM_VIDEO_DEFAULT_MAX_MB);
    if (problem) {
      setVideoError(problem);
      return;
    }

    // The scan on screen belongs to another file now.
    requestRef.current += 1;
    setFile(null);
    setPreview(null);
    setApplied(null);
    setError(null);
    setBusy(null);

    try {
      setUploaded(0);
      let current = await roomVideoApi.start(rigId, chosen, dense ? 'dense' : 'sparse', (fraction) => {
        if (videoRequestRef.current === request) setUploaded(fraction);
      });
      if (videoRequestRef.current !== request) {
        // The dialog moved on while the video was arriving; the job it started has nobody waiting.
        if (current.job_id) void roomVideoApi.stop(rigId, current.job_id).catch(() => undefined);
        return;
      }
      setUploaded(null);
      setJob(current);
      if (!current.job_id) return;            // 'unavailable': its message is shown
      const jobId = current.job_id;
      jobRef.current = { rigId, jobId };

      while (!jobEnded(current)) {
        await wait(ROOM_VIDEO_POLL_MS);
        if (videoRequestRef.current !== request) return;
        current = await roomVideoApi.status(rigId, jobId);
        if (videoRequestRef.current !== request) return;
        setJob(current);
      }
      if (current.state === 'done') await loadCloud(jobId, referenceRef.current, request);
    } catch (err) {
      if (videoRequestRef.current !== request) return;
      setUploaded(null);
      setVideoError(errorText(err));
    }
  };

  const handleStopVideo = () => {
    dropVideoJob();
    setJob((current) => (current && !jobEnded(current) ? { ...current, state: 'cancelled' } : current));
  };

  const handleRescale = () => {
    if (!job?.job_id || job.state !== 'done') return;
    setVideoError(null);
    void loadCloud(job.job_id, reference, videoRequestRef.current);
  };

  const handleFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    const chosen = event.target.files?.[0] ?? null;
    event.target.value = '';
    if (!chosen) return;
    const problem = fileProblem(chosen);
    if (problem) {
      requestRef.current += 1;
      setFile(null);
      setPreview(null);
      setApplied(null);
      setBusy(null);
      setError(problem);
      return;
    }
    // A scan file replaces whatever a video was doing.
    dropVideoJob();
    setJob(null);
    setVideoName(null);
    setVideoError(null);
    setScaledBy(null);
    setFile(chosen);
    void runPreview(chosen, options);
  };

  const changeOptions = (next: RoomScanOptions) => {
    setOptions(next);
    if (file) void runPreview(file, next);
  };

  const handleApply = async () => {
    if (!file || !preview) return;
    const request = requestRef.current + 1;
    requestRef.current = request;
    setError(null);
    setBusy('apply');
    try {
      const result = await roomScanApi.apply(rigId, file, options, moveFixtures && preview.fixtures.would_move > 0);
      if (requestRef.current !== request) {
        // The dialog moved on, but the rig was still written.
        onChanged();
        return;
      }
      setApplied(result);
      onChanged();
    } catch (err) {
      if (requestRef.current !== request) return;
      setError(errorText(err));
    } finally {
      if (requestRef.current === request) setBusy(null);
    }
  };

  const handleRemove = async () => {
    const request = requestRef.current + 1;
    requestRef.current = request;
    setError(null);
    setBusy('remove');
    try {
      const result = await roomScanApi.remove(rigId);
      onChanged();
      if (requestRef.current !== request) return;
      setFile(null);
      setPreview(null);
      setApplied(null);
      setNotice(
        result.removed
          ? 'The stored room was taken off this rig. Fixtures were left where they are.'
          : 'This rig had no stored room.',
      );
    } catch (err) {
      if (requestRef.current !== request) return;
      setError(errorText(err));
    } finally {
      if (requestRef.current === request) setBusy(null);
    }
  };

  const shown = applied ?? preview;
  const wouldMove = preview?.fixtures.would_move ?? 0;

  const videoWorking = uploaded !== null || (job !== null && !jobEnded(job));
  const measurementProblem = referenceProblem(reference);
  const measurementChanged = job?.state === 'done' && scaledBy !== null && scaledBy !== referenceKey(reference);

  return (
    <Dialog open={open} onClose={busy === 'apply' ? undefined : onClose} maxWidth="md" fullWidth>
      <DialogTitle>Room scan for {rigName}</DialogTitle>

      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Scan the room with a phone (Polycam, Scaniverse, Apple RoomPlan) and export it as OBJ or PLY,
          as a USDZ or USDA with a text layer, or as RoomPlan JSON. The scan is read for the floor,
          walls and ceiling, any stage, riser or booth, and trusses or bars overhead. Everything it
          finds is a suggestion: you see it here first, and nothing is stored until you apply it.
        </Typography>

        <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
          <input
            ref={fileInputRef}
            type="file"
            accept={ROOM_SCAN_ACCEPT}
            onChange={handleFile}
            style={{ display: 'none' }}
          />
          <Button
            variant="outlined"
            startIcon={<UploadFileIcon />}
            onClick={() => fileInputRef.current?.click()}
            disabled={busy === 'apply' || busy === 'remove'}
          >
            {file ? 'Choose another file' : 'Choose a scan file'}
          </Button>
          <input
            ref={videoInputRef}
            type="file"
            accept={ROOM_VIDEO_ACCEPT}
            onChange={(event) => { void handleVideo(event); }}
            style={{ display: 'none' }}
          />
          <Button
            variant="outlined"
            startIcon={<VideocamIcon />}
            onClick={() => videoInputRef.current?.click()}
            disabled={busy === 'apply' || busy === 'remove' || videoWorking}
          >
            Or a walkthrough video
          </Button>
          {file && (
            <Typography variant="body2">
              {file.name} ({(file.size / (1024 * 1024)).toFixed(1)} MB)
            </Typography>
          )}
        </Stack>

        <Box sx={{ mb: 2, p: 1.5, border: 1, borderColor: 'divider', borderRadius: 1 }}>
          <Typography variant="subtitle2">From a walkthrough video</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            Film one to two minutes walking slowly round the whole room with the lights up, floor and ceiling
            in shot. The server picks the sharp frames and rebuilds the room from them with free tools on
            that machine; it takes several minutes and nothing is stored until you apply the result. A video
            carries no real size, so give one thing you measured.
          </Typography>

          <Stack direction="row" spacing={2} alignItems="flex-start" sx={{ mb: 1 }}>
            <FormControl size="small" sx={{ minWidth: 210 }}>
              <InputLabel id="video-reference">What you measured</InputLabel>
              <Select
                labelId="video-reference"
                label="What you measured"
                value={reference.kind}
                onChange={(e) => setReference({ ...reference, kind: e.target.value as ReferenceKind })}
                disabled={busy === 'apply'}
              >
                <MenuItem value="none">Nothing yet</MenuItem>
                <MenuItem value="ceiling_height">Ceiling height</MenuItem>
                <MenuItem value="longest_wall">Length of the longest wall</MenuItem>
              </Select>
            </FormControl>
            <TextField
              size="small"
              label="Metres"
              value={reference.metres}
              onChange={(e) => setReference({ ...reference, metres: e.target.value })}
              disabled={reference.kind === 'none' || busy === 'apply'}
              error={measurementProblem !== null}
              helperText={measurementProblem ?? undefined}
              inputProps={{ inputMode: 'decimal', 'aria-label': 'Measurement in metres' }}
              sx={{ width: 140 }}
            />
            {measurementChanged && (
              <Button
                variant="outlined"
                onClick={handleRescale}
                disabled={measurementProblem !== null || busy !== null}
              >
                Read again with this
              </Button>
            )}
            <FormControlLabel
              control={
                <Checkbox
                  checked={dense}
                  onChange={(e) => setDense(e.target.checked)}
                  disabled={videoWorking}
                />
              }
              label="Dense cloud (much slower)"
            />
          </Stack>
          {scaleIsAssumed(reference) && (
            <Typography variant="body2" color="warning.main" sx={{ mb: 1 }}>
              With no measurement the scale is assumed (the phone held 1.5 m above the floor), and every
              size in the preview is a guess.
            </Typography>
          )}

          {tools && (
            <Typography variant="caption" color="text.secondary" component="div" sx={{ mb: 1 }}>
              {toolsText(job?.tools ?? tools)}
            </Typography>
          )}
          {tools && !tools.ready && tools.message && !videoError && (
            <Alert severity="info" sx={{ mb: 1 }}>
              {tools.message}
            </Alert>
          )}

          {uploaded !== null && (
            <Box sx={{ mb: 1 }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Typography variant="body2" sx={{ flexGrow: 1 }}>
                  Sending {videoName} to the server: {Math.round(uploaded * 100)}%
                </Typography>
                <Button size="small" color="warning" onClick={handleStopVideo}>
                  Stop
                </Button>
              </Stack>
              <LinearProgress variant="determinate" value={uploaded * 100} sx={{ mt: 1 }} />
            </Box>
          )}
          {job && job.state !== 'unavailable' && (
            <Box sx={{ mb: 1 }}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Chip
                  size="small"
                  label={job.state}
                  color={job.state === 'done' ? 'success' : job.state === 'failed' ? 'error' : 'default'}
                  variant="outlined"
                />
                <Typography variant="body2" sx={{ flexGrow: 1 }}>
                  {videoName ? `${videoName}: ` : ''}{job.state === 'failed' ? 'Failed.' : jobStatusText(job)}
                </Typography>
                {!jobEnded(job) && (
                  <Button size="small" color="warning" onClick={handleStopVideo}>
                    Stop
                  </Button>
                )}
              </Stack>
              {!jobEnded(job) && (
                <LinearProgress
                  variant={job.state === 'queued' ? 'indeterminate' : 'buffer'}
                  value={(job.progress ?? 0) * 100}
                  valueBuffer={Math.min(100, (job.progress ?? 0) * 100 + 15)}
                  sx={{ mt: 1 }}
                />
              )}
            </Box>
          )}
          {job && (job.state === 'failed' || job.state === 'unavailable') && (
            <Alert severity={job.state === 'failed' ? 'error' : 'info'} sx={{ mb: 1 }}>
              {jobStatusText(job)}
            </Alert>
          )}
          {videoError && (
            <Alert severity={tools && !tools.ready ? 'info' : 'error'} onClose={() => setVideoError(null)}>
              {videoError}
            </Alert>
          )}
        </Box>

        <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel id="scan-units">Units</InputLabel>
            <Select
              labelId="scan-units"
              label="Units"
              value={options.units}
              onChange={(e) => changeOptions({ ...options, units: e.target.value as ScanUnits })}
              disabled={busy === 'apply'}
            >
              <MenuItem value="auto">Guess</MenuItem>
              <MenuItem value="m">Metres</MenuItem>
              <MenuItem value="cm">Centimetres</MenuItem>
              <MenuItem value="mm">Millimetres</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel id="scan-up">Up axis</InputLabel>
            <Select
              labelId="scan-up"
              label="Up axis"
              value={options.upAxis}
              onChange={(e) => changeOptions({ ...options, upAxis: e.target.value as ScanUpAxis })}
              disabled={busy === 'apply'}
            >
              <MenuItem value="auto">Guess</MenuItem>
              <MenuItem value="y">Y is up</MenuItem>
              <MenuItem value="z">Z is up</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 210 }}>
            <InputLabel id="scan-turn">Turn the room</InputLabel>
            <Select
              labelId="scan-turn"
              label="Turn the room"
              value={options.rotate}
              onChange={(e) => changeOptions({ ...options, rotate: Number(e.target.value) as ScanRotate })}
              disabled={busy === 'apply'}
            >
              <MenuItem value={0}>As read</MenuItem>
              <MenuItem value={90}>A quarter turn clockwise</MenuItem>
              <MenuItem value={180}>A half turn</MenuItem>
              <MenuItem value={270}>A quarter turn anticlockwise</MenuItem>
            </Select>
          </FormControl>
        </Stack>

        {busy && <LinearProgress sx={{ mb: 2 }} />}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
        {notice && (
          <Alert severity="info" sx={{ mb: 2 }} onClose={() => setNotice(null)}>
            {notice}
          </Alert>
        )}

        {applied?.applied && (
          <Alert severity="success" sx={{ mb: 2 }}>
            {applied.applied.message}
          </Alert>
        )}

        {shown && (
          <Box>
            {!applied && (
              <Alert severity="info" sx={{ mb: 2 }}>
                This is a preview. Nothing has been stored and no fixture has moved.
                {shown.replaces_existing_shell && ' Applying it replaces the room already stored on this rig.'}
              </Alert>
            )}

            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
              <Typography variant="subtitle1">Suggested room</Typography>
              <Chip size="small" color="warning" variant="outlined" label="Suggestion - not checked against the room" />
            </Stack>
            <Typography variant="body2" sx={{ mb: 1 }}>
              {roomSizeText(shown)}. Read from {shown.file || 'the scan'} ({shown.format.toUpperCase()},{' '}
              {shown.summary.units}, {shown.summary.up_axis.toUpperCase()}-up).
            </Typography>
            <Box component="ul" sx={{ mt: 0, mb: 2, pl: 3 }}>
              {foundLines(shown).map((line) => (
                <Typography key={line} component="li" variant="body2">
                  {line}
                </Typography>
              ))}
            </Box>

            {shown.warnings.map((warning) => (
              <Alert key={warning} severity="warning" sx={{ mb: 1 }}>
                {warning}
              </Alert>
            ))}

            <Typography variant="subtitle2" sx={{ mt: 2 }}>
              How the scan was read
            </Typography>
            <Box component="ul" sx={{ mt: 0.5, mb: 2, pl: 3 }}>
              {shown.assumptions.map((line) => (
                <Typography key={line} component="li" variant="body2" color="text.secondary">
                  {line}
                </Typography>
              ))}
            </Box>

            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
              <Typography variant="subtitle1">{applied ? 'Fixtures moved' : 'Suggested fixture moves'}</Typography>
              <Chip size="small" color="warning" variant="outlined" label="Still unconfirmed afterwards" />
            </Stack>
            <Typography variant="body2" sx={{ mb: 1 }}>
              {applied?.applied
                ? `${applied.applied.fixtures_moved} moved. ${applied.applied.fixtures_still_unconfirmed} are still `
                  + 'unconfirmed: check them with Identify Lights, or drag them.'
                : fixtureMoveText(shown)}{' '}
              Positions that were tapped, confirmed, measured in a file or fitted between tapped ends are never moved.
            </Typography>

            {shown.fixtures.moves.length > 0 && !(applied && applied.applied?.fixtures_moved === 0) && (
              <TableContainer sx={{ maxHeight: 260, mb: 1 }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell>Fixture</TableCell>
                      <TableCell>Group</TableCell>
                      <TableCell>From x, y, z to x, y, z (m)</TableCell>
                      <TableCell>Why</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {shown.fixtures.moves.map((move) => (
                      <TableRow key={move.rig_fixture_id}>
                        <TableCell>{move.name}</TableCell>
                        <TableCell>{move.group}</TableCell>
                        <TableCell sx={{ whiteSpace: 'nowrap' }}>{moveText(move)}</TableCell>
                        <TableCell>{move.reason}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}

            {!applied && (
              <FormControlLabel
                control={
                  <Checkbox
                    checked={moveFixtures && wouldMove > 0}
                    disabled={wouldMove === 0 || busy !== null}
                    onChange={(e) => setMoveFixtures(e.target.checked)}
                  />
                }
                label={
                  wouldMove > 0
                    ? `Also move these ${wouldMove} unconfirmed fixtures. Unticked, only the room is stored.`
                    : 'No fixture would be moved: only the room is stored.'
                }
              />
            )}
          </Box>
        )}
      </DialogContent>

      <DialogActions>
        {hasRoom && !applied && (
          <Button color="warning" onClick={() => { void handleRemove(); }} disabled={busy !== null} sx={{ mr: 'auto' }}>
            Remove the stored room
          </Button>
        )}
        {applied && onView3D && (
          <Button onClick={onView3D}>See it in the 3D view</Button>
        )}
        <Button onClick={onClose} disabled={busy === 'apply'}>
          {videoWorking ? 'Stop the video and close' : 'Close'}
        </Button>
        {!applied && (
          <Button
            variant="contained"
            onClick={() => { void handleApply(); }}
            disabled={!file || !preview || busy !== null}
          >
            {busy === 'apply'
              ? 'Applying...'
              : moveFixtures && wouldMove > 0
                ? `Store the room and move ${wouldMove} fixtures`
                : 'Store the room'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
