import {
  Box,
  Typography,
  Chip,
  ToggleButtonGroup,
  ToggleButton,
  LinearProgress,
  Paper,
} from '@mui/material';
import {
  MusicNote as GenreIcon,
  Lightbulb as LightIcon,
  FlashOn as StrobeIcon,
  Sync as ChaseIcon,
  OpenWith as MovementIcon,
  Person as PerformerIcon,
} from '@mui/icons-material';
import { useDMXStore } from '../../stores/dmxStore';
import { proLightingApi } from '../../services/api';
import type { Genre, SongSection } from '../../types';

const GENRE_OPTIONS: { value: Genre; label: string }[] = [
  { value: 'EDM', label: 'EDM' },
  { value: 'ROCK', label: 'Rock' },
  { value: 'POP', label: 'Pop' },
  { value: 'HIP_HOP', label: 'Hip-Hop' },
  { value: 'JAZZ', label: 'Jazz' },
];

const SECTION_COLORS: Record<SongSection, string> = {
  INTRO: '#78909c',
  VERSE: '#42a5f5',
  PRE_CHORUS: '#ab47bc',
  CHORUS: '#66bb6a',
  DROP: '#ef5350',
  BREAKDOWN: '#7e57c2',
  BRIDGE: '#ffa726',
  BUILDUP: '#ffca28',
  OUTRO: '#78909c',
  INSTRUMENTAL: '#26c6da',
  SOLO: '#ec407a',
  UNKNOWN: '#616161',
};

const SECTION_LABELS: Record<SongSection, string> = {
  INTRO: 'Intro',
  VERSE: 'Verse',
  PRE_CHORUS: 'Pre-Chorus',
  CHORUS: 'Chorus',
  DROP: 'Drop',
  BREAKDOWN: 'Breakdown',
  BRIDGE: 'Bridge',
  BUILDUP: 'Build-Up',
  OUTRO: 'Outro',
  INSTRUMENTAL: 'Instrumental',
  SOLO: 'Solo',
  UNKNOWN: 'Unknown',
};

