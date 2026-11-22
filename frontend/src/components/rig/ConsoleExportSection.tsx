import { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';
import { Download as DownloadIcon, Close as CloseIcon } from '@mui/icons-material';
import axios from 'axios';
import { consoleExportApi } from '../../services/api';
import { CONSOLE_EXPORT_OPTIONS, summaryHeadline } from '../../utils/consoleExport';
import type {
  ConsoleExportKind,
  ConsoleExportSummary,
  ConsoleExportTarget,
} from '../../utils/consoleExport';

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function targetKey(target: ConsoleExportTarget): string {
  return 'rigId' in target ? `rig:${target.rigId}` : `preset:${target.preset}`;
}

interface ConsoleExportSectionProps {
  target: ConsoleExportTarget;
}

/**
 * Download buttons for sending a rig back to a console: grandMA2 XML, a
 * grandMA2 command-line script, and an MVR. The files are written by the
 * server from the rig as it is at that moment, the same rig the layout view
 * and the 3D view show.
 */
export function ConsoleExportSection({ target }: ConsoleExportSectionProps) {
  const [summary, setSummary] = useState<ConsoleExportSummary | null>(null);
  const [busy, setBusy] = useState<ConsoleExportKind | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [markNames, setMarkNames] = useState(false);
  const key = targetKey(target);

  useEffect(() => {
    let current = true;
    setSummary(null);
    setError(null);
    setDone(null);
    consoleExportApi
      .summary(target)
      .then((data) => {
        if (current) setSummary(data);
      })
      .catch(() => {
        // The downloads still work without it; they say the same in their notes.
        if (current) setSummary(null);
      });
    return () => {
      current = false;
    };
    // `key` stands for `target`, which is a new object on every render.
  }, [key]);

  const download = async (kind: ConsoleExportKind) => {
    setBusy(kind);
    setError(null);
    setDone(null);
    try {
      const file = await consoleExportApi.download(target, kind, markNames);
      saveBlob(file.blob, file.filename);
      setDone(`${file.filename} downloaded.`);
    } catch (err) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      setError(status === 404 ? 'This rig is no longer there to export.' : 'The export failed.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <Box>
      <Typography variant="subtitle2" gutterBottom>
        Export to a console
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        Patch, 3D positions, rotations and groups, from the rig as it is now.
        {summary ? ` ${summaryHeadline(summary)}` : ''} Not tested on a desk: read
        docs/CONSOLE_EXPORT.md for what still has to be done there.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 1.5 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {done && (
        <Alert severity="success" sx={{ mb: 1.5 }} onClose={() => setDone(null)}>
          {done}
        </Alert>
      )}
      {summary && summary.disclaimer && (
        <Alert severity="warning" sx={{ mb: 1.5 }}>
          {summary.disclaimer}
        </Alert>
      )}
      {summary && summary.notes.length > 0 && (
        <Alert severity="info" sx={{ mb: 1.5 }}>
          {summary.notes.map((note) => (
            <Typography key={note} variant="body2" sx={{ display: 'block' }}>
              {note}
            </Typography>
          ))}
        </Alert>
      )}

      <Stack spacing={1.5}>
        {CONSOLE_EXPORT_OPTIONS.map((option) => (
          <Button
            key={option.kind}
            variant="outlined"
            fullWidth
            startIcon={<DownloadIcon />}
            onClick={() => download(option.kind)}
            disabled={busy !== null}
            sx={{ justifyContent: 'flex-start', py: 1.5 }}
          >
            <Box sx={{ textAlign: 'left' }}>
              <Typography variant="body1" fontWeight="bold">
                {option.title}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {option.detail}
              </Typography>
            </Box>
          </Button>
        ))}
      </Stack>

      {summary && summary.position_unconfirmed > 0 && (
        <FormControlLabel
          sx={{ mt: 1 }}
          control={
            <Checkbox
              size="small"
              checked={markNames}
              onChange={(event) => setMarkNames(event.target.checked)}
            />
          }
          label={
            <Typography variant="body2">
              Add &quot;(position unconfirmed)&quot; to the names of the {summary.position_unconfirmed}{' '}
              fixture{summary.position_unconfirmed === 1 ? '' : 's'} nobody has checked
            </Typography>
          }
        />
      )}

      {busy && <LinearProgress sx={{ mt: 1.5 }} />}
    </Box>
  );
}

interface ConsoleExportButtonProps {
  target: ConsoleExportTarget;
}

/** A small "Export" button that opens the console export in a dialog. */
export function ConsoleExportButton({ target }: ConsoleExportButtonProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        size="small"
        variant="outlined"
        startIcon={<DownloadIcon />}
        onClick={() => setOpen(true)}
      >
        Export
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Export to a console</DialogTitle>
        <DialogContent>{open && <ConsoleExportSection target={target} />}</DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)} startIcon={<CloseIcon />}>
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export default ConsoleExportSection;
