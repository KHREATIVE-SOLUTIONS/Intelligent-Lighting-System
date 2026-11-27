/**
 * "Show stage plot in 3D", next to the 3D view's other controls
 * (docs/STAGE_PLOT.md). Not shown for a rig with no stage plot. A plot not
 * calibrated yet cannot be laid in metres, so the switch is off and says where
 * to calibrate it.
 */
import { Box, FormControlLabel, Switch, Typography } from '@mui/material';
import type { StagePlot3dStatus } from './useStagePlot3d';

export const CALIBRATE_FIRST = 'Calibrate the stage plot in the 2D plan first';

interface StagePlot3dToggleProps {
  status: StagePlot3dStatus;
  on: boolean;
  onChange: (on: boolean) => void;
}

export default function StagePlot3dToggle({ status, on, onChange }: StagePlot3dToggleProps) {
  if (status === 'none') return null;
  const calibrated = status === 'calibrated';
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <FormControlLabel
        sx={{ mr: 0 }}
        control={(
          <Switch
            size="small"
            checked={calibrated && on}
            disabled={!calibrated}
            onChange={(event) => onChange(event.target.checked)}
            inputProps={calibrated ? undefined : { 'aria-describedby': 'stage-plot-3d-why' }}
          />
        )}
        label={<Typography variant="body2">Show stage plot in 3D</Typography>}
      />
      {!calibrated && (
        <Typography id="stage-plot-3d-why" variant="caption" color="text.secondary">
          {CALIBRATE_FIRST}
        </Typography>
      )}
    </Box>
  );
}
