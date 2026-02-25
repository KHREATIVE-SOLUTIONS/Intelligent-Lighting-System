import {
  Box,
  Typography,
  Chip,
  ToggleButtonGroup,
  ToggleButton,
  LinearProgress,
  Paper,
  Slider,
  FormControlLabel,
  Switch,
  Divider,
} from '@mui/material';
import {
  MusicNote as GenreIcon,
  Lightbulb as LightIcon,
  FlashOn as StrobeIcon,
  Sync as ChaseIcon,
  OpenWith as MovementIcon,
  Person as PerformerIcon,
  Psychology as IntentIcon,
  Tune as ControlIcon,
} from '@mui/icons-material';
import { useDMXStore } from '../../stores/dmxStore';
import { proLightingApi } from '../../services/api';
import { audioWebSocket } from '../../services/websocket';
import type { BeamAggressionLevel, Genre, SongSection } from '../../types';

const GENRE_OPTIONS: { value: Genre; label: string }[] = [
  { value: 'EDM', label: 'EDM' },
  { value: 'ROCK', label: 'Rock' },
  { value: 'POP', label: 'Pop' },
  { value: 'HIP_HOP', label: 'Hip-Hop' },
  { value: 'JAZZ', label: 'Jazz' },
];

const BEAM_AGGRESSION_OPTIONS: { value: BeamAggressionLevel; label: string }[] = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
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
  const setOperatorIntentControls = useDMXStore((state) => state.setOperatorIntentControls);
  const setAutoRecommendIntent = useDMXStore((state) => state.setAutoRecommendIntent);

  const sendIntentControls = (next = proLighting.operatorIntentControls) => {
    proLightingApi.setIntentControls(
      next.beamAggression,
      next.movementDensity,
      next.colorVolatility,
      next.transitionStrictness,
      next.autoRecommend,
    ).catch(console.error);

    audioWebSocket.send({
      type: 'pro_intent_control',
      data: {
        beam_aggression: next.beamAggression,
        movement_density: next.movementDensity,
        color_volatility: next.colorVolatility,
        transition_strictness: next.transitionStrictness,
        auto_recommend: next.autoRecommend,
      },
    });
  };

  const handleGenreChange = (_: React.MouseEvent<HTMLElement>, newGenre: Genre | null) => {
    setGenre(newGenre);
    if (newGenre) {
      proLightingApi.setGenre(newGenre).catch(console.error);
    }
  };

  const handleBeamAggression = (_: React.MouseEvent<HTMLElement>, value: BeamAggressionLevel | null) => {
    if (!value) return;
    const next = { ...proLighting.operatorIntentControls, beamAggression: value };
    setOperatorIntentControls({ beamAggression: value });
    sendIntentControls(next);
  };

  const handleSliderChange = (field: 'movementDensity' | 'colorVolatility' | 'transitionStrictness') =>
    (_: Event, value: number | number[]) => {
      const nextValue = Array.isArray(value) ? value[0] : value;
      const next = { ...proLighting.operatorIntentControls, [field]: nextValue };
      setOperatorIntentControls({ [field]: nextValue });
      sendIntentControls(next);
    };

  const handleAutoRecommend = (_: React.ChangeEvent<HTMLInputElement>, checked: boolean) => {
    const next = { ...proLighting.operatorIntentControls, autoRecommend: checked };
    setAutoRecommendIntent(checked);
    sendIntentControls(next);
  };

  const sectionColor = SECTION_COLORS[proLighting.section] || SECTION_COLORS.UNKNOWN;
  const sectionLabel = SECTION_LABELS[proLighting.section] || 'Unknown';

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
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

      <Paper sx={{ p: 1.5, bgcolor: 'grey.900' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <ControlIcon sx={{ mr: 1, fontSize: 18 }} color="info" />
          <Typography variant="subtitle2">Operator Intent Controls</Typography>
        </Box>

        <Typography variant="caption" color="text.secondary">Beam Aggression</Typography>
        <ToggleButtonGroup
          value={proLighting.operatorIntentControls.beamAggression}
          exclusive
          onChange={handleBeamAggression}
          size="small"
          sx={{ mt: 0.5, mb: 1, width: '100%' }}
        >
          {BEAM_AGGRESSION_OPTIONS.map((o) => (
            <ToggleButton key={o.value} value={o.value} sx={{ flex: 1 }}>
              {o.label}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>

        <Typography variant="caption" color="text.secondary">Movement Density</Typography>
        <Slider
          size="small"
          min={0}
          max={1}
          step={0.05}
          value={proLighting.operatorIntentControls.movementDensity}
          onChangeCommitted={handleSliderChange('movementDensity')}
          valueLabelDisplay="auto"
        />

        <Typography variant="caption" color="text.secondary">Color Volatility</Typography>
        <Slider
          size="small"
          min={0}
          max={1}
          step={0.05}
          value={proLighting.operatorIntentControls.colorVolatility}
          onChangeCommitted={handleSliderChange('colorVolatility')}
          valueLabelDisplay="auto"
        />

        <Typography variant="caption" color="text.secondary">Transition Strictness (barline ↔ expressive)</Typography>
        <Slider
          size="small"
          min={0}
          max={1}
          step={0.05}
          value={proLighting.operatorIntentControls.transitionStrictness}
          onChangeCommitted={handleSliderChange('transitionStrictness')}
          valueLabelDisplay="auto"
        />

        <FormControlLabel
          control={<Switch checked={proLighting.operatorIntentControls.autoRecommend} onChange={handleAutoRecommend} />}
          label="Auto-recommend intent (genre/section aware)"
          sx={{ mt: 0.5 }}
        />
      </Paper>

      <Paper sx={{ p: 1.5, bgcolor: 'grey.900' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <IntentIcon sx={{ mr: 1, fontSize: 18 }} color="secondary" />
          <Typography variant="subtitle2">Active Intent Profile</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          <Chip size="small" color="secondary" label={proLighting.activeIntentProfile.label} />
          <Chip size="small" variant="outlined" label={`Source: ${proLighting.activeIntentProfile.source}`} />
          <Chip size="small" variant="outlined" label={`Section Fidelity: ${proLighting.decisionWeights.sectionFidelity.toFixed(2)}`} />
          <Chip size="small" variant="outlined" label={`Move W: ${proLighting.decisionWeights.movement.toFixed(2)}`} />
          <Chip size="small" variant="outlined" label={`Color W: ${proLighting.decisionWeights.color.toFixed(2)}`} />
        </Box>
      </Paper>

      <Divider />

      <Box>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <LightIcon sx={{ mr: 1, fontSize: 18 }} color="secondary" />
          <Typography variant="subtitle2">Current Section</Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Chip label={sectionLabel} sx={{ bgcolor: sectionColor, color: 'white', fontWeight: 'bold', fontSize: '0.9rem' }} />
          <Box sx={{ flex: 1 }}>
            <Typography variant="caption" color="text.secondary">Intensity</Typography>
            <LinearProgress variant="determinate" value={proLighting.sectionIntensity * 100} sx={{ height: 10, borderRadius: 5, bgcolor: 'grey.800', '& .MuiLinearProgress-bar': { bgcolor: sectionColor, borderRadius: 5 } }} />
          </Box>
        </Box>
      </Box>

      <Box>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>Active Effects</Typography>
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
          {proLighting.activeEffects.strobeMode !== 'off' && <Chip icon={<StrobeIcon />} label={`Strobe: ${proLighting.activeEffects.strobeMode}`} size="small" color="warning" variant="outlined" />}
          {proLighting.activeEffects.chaseType !== 'off' && <Chip icon={<ChaseIcon />} label={`Chase: ${proLighting.activeEffects.chaseType.replace('_', ' ')}`} size="small" color="info" variant="outlined" />}
          {proLighting.activeEffects.movementType !== 'none' && <Chip icon={<MovementIcon />} label={`Move: ${proLighting.activeEffects.movementType.replace('_', ' ')}`} size="small" color="success" variant="outlined" />}
          {proLighting.activeEffects.strobeMode === 'off' && proLighting.activeEffects.chaseType === 'off' && proLighting.activeEffects.movementType === 'none' && (
            <Typography variant="body2" color="text.secondary">No active effects</Typography>
          )}
        </Box>
      </Box>

      {proLighting.keyLightingZones.length > 0 && (
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <PerformerIcon sx={{ mr: 1, fontSize: 18 }} />
            <Typography variant="subtitle2">Key Lighting</Typography>
          </Box>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            {proLighting.keyLightingZones.filter((z) => z.active).map((zone) => (
              <Chip key={zone.zone} label={zone.performerLabel || zone.zone} size="small" sx={{ bgcolor: `rgb(${zone.color.r}, ${zone.color.g}, ${zone.color.b})`, color: 'white', opacity: zone.intensity }} />
            ))}
          </Box>
        </Box>
      )}

      <Paper sx={{ p: 1.5, bgcolor: 'grey.900' }}>
        <Typography variant="caption" color="text.secondary">Phrase Position</Typography>
        <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5 }}>
          {Array.from({ length: proLighting.beatsPerPhrase }, (_, i) => (
            <Box key={i} sx={{ flex: 1, height: 8, borderRadius: 1, bgcolor: i < proLighting.beatPhrase ? 'primary.main' : 'grey.700', transition: 'background-color 0.1s' }} />
          ))}
        </Box>
      </Paper>
    </Box>
  );
}
