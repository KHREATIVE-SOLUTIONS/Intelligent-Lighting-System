import { useState, useCallback, useRef } from 'react';
import {
  Box,
  Typography,
  Button,
  Slider,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Stack,
  Chip,
  Popover,
} from '@mui/material';
import {
  FlashOn as FlashOnIcon,
  Palette as PaletteIcon,
  OpenWith as MoveIcon,
  PlayArrow as PlayIcon,
  Stop as StopIcon,
  ExpandMore as ExpandMoreIcon,
} from '@mui/icons-material';
import { rigsApi } from '../../services/api';
import type { RigFixture, FixtureChannel } from '../../types';

interface FixtureTestPanelProps {
  rigId: number;
  fixture: RigFixture;
  channels?: FixtureChannel[];
  anchorEl: HTMLElement | null;
  onClose: () => void;
}

export default function FixtureTestPanel({
  rigId,
  fixture,
  channels = [],
  anchorEl,
  onClose,
}: FixtureTestPanelProps) {
  const [testing, setTesting] = useState(false);
  const [testType, setTestType] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const handleTest = async (type: string) => {
    setTesting(true);
    setTestType(type);
    try {
      await rigsApi.testFixture(rigId, fixture.id, type);
    } catch (err) {
      console.error('Test failed:', err);
    }
  };

  const handleStop = async () => {
    try {
      await rigsApi.stopFixtureTest(rigId, fixture.id);
    } catch (err) {
      console.error('Stop failed:', err);
    } finally {
      setTesting(false);
      setTestType('');
    }
  };

  const handleSliderChange = useCallback(
    (offset: number, value: number) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        rigsApi.setFixtureChannels(rigId, fixture.id, { [String(offset)]: value });
      }, 50);
    },
    [rigId, fixture.id]
  );

  return (
    <Popover
      open={Boolean(anchorEl)}
      anchorEl={anchorEl}
      onClose={onClose}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      transformOrigin={{ vertical: 'top', horizontal: 'left' }}
      PaperProps={{ sx: { p: 2, width: 360 } }}
    >
      <Typography variant="subtitle1" fontWeight="bold" gutterBottom>
        {fixture.name || `Fixture @ ${fixture.dmx_address}`}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" mb={2}>
        Universe {fixture.universe}, Address {fixture.dmx_address}
      </Typography>

      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap mb={2}>
        <Button
          size="small"
          variant={testType === 'identify' ? 'contained' : 'outlined'}
          startIcon={<FlashOnIcon />}
          onClick={() => handleTest('identify')}
          disabled={testing && testType !== 'identify'}
        >
          Identify
        </Button>
        <Button
          size="small"
          variant={testType === 'color_cycle' ? 'contained' : 'outlined'}
          startIcon={<PaletteIcon />}
          onClick={() => handleTest('color_cycle')}
          disabled={testing && testType !== 'color_cycle'}
        >
          Colors
        </Button>
        <Button
          size="small"
          variant={testType === 'movement' ? 'contained' : 'outlined'}
          startIcon={<MoveIcon />}
          onClick={() => handleTest('movement')}
          disabled={testing && testType !== 'movement'}
        >
          Movement
        </Button>
        <Button
          size="small"
          variant={testType === 'full' ? 'contained' : 'outlined'}
          startIcon={<PlayIcon />}
          onClick={() => handleTest('full')}
          disabled={testing && testType !== 'full'}
        >
          Full
        </Button>
        {testing && (
          <Button
            size="small"
            color="error"
            variant="outlined"
            startIcon={<StopIcon />}
            onClick={handleStop}
          >
            Stop
          </Button>
        )}
      </Stack>

      {channels.length > 0 && (
        <Accordion>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography variant="body2">Channel Sliders ({channels.length})</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Box sx={{ maxHeight: 300, overflow: 'auto' }}>
              {channels
                .sort((a, b) => a.channel_number - b.channel_number)
                .map((ch) => (
                <Box key={ch.channel_number} sx={{ mb: 1 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: -0.5 }}>
                    <Typography variant="caption">
                      {ch.channel_number}. {ch.name}
                    </Typography>
                    <Chip label={ch.channel_type} size="small" sx={{ fontSize: '0.6rem', height: 18 }} />
                  </Box>
                  <Slider
                    size="small"
                    min={0}
                    max={255}
                    defaultValue={ch.default_value}
                    onChange={(_, val) => handleSliderChange(ch.channel_number - 1, val as number)}
                    valueLabelDisplay="auto"
                  />
                </Box>
              ))}
            </Box>
          </AccordionDetails>
        </Accordion>
      )}
    </Popover>
  );
}
