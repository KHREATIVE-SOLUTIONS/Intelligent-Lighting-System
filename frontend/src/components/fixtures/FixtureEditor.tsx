import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Stepper,
  Step,
  StepLabel,
  Button,
  TextField,
  Grid,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  IconButton,
  Paper,
  Chip,
  Alert,
} from '@mui/material';
import { Add as AddIcon, Delete as DeleteIcon, ArrowBack } from '@mui/icons-material';
import { fixturesApi } from '../../services/api';
import type { Fixture, FixtureMode, FixtureChannel, FixtureType, ChannelType } from '../../types';

const FIXTURE_TYPES: FixtureType[] = [
  'moving_head', 'led_par', 'led_bar', 'wash', 'spot',
  'beam', 'strobe', 'laser', 'effect', 'dimmer', 'other',
];

const CHANNEL_TYPES: ChannelType[] = [
  'dimmer', 'red', 'green', 'blue', 'white', 'amber', 'uv', 'lime', 'indigo',
  'cyan', 'magenta', 'yellow', 'cto', 'ctb',
  'pan', 'pan_fine', 'tilt', 'tilt_fine', 'zoom', 'focus', 'iris', 'frost',
  'gobo', 'gobo_rotation', 'gobo2', 'gobo2_rotation', 'animation', 'framing',
  'prism', 'color_wheel', 'shutter', 'strobe', 'speed', 'effect', 'macro', 'other',
];

const STEPS = ['Basic Info', 'Modes', 'Channel Mapping'];

interface EditMode {
  name: string;
  channel_count: number;
  channels: EditChannel[];
}

interface EditChannel {
  channel_number: number;
  channel_type: ChannelType;
  name: string;
  default_value: number;
}

