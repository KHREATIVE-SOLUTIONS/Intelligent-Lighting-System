import { useState } from 'react';
import { Alert, Box, Button, CircularProgress } from '@mui/material';
import { Print as PrintIcon } from '@mui/icons-material';
import axios from 'axios';
import { readinessApi } from '../../services/api';

interface PatchSheetButtonProps {
  rigId: number;
}

// Long enough for the new tab to load the page and for a Save As; then the memory goes.
const REVOKE_AFTER_MS = 5 * 60 * 1000;

/**
 * "Open printable patch sheet": GET /api/rigs/{id}/patch-sheet in a new tab, one
 * universe per printed page (docs/HANDOFF_PACK.md). Reads only.
 *
 * Every /api route needs the operator token, which only the axios client carries, so
 * a bare link would open on a 401. The sheet is fetched here and shown from a blob
 * URL. The tab is opened in the click itself, before the fetch, so a popup blocker
 * lets it through; the page has no script, so the tab gets nothing from its opener.
 */
export default function PatchSheetButton({ rigId }: PatchSheetButtonProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = async () => {
    setBusy(true);
    setError(null);
    const tab = window.open('', '_blank');
    try {
      const url = URL.createObjectURL(await readinessApi.patchSheet(rigId));
      if (tab) {
        tab.location.href = url;
      } else if (!window.open(url, '_blank')) {
        setError('The browser blocked the new tab. Allow pop-ups for this page and try again.');
      }
      window.setTimeout(() => URL.revokeObjectURL(url), REVOKE_AFTER_MS);
    } catch (err) {
      tab?.close();
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      setError(status === 404 ? 'This rig is no longer there.' : 'The patch sheet did not open. Try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Button
        variant="outlined"
        size="small"
        startIcon={busy ? <CircularProgress size={14} /> : <PrintIcon />}
        disabled={busy}
        onClick={() => { void open(); }}
      >
        Open printable patch sheet
      </Button>
      {error && (
        <Box sx={{ flexBasis: '100%' }}>
          <Alert severity="error" data-testid="patch-sheet-error" onClose={() => setError(null)}>
            {error}
          </Alert>
        </Box>
      )}
    </>
  );
}
