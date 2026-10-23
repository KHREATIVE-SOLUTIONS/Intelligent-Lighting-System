import { useState } from 'react';
import { Box, Button, CircularProgress, Tooltip, Typography } from '@mui/material';
import {
  AutoMode as AutoIcon,
  PanTool as ManualIcon,
  FlashOff as StrobeOffIcon,
  FlashOn as StrobeOnIcon,
  CleaningServices as CleanIcon,
} from '@mui/icons-material';
import { effectsApi } from '../../services/api';
import { useDMXStore } from '../../stores/dmxStore';
import { useHealthStore } from '../../stores/healthStore';
import { pollShowHealth } from '../../hooks/useShowHealth';

const pretty = (value: string | null | undefined) =>
  value
    ? value
        .toLowerCase()
        .split('_')
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(' ')
    : '';

type Busy = 'auto' | 'strobe' | 'clean' | null;

// What the autopilot is doing, and the takeovers that actually work while it
// runs. Only controls the engine honours in auto mode live here; drop, build
// and look holds are ignored by the engine in auto today, so a button for them
// would lie to the operator.
export default function AutopilotControl() {
  const status = useHealthStore((state) => state.effects);
  const reachable = useHealthStore((state) => state.reachable);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const section = useDMXStore((state) => state.proLighting.section);
  const genre = useDMXStore((state) => state.proLighting.genre);

  const run = (which: Busy, action: () => Promise<unknown>, failure: string) => {
    setBusy(which);
    setError(null);
    action()
      .then(pollShowHealth)
      .catch(() => setError(failure))
      .finally(() => setBusy(null));
  };

  const auto = status?.auto_mode ?? null;
  const strobeOn = status?.strobe_enabled ?? null;
  const engineStopped = status !== null && !status.running;

  const where = [section && section !== 'UNKNOWN' ? pretty(section) : '', pretty(genre)]
    .filter(Boolean)
    .join(' · ');

  const autoLabel =
    auto === null ? 'Autopilot ?' : auto ? `Autopilot on${where ? ` · ${where}` : ''}` : 'Manual';

  const buttonSx = { minHeight: 56, fontWeight: 700, fontSize: '1rem', borderWidth: 2, '&:hover': { borderWidth: 2 } };

  return (
    <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
      <Tooltip
        title={
          auto
            ? 'Tap to take over by hand. The look changes to the manual layers.'
            : 'Tap to hand the lights back to the autopilot.'
        }
      >
        <span>
          <Button
            variant="contained"
            color={auto ? 'success' : 'warning'}
            startIcon={busy === 'auto' ? <CircularProgress size={20} color="inherit" /> : auto ? <AutoIcon /> : <ManualIcon />}
            onClick={() =>
              run('auto', () => effectsApi.setAutoMode(!auto), 'Could not switch autopilot')
            }
            disabled={auto === null || busy !== null}
            aria-pressed={auto ?? undefined}
            data-testid="autopilot-toggle"
            sx={{ ...buttonSx, minWidth: 220, justifyContent: 'flex-start' }}
          >
            {autoLabel}
          </Button>
        </span>
      </Tooltip>

      <Button
        variant={strobeOn === false ? 'contained' : 'outlined'}
        color="warning"
        startIcon={busy === 'strobe' ? <CircularProgress size={20} color="inherit" /> : strobeOn === false ? <StrobeOffIcon /> : <StrobeOnIcon />}
        onClick={() =>
          run('strobe', () => effectsApi.setLayerEnabled('strobe', !strobeOn), 'Could not change strobes')
        }
        disabled={strobeOn === null || busy !== null}
        aria-pressed={strobeOn === false}
        data-testid="strobe-toggle"
        sx={buttonSx}
      >
        {strobeOn === false ? 'Strobes off' : 'Kill strobes'}
      </Button>

      <Tooltip title="Stop strobes and effects and drop to a plain, readable stage look.">
        <span>
          <Button
            variant="outlined"
            color="inherit"
            startIcon={busy === 'clean' ? <CircularProgress size={20} color="inherit" /> : <CleanIcon />}
            onClick={() => run('clean', effectsApi.cleanStage, 'Clean stage failed')}
            disabled={busy !== null}
            data-testid="clean-stage"
            sx={buttonSx}
          >
            Clean stage
          </Button>
        </span>
      </Tooltip>

      {engineStopped && (
        <Typography role="alert" variant="body2" color="error.main" fontWeight={700}>
          Effects engine is stopped
        </Typography>
      )}
      {!reachable && (
        <Typography role="alert" variant="body2" color="error.main" fontWeight={700}>
          Engine not reachable
        </Typography>
      )}
      {error && (
        <Typography role="alert" variant="body2" color="error.main" fontWeight={700}>
          {error}
        </Typography>
      )}
    </Box>
  );
}
