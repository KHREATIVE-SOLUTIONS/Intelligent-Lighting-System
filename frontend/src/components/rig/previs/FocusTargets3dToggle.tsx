/**
 * "Show focus targets in 3D", next to the 3D view's other controls
 * (docs/FOCUS_PRESETS.md, "In the app"). Not shown for a demo rig.
 */
import { FormControlLabel, Switch, Tooltip, Typography } from '@mui/material';

interface FocusTargets3dToggleProps {
  available: boolean;
  on: boolean;
  onChange: (on: boolean) => void;
}

export default function FocusTargets3dToggle({ available, on, onChange }: FocusTargets3dToggleProps) {
  if (!available) return null;
  return (
    <Tooltip
      describeChild
      title="Mark the points the focus presets aim at. Cyan: every moving head reaches it. Orange: some cannot. Red cross: none can."
    >
      <FormControlLabel
        sx={{ mr: 0 }}
        control={<Switch size="small" checked={on} onChange={(event) => onChange(event.target.checked)} />}
        label={<Typography variant="body2">Show focus targets in 3D</Typography>}
      />
    </Tooltip>
  );
}
