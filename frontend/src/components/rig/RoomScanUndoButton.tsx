/**
 * Undo room scan moves: puts the fixtures a room scan moved back where they
 * stood before it (docs/ROOM_SCAN.md).
 *
 * Shown wherever the rig says there is something to undo: the Room Scan
 * dialog and the 3D view. It asks once before doing anything, because it moves
 * fixtures. A fixture a person has tapped, confirmed, dragged or moved since
 * the scan is left alone by the server and named in the answer.
 *
 * Nothing here reaches a device: stored positions change, no DMX is sent.
 */
import { useEffect, useState } from 'react';
import { Box, Button, Typography } from '@mui/material';
import { Undo as UndoIcon } from '@mui/icons-material';
import axios from 'axios';
import { roomScanApi } from '../../services/api';
import { undoButtonText, undoQuestionText } from '../../utils/roomScan';
import type { RoomScanUndoResult } from '../../utils/roomScan';

interface RoomScanUndoButtonProps {
  rigId: number;
  /** How many fixture moves the rig's undo record holds. With none, nothing is drawn. */
  moves: number;
  disabled?: boolean;
  /** Called before the request is sent, so anything still unsaved can be written first. */
  onBefore?: () => void | Promise<void>;
  /** The fixtures were put back: the rig has changed and should be read again. */
  onDone: (result: RoomScanUndoResult) => void;
  onError?: (message: string) => void;
  size?: 'small' | 'medium';
}

export function undoErrorText(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    const status = err.response?.status;
    if (status === 409) {
      return 'A locate walkthrough is running on this rig. Finish or end it, then undo the room scan moves.';
    }
    if (status === 404) return 'This rig no longer exists.';
    if (status === 401 || status === 403) return 'Sign in again to undo the room scan moves.';
    if (status !== undefined) return 'The moves could not be undone. Nothing was changed.';
  }
  return 'The server could not be reached. Nothing was changed.';
}

export default function RoomScanUndoButton({
  rigId,
  moves,
  disabled = false,
  onBefore,
  onDone,
  onError,
  size = 'medium',
}: RoomScanUndoButtonProps) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A different rig, or an undo record that has changed, starts the question over.
  useEffect(() => {
    setAsking(false);
    setError(null);
  }, [rigId, moves]);

  if (moves <= 0) return null;

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await onBefore?.();
      const result = await roomScanApi.undoMoves(rigId);
      setAsking(false);
      onDone(result);
    } catch (err) {
      const message = undoErrorText(err);
      setError(message);
      onError?.(message);
    } finally {
      setBusy(false);
    }
  };

  if (!asking) {
    return (
      <Button
        size={size}
        color="warning"
        startIcon={<UndoIcon />}
        disabled={disabled || busy}
        onClick={() => { setError(null); setAsking(true); }}
      >
        {undoButtonText(moves)}
      </Button>
    );
  }

  return (
    <Box
      role="group"
      aria-label="Undo room scan moves"
      sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}
    >
      <Typography variant="body2" sx={{ maxWidth: 520 }}>
        {error ?? undoQuestionText(moves)}
      </Typography>
      <Button size={size} variant="contained" color="warning" disabled={disabled || busy} onClick={() => { void run(); }}>
        {busy ? 'Putting them back...' : error ? 'Try again' : 'Put them back'}
      </Button>
      <Button size={size} disabled={busy} onClick={() => { setAsking(false); setError(null); }}>
        Cancel
      </Button>
    </Box>
  );
}
