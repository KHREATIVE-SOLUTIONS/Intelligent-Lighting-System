import {
  Card,
  CardContent,
  CardActions,
  Typography,
  Button,
  Chip,
  Box,
  Stack,
} from '@mui/material';
import {
  Lightbulb as LightbulbIcon,
  Add as AddIcon,
  Check as CheckIcon,
} from '@mui/icons-material';
import type { Fixture, FixtureType } from '../../types';

const FIXTURE_TYPE_COLORS: Record<string, string> = {
  moving_head: '#e91e63',
  led_par: '#4caf50',
  led_bar: '#2196f3',
  wash: '#ff9800',
  spot: '#9c27b0',
  beam: '#f44336',
  strobe: '#ffeb3b',
  laser: '#00bcd4',
  effect: '#795548',
  dimmer: '#607d8b',
  other: '#9e9e9e',
};

interface FixtureCardProps {
  fixture: Fixture | { manufacturer: string; model: string; fixture_type?: string; categories?: string[]; manufacturer_key?: string; fixture_key?: string };
  isOnline?: boolean;
  isImported?: boolean;
  onImport?: () => void;
  onClick?: () => void;
}

export default function FixtureCard({ fixture, isOnline, isImported, onImport, onClick }: FixtureCardProps) {
  const fixtureType = ('fixture_type' in fixture ? fixture.fixture_type : 'other') as string;
  const modes = 'modes' in fixture ? fixture.modes : [];

  return (
    <Card
      sx={{
        cursor: onClick ? 'pointer' : 'default',
        '&:hover': onClick ? { boxShadow: 4 } : {},
        borderLeft: `4px solid ${FIXTURE_TYPE_COLORS[fixtureType] || '#9e9e9e'}`,
      }}
      onClick={onClick}
    >
      <CardContent sx={{ pb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <LightbulbIcon sx={{ color: FIXTURE_TYPE_COLORS[fixtureType] || '#9e9e9e' }} fontSize="small" />
          <Typography variant="subtitle2" color="text.secondary" noWrap>
            {fixture.manufacturer}
          </Typography>
        </Box>
        <Typography variant="h6" sx={{ fontSize: '1rem', mb: 1 }} noWrap>
          {fixture.model}
        </Typography>
        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
          <Chip
            label={fixtureType.replace('_', ' ')}
            size="small"
            sx={{
              bgcolor: FIXTURE_TYPE_COLORS[fixtureType] || '#9e9e9e',
              color: 'white',
              fontSize: '0.7rem',
            }}
          />
          {modes.length > 0 && (
            <Chip
              label={`${modes.length} mode${modes.length > 1 ? 's' : ''}`}
              size="small"
              variant="outlined"
            />
          )}
          {modes.length > 0 && (
            <Chip
              label={`${modes[0].channel_count}ch`}
              size="small"
              variant="outlined"
            />
          )}
        </Stack>
      </CardContent>
      {isOnline && (
        <CardActions sx={{ pt: 0 }}>
          {isImported ? (
            <Button size="small" disabled startIcon={<CheckIcon />}>
              Added
            </Button>
          ) : (
            <Button size="small" color="primary" startIcon={<AddIcon />} onClick={(e) => { e.stopPropagation(); onImport?.(); }}>
              Add to Library
            </Button>
          )}
        </CardActions>
      )}
    </Card>
  );
}
