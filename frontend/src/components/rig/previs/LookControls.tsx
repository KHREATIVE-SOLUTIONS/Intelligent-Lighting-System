/**
 * The look controls in the visualizer's toolbar (docs/PREVIZ_LOOK.md): the
 * Haze slider always in view, and a Look button opening the rest.
 */
import { useState } from 'react';
import {
  Box, Button, FormControlLabel, Popover, Slider, Switch, Tooltip, Typography,
} from '@mui/material';
import type { LookSettings } from './lookSettings';

const percent = (value: number) => `${Math.round(value * 100)}%`;

export default function LookControls({
  settings,
  onChange,
}: {
  settings: LookSettings;
  onChange: (next: Partial<LookSettings>) => void;
}) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Tooltip describeChild title="How much haze is in the room. 0 is clean air: beams show only at the lens and where they land.">
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 150 }}>
          <Typography variant="body2" component="label" id="previz-haze-label">Haze</Typography>
          <Slider
            size="small"
            aria-labelledby="previz-haze-label"
            min={0}
            max={1}
            step={0.01}
            value={settings.haze}
            valueLabelDisplay="auto"
            valueLabelFormat={percent}
            onChange={(_, value) => onChange({ haze: Array.isArray(value) ? value[0] : value })}
            sx={{ width: 100 }}
            data-testid="previz-haze"
          />
        </Box>
      </Tooltip>
      <Button
        size="small"
        variant={anchor ? 'contained' : 'outlined'}
        aria-haspopup="dialog"
        onClick={(event) => setAnchor(event.currentTarget)}
      >
        Look
      </Button>
      <Popover
        open={anchor !== null}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      >
        <Box sx={{ p: 2, width: 260, display: 'grid', gap: 0.5 }}>
          <Typography variant="subtitle2">Look</Typography>
          <Tooltip describeChild placement="left" title="A few big soft haze clouds drifting slowly, lit by the rig. Costs fill rate.">
            <FormControlLabel
              control={<Switch size="small" checked={settings.hazeDrift} onChange={(_, on) => onChange({ hazeDrift: on })} />}
              label="Drifting haze"
            />
          </Tooltip>
        </Box>
      </Popover>
    </Box>
  );
}
