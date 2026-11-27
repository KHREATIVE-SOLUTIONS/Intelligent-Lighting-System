import { useState } from 'react';
import { Alert, Box, Button, CircularProgress, Typography } from '@mui/material';
import { Download as DownloadIcon } from '@mui/icons-material';
import axios from 'axios';
import { readinessApi } from '../../services/api';
import { saveBlob } from '../../utils/download';
import { handoffWarning } from '../../utils/readiness';

interface HandoffPackButtonProps {
  rigId: number;
  /** How many readiness checks fail. Any shows a warning line first; it never blocks. */
  failCount?: number | null;
}

/**
 * "Download handoff pack": one zip with the patch, groups, readiness report and the
 * grandMA2 and MVR files (GET /api/rigs/{id}/handoff-pack, docs/HANDOFF_PACK.md).
 * Reads only. One press, no confirm step.
 */
export default function HandoffPackButton({ rigId, failCount }: HandoffPackButtonProps) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ severity: 'success' | 'error'; text: string } | null>(null);
  const warning = handoffWarning(failCount);

  const download = async () => {
    setBusy(true);
    setNote(null);
    try {
      const file = await readinessApi.handoffPack(rigId);
      saveBlob(file.blob, file.filename);
      setNote({ severity: 'success', text: `${file.filename} downloaded.` });
    } catch (err) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      setNote({
        severity: 'error',
        text: status === 404 ? 'This rig is no longer there.' : 'The handoff pack did not download. Try again.',
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Box data-testid="handoff-pack">
      {warning && (
        <Alert severity="warning" data-testid="handoff-pack-warning" sx={{ mb: 1 }}>
          {warning}
        </Alert>
      )}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Button
          variant="outlined"
          size="small"
          startIcon={busy ? <CircularProgress size={14} /> : <DownloadIcon />}
          disabled={busy}
          onClick={() => { void download(); }}
        >
          Download handoff pack
        </Button>
        <Typography variant="caption" color="text.secondary">
          Patch, groups, this report, grandMA2 and MVR files, in one zip.
        </Typography>
      </Box>
      {note && (
        <Alert severity={note.severity} data-testid="handoff-pack-note" sx={{ mt: 1 }} onClose={() => setNote(null)}>
          {note.text}
        </Alert>
      )}
    </Box>
  );
}