export default function ProLightingPanel() {
  const proLighting = useDMXStore((state) => state.proLighting);
  const setGenre = useDMXStore((state) => state.setGenre);

  const handleGenreChange = (_: React.MouseEvent<HTMLElement>, newGenre: Genre | null) => {
    setGenre(newGenre);
    if (newGenre) {
      proLightingApi.setGenre(newGenre).catch(console.error);
    }
  };

  const sectionColor = SECTION_COLORS[proLighting.section] || SECTION_COLORS.UNKNOWN;
  const sectionLabel = SECTION_LABELS[proLighting.section] || 'Unknown';

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {/* Genre Selector */}
      <Box>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <GenreIcon sx={{ mr: 1, fontSize: 18 }} color="primary" />
          <Typography variant="subtitle2">Genre</Typography>
        </Box>
        <ToggleButtonGroup
          value={proLighting.genre}
          exclusive
          onChange={handleGenreChange}
          size="small"
          sx={{ flexWrap: 'wrap' }}
        >
          {GENRE_OPTIONS.map((g) => (
            <ToggleButton key={g.value} value={g.value} sx={{ px: 2 }}>
              {g.label}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Box>

      {/* Current Section */}
      <Box>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <LightIcon sx={{ mr: 1, fontSize: 18 }} color="secondary" />
          <Typography variant="subtitle2">Current Section</Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Chip
            label={sectionLabel}
            sx={{
              bgcolor: sectionColor,
              color: 'white',
              fontWeight: 'bold',
              fontSize: '0.9rem',
            }}
          />
          <Box sx={{ flex: 1 }}>
            <Typography variant="caption" color="text.secondary">
              Intensity
            </Typography>
            <LinearProgress
              variant="determinate"
              value={proLighting.sectionIntensity * 100}
              sx={{
                height: 10,
                borderRadius: 5,
                bgcolor: 'grey.800',
                '& .MuiLinearProgress-bar': {
                  bgcolor: sectionColor,
                  borderRadius: 5,
                },
              }}
            />
          </Box>
        </Box>
      </Box>

      {/* Active Effects */}
      <Box>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>Active Effects</Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
          {proLighting.activeEffects.strobeMode !== 'off' && (
            <Chip
              icon={<StrobeIcon />}
              label={`Strobe: ${proLighting.activeEffects.strobeMode}`}
              size="small"
              color="warning"
              variant="outlined"
            />
          )}
          {proLighting.activeEffects.chaseType !== 'off' && (
            <Chip
              icon={<ChaseIcon />}
              label={`Chase: ${proLighting.activeEffects.chaseType.replace('_', ' ')}`}
              size="small"
              color="info"
              variant="outlined"
            />
          )}
          {proLighting.activeEffects.movementType !== 'none' && (
            <Chip
              icon={<MovementIcon />}
              label={`Move: ${proLighting.activeEffects.movementType.replace('_', ' ')}`}
              size="small"
              color="success"
              variant="outlined"
            />
          )}
          {proLighting.activeEffects.strobeMode === 'off' &&
           proLighting.activeEffects.chaseType === 'off' &&
           proLighting.activeEffects.movementType === 'none' && (
            <Typography variant="body2" color="text.secondary">
              No active effects
            </Typography>
          )}
        </Box>
      </Box>

      {/* Key Lighting Zones */}
      {proLighting.keyLightingZones.length > 0 && (
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <PerformerIcon sx={{ mr: 1, fontSize: 18 }} />
            <Typography variant="subtitle2">Key Lighting</Typography>
          </Box>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            {proLighting.keyLightingZones
              .filter((z) => z.active)
              .map((zone) => (
                <Chip
                  key={zone.zone}
                  label={zone.performerLabel || zone.zone}
                  size="small"
                  sx={{
                    bgcolor: `rgb(${zone.color.r}, ${zone.color.g}, ${zone.color.b})`,
                    color: 'white',
                    opacity: zone.intensity,
                  }}
                />
              ))}
          </Box>
        </Box>
      )}

      {/* Emotion Vector (if available) */}
      {proLighting.emotionVector && (
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Emotion</Typography>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
            {[
              { label: 'Valence', value: proLighting.emotionVector.valence, range: [-1, 1] },
              { label: 'Arousal', value: proLighting.emotionVector.arousal, range: [-1, 1] },
              { label: 'Energy', value: proLighting.emotionVector.energy_trajectory, range: [-1, 1] },
              { label: 'Groove', value: proLighting.emotionVector.groove, range: [0, 1] },
              { label: 'Darkness', value: proLighting.emotionVector.darkness, range: [0, 1] },
            ].map((dim) => {
              const normalizedValue = dim.range[0] === -1
                ? ((dim.value + 1) / 2) * 100
                : dim.value * 100;
              return (
                <Box key={dim.label} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography variant="caption" sx={{ width: 60, flexShrink: 0 }}>
                    {dim.label}
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={Math.max(0, Math.min(100, normalizedValue))}
                    sx={{
                      flex: 1,
                      height: 6,
                      borderRadius: 3,
                      bgcolor: 'grey.800',
                    }}
                  />
                  <Typography variant="caption" sx={{ width: 36, textAlign: 'right' }}>
                    {dim.value.toFixed(2)}
                  </Typography>
                </Box>
              );
            })}
          </Box>
        </Box>
      )}

      {/* Beat Phrase */}
      <Paper sx={{ p: 1.5, bgcolor: 'grey.900' }}>
        <Typography variant="caption" color="text.secondary">
          Phrase Position
        </Typography>
        <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5 }}>
          {Array.from({ length: proLighting.beatsPerPhrase }, (_, i) => (
            <Box
              key={i}
              sx={{
                flex: 1,
                height: 8,
                borderRadius: 1,
                bgcolor: i < proLighting.beatPhrase ? 'primary.main' : 'grey.700',
                transition: 'background-color 0.1s',
              }}
            />
          ))}
        </Box>
      </Paper>
    </Box>
  );
}
