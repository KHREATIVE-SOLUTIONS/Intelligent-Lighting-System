/**
 * Edit Room: rename, move or delete what a room scan found, one item at a
 * time (docs/ROOM_SCAN.md).
 *
 * A scan suggests a stage, risers, a booth, trusses and rings. Somebody who
 * can see the room corrects it here: each raised area, overhead line and ring
 * of the stored room is a row with its name and where its middle is. Save
 * sends that row's changes; Delete asks first, because the editor's Undo does
 * not reach the room and the only way back is to read the scan again.
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
  SHELL_NAME_MAX,
  deleteQuestionText,
  draftOf,
  editResultText,
  readDraft,
  shellEditErrorText,
  shellItemKey,
  shellItemTitle,
  shellItems,
} from '../../utils/roomShellEdit';
import type { ShellItem, ShellItemDraft } from '../../utils/roomShellEdit';

interface RoomShellEditDialogProps {
  open: boolean;
  rigId: number;
  rigName: string;
  /** The rig's stored room. Only one read from a scan has anything to edit. */
  shell: RoomShell | null | undefined;
  onClose: () => void;
  /** Called with the room as the server now has it, after each change that was stored. */
  onChanged: (shell: RoomShell) => void;
}

function errorText(err: unknown): string {
  if (axios.isAxiosError(err)) return shellEditErrorText(err.response?.status, err.response?.data?.detail);
  return shellEditErrorText(undefined, undefined);
}

export default function RoomShellEditDialog({
  open,
  rigId,
  rigName,
  shell,
  onClose,
  onChanged,
}: RoomShellEditDialogProps) {
  // What has been typed into a row and not yet saved, by the row's key. A row
  // with nothing typed shows what is stored.
  const [drafts, setDrafts] = useState<Record<string, ShellItemDraft>>({});
  // The row a request is out for: one change at a time, each built on the last one stored.
  const [busyWith, setBusyWith] = useState<{ key: string; what: 'save' | 'delete' } | null>(null);
  // The row whose Delete was pressed and is waiting for an answer.
  const [askDeleteKey, setAskDeleteKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // A dialog opened again starts clean.
  useEffect(() => {
    if (!open) return;
    setDrafts({});
    setBusyWith(null);
    setAskDeleteKey(null);
    setError(null);
    setNotice(null);
  }, [open, rigId]);

  const items = shellItems(shell);

  const setField = (item: ShellItem, field: keyof ShellItemDraft, value: string) => {
    const key = shellItemKey(item);
    setDrafts((current) => ({ ...current, [key]: { ...(current[key] ?? draftOf(item)), [field]: value } }));
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
      onChanged(result.room_shell);
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
      onChanged(result.room_shell);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusyWith(null);
    }
  };

  const busy = busyWith !== null;

  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} maxWidth="md" fullWidth>
      <DialogTitle>Edit the room of {rigName}</DialogTitle>

      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          What the room scan found, for you to correct: give a thing its real name, put it where it
          really is, or take out what is not there. Across is metres from the centre line (stage left
          is positive). Depth is metres from the middle of the floor (downstage is positive, upstage
          negative). A line keeps its length and the way it runs. No fixture moves with anything
          here, and reading the scan again replaces every change.
        </Typography>

        {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>}
        {notice && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setNotice(null)}>{notice}</Alert>}

        {items.length === 0 ? (
          <Alert severity="info">
            {shell?.source === 'scan'
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
                  <TableCell>What the scan found</TableCell>
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
                      <TableCell sx={{ minWidth: 180 }}>
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
                      <TableCell sx={{ width: 110 }}>
                        <TextField
                          size="small"
                          value={draft.x}
                          disabled={busy || !item.centre}
                          onChange={(e) => setField(item, 'x', e.target.value)}
                          inputProps={{ 'aria-label': `Across of ${title}`, inputMode: 'decimal' }}
                        />
                      </TableCell>
                      <TableCell sx={{ width: 110 }}>
                        <TextField
                          size="small"
                          value={draft.z}
                          disabled={busy || !item.centre}
                          onChange={(e) => setField(item, 'z', e.target.value)}
                          inputProps={{ 'aria-label': `Depth of ${title}`, inputMode: 'decimal' }}
                        />
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{item.detail}</Typography>
                        {!item.suggested && (
                          <Chip size="small" label="Moved by hand" sx={{ mt: 0.5 }} />
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
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}
