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
 * No fixture moves with anything here, and nothing is sent to a light.
 */
import { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
  NEW_ITEM_CHOICES,
  SHELL_FIELD_LABELS,
  SHELL_NAME_MAX,
  SHELL_SIZE_FIELDS,
  deleteQuestionText,
  draftOf,
  editResultText,
  newItemDraft,
  newItemKind,
  quarterTurned,
  readDraft,
  readNewItem,
  shellEditErrorText,
  shellItemKey,
  shellItemTitle,
  shellItems,
  shellUndoCount,
  undoButtonText,
} from '../../utils/roomShellEdit';
import type {
  NewItemDraft, NewItemWhat, ShellItem, ShellItemDraft, ShellSizeField, ShellUndoInfo,
} from '../../utils/roomShellEdit';

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
}

function errorText(err: unknown): string {
  if (axios.isAxiosError(err)) return shellEditErrorText(err.response?.status, err.response?.data?.detail);
  return shellEditErrorText(undefined, undefined);
}

/** The size fields of a row that stand in its Size cell: all but the height, which has a column. */
const planFields = (item: ShellItem): ShellSizeField[] =>
  SHELL_SIZE_FIELDS[item.kind].filter((field) => field !== 'height');

const unitOf = (field: ShellSizeField) => (field === 'heading_deg' ? 'deg' : 'm');

type Busy = { key: string; what: 'save' | 'delete' | 'add' | 'undo' };

export default function RoomShellEditDialog({
  open,
  rigId,
  rigName,
  shell,
  undo,
  onClose,
  onChanged,
}: RoomShellEditDialogProps) {
  // What has been typed into a row and not yet saved, by the row's key. A row
  // with nothing typed shows what is stored.
  const [drafts, setDrafts] = useState<Record<string, ShellItemDraft>>({});
  // The request that is out: one change at a time, each built on the last one stored.
  const [busyWith, setBusyWith] = useState<Busy | null>(null);
  // The row whose Delete was pressed and is waiting for an answer.
  const [askDeleteKey, setAskDeleteKey] = useState<string | null>(null);
  // The form that adds what the scan missed.
  const [adding, setAdding] = useState<NewItemDraft>(() => newItemDraft('riser', shell));
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // A dialog opened again starts clean.
  useEffect(() => {
    if (!open) return;
    setDrafts({});
    setBusyWith(null);
    setAskDeleteKey(null);
    setAdding(newItemDraft('riser', shell));
    setError(null);
    setNotice(null);
    // Not on `shell`: the room as it is when the dialog opens sets the form's
    // first height, and a room that then changes must not wipe what is typed.
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
      const result = await roomScanApi.editShellItem(rigId, item.kind, item.index, reading.changes);
      // This row now shows what was stored; what is typed in the others is kept.
      setDrafts((current) => {
        const next = { ...current };
        delete next[key];
        return next;
      });
      setNotice(editResultText(item, reading.changes, result.room_shell));
      onChanged(result.room_shell, result.undo);
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
      // the old places would land on the wrong rows.
      setDrafts({});
      setNotice(result.message);
      onChanged(result.room_shell, result.undo);
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
      setNotice(result.message);
      onChanged(result.room_shell, result.undo);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusyWith(null);
    }
  };

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
          downstage. A moved line keeps its length and the way it runs. No fixture moves with
          anything here. Undo takes back one change at a time; reading the scan again replaces every
          change, and then there is nothing left to undo.
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
                            // A raised area stands square to the room: a quarter turn is the turn it has.
                            <Button
                              size="small"
                              disabled={busy || item.sizes.width === undefined || item.sizes.depth === undefined}
                              onClick={() => handleTurn(item)}
                              aria-label={`Turn ${title} a quarter turn`}
                            >
                              Turn
                            </Button>
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

        {scanned && (
          <Box sx={{ mt: 3 }} data-testid="room-shell-add">
            <Typography variant="subtitle2">Add what the scan missed</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              It is stored as added by hand, not as something the scan found. Leave the name empty
              to have it called what it is.
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
