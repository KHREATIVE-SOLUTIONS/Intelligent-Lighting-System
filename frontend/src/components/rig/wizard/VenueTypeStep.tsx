import { useState, useEffect } from 'react';
import { Grid, Card, CardContent, CardActionArea, Typography, Box } from '@mui/material';
import { wizardApi } from '../../../services/api';
import type { VenuePreset } from '../../../types';

interface VenueTypeStepProps {
  selected: VenuePreset | null;
  onSelect: (preset: VenuePreset) => void;
}

const VENUE_ICONS: Record<string, string> = {
  small_club: '\uD83C\uDFA4',
  medium_venue: '\uD83C\uDFB5',
  church: '\u26EA',
  theater: '\uD83C\uDFAD',
  festival_stage: '\uD83C\uDFAA',
  large_venue: '\uD83C\uDFDF\uFE0F',
  nightclub: '\uD83E\uDEA9',
  outdoor: '\uD83C\uDF19',
};

export default function VenueTypeStep({ selected, onSelect }: VenueTypeStepProps) {
  const [presets, setPresets] = useState<VenuePreset[]>([]);

  useEffect(() => {
    wizardApi.getVenuePresets().then((data) => setPresets(data.presets || [])).catch(() => {});
  }, []);

  return (
    <Box>
      <Typography variant="h6" gutterBottom>Select Venue Type</Typography>
      <Typography variant="body2" color="text.secondary" gutterBottom>
        Choose a venue preset to get suggested dimensions and fixtures, or skip to customize.
      </Typography>
      <Grid container spacing={2} sx={{ mt: 1 }}>
        {presets.map((preset) => (
          <Grid item xs={6} sm={4} md={3} key={preset.key}>
            <Card
              sx={{
                border: selected?.key === preset.key ? '2px solid' : '1px solid transparent',
                borderColor: selected?.key === preset.key ? 'primary.main' : 'transparent',
              }}
            >
              <CardActionArea onClick={() => onSelect(preset)}>
                <CardContent sx={{ textAlign: 'center', py: 2 }}>
                  <Typography variant="h4" sx={{ mb: 1 }}>
                    {VENUE_ICONS[preset.key] || '\uD83D\uDCA1'}
                  </Typography>
                  <Typography variant="subtitle2">{preset.name}</Typography>
                  <Typography variant="caption" color="text.secondary" display="block">
                    {preset.description}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {preset.stage_width}x{preset.stage_depth}x{preset.stage_height}m
                  </Typography>
                </CardContent>
              </CardActionArea>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}
