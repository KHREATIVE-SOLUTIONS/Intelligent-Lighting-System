/**
 * Edit Room: correct what a room scan found without scanning again, one
 * change at a time (docs/ROOM_SCAN.md).
 *
 * A scan suggests a stage, risers, a booth, trusses and rings. Somebody who
 * can see the room corrects it here: each raised area, overhead line and ring
 * of the stored room is a row with its name, where its middle is, its size
 * and its height. Save sends that row's changes; Delete asks first. The form
 * under the rows adds what the scan missed. Undo takes the latest change
 * back, one at a time: the server keeps the room as it was before each, so
 * the steps are still there after the page is loaded again, until the scan
 * is read again.
 *
 * Under those, Walls: the corners of the room's floor, each a row with where
 * it is, a corner added after it or taken out, the room's height, and a list
 * of what the walls as they now stand leave outside them. The walls go
 * through the same Undo. A button hands the corners to the 2D plan to be
 * dragged there, which this dialog, being in front of the plan, cannot do.
 *
 * A truss line or ring that is moved, raised, turned or resized takes the
 * fixtures hung on it along, unless its "Move the fixtures hung on it" box is
 * unticked; the notice says how many moved, and the editor is told to read
 * the rig again (`onFixturesMoved`). A raised area takes the fixtures standing
 * on it in the same way ("Move the fixtures standing on it"), and its row has
 * a selector for what it is (stage, riser, booth) and a base height, for a
 * platform that floats. Nothing else here moves a fixture, and nothing is
 * sent to a light.
 */
import { useEffect, useRef, useState } from 'react';
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
  FormControlLabel,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import axios from 'axios';
import { roomScanApi } from '../../services/api';
import type { RoomShell } from '../../types';
import {
  AREA_HEADING_LABEL,
  BASE_HEIGHT_LABEL,
  NEW_ITEM_CHOICES,
  RISER_KIND_CHOICES,
  SHELL_FIELD_LABELS,
  SHELL_NAME_MAX,
  SHELL_SIZE_FIELDS,
  baseHeightShown,
  carriedCount,
  carriesFixtures,
  carryBoxName,
  carryLabel,
  deleteQuestionText,
  draftOf,
  editResultText,
  headingShown,
  newItemDraft,
  newItemKind,
  positionText,
  quarterTurned,
  readDraft,
  readNewItem,
  riserKindShown,
  shellEditErrorText,
  shellItemKey,
  shellItemTitle,
  shellItems,
  shellUndoCount,
  undoButtonText,
  withCarry,
} from '../../utils/roomShellEdit';
import type {
  NewItemDraft, NewItemWhat, ShellItem, ShellItemDraft, ShellSizeField, ShellUndoInfo,
} from '../../utils/roomShellEdit';
import {
  WALL_LIMITS, cornerDraftOf, outsideHeading, outsideLines, outsideOf, readCorner, readRoomHeight, roomHeight,
  wallCorners, wallsSizeText,
} from '../../utils/roomWallsEdit';
import type { CornerDraft, OutlineAnswer, OutsideReport } from '../../utils/roomWallsEdit';

interface RoomShellEditDialogProps {
  open: boolean;
  rigId: number;
  rigName: string;
  /** The rig's stored room. Only one read from a scan has anything to edit. */
  shell: RoomShell | null | undefined;
  /** How many edits to the room can be undone, as the rig has it (`room_shell_edits`). */
  undo?: ShellUndoInfo | null;
  onClose: () => void;
  /**
   * Called with the room as the server now has it, after each change that was
   * stored or taken back, and with what can then be undone where the server
   * said.
   */
  onChanged: (shell: RoomShell, undo?: ShellUndoInfo) => void;
  /**
   * Called, after `onChanged`, when a change moved fixtures on the server: a
   * truss or ring took the ones hung on it along, or an undo put them back.
   * The positions the editor holds are then stale, and the rig is to be read
   * again.
   */
  onFixturesMoved?: () => void;
  /**
   * Asks for the corners to be dragged on the 2D plan: the editor closes this
   * dialog, which is in front of the plan, and puts handles on the corners.
   * Without it the button is left out.
   */
  onDragWalls?: () => void;
  /**
   * Asks for the raised areas, truss lines and rings to be dragged on the 2D
   * plan: the editor closes this dialog and lets them be picked up there.
   * Called with the rows whose "Move the fixtures ..." box is unticked, by
   * the row's key, so a drag on the plan carries, or leaves, the same
   * fixtures a save here would. Without it the button is left out.
   */
  onArrangeItems?: (leftAlone: Record<string, boolean>) => void;
}

