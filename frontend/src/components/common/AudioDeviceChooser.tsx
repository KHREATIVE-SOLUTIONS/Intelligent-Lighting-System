import { useState, useEffect, useCallback } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  IconButton,
  InputLabel,
  ListSubheader,
  MenuItem,
  Select,
  Stack,
  Tooltip,
} from '@mui/material';
import {
  ErrorOutline as ErrorIcon,
  Mic as MicIcon,
  VolumeUp as SpeakerIcon,
  FiberManualRecord as RecordIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import {
  audioApi,
  type AudioCaptureDevice,
  type AudioCaptureStatus,
} from '../../services/api';
import { useAudioStore } from '../../stores/audioStore';

// Remembered by name: indexes shift when a USB interface is replugged.
const LAST_DEVICE_KEY = 'audio.lastDeviceName';

const readLastDevice = (): string | null => {
  try {
    return window.localStorage.getItem(LAST_DEVICE_KEY);
  } catch {
    return null;
  }
};

const rememberDevice = (name: string) => {
  try {
    window.localStorage.setItem(LAST_DEVICE_KEY, name);
  } catch {
    // Private mode or blocked storage: just don't remember.
  }
};

// At a venue the feed is usually a line input from the desk; loopback is for
// playing from this computer. Show both, inputs first.
export function sortCaptureDevices(devices: AudioCaptureDevice[]): {
  inputs: AudioCaptureDevice[];
  loopback: AudioCaptureDevice[];
} {
  const loopback = devices.filter((d) => d.is_loopback);
  const pyaudioLoopback = loopback.filter((d) => d.device_type === 'pyaudio_loopback');
  return {
    inputs: devices.filter((d) => !d.is_loopback && d.max_input_channels > 0),
    // Prefer the PyAudio loopback entries when present; the others duplicate them.
    loopback: pyaudioLoopback.length > 0 ? pyaudioLoopback : loopback,
  };
}

export default function AudioDeviceChooser() {
  const setStreaming = useAudioStore((state) => state.setStreaming);
  const [devices, setDevices] = useState<AudioCaptureDevice[]>([]);
  const [status, setStatus] = useState<AudioCaptureStatus | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<number>(-1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  const [inputs, setInputs] = useState<AudioCaptureDevice[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const fetchDevices = useCallback(async () => {
    setRefreshing(true);
    try {
      const captureDevices = await audioApi.getCaptureDevices();
      const sorted = sortCaptureDevices(captureDevices);
      const all = [...sorted.inputs, ...sorted.loopback];
      setInputs(sorted.inputs);
      setDevices(sorted.loopback);
      if (all.length > 0) {
        const remembered = readLastDevice();
        const match = remembered ? all.find((d) => d.name === remembered) : undefined;
        setSelectedDevice((prev) =>
          all.some((d) => d.index === prev) ? prev : (match ?? all[0]).index
        );
        setError('');
      } else {
        setError('No audio inputs found. Plug in the interface from the desk, then tap refresh.');
      }
    } catch (e) {
      console.error('Failed to fetch devices:', e);
      setError('Could not load audio devices from the box. Tap refresh to try again.');
    } finally {
      setRefreshing(false);
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const captureStatus = await audioApi.getCaptureStatus();
      setStatus(captureStatus);
      setStreaming(!!captureStatus.running);
      if (!captureStatus.available) {
        setError('Audio capture is not available on the box.');
      }
    } catch (e) {
      console.error('Failed to fetch capture status:', e);
    }
  }, [setStreaming]);

  useEffect(() => {
    fetchDevices();
    fetchStatus();
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, [fetchDevices, fetchStatus]);

  const handleStart = async () => {
    if (selectedDevice < 0) {
      setError('Select a specific audio device before starting capture.');
      return;
    }

    setLoading(true);
    setError('');
    try {
      await audioApi.startCapture(selectedDevice);
      const picked = [...inputs, ...devices].find((d) => d.index === selectedDevice);
      if (picked) rememberDevice(picked.name);
      await fetchStatus();
    } catch (e: any) {
      console.error('Failed to start capture:', e);
      const detail = e?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Failed to start capture.');
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    // Stopping capture leaves the autopilot deaf for the rest of the night.
    if (!window.confirm('Stop audio capture? The lights stop following the music.')) return;
    setLoading(true);
    setError('');
    try {
      await audioApi.stopCapture();
      await fetchStatus();
    } catch (e) {
      console.error('Failed to stop capture:', e);
      setError('Failed to stop capture.');
    } finally {
      setLoading(false);
    }
  };

  const isRunning = status?.running ?? false;
  const isUnavailable = status ? !status.available : false;
  const signalLevel = status?.last_rms ?? 0;
  const hasSignal = signalLevel > 0.001;

  return (
    <Stack spacing={1.5}>
      {error ? (
        <Alert severity="error" icon={<ErrorIcon fontSize="inherit" />}>
          {error}
        </Alert>
      ) : null}

      <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
        <Chip
          icon={isRunning ? <RecordIcon sx={{ fontSize: 12 }} /> : undefined}
          label={isRunning ? status?.device_name || 'Capturing' : 'Not capturing'}
          color={isRunning ? 'success' : 'default'}
          size="small"
          sx={isRunning ? { '& .MuiChip-icon': { color: '#f44336', animation: 'pulse 1.5s infinite' } } : {}}
        />

        <FormControl sx={{ minWidth: 280 }} disabled={isRunning || isUnavailable}>
          <InputLabel>Audio Device</InputLabel>
          <Select
            value={selectedDevice}
            label="Audio Device"
            onChange={(e) => setSelectedDevice(Number(e.target.value))}
          >
            <MenuItem value={-1} disabled>
              Select a device...
            </MenuItem>
            {inputs.length > 0 && <ListSubheader>Inputs (desk feed, mic)</ListSubheader>}
            {inputs.map((dev) => (
              <MenuItem key={`in-${dev.index}`} value={dev.index}>
                <MicIcon sx={{ fontSize: 16, mr: 0.5 }} />
                {dev.name}
              </MenuItem>
            ))}
            {devices.length > 0 && <ListSubheader>This computer's audio (loopback)</ListSubheader>}
            {devices.map((dev) => (
              <MenuItem key={`lb-${dev.index}`} value={dev.index}>
                <SpeakerIcon sx={{ fontSize: 16, mr: 0.5, color: 'success.main' }} />
                {dev.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <Tooltip title="Look for devices again">
          <span>
            <IconButton
              onClick={fetchDevices}
              disabled={refreshing || isRunning}
              aria-label="Refresh audio devices"
              size="large"
            >
              {refreshing ? <CircularProgress size={24} /> : <RefreshIcon />}
            </IconButton>
          </span>
        </Tooltip>

        {!isRunning ? (
          <Button
            variant="contained"
            size="large"
            onClick={handleStart}
            disabled={loading || selectedDevice < 0 || isUnavailable}
            startIcon={loading ? <CircularProgress size={16} /> : <SpeakerIcon />}
          >
            Start Capture
          </Button>
        ) : (
          <Button
            variant="outlined"
            size="large"
            color="error"
            onClick={handleStop}
            disabled={loading}
          >
            Stop
          </Button>
        )}

        {isRunning && status?.capture_method && (
          <Chip
            label={
              status.capture_method === 'soundcard_loopback'
                ? status?.platform === 'darwin'
                  ? 'CoreAudio Loopback'
                  : 'WASAPI Loopback'
                : status.capture_method === 'pyaudio_loopback'
                ? 'WASAPI (PyAudio)'
                : status.capture_method === 'sounddevice'
                ? 'Audio Input'
                : 'Direct Input'
            }
            size="small"
            variant="outlined"
            color={
              status.capture_method === 'soundcard_loopback' || status.capture_method === 'pyaudio_loopback'
                ? 'info'
                : 'warning'
            }
          />
        )}

        {isRunning && (
          <Chip
            size="small"
            color={hasSignal ? 'success' : 'warning'}
            label={hasSignal ? `Signal ${(signalLevel * 100).toFixed(1)}%` : 'No input signal'}
            variant="outlined"
          />
        )}
      </Box>
    </Stack>
  );
}
