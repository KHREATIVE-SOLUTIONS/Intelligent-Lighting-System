/**
 * The look controls in the visualizer's toolbar (docs/PREVIZ_LOOK.md): the
 * Haze slider always in view, and a Look button opening the rest.
 */
import { useState } from 'react';
import {
  Box, Button, FormControlLabel, Popover, Slider, Switch, Tooltip, Typography,
} from '@mui/material';
import { DEFAULT_EXPOSURE, DEFAULT_LOOK, EXPOSURE_MAX, EXPOSURE_MIN } from './lookSettings';
import type { LookSettings } from './lookSettings';

const percent = (value: number) => `${Math.round(value * 100)}%`;

export default function LookControls({
  settings,
  onChange,
  bloom,
  onBloom,
}: {
  settings: LookSettings;
  onChange: (next: Partial<LookSettings>) => void;
  /** Bloom at the current quality (it is kept per quality). */
  bloom: boolean;
  onBloom: (on: boolean) => void;
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
          <Typography variant="caption" color="text.secondary" id="previz-exposure-label">
            Exposure {settings.exposure.toFixed(2)}
          </Typography>
          <Slider
            size="small"
            aria-labelledby="previz-exposure-label"
            min={EXPOSURE_MIN}
            max={EXPOSURE_MAX}
            step={0.05}
            marks={[{ value: DEFAULT_EXPOSURE, label: '' }]}
            value={settings.exposure}
            onChange={(_, value) => onChange({ exposure: Array.isArray(value) ? value[0] : value })}
            data-testid="previz-exposure"
          />
          <Tooltip describeChild placement="left" title="Glow round the lenses and the beam cores. About a millisecond a frame; starts off in Perf. Kept per quality.">
            <FormControlLabel
              control={<Switch size="small" checked={bloom} onChange={(_, on) => onBloom(on)} />}
              label="Bloom"
            />
          </Tooltip>
          <Tooltip describeChild placement="left" title="Beams bright at the lens, fading with distance and toward the edge of the cone. Off: one flat strength end to end.">
            <FormControlLabel
              control={<Switch size="small" checked={settings.softBeams} onChange={(_, on) => onChange({ softBeams: on })} />}
              label="Soft beams"
            />
          </Tooltip>
          <Tooltip describeChild placement="left" title="Show the selected gobo in the pool of light, turning with the gobo rotation channel. Off: open pools.">
            <FormControlLabel
              control={<Switch size="small" checked={settings.gobos} onChange={(_, on) => onChange({ gobos: on })} />}
              label="Gobos"
            />
          </Tooltip>
          <Tooltip describeChild placement="left" title="A few big soft haze clouds drifting slowly, lit by the rig. Costs fill rate.">
            <FormControlLabel
              control={<Switch size="small" checked={settings.hazeDrift} onChange={(_, on) => onChange({ hazeDrift: on })} />}
              label="Drifting haze"
            />
          </Tooltip>
          <Button
            size="small"
            onClick={() => {
              onChange({
                haze: DEFAULT_LOOK.haze,
                exposure: DEFAULT_LOOK.exposure,
                softBeams: DEFAULT_LOOK.softBeams,
                gobos: DEFAULT_LOOK.gobos,
                hazeDrift: DEFAULT_LOOK.hazeDrift,
                bloom: {},
              });
            }}
          >
            Reset look
          </Button>
        </Box>
      </Popover>
    </Box>
  );
}
