import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react';
import { Box, Button, CircularProgress, Slider, Typography } from '@mui/material';
import { PowerSettingsNew as BlackoutIcon } from '@mui/icons-material';
import { masterApi, MasterState } from '../../services/api';

export const MASTER_POLL_MS = 2000;
// A drag sends every 40ms; ignore polled levels for a moment after the last
// local change so the fader does not jump back under the operator's finger.
const LOCAL_HOLD_MS = 1500;

const isTypingTarget = (target: EventTarget | null) => {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
};

// Grand master and a blackout that holds. Both act on intensity only, so heads
// stay where they are. The server owns the state; this panel mirrors it and
// keeps polling, so a blackout from another screen or a box restart shows up.
// Blackout is never disabled: in a panic it must always be pressable.
interface MasterControlProps {
  // Folded strip: blackout and the master level only, no fader. Blackout and
  // its B key stay live either way.
  compact?: boolean;
  // Slot at the end of the row, used by Layout for the fold toggle.
  trailing?: ReactNode;
}

export default function MasterControl({ compact = false, trailing }: MasterControlProps) {
  const [state, setState] = useState<MasterState | null>(null);
  const [level, setLevel] = useState(100);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const sendTimer = useRef<number | undefined>(undefined);
  const lastLocalChange = useRef(0);

  const refresh = useCallback(
    () =>
      masterApi
        .get()
        .then((s) => {
          setState(s);
          if (Date.now() - lastLocalChange.current > LOCAL_HOLD_MS) {
            setLevel(Math.round(s.grand_master * 100));
          }
          setError(null);
        })
        .catch(() => setError('Engine not reachable')),
    []
  );

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(refresh, MASTER_POLL_MS);
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(sendTimer.current);
    };
  }, [refresh]);

  const handleLevel = (_: Event, value: number | number[]) => {
    const next = Array.isArray(value) ? value[0] : value;
    setLevel(next);
    lastLocalChange.current = Date.now();
    // Coalesce a drag into a few requests instead of one per pixel.
    window.clearTimeout(sendTimer.current);
    sendTimer.current = window.setTimeout(() => {
      masterApi
        .setGrandMaster(next / 100)
        .then((s) => {
          setState(s);
          setError(null);
        })
        .catch(() => setError('Could not set the grand master'));
    }, 40);
  };

  const blackedOut = state?.blackout ?? false;

  const toggleBlackout = useCallback(() => {
    // Unknown state means the box was unreachable: the safe guess is "go dark".
    const action = blackedOut ? masterApi.restore() : masterApi.blackout();
    setPending(true);
    action
      .then(refresh)
      .catch(() => setError(blackedOut ? 'Release failed, try again' : 'Blackout failed, try again'))
      .finally(() => setPending(false));
  }, [blackedOut, refresh]);

  // B toggles blackout from anywhere, unless the operator is typing.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.repeat || event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.key !== 'b' && event.key !== 'B') return;
      if (isTypingTarget(event.target)) return;
      event.preventDefault();
      toggleBlackout();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [toggleBlackout]);

  return (
    <Box
      component="div"
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: { xs: 2, sm: 3 },
        flexWrap: 'wrap',
        p: compact ? 1 : 1.5,
        borderRadius: 2,
        border: 2,
        borderColor: blackedOut ? 'error.main' : 'divider',
        bgcolor: blackedOut ? 'rgba(244, 67, 54, 0.15)' : 'background.paper',
      }}
    >
      <Button
        variant={blackedOut ? 'contained' : 'outlined'}
        color="error"
        size="large"
        startIcon={pending ? <CircularProgress size={22} color="inherit" /> : <BlackoutIcon />}
        onClick={toggleBlackout}
        aria-pressed={blackedOut}
        aria-keyshortcuts="B"
        title="Blackout (B)"
        sx={{
          minWidth: compact ? 160 : 200,
          minHeight: compact ? 48 : 64,
          fontSize: '1.1rem',
          fontWeight: 700,
          borderWidth: 2,
          '&:hover': { borderWidth: 2 },
        }}
      >
        {blackedOut ? 'Release blackout' : 'Blackout'}
      </Button>
      {compact ? (
        <Box component="div" sx={{ flex: 1, display: 'flex', alignItems: 'baseline', gap: 1 }}>
          <Typography variant="subtitle2" color="text.secondary">
            Master
          </Typography>
          <Typography variant="h6" fontWeight={700} data-testid="grand-master-level">
            {level}%
          </Typography>
          {blackedOut && (
            <Typography variant="subtitle2" color="error.main" fontWeight={700}>
              BLACKOUT ON
            </Typography>
          )}
        </Box>
      ) : (
        <Box component="div" sx={{ flex: 1, minWidth: 220 }}>
          <Box component="div" sx={{ display: 'flex', alignItems: 'baseline', gap: 1 }}>
            <Typography variant="subtitle2" color="text.secondary">
              Grand master
            </Typography>
            <Typography variant="h5" fontWeight={700} data-testid="grand-master-level">
              {level}%
            </Typography>
            {blackedOut && (
              <Typography variant="subtitle2" color="error.main" fontWeight={700}>
                BLACKOUT ON
              </Typography>
            )}
          </Box>
          <Slider
            value={level}
            onChange={handleLevel}
            min={0}
            max={100}
            aria-label="Grand master"
            sx={{
              height: 10,
              '& .MuiSlider-thumb': { width: 32, height: 32 },
            }}
          />
        </Box>
      )}
      {error && (
        <Typography role="alert" variant="body2" color="error.main" fontWeight={700}>
          {error}
        </Typography>
      )}
      {trailing}
    </Box>
  );
}
