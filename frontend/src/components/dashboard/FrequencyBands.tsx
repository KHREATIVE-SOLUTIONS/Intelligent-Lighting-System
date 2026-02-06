import { Box, Typography, LinearProgress } from '@mui/material';
import type { FrequencyBand } from '../../types';

interface FrequencyBandsProps {
  bands: FrequencyBand[];
}

const bandColors: Record<string, string> = {
  sub_bass: '#7c4dff',
  bass: '#651fff',
  low_mid: '#536dfe',
  mid: '#448aff',
  high_mid: '#40c4ff',
  high: '#18ffff',
  brilliance: '#64ffda',
};

const bandLabels: Record<string, string> = {
  sub_bass: 'Sub Bass',
  bass: 'Bass',
  low_mid: 'Low Mid',
  mid: 'Mid',
  high_mid: 'High Mid',
  high: 'High',
  brilliance: 'Brilliance',
};

export default function FrequencyBands({ bands }: FrequencyBandsProps) {
  if (bands.length === 0) {
    return (
      <Box sx={{ textAlign: 'center', py: 4 }}>
        <Typography color="text.secondary">No frequency data available</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {bands.map((band) => (
        <Box key={band.name}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
            <Typography variant="body2">
              {bandLabels[band.name] || band.name}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {band.frequency_range[0]}-{band.frequency_range[1]} Hz
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={band.energy * 100}
            sx={{
              height: 16,
              borderRadius: 2,
              bgcolor: 'grey.800',
              '& .MuiLinearProgress-bar': {
                bgcolor: bandColors[band.name] || 'primary.main',
                borderRadius: 2,
              },
            }}
          />
        </Box>
      ))}

      {/* Frequency spectrum visualization */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'flex-end',
          height: 100,
          gap: 0.5,
          mt: 2,
          p: 2,
          bgcolor: 'grey.900',
          borderRadius: 2,
        }}
      >
        {bands.map((band) => (
          <Box
            key={band.name}
            sx={{
              flex: 1,
              height: `${band.energy * 100}%`,
              minHeight: 4,
              bgcolor: bandColors[band.name] || 'primary.main',
              borderRadius: '4px 4px 0 0',
              transition: 'height 0.1s ease-out',
            }}
          />
        ))}
      </Box>
    </Box>
  );
}
