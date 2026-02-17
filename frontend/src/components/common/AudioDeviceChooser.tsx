import { useState, useEffect, useCallback } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
} from '@mui/material';
import {
  ErrorOutline as ErrorIcon,
  Mic as MicIcon,
  VolumeUp as SpeakerIcon,
  FiberManualRecord as RecordIcon,
} from '@mui/icons-material';
import {
  audioApi,
  type AudioCaptureDevice,
  type AudioCaptureStatus,
} from '../../services/api';

export default function AudioDeviceChooser() {
  const [devices, setDevices] = useState<AudioCaptureDevice[]>([]);
  const [status, setStatus] = useState<AudioCaptureStatus | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<number>(-1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  const fetchDevices = useCallback(async () => {
    try {
      const captureDevices = await audioApi.getCaptureDevices();
      setDevices(captureDevices);
      if (captureDevices.length > 0) {
        setSelectedDevice((prev) => (prev >= 0 ? prev : captureDevices[0].index));
        setError('');
      }
      if (captureDevices.length === 0) {
        setError('No capture devices found. Ensure backend audio dependencies are installed and device is active.');
      }
    } catch (e) {
      console.error('Failed to fetch devices:', e);
      setError('Failed to load audio devices.');
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const captureStatus = await audioApi.getCaptureStatus();
      setStatus(captureStatus);
      if (!captureStatus.available) {
        setError('Audio capture service is not available in backend.');
      }
    } catch (e) {
      console.error('Failed to fetch capture status:', e);
      setError('Failed to load capture status.');
    }
  }, []);

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

  return (
    <Stack spacing={1.5}>
      {error ? (
        <Alert severity="error" icon={<ErrorIcon fontSize="inherit" />}>
          {error}
        </Alert>
      ) : null}

      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
        <Chip
          icon={isRunning ? <RecordIcon sx={{ fontSize: 12 }} /> : undefined}
          label={isRunning ? status?.device_name || 'Capturing' : 'Not capturing'}
          color={isRunning ? 'success' : 'default'}
          size="small"
          sx={isRunning ? { '& .MuiChip-icon': { color: '#f44336', animation: 'pulse 1.5s infinite' } } : {}}
        />

        <FormControl size="small" sx={{ minWidth: 280 }} disabled={isRunning || isUnavailable}>
          <InputLabel>Audio Device</InputLabel>
          <Select
            value={selectedDevice}
            label="Audio Device"
            onChange={(e) => setSelectedDevice(Number(e.target.value))}
          >
            <MenuItem value={-1} disabled>
              Select a device...
            </MenuItem>
            {devices.map((dev) => (
              <MenuItem key={dev.index} value={dev.index}>
                {dev.is_loopback ? (
                  <SpeakerIcon sx={{ fontSize: 16, mr: 0.5, color: 'success.main' }} />
                ) : dev.max_input_channels > 0 ? (
                  <MicIcon sx={{ fontSize: 16, mr: 0.5 }} />
                ) : null}
                {dev.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        {!isRunning ? (
          <Button
            variant="contained"
            size="small"
            onClick={handleStart}
            disabled={loading || selectedDevice < 0 || isUnavailable}
            startIcon={loading ? <CircularProgress size={16} /> : <SpeakerIcon />}
          >
            Start Capture
          </Button>
        ) : (
          <Button
            variant="outlined"
            size="small"
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
                ? 'WASAPI Loopback'
                : status.capture_method === 'pyaudio_loopback'
                ? 'WASAPI (PyAudio)'
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
      </Box>
    </Stack>
  );
}
