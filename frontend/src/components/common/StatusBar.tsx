import { useEffect, useState } from 'react';
import { Box, ButtonBase, Tooltip, Typography } from '@mui/material';
import {
  CheckCircle as OkIcon,
  Warning as WarnIcon,
  Error as DownIcon,
  HelpOutline as UnknownIcon,
} from '@mui/icons-material';
import { useHealthStore } from '../../stores/healthStore';
import { audioWebSocket } from '../../services/websocket';
import {
  readAudioHealth,
  readDmxHealth,
  readLinkHealth,
  type HealthLevel,
  type HealthReading,
} from '../../utils/showHealth';

const LEVEL_COLOR: Record<HealthLevel, string> = {
  ok: 'success.main',
  warn: 'warning.main',
  down: 'error.main',
  unknown: 'grey.600',
};

const LEVEL_ICON: Record<HealthLevel, typeof OkIcon> = {
  ok: OkIcon,
  warn: WarnIcon,
  down: DownIcon,
  unknown: UnknownIcon,
};

function Pill({ reading, onClick, testId }: { reading: HealthReading; onClick?: () => void; testId: string }) {
  const Icon = LEVEL_ICON[reading.level];
  const color = LEVEL_COLOR[reading.level];
  return (
    <Tooltip title={reading.detail}>
      {/* The span lets the tooltip work on a pill that is not tappable. */}
      <span>
        <ButtonBase
          onClick={onClick}
          disabled={!onClick}
          aria-label={`${reading.label}. ${reading.detail}`}
          data-testid={testId}
          data-level={reading.level}
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 0.75,
            px: 1.5,
            minHeight: 40,
            borderRadius: 20,
            border: 2,
            borderColor: color,
            // Solid fill when something is wrong so it reads from across the booth.
            bgcolor: reading.level === 'down' ? color : 'transparent',
            color: reading.level === 'down' ? 'common.white' : color,
            animation: reading.level === 'down' ? 'statusPulse 1.2s ease-in-out infinite' : 'none',
            '@keyframes statusPulse': { '50%': { opacity: 0.6 } },
            '&.Mui-disabled': { color: reading.level === 'down' ? 'common.white' : color },
          }}
        >
          <Icon sx={{ fontSize: 20 }} />
          {/* Phones get icons only so the bar stays one line; tablets and up get words. */}
          <Typography variant="body2" fontWeight={700} noWrap sx={{ display: { xs: 'none', sm: 'block' } }}>
            {reading.label}
        </Typography>
      </ButtonBase>
      </span>
    </Tooltip>
  );
}

// Always-on health readout for the app bar: light out, audio in, and the link
// to the engine. Colour plus icon plus words, so it still reads under coloured
// stage wash or to someone colour-blind.
export default function StatusBar() {
  const { reachable, dmx, capture, link, lastAnalysisAt } = useHealthStore();
  const [now, setNow] = useState(() => Date.now());

  // Re-evaluate staleness even when no new data arrives; that is exactly when
  // it matters.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const dmxReading = readDmxHealth(dmx, reachable);
  const audioReading = readAudioHealth(capture, reachable, lastAnalysisAt, now);
  const linkReading = readLinkHealth(link, reachable);
  const canRetry = reachable && link !== 'connected';

  return (
    <Box
      component="div"
      role="status"
      aria-live="polite"
      sx={{ display: 'flex', gap: 1, alignItems: 'center', justifyContent: 'flex-end', flexWrap: 'nowrap' }}
    >
      <Pill reading={dmxReading} testId="status-dmx" />
      <Pill reading={audioReading} testId="status-audio" />
      <Pill
        reading={linkReading}
        testId="status-link"
        onClick={canRetry ? () => audioWebSocket.retryNow() : undefined}
      />
    </Box>
  );
}