export default function FixtureEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const isEdit = Boolean(id);

  // Basic info
  const [manufacturer, setManufacturer] = useState('');
  const [model, setModel] = useState('');
  const [fixtureType, setFixtureType] = useState<FixtureType>('other');
  const [weight, setWeight] = useState<number | ''>('');
  const [power, setPower] = useState<number | ''>('');
  const [beamAngle, setBeamAngle] = useState<number | ''>('');
  const [hasRgb, setHasRgb] = useState(false);
  const [hasColorWheel, setHasColorWheel] = useState(false);

  // Modes
  const [modes, setModes] = useState<EditMode[]>([
    { name: 'Standard', channel_count: 0, channels: [] },
  ]);
  const [activeModeIdx, setActiveModeIdx] = useState(0);

  // Load existing fixture for edit
  useEffect(() => {
    if (id) {
      fixturesApi.get(Number(id)).then((fixture) => {
        setManufacturer(fixture.manufacturer);
        setModel(fixture.model);
        setFixtureType(fixture.fixture_type);
        setWeight(fixture.weight || '');
        setPower(fixture.power || '');
        setBeamAngle(fixture.beam_angle || '');
        setHasRgb(fixture.has_rgb);
        setHasColorWheel(fixture.has_color_wheel);
        if (fixture.modes.length > 0) {
          setModes(
            fixture.modes.map((m) => ({
              name: m.name,
              channel_count: m.channel_count,
              channels: m.channels.map((ch) => ({
                channel_number: ch.channel_number,
                channel_type: ch.channel_type,
                name: ch.name,
                default_value: ch.default_value,
              })),
            }))
          );
        }
      }).catch(() => setError('Failed to load fixture'));
    }
  }, [id]);

  const handleAddMode = () => {
    setModes([...modes, { name: `Mode ${modes.length + 1}`, channel_count: 0, channels: [] }]);
  };

  const handleRemoveMode = (idx: number) => {
    if (modes.length <= 1) return;
    setModes(modes.filter((_, i) => i !== idx));
    if (activeModeIdx >= idx && activeModeIdx > 0) setActiveModeIdx(activeModeIdx - 1);
  };

  const handleAddChannel = () => {
    const mode = modes[activeModeIdx];
    const nextNum = mode.channels.length + 1;
    const updated = [...modes];
    updated[activeModeIdx] = {
      ...mode,
      channels: [
        ...mode.channels,
        { channel_number: nextNum, channel_type: 'other', name: `Channel ${nextNum}`, default_value: 0 },
      ],
      channel_count: mode.channels.length + 1,
    };
    setModes(updated);
  };

  const handleRemoveChannel = (chIdx: number) => {
    const mode = modes[activeModeIdx];
    const updated = [...modes];
    const newChannels = mode.channels.filter((_, i) => i !== chIdx)
      .map((ch, i) => ({ ...ch, channel_number: i + 1 }));
    updated[activeModeIdx] = {
      ...mode,
      channels: newChannels,
      channel_count: newChannels.length,
    };
    setModes(updated);
  };

  const handleChannelChange = (chIdx: number, field: string, value: any) => {
    const updated = [...modes];
    const mode = { ...updated[activeModeIdx] };
    mode.channels = mode.channels.map((ch, i) =>
      i === chIdx ? { ...ch, [field]: value } : ch
    );
    updated[activeModeIdx] = mode;
    setModes(updated);
  };

  const handleAutoFill = () => {
    const templates: Record<string, EditChannel[]> = {
      moving_head: [
        { channel_number: 1, channel_type: 'pan', name: 'Pan', default_value: 128 },
        { channel_number: 2, channel_type: 'pan_fine', name: 'Pan Fine', default_value: 0 },
        { channel_number: 3, channel_type: 'tilt', name: 'Tilt', default_value: 128 },
        { channel_number: 4, channel_type: 'tilt_fine', name: 'Tilt Fine', default_value: 0 },
        { channel_number: 5, channel_type: 'speed', name: 'Speed', default_value: 0 },
        { channel_number: 6, channel_type: 'dimmer', name: 'Dimmer', default_value: 0 },
        { channel_number: 7, channel_type: 'shutter', name: 'Shutter', default_value: 255 },
        { channel_number: 8, channel_type: 'red', name: 'Red', default_value: 0 },
        { channel_number: 9, channel_type: 'green', name: 'Green', default_value: 0 },
        { channel_number: 10, channel_type: 'blue', name: 'Blue', default_value: 0 },
        { channel_number: 11, channel_type: 'white', name: 'White', default_value: 0 },
        { channel_number: 12, channel_type: 'zoom', name: 'Zoom', default_value: 128 },
      ],
      led_par: [
        { channel_number: 1, channel_type: 'dimmer', name: 'Dimmer', default_value: 0 },
        { channel_number: 2, channel_type: 'red', name: 'Red', default_value: 0 },
        { channel_number: 3, channel_type: 'green', name: 'Green', default_value: 0 },
        { channel_number: 4, channel_type: 'blue', name: 'Blue', default_value: 0 },
        { channel_number: 5, channel_type: 'white', name: 'White', default_value: 0 },
        { channel_number: 6, channel_type: 'strobe', name: 'Strobe', default_value: 0 },
      ],
      led_bar: [
        { channel_number: 1, channel_type: 'dimmer', name: 'Dimmer', default_value: 0 },
        { channel_number: 2, channel_type: 'strobe', name: 'Strobe', default_value: 0 },
        { channel_number: 3, channel_type: 'red', name: 'Red', default_value: 0 },
        { channel_number: 4, channel_type: 'green', name: 'Green', default_value: 0 },
        { channel_number: 5, channel_type: 'blue', name: 'Blue', default_value: 0 },
      ],
    };

    const template = templates[fixtureType];
    if (template) {
      const updated = [...modes];
      updated[activeModeIdx] = {
        ...updated[activeModeIdx],
        channels: template,
        channel_count: template.length,
      };
      setModes(updated);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');

    const fixtureData = {
      manufacturer,
      model,
      fixture_type: fixtureType,
      weight: weight || null,
      power: power || null,
      beam_angle: beamAngle || null,
      has_rgb: hasRgb,
      has_color_wheel: hasColorWheel,
      modes: modes.map((m) => ({
        name: m.name,
        channel_count: m.channels.length,
        channels: m.channels,
      })),
    };

    try {
      if (isEdit) {
        await fixturesApi.update(Number(id), fixtureData);
      } else {
        await fixturesApi.create(fixtureData);
      }
      navigate('/fixtures');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const activeMode = modes[activeModeIdx];

  return (
    <Box sx={{ maxWidth: 900, mx: 'auto' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
        <IconButton onClick={() => navigate('/fixtures')}>
          <ArrowBack />
        </IconButton>
        <Typography variant="h5">
          {isEdit ? 'Edit Fixture' : 'Create Fixture'}
        </Typography>
      </Box>

      <Stepper activeStep={step} sx={{ mb: 3 }}>
        {STEPS.map((label) => (
          <Step key={label}><StepLabel>{label}</StepLabel></Step>
        ))}
      </Stepper>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Paper sx={{ p: 3, mb: 3 }}>
        {step === 0 && (
          <Grid container spacing={2}>
            <Grid item xs={6}>
              <TextField fullWidth label="Manufacturer" value={manufacturer} onChange={(e) => setManufacturer(e.target.value)} required />
            </Grid>
            <Grid item xs={6}>
              <TextField fullWidth label="Model" value={model} onChange={(e) => setModel(e.target.value)} required />
            </Grid>
            <Grid item xs={6}>
              <FormControl fullWidth>
                <InputLabel>Fixture Type</InputLabel>
                <Select value={fixtureType} label="Fixture Type" onChange={(e) => setFixtureType(e.target.value as FixtureType)}>
                  {FIXTURE_TYPES.map((t) => <MenuItem key={t} value={t}>{t.replace('_', ' ')}</MenuItem>)}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={2}>
              <TextField fullWidth label="Weight (kg)" type="number" value={weight} onChange={(e) => setWeight(e.target.value ? Number(e.target.value) : '')} />
            </Grid>
            <Grid item xs={2}>
              <TextField fullWidth label="Power (W)" type="number" value={power} onChange={(e) => setPower(e.target.value ? Number(e.target.value) : '')} />
            </Grid>
            <Grid item xs={2}>
              <TextField fullWidth label="Beam Angle" type="number" value={beamAngle} onChange={(e) => setBeamAngle(e.target.value ? Number(e.target.value) : '')} />
            </Grid>
          </Grid>
        )}

        {step === 1 && (
          <Box>
            <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
              {modes.map((m, i) => (
                <Chip
                  key={i}
                  label={`${m.name} (${m.channels.length}ch)`}
                  onClick={() => setActiveModeIdx(i)}
                  onDelete={modes.length > 1 ? () => handleRemoveMode(i) : undefined}
                  color={i === activeModeIdx ? 'primary' : 'default'}
                  variant={i === activeModeIdx ? 'filled' : 'outlined'}
                />
              ))}
              <Button size="small" startIcon={<AddIcon />} onClick={handleAddMode}>Add Mode</Button>
            </Box>

            <TextField
              label="Mode Name"
              value={activeMode.name}
              onChange={(e) => {
                const updated = [...modes];
                updated[activeModeIdx] = { ...activeMode, name: e.target.value };
                setModes(updated);
              }}
              sx={{ mb: 2 }}
            />
          </Box>
        )}

        {step === 2 && (
          <Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
              <Typography variant="subtitle1">
                {activeMode.name} - Channels ({activeMode.channels.length})
              </Typography>
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button size="small" onClick={handleAutoFill}>Auto-fill from Template</Button>
                <Button size="small" startIcon={<AddIcon />} onClick={handleAddChannel}>Add Channel</Button>
              </Box>
            </Box>

            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>#</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Name</TableCell>
                  <TableCell>Default</TableCell>
                  <TableCell></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {activeMode.channels.map((ch, idx) => (
                  <TableRow key={idx}>
                    <TableCell>{ch.channel_number}</TableCell>
                    <TableCell>
                      <Select
                        size="small"
                        value={ch.channel_type}
                        onChange={(e) => handleChannelChange(idx, 'channel_type', e.target.value)}
                        sx={{ minWidth: 120 }}
                      >
                        {CHANNEL_TYPES.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
                      </Select>
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        value={ch.name}
                        onChange={(e) => handleChannelChange(idx, 'name', e.target.value)}
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        size="small"
                        type="number"
                        value={ch.default_value}
                        onChange={(e) => handleChannelChange(idx, 'default_value', Number(e.target.value))}
                        inputProps={{ min: 0, max: 255 }}
                        sx={{ width: 80 }}
                      />
                    </TableCell>
                    <TableCell>
                      <IconButton size="small" color="error" onClick={() => handleRemoveChannel(idx)}>
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}
      </Paper>

      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button onClick={() => navigate('/fixtures')} color="inherit">Cancel</Button>
        <Box sx={{ display: 'flex', gap: 1 }}>
          {step > 0 && <Button onClick={() => setStep(step - 1)}>Back</Button>}
          {step < STEPS.length - 1 ? (
            <Button variant="contained" onClick={() => setStep(step + 1)} disabled={!manufacturer || !model}>
              Next
            </Button>
          ) : (
            <Button variant="contained" onClick={handleSave} disabled={saving || !manufacturer || !model}>
              {saving ? 'Saving...' : isEdit ? 'Save Changes' : 'Create Fixture'}
            </Button>
          )}
        </Box>
      </Box>
    </Box>
  );
}