function errorText(err: unknown): string {
  if (axios.isAxiosError(err)) return shellEditErrorText(err.response?.status, err.response?.data?.detail);
  return shellEditErrorText(undefined, undefined);
}

/** The size fields of a row that stand in its Size cell: all but the height, which has a column. */
const planFields = (item: ShellItem): ShellSizeField[] =>
  SHELL_SIZE_FIELDS[item.kind].filter((field) => field !== 'height');

const unitOf = (field: ShellSizeField) => (field === 'heading_deg' ? 'deg' : 'm');

type Busy = { key: string; what: 'save' | 'delete' | 'add' | 'undo' | 'walls' };

export default function RoomShellEditDialog({
  open,
  rigId,
  rigName,
  shell,
  undo,
  onClose,
  onChanged,
  onFixturesMoved,
  onDragWalls,
  onArrangeItems,
}: RoomShellEditDialogProps) {
  // What has been typed against a corner of the walls and not yet saved, by
  // the corner's place in the outline. Cleared by every change to the walls:
  // a corner added or taken out moves the ones after it.
  const [cornerDrafts, setCornerDrafts] = useState<Record<number, CornerDraft>>({});
  // The room height as typed, or null while the field shows what is stored.
  const [heightDraft, setHeightDraft] = useState<string | null>(null);
  // What the walls leave outside them, as the server last said. Null until it has.
  const [outside, setOutside] = useState<OutsideReport | null>(null);
  // Counts the changes to the room that were answered, so a read of the list
  // begun before one of them can tell it is out of date.
  const outsideAsOf = useRef(0);
  // What has been typed into a row and not yet saved, by the row's key. A row
  // with nothing typed shows what is stored.
  const [drafts, setDrafts] = useState<Record<string, ShellItemDraft>>({});
  // The rows whose "Move the fixtures hung on it" (or "standing on it") box is unticked, by the row's key.
  // A row not here takes its fixtures along, which is how every row starts.
  const [leftAlone, setLeftAlone] = useState<Record<string, boolean>>({});
  // The request that is out: one change at a time, each built on the last one stored.
  const [busyWith, setBusyWith] = useState<Busy | null>(null);
  // The row whose Delete was pressed and is waiting for an answer.
  const [askDeleteKey, setAskDeleteKey] = useState<string | null>(null);
  // The form that adds what the scan missed.
  const [adding, setAdding] = useState<NewItemDraft>(() => newItemDraft('riser', shell));
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // The room as it is now, for the effect below to read without running again
  // each time it changes: a room that changes must not wipe what is typed.
  const shellRef = useRef(shell);
  shellRef.current = shell;

  /**
   * Asks the server what the walls now leave outside them. The list is a
   * warning beside the edit, not part of it: when it cannot be read the
   * dialog carries on without it, as it did before there was one.
   */
  const refreshOutside = async (wanted: () => boolean = () => true) => {
    // A list that an answer to a later change has since replaced is the
    // fresher one: a slow read must not land on top of it.
    const asked = outsideAsOf.current;
    try {
      const read = await roomScanApi.getOutline(rigId);
      if (wanted() && asked === outsideAsOf.current && read && typeof read === 'object' && read.outside) {
        setOutside(outsideOf(read.outside));
      }
    } catch {
      // Left as it was.
    }
  };

  // A dialog opened again starts clean.
  useEffect(() => {
    if (!open) return undefined;
    setDrafts({});
    setLeftAlone({});
    setBusyWith(null);
    setAskDeleteKey(null);
    setAdding(newItemDraft('riser', shellRef.current));
    setError(null);
    setNotice(null);
    setCornerDrafts({});
    setHeightDraft(null);
    setOutside(null);
    if (shellRef.current?.source !== 'scan') return undefined;
    // The walls may have been dragged on the plan, or a fixture moved, since it was last open.
    let current = true;
    void refreshOutside(() => current);
    return () => { current = false; };
  }, [open, rigId]);

  const items = shellItems(shell);
  const scanned = shell?.source === 'scan';

  const setField = (item: ShellItem, field: keyof ShellItemDraft, value: string) => {
    const key = shellItemKey(item);
    setDrafts((current) => ({ ...current, [key]: { ...(current[key] ?? draftOf(item)), [field]: value } }));
  };

  const handleTurn = (item: ShellItem) => {
    const key = shellItemKey(item);
    setDrafts((current) => ({ ...current, [key]: quarterTurned(item, current[key] ?? draftOf(item)) }));
  };

  const handleSave = async (item: ShellItem) => {
    const key = shellItemKey(item);
    const reading = readDraft(item, drafts[key] ?? draftOf(item));
    if (reading.problem || !reading.changes) return;
    setError(null);
    setNotice(null);
    setBusyWith({ key, what: 'save' });
    try {
      // A truss or ring that is moved, raised, turned or resized takes the fixtures hung on it, and a
      // raised area the ones standing on it, unless its box is unticked.
      const carry = !leftAlone[key];
      const result = await roomScanApi.editShellItem(
        rigId, item.kind, item.index, withCarry(item, reading.changes, carry),
      );
      // This row now shows what was stored; what is typed in the others is kept, but for the rows of
      // the raised areas that went with this one: a row holds its place and sizes as they were when
      // it was first typed in, and saving it would send a carried area back to where it had been.
      const carriedRows = (Array.isArray(result.items_moved) ? result.items_moved : [])
        .map((entry) => shellItemKey({ kind: 'risers', index: entry.index }));
      setDrafts((current) => {
        const next = { ...current };
        delete next[key];
        for (const row of carriedRows) delete next[row];
        return next;
      });
      const moved = carriedCount(result.fixtures_moved);
      // A raised area also takes the raised areas standing on it: a riser on a stage goes with the stage.
      const areas = carriedCount(result.items_moved);
      setNotice(editResultText(item, reading.changes, result.room_shell, { moved, asked: carry, areas }));
      onChanged(result.room_shell, result.undo);
      // Fixtures stand somewhere new on the server: the rig on screen is to be read again.
      if (moved > 0) onFixturesMoved?.();
      // A moved or resized item may now reach past a wall, or have come back inside.
      void refreshOutside();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusyWith(null);
    }
  };

  const handleDelete = async (item: ShellItem) => {
    const key = shellItemKey(item);
    setAskDeleteKey(null);
    setError(null);
    setNotice(null);
    setBusyWith({ key, what: 'delete' });
    try {
      const result = await roomScanApi.deleteShellItem(rigId, item.kind, item.index);
      // The items after it have each moved up a place: what was typed against
      // the old places would land on the wrong rows. So would an unticked box.
      setDrafts({});
      setLeftAlone({});
      setNotice(result.message);
      onChanged(result.room_shell, result.undo);
      // The places of the items after it have changed, and the list goes by place.
      void refreshOutside();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusyWith(null);
    }
  };

  const newItem = readNewItem(adding);

  const handleAdd = async () => {
    if (newItem.problem || !newItem.body) return;
    setAskDeleteKey(null);
    setError(null);
    setNotice(null);
    setBusyWith({ key: '', what: 'add' });
    try {
      const result = await roomScanApi.addShellItem(rigId, newItem.kind, newItem.body);
      // It went at the end of its list, so every other row is where it was
      // and keeps what is typed in it. The form is ready for another of the same.
      setAdding(newItemDraft(adding.what, result.room_shell));
      setNotice(result.message);
      onChanged(result.room_shell, result.undo);
      void refreshOutside();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusyWith(null);
    }
  };

  const handleUndo = async () => {
    setAskDeleteKey(null);
    setError(null);
    setNotice(null);
    setBusyWith({ key: '', what: 'undo' });
    try {
      const result = await roomScanApi.undoShellEdit(rigId);
      // The whole room went back a step: a deleted item is in its list again,
      // and what was typed against the places as they were may be on the wrong rows.
      setDrafts({});
      setLeftAlone({});
      // The walls may be the ones that went back: so may their corners, and what they leave outside.
      setCornerDrafts({});
      setHeightDraft(null);
      if (result.outside) {
        outsideAsOf.current += 1;
        setOutside(outsideOf(result.outside));
      }
      // The server's words say how many fixtures went back with their truss, and how many were left.
      setNotice(result.message);
      onChanged(result.room_shell, result.undo);
      if (carriedCount(result.fixtures_restored) > 0) onFixturesMoved?.();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusyWith(null);
    }
  };

  // --- The walls ---------------------------------------------------------------

  const walls = scanned ? wallCorners(shell) : null;
  const storedHeight = roomHeight(shell);
  const heightText = heightDraft ?? (storedHeight === null ? '' : positionText(storedHeight));
  const heightReading = readRoomHeight(storedHeight, heightText);

  /**
   * One change to the walls: sent, and answered with the whole room and
   * what the walls now leave outside. Every change to the walls clears what
   * is typed against their corners, whose places may have changed.
   */
  const changeWalls = async (key: string, send: () => Promise<OutlineAnswer>) => {
    setAskDeleteKey(null);
    setError(null);
    setNotice(null);
    setBusyWith({ key, what: 'walls' });
    try {
      const result = await send();
      setCornerDrafts({});
      setHeightDraft(null);
      outsideAsOf.current += 1;
      setOutside(outsideOf(result.outside));
      setNotice(result.message);
      onChanged(result.room_shell, result.undo);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusyWith(null);
    }
  };

  const setCornerField = (index: number, field: keyof CornerDraft, value: string) => {
    const stored = walls?.corners[index];
    if (!stored) return;
    setCornerDrafts((current) => ({ ...current, [index]: { ...(current[index] ?? cornerDraftOf(stored)), [field]: value } }));
  };

  const handleSaveCorner = (index: number) => {
    const stored = walls?.corners[index];
    if (!stored) return;
    const reading = readCorner(stored, cornerDrafts[index] ?? cornerDraftOf(stored));
    if (reading.problem || !reading.changes) return;
    const to = reading.changes;
    void changeWalls(`corner:${index}`, () => roomScanApi.moveOutlineCorner(rigId, index, to));
  };

  const handleAddCorner = (after: number) => {
    void changeWalls(`corner:${after}`, () => roomScanApi.addOutlineCorner(rigId, after));
  };

  const handleDeleteCorner = (index: number) => {
    void changeWalls(`corner:${index}`, () => roomScanApi.deleteOutlineCorner(rigId, index));
  };

  const handleSaveHeight = () => {
    if (heightReading.problem || heightReading.height === null) return;
    const height = heightReading.height;
    void changeWalls('height', () => roomScanApi.setOutline(rigId, { height }));
  };

  const outsideList = outsideLines(outside);

  const busy = busyWith !== null;
  const undoable = shellUndoCount(undo);

  const sizeField = (item: ShellItem, draft: ShellItemDraft, field: ShellSizeField, title: string, labelled: boolean) => (
    <TextField
      key={field}
      size="small"
      label={labelled ? `${SHELL_FIELD_LABELS[field]} (${unitOf(field)})` : undefined}
      value={draft[field] ?? ''}
      // A size with no number stored has nothing to change; a size on the plan needs a middle to keep.
      disabled={busy || item.sizes[field] === undefined || (field !== 'height' && !item.centre)}
      onChange={(e) => setField(item, field, e.target.value)}
      inputProps={{ 'aria-label': `${SHELL_FIELD_LABELS[field]} of ${title}`, inputMode: 'decimal' }}
      sx={{ width: 104 }}
    />
  );

  const addField = (field: keyof Omit<NewItemDraft, 'what'>, label: string, width = 104) => (
    <TextField
      key={field}
      size="small"
      label={label}
      value={adding[field]}
      disabled={busy}
      onChange={(e) => setAdding((current) => ({ ...current, [field]: e.target.value }))}
      inputProps={{
        'aria-label': `${label.replace(/ \((m|deg)\)$/, '')} of the new item`,
        ...(field === 'name' ? { maxLength: SHELL_NAME_MAX + 20 } : { inputMode: 'decimal' as const }),
      }}
      sx={{ width }}
    />
  );

  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} maxWidth="lg" fullWidth>
      <DialogTitle>Edit the room of {rigName}</DialogTitle>

      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          What the room scan found, for you to correct: give a thing its real name, put it where it
          really is, set its size and its height, add what the scan missed, or take out what is not
          there. Across is metres from the centre line (stage left is positive). Depth is metres from
          the middle of the floor (downstage is positive, upstage negative). A heading is degrees
          clockwise from across the room, seen from above: 0 runs across, 90 from upstage to
          downstage. A moved line keeps its length and the way it runs. The fixtures hung on a truss
          or a ring, and the ones standing on a raised area, go with it when it is moved, raised,
          turned or resized, unless its box is unticked; nothing else here moves a fixture. A raised
          area&apos;s base height is how far its underside is above the floor: 0 stands on it, more
          floats, as a balcony does. A raised area standing on another (its middle over it, its base
          at its top) goes with it too, with its own fixtures. Undo takes back one change at a time, with
          the fixtures it moved; reading the scan again replaces every change, and then there is
          nothing left to undo.
        </Typography>

        {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>}
        {notice && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setNotice(null)}>{notice}</Alert>}

        {items.length === 0 ? (
          <Alert severity="info">
            {scanned
              ? 'This room has no stage, riser, booth, truss or ring left in it: only its floor, walls and ceiling.'
              : 'This rig has no scanned room stored. Use Room Scan to read one.'}
          </Alert>
        ) : (
          <TableContainer>
            {/* Only what the plan draws can be picked up there. What is typed here and not saved is let go. */}
            {onArrangeItems && items.some((item) => item.drawn && item.centre) && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
                <Button size="small" variant="outlined" disabled={busy} onClick={() => onArrangeItems(leftAlone)}>
                  Arrange room items on the plan
                </Button>
                <Typography variant="caption" color="text.secondary">
                  Drag a raised area, a truss or a ring where it goes, or nudge it with the arrow keys.
                  Each box below is kept as it is ticked here.
                </Typography>
              </Box>
            )}
            <Table size="small" data-testid="room-shell-items">
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Across (m)</TableCell>
                  <TableCell>Depth (m)</TableCell>
                  <TableCell>Size</TableCell>
                  <TableCell>Height (m)</TableCell>
                  <TableCell>What is stored</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {items.map((item) => {
                  const key = shellItemKey(item);
                  const draft = drafts[key] ?? draftOf(item);
                  const reading = readDraft(item, draft);
                  const title = shellItemTitle(item);
                  const asking = askDeleteKey === key;
                  return (
                    <TableRow key={key} data-testid={`room-shell-item-${key}`}>
                      <TableCell sx={{ minWidth: 170 }}>
                        <TextField
                          size="small"
                          fullWidth
                          value={draft.name}
                          placeholder={item.fallbackName}
                          disabled={busy}
                          onChange={(e) => setField(item, 'name', e.target.value)}
                          inputProps={{ 'aria-label': `Name of ${title}`, maxLength: SHELL_NAME_MAX + 20 }}
                        />
                      </TableCell>
                      <TableCell sx={{ width: 100 }}>
                        <TextField
                          size="small"
                          value={draft.x}
                          disabled={busy || !item.centre}
                          onChange={(e) => setField(item, 'x', e.target.value)}
                          inputProps={{ 'aria-label': `Across of ${title}`, inputMode: 'decimal' }}
                        />
                      </TableCell>
                      <TableCell sx={{ width: 100 }}>
                        <TextField
                          size="small"
                          value={draft.z}
                          disabled={busy || !item.centre}
                          onChange={(e) => setField(item, 'z', e.target.value)}
                          inputProps={{ 'aria-label': `Depth of ${title}`, inputMode: 'decimal' }}
                        />
                      </TableCell>
                      <TableCell>
                        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap', pt: 0.5 }}>
                          {planFields(item).map((field) => sizeField(item, draft, field, title, true))}
                          {item.kind === 'risers' && (
                            // A quarter turn: its width and its front to back change places. Any other turn is its heading.
                            <Button
                              size="small"
                              disabled={busy || item.sizes.width === undefined || item.sizes.depth === undefined}
                              onClick={() => handleTurn(item)}
                              aria-label={`Turn ${title} a quarter turn`}
                            >
                              Turn
                            </Button>
                          )}
                          {item.kind === 'risers' && (
                            // Which way its width runs: 0 stands square to the room, 30 is turned 30 degrees
                            // clockwise seen from above. What stands on it is swung about its middle with the turn.
                            <TextField
                              size="small"
                              label={`${AREA_HEADING_LABEL} (deg)`}
                              value={headingShown(item, draft)}
                              // A turn is about its middle, and needs its two sides to hold the whole of it to the room.
                              disabled={busy || !item.centre || item.sizes.width === undefined || item.sizes.depth === undefined}
                              onChange={(e) => setField(item, 'heading_deg', e.target.value)}
                              inputProps={{ 'aria-label': `${AREA_HEADING_LABEL} of ${title}`, inputMode: 'decimal' }}
                              sx={{ width: 104 }}
                            />
                          )}
                          {item.kind === 'risers' && (
                            // How far its underside is above the floor: 0 stands on it, more floats.
                            <TextField
                              size="small"
                              label={`${BASE_HEIGHT_LABEL} (m)`}
                              value={baseHeightShown(item, draft)}
                              disabled={busy}
                              onChange={(e) => setField(item, 'base_height', e.target.value)}
                              inputProps={{ 'aria-label': `${BASE_HEIGHT_LABEL} of ${title}`, inputMode: 'decimal' }}
                              sx={{ width: 124 }}
                            />
                          )}
                          {item.kind === 'risers' && (
                            // What it is. Its place in the list is kept; only the first stage takes a scan's floor lights.
                            <TextField
                              select
                              size="small"
                              label="Kind"
                              value={riserKindShown(item, draft)}
                              disabled={busy}
                              onChange={(e) => setField(item, 'riser_kind', e.target.value)}
                              SelectProps={{ native: true }}
                              inputProps={{ 'aria-label': `Kind of ${title}` }}
                              sx={{ width: 160 }}
                            >
                              {/* One stored with no kind the row knows shows as none until one is chosen. */}
                              {item.riserKind === null && <option value="" disabled>Not set</option>}
                              {RISER_KIND_CHOICES.map((choice) => (
                                <option key={choice.kind} value={choice.kind}>{choice.label}</option>
                              ))}
                            </TextField>
                          )}
                        </Box>
                      </TableCell>
                      <TableCell sx={{ width: 120 }}>
                        {sizeField(item, draft, 'height', title, false)}
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{item.detail}</Typography>
                        {item.marks.map((mark) => (
                          <Chip key={mark} size="small" label={mark} sx={{ mt: 0.5, mr: 0.5 }} />
                        ))}
                        {carriesFixtures(item.kind) && (
                          // Fixtures hang on a line or a ring and stand on a raised area: when it is
                          // moved, raised, turned or resized they go with it, unless this is unticked.
                          <FormControlLabel
                            sx={{ display: 'flex', mt: 0.5, mr: 0 }}
                            control={
                              <Checkbox
                                size="small"
                                checked={!leftAlone[key]}
                                disabled={busy}
                                onChange={(e) => setLeftAlone((current) => ({ ...current, [key]: !e.target.checked }))}
                                inputProps={{ 'aria-label': carryBoxName(item.kind, title) }}
                              />
                            }
                            label={<Typography variant="caption">{carryLabel(item.kind)}</Typography>}
                          />
                        )}
                        {reading.problem && (
                          <Typography variant="caption" color="error" display="block" role="alert">
                            {reading.problem}
                          </Typography>
                        )}
                        {asking && (
                          <Alert
                            severity="warning"
                            sx={{ mt: 1 }}
                            action={
                              <Box sx={{ display: 'flex', gap: 1 }}>
                                <Button color="inherit" size="small" onClick={() => setAskDeleteKey(null)}>
                                  Keep it
                                </Button>
                                <Button color="error" size="small" onClick={() => { void handleDelete(item); }}>
                                  Delete it
                                </Button>
                              </Box>
                            }
                          >
                            {deleteQuestionText(item)}
                          </Alert>
                        )}
                      </TableCell>
                      <TableCell sx={{ whiteSpace: 'nowrap' }}>
                        <Button
                          size="small"
                          variant="contained"
                          disabled={busy || !!reading.problem || !reading.changes}
                          onClick={() => { void handleSave(item); }}
                          aria-label={`Save ${title}`}
                        >
                          {busyWith?.key === key && busyWith.what === 'save' ? 'Saving...' : 'Save'}
                        </Button>
                        <Button
                          size="small"
                          color="warning"
                          sx={{ ml: 1 }}
                          disabled={busy || asking}
                          onClick={() => setAskDeleteKey(key)}
                          aria-label={`Delete ${title}`}
                        >
                          {busyWith?.key === key && busyWith.what === 'delete' ? 'Deleting...' : 'Delete'}
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        )}

        {walls && (
          <Box sx={{ mt: 3 }} data-testid="room-shell-walls">
            <Typography variant="subtitle2">Walls</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              The corners of the floor, in order round the room; each wall runs from one corner to
              the next, and the last back to the first. Now: {wallsSizeText(walls.corners, walls.box)}.
              Move a corner by typing where it goes, add one half way along the wall after a corner
              and then move it, or take one out. Nothing in the room and no fixture is moved to suit
              new walls: what they leave outside is listed here for you to deal with.
            </Typography>

            {outsideList.length > 0 && (
              <Alert severity="warning" sx={{ mb: 1.5 }} data-testid="room-shell-outside">
                {outsideHeading(outside)}
                <Box component="ul" sx={{ m: 0, mt: 0.5, pl: 2.5 }}>
                  {outsideList.map((line) => <li key={line}>{line}</li>)}
                </Box>
              </Alert>
            )}

            <TableContainer>
              <Table size="small" data-testid="room-shell-corners">
                <TableHead>
                  <TableRow>
                    <TableCell>Corner</TableCell>
                    <TableCell>Across (m)</TableCell>
                    <TableCell>Depth (m)</TableCell>
                    <TableCell />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {walls.corners.map((corner, index) => {
                    const number = index + 1;
                    const draft = cornerDrafts[index] ?? cornerDraftOf(corner);
                    const reading = readCorner(corner, draft);
                    const mine = busyWith?.what === 'walls' && busyWith.key === `corner:${index}`;
                    return (
                      <TableRow key={index} data-testid={`room-shell-corner-${index}`}>
                        <TableCell sx={{ width: 90 }}>{number}</TableCell>
                        <TableCell sx={{ width: 130 }}>
                          <TextField
                            size="small"
                            value={draft.x}
                            disabled={busy}
                            onChange={(e) => setCornerField(index, 'x', e.target.value)}
                            inputProps={{ 'aria-label': `Across of corner ${number}`, inputMode: 'decimal' }}
                          />
                        </TableCell>
                        <TableCell sx={{ width: 130 }}>
                          <TextField
                            size="small"
                            value={draft.z}
                            disabled={busy}
                            onChange={(e) => setCornerField(index, 'z', e.target.value)}
                            inputProps={{ 'aria-label': `Depth of corner ${number}`, inputMode: 'decimal' }}
                          />
                        </TableCell>
                        <TableCell sx={{ whiteSpace: 'nowrap' }}>
                          <Button
                            size="small"
                            variant="contained"
                            disabled={busy || !!reading.problem || !reading.changes}
                            onClick={() => handleSaveCorner(index)}
                            aria-label={`Save corner ${number}`}
                          >
                            {mine ? 'Saving...' : 'Save'}
                          </Button>
                          <Button
                            size="small"
                            sx={{ ml: 1 }}
                            disabled={busy || walls.corners.length >= WALL_LIMITS.cornersMax}
                            onClick={() => handleAddCorner(index)}
                            aria-label={`Add a corner after corner ${number}`}
                          >
                            Add after
                          </Button>
                          <Button
                            size="small"
                            color="warning"
                            sx={{ ml: 1 }}
                            // A room keeps at least three corners.
                            disabled={busy || walls.corners.length <= WALL_LIMITS.cornersMin}
                            onClick={() => handleDeleteCorner(index)}
                            aria-label={`Delete corner ${number}`}
                          >
                            Delete
                          </Button>
                          {reading.problem && (
                            <Typography variant="caption" color="error" display="block" role="alert">
                              {reading.problem}
                            </Typography>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>

            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap', mt: 1.5 }}>
              <TextField
                size="small"
                label="Room height (m)"
                value={heightText}
                disabled={busy}
                onChange={(e) => setHeightDraft(e.target.value)}
                inputProps={{ 'aria-label': 'Height of the room', inputMode: 'decimal' }}
                sx={{ width: 150 }}
              />
              <Button
                size="small"
                variant="contained"
                disabled={busy || !!heightReading.problem || heightReading.height === null}
                onClick={handleSaveHeight}
                aria-label="Save the height of the room"
              >
                {busyWith?.what === 'walls' && busyWith.key === 'height' ? 'Saving...' : 'Set height'}
              </Button>
              {onDragWalls && (
                <Button size="small" disabled={busy} onClick={onDragWalls} sx={{ ml: 'auto' }}>
                  Drag corners on the plan
                </Button>
              )}
            </Box>
            {heightReading.problem && (
              <Typography variant="caption" color="error" display="block" role="alert" sx={{ mt: 0.5 }}>
                {heightReading.problem}
              </Typography>
            )}
          </Box>
        )}

        {scanned && (
          <Box sx={{ mt: 3 }} data-testid="room-shell-add">
            <Typography variant="subtitle2">Add what the scan missed</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              It is stored as added by hand, not as something the scan found. Leave the name empty
              to have it called what it is. A raised area&apos;s base height is 0 for one that stands
              on the floor; give a riser that stands on a stage the height of the stage&apos;s top, and
              it will go with the stage when the stage is moved, raised or turned.
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
              <TextField
                select
                size="small"
                label="What to add"
                value={adding.what}
                disabled={busy}
                // Each kind starts at its own usual size; the name and the place typed so far are kept.
                onChange={(e) => setAdding((current) => ({
                  ...newItemDraft(e.target.value as NewItemWhat, shell),
                  name: current.name,
                  x: current.x,
                  z: current.z,
                  // A stage made a riser floats as it did; a truss has no base and does not read it.
                  base_height: current.base_height,
                  // And stands at the heading typed for it. A ring has none and does not read it.
                  heading_deg: current.heading_deg,
                }))}
                SelectProps={{ native: true }}
                inputProps={{ 'aria-label': 'What to add' }}
                sx={{ width: 190 }}
              >
                {NEW_ITEM_CHOICES.map((choice) => (
                  <option key={choice.what} value={choice.what}>{choice.label}</option>
                ))}
              </TextField>
              {addField('name', 'Name', 180)}
              {addField('x', 'Across (m)')}
              {addField('z', 'Depth (m)')}
              {SHELL_SIZE_FIELDS[newItemKind(adding.what)].map((field) =>
                addField(field, `${SHELL_FIELD_LABELS[field]} (${unitOf(field)})`, field === 'depth' ? 130 : 104))}
              {/* How far a raised area's underside is above the floor: 0 stands on it, more floats. */}
              {/* Which way a raised area's width runs: 0 stands square to the room. A line's heading is among its sizes. */}
              {newItemKind(adding.what) === 'risers' && addField('heading_deg', `${AREA_HEADING_LABEL} (deg)`)}
              {newItemKind(adding.what) === 'risers' && addField('base_height', `${BASE_HEIGHT_LABEL} (m)`, 130)}
              <Button
                variant="contained"
                size="small"
                disabled={busy || !!newItem.problem}
                onClick={() => { void handleAdd(); }}
              >
                {busyWith?.what === 'add' ? 'Adding...' : 'Add to the room'}
              </Button>
            </Box>
            {newItem.problem && (
              <Typography variant="caption" color="error" display="block" role="alert" sx={{ mt: 0.5 }}>
                {newItem.problem}
              </Typography>
            )}
          </Box>
        )}
      </DialogContent>

      <DialogActions>
        {scanned && (
          <Button
            onClick={() => { void handleUndo(); }}
            disabled={busy || undoable === 0}
            data-testid="room-shell-undo"
            sx={{ mr: 'auto' }}
          >
            {busyWith?.what === 'undo' ? 'Undoing...' : undoButtonText(undo)}
          </Button>
        )}
        <Button onClick={onClose} disabled={busy}>
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}
