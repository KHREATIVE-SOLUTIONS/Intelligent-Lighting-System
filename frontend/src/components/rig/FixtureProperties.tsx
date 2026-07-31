import {
  Box,
  Typography,
  TextField,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  FormControlLabel,
  Switch,
} from '@mui/material';
import type { RigFixture, Fixture } from '../../types';

/**
 * What a light points at, said in the words the owner would use. The values are
 * the engine's PerformerZone vocabulary; the labels are not, because "this one
 * is on the singer" is the whole point and "downstage_center" is not that.
 *
 * Optional throughout: leaving it on "Not set" is exactly how the rig behaved
 * before zones existed.
 */
const ZONE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'Not set' },
  { value: 'stage_center', label: 'The singer / centre stage' },
  { value: 'stage_left', label: 'Stage left' },
  { value: 'stage_right', label: 'Stage right' },
  { value: 'downstage_center', label: 'Front of the stage' },
  { value: 'upstage_center', label: 'Back of the stage' },
  { value: 'drum_riser', label: 'The drums' },
  { value: 'keyboard', label: 'The keyboard' },
  { value: 'dj_booth', label: 'The DJ booth' },
  { value: 'dance_floor', label: 'The dance floor' },
  { value: 'bar', label: 'The bar' },
  { value: 'audience', label: 'The audience' },
  { value: 'entrance', label: 'The way in / out' },
];

interface FixturePropertiesProps {
  fixture: RigFixture;
  availableModes?: Fixture['modes'];
  onChange: (updates: Partial<RigFixture>) => void;
}

export default function FixtureProperties({ fixture, availableModes = [], onChange }: FixturePropertiesProps) {
  return (
    <Box sx={{ p: 1.5 }}>
      <Typography variant="subtitle2" gutterBottom>
        {fixture.name || fixture.fixture?.model || `Fixture ${fixture.id}`}
      </Typography>

      <Grid container spacing={1}>
        <Grid item xs={6}>
          <TextField
            size="small"
            label="Name"
            fullWidth
            value={fixture.name || ''}
            onChange={(e) => onChange({ name: e.target.value })}
          />
        </Grid>
        <Grid item xs={3}>
          <TextField
            size="small"
            label="Universe"
            type="number"
            fullWidth
            value={fixture.universe}
            onChange={(e) => onChange({ universe: Number(e.target.value) })}
            inputProps={{ min: 0, max: 15 }}
          />
        </Grid>
        <Grid item xs={3}>
          <TextField
            size="small"
            label="Address"
            type="number"
            fullWidth
            value={fixture.dmx_address}
            onChange={(e) => onChange({ dmx_address: Number(e.target.value) })}
            inputProps={{ min: 1, max: 512 }}
          />
        </Grid>

        {availableModes.length > 0 && (
          <Grid item xs={4}>
            <FormControl size="small" fullWidth>
              <InputLabel>Mode</InputLabel>
              <Select
                value={fixture.mode_id || ''}
                label="Mode"
                onChange={(e) => onChange({ mode_id: Number(e.target.value) || undefined })}
              >
                {availableModes.map((m) => (
                  <MenuItem key={m.id} value={m.id}>
                    {m.name} ({m.channel_count}ch)
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
        )}

        <Grid item xs={4}>
          <TextField
            size="small"
            label="Group"
            fullWidth
            value={fixture.group_name || ''}
            onChange={(e) => onChange({ group_name: e.target.value })}
          />
        </Grid>

        <Grid item xs={12}>
          <FormControl size="small" fullWidth>
            <InputLabel>Points at</InputLabel>
            <Select
              value={fixture.zone || ''}
              label="Points at"
              onChange={(e) => onChange({ zone: String(e.target.value) })}
            >
              {ZONE_OPTIONS.map((option) => (
                <MenuItem key={option.value || 'none'} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>

        <Grid item xs={4}>
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={fixture.is_address_locked}
                onChange={(e) => onChange({ is_address_locked: e.target.checked })}
              />
            }
            label="Lock Addr"
            sx={{ '& .MuiTypography-root': { fontSize: '0.75rem' } }}
          />
        </Grid>

        <Grid item xs={4}>
          <TextField
            size="small"
            label="X"
            type="number"
            fullWidth
            value={fixture.position_x}
            onChange={(e) => onChange({ position_x: Number(e.target.value) })}
            inputProps={{ step: 0.1 }}
          />
        </Grid>
        <Grid item xs={4}>
          <TextField
            size="small"
            label="Y (Height)"
            type="number"
            fullWidth
            value={fixture.position_y}
            onChange={(e) => onChange({ position_y: Number(e.target.value) })}
            inputProps={{ step: 0.1 }}
          />
        </Grid>
        <Grid item xs={4}>
          <TextField
            size="small"
            label="Z (Depth)"
            type="number"
            fullWidth
            value={fixture.position_z}
            onChange={(e) => onChange({ position_z: Number(e.target.value) })}
            inputProps={{ step: 0.1 }}
          />
        </Grid>
      </Grid>
    </Box>
  );
}
