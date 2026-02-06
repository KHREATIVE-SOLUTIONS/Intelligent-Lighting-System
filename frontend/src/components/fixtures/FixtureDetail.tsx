import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  Tab,
  Chip,
  IconButton,
  Button,
  Stack,
} from '@mui/material';
import { ArrowBack, Edit as EditIcon } from '@mui/icons-material';
import { fixturesApi } from '../../services/api';
import type { Fixture } from '../../types';

const CHANNEL_TYPE_COLORS: Record<string, string> = {
  dimmer: '#ffd600',
  red: '#f44336',
  green: '#4caf50',
  blue: '#2196f3',
  white: '#ffffff',
  amber: '#ff9800',
  uv: '#7c4dff',
  pan: '#e91e63',
  pan_fine: '#e91e63',
  tilt: '#9c27b0',
  tilt_fine: '#9c27b0',
  zoom: '#00bcd4',
  focus: '#009688',
  gobo: '#795548',
  shutter: '#607d8b',
  strobe: '#ffeb3b',
  speed: '#ff5722',
  effect: '#3f51b5',
  other: '#9e9e9e',
};

export default function FixtureDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [fixture, setFixture] = useState<Fixture | null>(null);
  const [activeMode, setActiveMode] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (id) {
      fixturesApi.get(Number(id)).then((data) => {
        setFixture(data);
        setLoading(false);
      }).catch(() => setLoading(false));
    }
  }, [id]);

  if (loading) return <Typography>Loading...</Typography>;
  if (!fixture) return <Typography>Fixture not found</Typography>;

  const currentMode = fixture.modes[activeMode];

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
        <IconButton onClick={() => navigate('/fixtures')}>
          <ArrowBack />
        </IconButton>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="h5">{fixture.model}</Typography>
          <Typography variant="subtitle1" color="text.secondary">
            {fixture.manufacturer} | {fixture.fixture_type.replace('_', ' ')}
          </Typography>
        </Box>
        <Button variant="outlined" startIcon={<EditIcon />} onClick={() => navigate(`/fixtures/${id}/edit`)}>
          Edit
        </Button>
      </Box>

      <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
        <Paper sx={{ p: 2, minWidth: 250 }}>
          <Typography variant="h6" gutterBottom>Properties</Typography>
          <Stack spacing={1}>
            {fixture.weight && <Typography variant="body2">Weight: {fixture.weight} kg</Typography>}
            {fixture.power && <Typography variant="body2">Power: {fixture.power} W</Typography>}
            {fixture.beam_angle && <Typography variant="body2">Beam Angle: {fixture.beam_angle}°</Typography>}
            <Typography variant="body2">Pan Range: {fixture.pan_range}°</Typography>
            <Typography variant="body2">Tilt Range: {fixture.tilt_range}°</Typography>
            <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
              {fixture.has_rgb && <Chip label="RGB" size="small" color="primary" />}
              {fixture.has_cmy && <Chip label="CMY" size="small" color="secondary" />}
              {fixture.has_color_wheel && <Chip label="Color Wheel" size="small" />}
            </Box>
            {fixture.source && (
              <Typography variant="caption" color="text.secondary">
                Source: {fixture.source} {fixture.source_id && `(${fixture.source_id})`}
              </Typography>
            )}
          </Stack>
        </Paper>

        <Paper sx={{ p: 2, flexGrow: 1 }}>
          <Typography variant="h6" gutterBottom>
            Modes ({fixture.modes.length})
          </Typography>

          {fixture.modes.length > 0 && (
            <>
              <Tabs
                value={activeMode}
                onChange={(_, v) => setActiveMode(v)}
                sx={{ mb: 2 }}
              >
                {fixture.modes.map((mode, i) => (
                  <Tab key={mode.id} label={`${mode.name} (${mode.channel_count}ch)`} value={i} />
                ))}
              </Tabs>

              {currentMode && (
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Ch #</TableCell>
                        <TableCell>Name</TableCell>
                        <TableCell>Type</TableCell>
                        <TableCell>Default</TableCell>
                        <TableCell>Range</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {currentMode.channels
                        .sort((a, b) => a.channel_number - b.channel_number)
                        .map((ch) => (
                        <TableRow key={ch.id}>
                          <TableCell>{ch.channel_number}</TableCell>
                          <TableCell>{ch.name}</TableCell>
                          <TableCell>
                            <Chip
                              label={ch.channel_type}
                              size="small"
                              sx={{
                                bgcolor: CHANNEL_TYPE_COLORS[ch.channel_type] || '#9e9e9e',
                                color: ['white', 'yellow'].includes(ch.channel_type) ? '#333' : '#fff',
                                fontSize: '0.7rem',
                              }}
                            />
                            {ch.is_fine && <Chip label="Fine" size="small" variant="outlined" sx={{ ml: 0.5 }} />}
                          </TableCell>
                          <TableCell>{ch.default_value}</TableCell>
                          <TableCell>{ch.min_value}–{ch.max_value}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </>
          )}
        </Paper>
      </Box>
    </Box>
  );
}
