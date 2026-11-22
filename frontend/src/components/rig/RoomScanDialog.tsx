/**
 * Room scan: read a phone scan of the room, show what it suggests, and only
 * then store it (docs/ROOM_SCAN.md).
 *
 * Choosing a file asks the server for a preview, which writes nothing. Apply
 * sends the same file again with the same options, so what is stored is what
 * was shown. Everything on screen here is a suggestion: the room is scenery
 * for the 3D view, and the only fixtures that move are template guesses nobody
 * has confirmed. They stay unconfirmed afterwards.
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
  Typography,
} from '@mui/material';
import { UploadFile as UploadFileIcon } from '@mui/icons-material';
import axios from 'axios';
import { roomScanApi } from '../../services/api';
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
          {file && (
            <Typography variant="body2">
              {file.name} ({(file.size / (1024 * 1024)).toFixed(1)} MB)
            </Typography>
          )}
        </Stack>

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
          Close
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
