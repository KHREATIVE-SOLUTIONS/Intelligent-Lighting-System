import { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
} from '@mui/material';
import { rigsApi } from '../../services/api';

interface RigFixtureQrDialogProps {
  rigId: number;
  /** The rig fixture to show, or null when the dialog is closed. */
  fixture: { id: number; name?: string | null } | null;
  onClose: () => void;
}

/**
 * One rig fixture's label QR (GET /rigs/{rig_id}/fixtures/{id}/qr-code), the
 * same code the label sheet prints, token included, with a Download PNG button.
 * MUI's Dialog closes on Escape and labels itself from the title.
 */
export default function RigFixtureQrDialog({ rigId, fixture, onClose }: RigFixtureQrDialogProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Kept through the close so the fading dialog still shows the code, its
  // title and its file name; the image is freed when the next fixture opens
  // or the dialog unmounts.
  const [shown, setShown] = useState(fixture);
  useEffect(() => {
    if (fixture) setShown(fixture);
  }, [fixture]);
  const fixtureId = (fixture ?? shown)?.id ?? null;

  useEffect(() => {
    if (fixtureId === null) return undefined;
    let cancelled = false;
    let made: string | null = null;
    setUrl(null);
    setError(null);
    rigsApi
      .rigFixtureQrPng(rigId, fixtureId)
      .then((blob) => {
        if (cancelled) return;
        made = URL.createObjectURL(blob);
        setUrl(made);
      })
      .catch(() => {
        if (!cancelled) setError('Could not load the QR code.');
      });
    return () => {
      cancelled = true;
      if (made) URL.revokeObjectURL(made);
    };
  }, [rigId, fixtureId]);

  const label = (fixture ?? shown)?.name || (fixtureId !== null ? `Fixture ${fixtureId}` : '');
  const filename = `rig_${rigId}_fixture_${fixtureId}_qr.png`;

  return (
    <Dialog open={fixture !== null} onClose={onClose} aria-labelledby="rig-fixture-qr-title">
      <DialogTitle id="rig-fixture-qr-title">QR label: {label}</DialogTitle>
      <DialogContent>
        <Box sx={{ width: 300, height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {url && (
            <img
              src={url}
              alt={`QR code label for ${label}`}
              width={300}
              height={300}
              style={{ imageRendering: 'pixelated' }}
            />
          )}
          {!url && !error && <CircularProgress aria-label="Loading QR code" />}
          {error && <Alert severity="error">{error}</Alert>}
        </Box>
        <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 1, maxWidth: 300 }}>
          Scanning this names this fixture only. A label of a deleted fixture never matches the one
          that took its id.
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button
          component="a"
          href={url ?? undefined}
          download={filename}
          disabled={!url}
        >
          Download PNG
        </Button>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
