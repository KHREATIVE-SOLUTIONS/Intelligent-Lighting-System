import { useEffect, useRef, useState } from 'react';
import { Box, Button, Slider, Typography } from '@mui/material';
import { PowerSettingsNew as BlackoutIcon } from '@mui/icons-material';
import { masterApi, MasterState } from '../../services/api';

// Grand master and a blackout that holds. Both act on intensity only, so heads
// stay where they are. The server owns the state; this panel only mirrors it.
export default function MasterControl() {
  const [state, setState] = useState<MasterState | null>(null);
  const [level, setLevel] = useState(100);
  const [error, setError] = useState<string | null>(null);
  const sendTimer = useRef<number | undefined>(undefined);

  const refresh = () =>
    masterApi
      .get()
      .then((s) => {
        setState(s);
        setLevel(Math.round(s.grand_master * 100));
        setError(null);
      })
      .catch(() => setError('Engine not reachable'));

  useEffect(() => {
    refresh();
    return () => window.clearTimeout(sendTimer.current);
  }, []);

  const handleLevel = (_: Event, value: number | number[]) => {
    const next = Array.isArray(value) ? value[0] : value;
    setLevel(next);
    // Coalesce a drag into a few requests instead of one per pixel.
    window.clearTimeout(sendTimer.current);
    sendTimer.current = window.setTimeout(() => {
      masterApi
        .setGrandMaster(next / 100)
        .then(setState)
        .catch(() => setError('Could not set the grand master'));
    }, 40);
  };

  const toggleBlackout = () => {
    const action = state?.blackout ? masterApi.restore() : masterApi.blackout();
    action.then(refresh).catch(() => setError('Blackout request failed'));
  };

  const blackedOut = state?.blackout ?? false;

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 3, flexWrap: 'wrap' }}>
      <Button
        variant={blackedOut ? 'contained' : 'outlined'}
        color="error"
        size="large"
        startIcon={<BlackoutIcon />}
        onClick={toggleBlackout}
        disabled={state === null}
        sx={{ minWidth: 180 }}
      >
        {blackedOut ? 'Release blackout' : 'Blackout'}
      </Button>
      <Box sx={{ flex: 1, minWidth: 220 }}>
        <Typography variant="subtitle2" gutterBottom>
          Grand master {level}%
        </Typography>
        <Slider
          value={level}
          onChange={handleLevel}
          min={0}
          max={100}
          disabled={state === null}
          aria-label="Grand master"
        />
      </Box>
      {error && (
        <Typography variant="caption" color="error">
          {error}
        </Typography>
      )}
    </Box>
  );
}
