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
import RoomScanUndoButton from './RoomScanUndoButton';
import {
  DEFAULT_SCAN_OPTIONS,
  ROOM_SCAN_ACCEPT,
  djBoothDroppedText,
  djBoothPreviewLine,
  HAND_EDIT_ITEMS_SHOWN,
  carryOverButtonText,
  carryOverKey,
  handEditCarryOver,
  handEditItems,
  handEditItemText,
  handEditWarningEntries,
  handEditsLine,
  keepAllButtonText,
  fileProblem,
  fixtureMoveText,
  foundLines,
  fixtureCountText,
  moveText,
  removeResultText,
  roomScanErrorText,
  roomSizeText,
  turnSummaryText,
  turnText,
  undoResultText,
} from '../../utils/roomScan';
import type {
  RoomScanCarryOver,
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
  /** How many fixture moves the rig's room scan undo record holds (0 for none). */
  undoMoves?: number;
  onClose: () => void;
  /** Called once a scan has been applied or the stored room removed: the rig has changed. */
  onChanged: () => void;
  /** Opens the 3D view, where the stored room is drawn. */
  onView3D?: () => void;
  /**
   * What the last scan applied lost that can still be put back, as kept with the stored room
   * (`room_shell.pending_carry_over`, slice 37): shown, with its buttons, when the dialog is opened again.
   */
  pendingCarryOver?: RoomScanCarryOver[];
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
  undoMoves = 0,
  onClose,
  onChanged,
  onView3D,
  pendingCarryOver = [],
}: RoomScanDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [options, setOptions] = useState<RoomScanOptions>(DEFAULT_SCAN_OPTIONS);
  const [preview, setPreview] = useState<RoomScanPreview | null>(null);
  const [applied, setApplied] = useState<RoomScanPreview | null>(null);
  const [moveFixtures, setMoveFixtures] = useState(true);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // Removing a room whose scan moved fixtures asks first whether to put them back.
  const [askRemove, setAskRemove] = useState(false);
  // The list of what a scan applied again did shows its first few, until asked for all of it.
  const [showAllItems, setShowAllItems] = useState(false);
  // Which `carry_over` entries have been put back (by `carryOverKey`, not by place: the list kept with the
  // room shrinks as the rig is read again), and the one being sent ('all' for "Keep all").
  const [carried, setCarried] = useState<string[]>([]);
  const [carrying, setCarrying] = useState<string | null>(null);
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
    setAskRemove(false);
    setShowAllItems(false);
    setCarried([]);
    setCarrying(null);
  }, [open, rigId]);

  const runPreview = useCallback(async (chosen: File, using: RoomScanOptions) => {
    const request = requestRef.current + 1;
    requestRef.current = request;
    setPreview(null);
    setApplied(null);
    setShowAllItems(false);
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
      setCarried([]);
      onChanged();
    } catch (err) {
      if (requestRef.current !== request) return;
      setError(errorText(err));
    } finally {
      if (requestRef.current === request) setBusy(null);
    }
  };

  // "Keep Front truss on this one": the old name and trim onto the item the scan read in its place (slice 36).
  const handleCarryOver = async (entry: RoomScanCarryOver) => {
    const key = carryOverKey(entry);
    setError(null);
    setCarrying(key);
    try {
      const result = await roomScanApi.carryOver(rigId, entry);
      setCarried((done) => [...done, key]);
      setNotice(result.message);
      onChanged();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setCarrying(null);
    }
  };

  // "Keep all" (slice 37): every entry not yet kept, in one request and one step of the room's Undo.
  // All or none: a refusal leaves every button as it was, to try again or one at a time.
  const handleKeepAll = async (entries: RoomScanCarryOver[]) => {
    setError(null);
    setCarrying('all');
    try {
      const result = await roomScanApi.carryOverAll(rigId, entries);
      setCarried((done) => [...done, ...entries.map(carryOverKey)]);
      setNotice(result.message);
      onChanged();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setCarrying(null);
    }
  };

  const handleRemove = async (restoreFixtures: boolean) => {
    setAskRemove(false);
    const request = requestRef.current + 1;
    requestRef.current = request;
    setError(null);
    setBusy('remove');
    try {
      const result = await roomScanApi.remove(rigId, restoreFixtures);
      onChanged();
      if (requestRef.current !== request) return;
      setFile(null);
      setPreview(null);
      setApplied(null);
      setNotice(removeResultText(result));
    } catch (err) {
      if (requestRef.current !== request) return;
      setError(errorText(err));
    } finally {
      if (requestRef.current === request) setBusy(null);
    }
  };

  const shown = applied ?? preview;
  const wouldMove = preview?.fixtures.would_move ?? 0;
  // Said of the preview only: once applied, the answer's own words take over.
  const markLine = applied ? null : djBoothPreviewLine(preview);
  // Before Apply what would be kept of the edits made by hand, and after it what was.
  const editsLine = handEditsLine(shown);
  // The same by name, one thing at a time, and what was lost or is to be checked (slice 35).
  const editItems = handEditItems(shown);
  const editWarnings = handEditWarningEntries(shown);
  // After Apply, what was lost that can be put on an item of the new room (slice 36). With no scan on
  // screen, what the last one applied left open, as kept with the stored room (slice 37).
  const fromStore = !applied && !preview && !file;
  const carryOver = applied ? handEditCarryOver(applied) : fromStore ? pendingCarryOver : [];
  // Slice 37: a button finds its warning by the warning's id; an entry from before ids, by the server's place.
  const belongsTo = (entry: RoomScanCarryOver, warning: { id?: string; place: number }) => (
    entry.warning_id !== undefined ? entry.warning_id === warning.id : entry.warning === warning.place
  );
  const carryOverFor = (warning: { id?: string; place: number }) => carryOver.filter((entry) => belongsTo(entry, warning));
  const carryOverUnplaced = carryOver.filter((entry) => !editWarnings.some((warning) => belongsTo(entry, warning)));
  const stillToKeep = carryOver.filter((entry) => !carried.includes(carryOverKey(entry)));
  const carryOverButton = (entry: RoomScanCarryOver) => {
    const key = carryOverKey(entry);
    return (
      <Button
        key={key}
        size="small"
        variant="outlined"
        color="inherit"
        data-testid="room-scan-carry-over"
        disabled={carried.includes(key) || carrying !== null || busy !== null}
        onClick={() => { void handleCarryOver(entry); }}
      >
        {carried.includes(key) ? `Kept ${entry.old_name} on ${entry.new_name}` : carryOverButtonText(entry)}
      </Button>
    );
  };
  // Shown where there are two or more to keep: one at a time is the button in each warning.
  const keepAllButton = carryOver.length >= 2 && (
    <Button
      size="small"
      variant="contained"
      color="inherit"
      sx={{ mb: 2 }}
      data-testid="room-scan-carry-over-all"
      disabled={stillToKeep.length === 0 || carrying !== null || busy !== null}
      onClick={() => { void handleKeepAll(stillToKeep); }}
    >
      {stillToKeep.length === 0 ? 'Kept all' : keepAllButtonText(stillToKeep.length)}
    </Button>
  );
  // How many of the moves on screen turn their fixture. Once applied it is said
  // only when fixtures were moved: with the box unticked nothing was turned.
  const turnSummary = !shown
    ? ''
    : applied
      ? ((applied.applied?.fixtures_moved ?? 0) > 0 ? turnSummaryText(shown.fixtures.moves, true) : '')
      : turnSummaryText(shown.fixtures.moves);

  return (
    <Dialog open={open} onClose={busy === 'apply' ? undefined : onClose} maxWidth="md" fullWidth>
      <DialogTitle>Room scan for {rigName}</DialogTitle>

      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Scan the room with a phone (Polycam, Scaniverse, Apple RoomPlan) and export it as OBJ, PLY or
          glTF (.glb or .gltf), as USDZ, USDC or USDA (binary USD is read as well as text), or as RoomPlan JSON.
          If the app shares a zip (a glTF with its .bin, or an OBJ with its textures), choose the zip as it is.
          The scan is read for the floor,
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

        {askRemove && (
          <Alert
            severity="warning"
            sx={{ mb: 2 }}
            action={(
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Button color="inherit" size="small" variant="outlined" onClick={() => { void handleRemove(true); }}>
                  Remove the room and put them back
                </Button>
                <Button color="inherit" size="small" onClick={() => { void handleRemove(false); }}>
                  Remove the room only
                </Button>
                <Button color="inherit" size="small" onClick={() => setAskRemove(false)}>
                  Cancel
                </Button>
              </Stack>
            )}
          >
            The scan that drew this room moved {fixtureCountText(undoMoves)}. Put{' '}
            {undoMoves === 1 ? 'it' : 'them'} back where {undoMoves === 1 ? 'it' : 'they'} stood before the scan
            as well? Any you have tapped, confirmed, dragged or moved since are left where they are.
          </Alert>
        )}

        {applied?.applied && (
          <Alert severity="success" sx={{ mb: 2 }}>
            {applied.applied.message}
          </Alert>
        )}

        {/* A scan applied over a room with a marked DJ booth that the new reading does not have there. */}
        {djBoothDroppedText(applied?.applied) && (
          <Alert severity="warning" sx={{ mb: 2 }} data-testid="room-scan-dj-booth-dropped">
            {djBoothDroppedText(applied?.applied)}
          </Alert>
        )}

        {/* Opened again with no scan on screen: what the last one applied lost and is still to put back (slice 37). */}
        {fromStore && carryOver.length > 0 && (
          <Box data-testid="room-scan-pending-carry-over" sx={{ mb: 2 }}>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>
              From the last scan applied: what it could not keep, still to put back
            </Typography>
            {carryOver.map((entry) => (
              <Alert key={carryOverKey(entry)} severity="warning" sx={{ mb: 1 }} data-testid="room-scan-pending-warning">
                {entry.message ?? `${entry.old_name} was not kept: the scan reads ${entry.new_name} in its place.`}
                <Stack direction="row" spacing={1} sx={{ mt: 1 }}>{carryOverButton(entry)}</Stack>
              </Alert>
            ))}
            {keepAllButton}
          </Box>
        )}

        {shown && (
          <Box>
            {!applied && (
              <Alert severity="info" sx={{ mb: 2 }}>
                This is a preview. Nothing has been stored and no fixture has moved.
                {shown.replaces_existing_shell && ' Applying it replaces the room already stored on this rig.'}
              </Alert>
            )}

            {/* Before Apply: what it would do to the DJ booth mark of the room already stored. */}
            {markLine && (markLine.dropped ? (
              <Alert severity="warning" sx={{ mb: 2 }} data-testid="room-scan-dj-booth-preview">
                {markLine.text}
              </Alert>
            ) : (
              <Typography variant="body2" sx={{ mb: 2 }} data-testid="room-scan-dj-booth-preview">
                {markLine.text}
              </Typography>
            ))}

            {/* What the scan keeps of the edits made by hand to the room already stored (slice 32). */}
            {editsLine && (editsLine.replaced ? (
              <Alert severity="warning" sx={{ mb: 2 }} data-testid="room-scan-hand-edits">
                {editsLine.text}
              </Alert>
            ) : (
              <Typography variant="body2" sx={{ mb: 2 }} data-testid="room-scan-hand-edits">
                {editsLine.text}
              </Typography>
            ))}

            {/* The same by name: each thing kept, left out or replaced, the first few until asked (slice 35). */}
            {editItems.length > 0 && (
              <Box sx={{ mt: -1, mb: 2 }} data-testid="room-scan-hand-edit-items">
                <Box component="ul" sx={{ my: 0, pl: 3 }}>
                  {(showAllItems ? editItems : editItems.slice(0, HAND_EDIT_ITEMS_SHOWN)).map((item, index) => (
                    // Two things can share a name and an outcome: the place in the list is the key.
                    <Typography key={index} component="li" variant="body2">
                      {handEditItemText(item)}
                    </Typography>
                  ))}
                </Box>
                {editItems.length > HAND_EDIT_ITEMS_SHOWN && (
                  <Button
                    size="small"
                    sx={{ ml: 1 }}
                    aria-expanded={showAllItems}
                    data-testid="room-scan-hand-edit-items-toggle"
                    onClick={() => setShowAllItems((all) => !all)}
                  >
                    {showAllItems ? 'Show fewer' : `Show all ${editItems.length}`}
                  </Button>
                )}
              </Box>
            )}

            {/* What was lost, and what was kept that the new room does not hold: shown as the scan's own warnings are. */}
            {editWarnings.map((warning) => (
              <Alert key={warning.place} severity="warning" sx={{ mb: 1 }} data-testid="room-scan-hand-edit-warning">
                {warning.text}
                {/* Slice 36: the old name and trim can be put on the item the scan read in their place. */}
                {carryOverFor(warning).length > 0 && (
                  <Stack direction="row" spacing={1} sx={{ mt: 1 }}>{carryOverFor(warning).map(carryOverButton)}</Stack>
                )}
              </Alert>
            ))}
            {carryOverUnplaced.length > 0 && (
              <Stack direction="row" spacing={1} sx={{ mb: 1 }}>{carryOverUnplaced.map(carryOverButton)}</Stack>
            )}
            {keepAllButton}

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
            <Typography variant="body2" sx={{ mb: 1 }} data-testid="room-scan-move-summary">
              {applied?.applied
                ? `${applied.applied.fixtures_moved} moved. ${applied.applied.fixtures_still_unconfirmed} are still `
                  + 'unconfirmed: check them with Identify Lights, or drag them in the 3D view.'
                : fixtureMoveText(shown)}{' '}
              {turnSummary && `${turnSummary} `}
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
                      <TableCell title="Degrees the fixture is turned with a stage that stands at a heading, clockwise seen from above">
                        Turn
                      </TableCell>
                      <TableCell>Why</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {shown.fixtures.moves.map((move) => (
                      <TableRow key={move.rig_fixture_id}>
                        <TableCell>{move.name}</TableCell>
                        <TableCell>{move.group}</TableCell>
                        <TableCell sx={{ whiteSpace: 'nowrap' }}>{moveText(move)}</TableCell>
                        <TableCell sx={{ whiteSpace: 'nowrap' }} data-testid={`room-scan-turn-${move.rig_fixture_id}`}>
                          {turnText(move)}
                        </TableCell>
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
        <Box sx={{ mr: 'auto', display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          {hasRoom && !applied && (
            <Button
              color="warning"
              onClick={() => {
                // With moves to undo, ask whether to put them back; with none, just remove.
                if (undoMoves > 0) setAskRemove(true);
                else void handleRemove(false);
              }}
              disabled={busy !== null || askRemove}
            >
              Remove the stored room
            </Button>
          )}
          {!askRemove && (
            <RoomScanUndoButton
              rigId={rigId}
              moves={undoMoves}
              disabled={busy !== null}
              onDone={(result) => {
                // The preview on screen describes moves that are no longer true.
                requestRef.current += 1;
                setFile(null);
                setPreview(null);
                setApplied(null);
                setError(null);
                setNotice(undoResultText(result));
                onChanged();
              }}
            />
          )}
        </Box>
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
