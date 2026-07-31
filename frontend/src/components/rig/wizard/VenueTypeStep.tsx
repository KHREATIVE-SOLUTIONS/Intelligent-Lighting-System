import { useCallback, useEffect, useState } from 'react';
import {
  Alert, AlertTitle, Button, Card, CardActionArea, CardContent, CircularProgress,
  Grid, Stack, Typography, Box,
} from '@mui/material';
import { Refresh as RefreshIcon } from '@mui/icons-material';
import { wizardApi } from '../../../services/api';
import { describeType } from './PickFixturesStep';
import type { VenuePreset } from '../../../types';

interface VenueTypeStepProps {
  selected: VenuePreset | null;
  onSelect: (preset: VenuePreset) => void;
  onClear: () => void;
}

const VENUE_ICONS: Record<string, string> = {
  small_club: '🎤',
  medium_venue: '🎵',
  church: '⛪',
  theater: '🎭',
  festival_stage: '🎪',
  large_venue: '🏟️',
  nightclub: '🪩',
  outdoor: '🌙',
};

const DEFAULT_ICON = '💡';
const CUSTOM_ICON = '✏️';

const summariseKit = (preset: VenuePreset): string => {
  const parts = (preset.suggested_fixtures || []).map(
    (s) => `${s.count} ${describeType(s.fixture_type)}${s.count === 1 ? '' : 's'}`
  );
  if (parts.length === 0) return 'No lights suggested.';
  return parts.join(', ');
};

export default function VenueTypeStep({ selected, onSelect, onClear }: VenueTypeStepProps) {
  const [presets, setPresets] = useState<VenuePreset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await wizardApi.getVenuePresets();
      setPresets(data.presets || []);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
        err?.message ||
        'The venue presets could not be reached.'
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Box>
      <Typography variant="h6" gutterBottom>What sort of room is this?</Typography>
      <Typography variant="body2" color="text.secondary">
        Pick the closest match and we will suggest a stage size and a set of lights. You can
        change everything on the next screens, so nothing here locks you in.
      </Typography>

      {loading && (
        <Stack direction="row" spacing={1.5} alignItems="center" sx={{ my: 3 }}>
          <CircularProgress size={20} />
          <Typography variant="body2" color="text.secondary">Loading venue types...</Typography>
        </Stack>
      )}

      {!loading && error && (
        <Alert
          severity="error"
          sx={{ mt: 2 }}
          action={
            <Button color="inherit" size="small" startIcon={<RefreshIcon />} onClick={load}>
              Try again
            </Button>
          }
        >
          <AlertTitle>We could not load the venue types</AlertTitle>
          {error} You can still press Next and set the stage size and lights yourself.
        </Alert>
      )}

      {!loading && !error && presets.length === 0 && (
        <Alert severity="info" sx={{ mt: 2 }}>
          No venue types came back from the box. Press Next and set the stage size and
          lights yourself.
        </Alert>
      )}

      {selected && (
        <Alert severity="success" sx={{ mt: 2 }} onClose={onClear}>
          <AlertTitle>{selected.name} selected</AlertTitle>
          Suggested kit: {summariseKit(selected)}. Picking a different room type replaces
          this suggested list.
        </Alert>
      )}

      <Grid container spacing={2} sx={{ mt: 1 }}>
        {presets.map((preset) => (
          <Grid item xs={6} sm={4} md={3} key={preset.key}>
            <Card
              sx={{
                height: '100%',
                border: '2px solid',
                borderColor: selected?.key === preset.key ? 'primary.main' : 'transparent',
              }}
            >
              <CardActionArea onClick={() => onSelect(preset)} sx={{ height: '100%' }}>
                <CardContent sx={{ textAlign: 'center', py: 2 }}>
                  <Typography variant="h4" sx={{ mb: 1 }}>
                    {VENUE_ICONS[preset.key] || DEFAULT_ICON}
                  </Typography>
                  <Typography variant="subtitle2">{preset.name}</Typography>
                  <Typography variant="caption" color="text.secondary" display="block">
                    {preset.description}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                    Stage about {preset.stage_width} m across, {preset.stage_depth} m deep
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                    {summariseKit(preset)}
                  </Typography>
                </CardContent>
              </CardActionArea>
            </Card>
          </Grid>
        ))}

        <Grid item xs={6} sm={4} md={3}>
          <Card
            sx={{
              height: '100%',
              border: '2px dashed',
              borderColor: selected ? 'divider' : 'primary.main',
            }}
          >
            <CardActionArea onClick={onClear} sx={{ height: '100%' }}>
              <CardContent sx={{ textAlign: 'center', py: 2 }}>
                <Typography variant="h4" sx={{ mb: 1 }}>{CUSTOM_ICON}</Typography>
                <Typography variant="subtitle2">None of these</Typography>
                <Typography variant="caption" color="text.secondary" display="block">
                  Start empty and tell us your own stage size and lights.
                </Typography>
              </CardContent>
            </CardActionArea>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
