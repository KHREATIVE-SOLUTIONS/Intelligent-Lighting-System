import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box,
  Typography,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Checkbox,
  LinearProgress,
  Chip,
  IconButton,
  Tooltip,
  Alert,
  Stack,
} from '@mui/material';
import {
  PlayArrow as StartIcon,
  Stop as StopIcon,
  Highlight as IdentifyIcon,
  CloudDownload as ImportIcon,
  Refresh as RefreshIcon,
  DeviceHub as DeviceIcon,
  CheckCircle as MatchedIcon,
  HelpOutline as UnmatchedIcon,
} from '@mui/icons-material';
import axios from 'axios';

interface RDMDevice {
  uid: string;
  manufacturer: string;
  model: string;
  dmx_footprint: number;
  status: 'matched' | 'unmatched';
  fixture_id?: number;
}

interface RDMDiscoveryProps {
  rigId?: number;
  onImport?: (deviceIds: string[]) => void;
}

export default function RDMDiscovery({ rigId, onImport }: RDMDiscoveryProps) {
  const [discovering, setDiscovering] = useState(false);
  const [devices, setDevices] = useState<RDMDevice[]>([]);
  const [selectedUids, setSelectedUids] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [identifyingUid, setIdentifyingUid] = useState<string | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDevices = useCallback(async () => {
    try {
      const response = await axios.get('/api/rdm/devices');
      const fetchedDevices: RDMDevice[] = response.data;
      setDevices(fetchedDevices);
    } catch (err) {
      // During discovery, failed polls are expected sometimes
      if (!discovering) {
        console.error('Failed to fetch RDM devices:', err);
      }
    }
  }, [discovering]);

  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
    }
    pollIntervalRef.current = setInterval(fetchDevices, 2000);
  }, [fetchDevices]);

  const stopPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  const handleStartDiscovery = async () => {
    setError(null);
    setSuccess(null);
    setDiscovering(true);
    setDevices([]);
    setSelectedUids(new Set());

    try {
      await axios.post('/api/rdm/start');
      startPolling();
      // Also do an immediate fetch
      await fetchDevices();
    } catch (err) {
      setDiscovering(false);
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || 'Failed to start RDM discovery.');
      } else {
        setError('Failed to start RDM discovery.');
      }
    }
  };

  const handleStopDiscovery = async () => {
    try {
      await axios.post('/api/rdm/stop');
    } catch (err) {
      console.error('Failed to stop discovery:', err);
    } finally {
      setDiscovering(false);
      stopPolling();
      // Do one final fetch
      await fetchDevices();
    }
  };

  const handleRefresh = async () => {
    setLoading(true);
    try {
      await fetchDevices();
    } finally {
      setLoading(false);
    }
  };

  const handleIdentify = async (uid: string) => {
    setIdentifyingUid(uid);
    try {
      await axios.get(`/api/rdm/device/${uid}/identify`);
    } catch (err) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || `Failed to identify device ${uid}.`);
      } else {
        setError(`Failed to identify device ${uid}.`);
      }
    } finally {
      // Keep the identify indicator for a short time so the user sees feedback
      setTimeout(() => setIdentifyingUid(null), 2000);
    }
  };

  const handleToggleSelect = (uid: string) => {
    setSelectedUids((prev) => {
      const next = new Set(prev);
      if (next.has(uid)) {
        next.delete(uid);
      } else {
        next.add(uid);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    if (selectedUids.size === devices.length) {
      setSelectedUids(new Set());
    } else {
      setSelectedUids(new Set(devices.map((d) => d.uid)));
    }
  };

  const handleImportSelected = async () => {
    if (selectedUids.size === 0 || !rigId) return;

    setLoading(true);
    setError(null);
    setSuccess(null);

    const uids = Array.from(selectedUids);

    try {
      await axios.post('/api/rdm/import', {
        device_uids: uids,
        rig_id: rigId,
      });
      setSuccess(`Successfully imported ${uids.length} device${uids.length > 1 ? 's' : ''} into rig.`);
      setSelectedUids(new Set());
      onImport?.(uids);
    } catch (err) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || 'Failed to import selected devices.');
      } else {
        setError('Failed to import selected devices.');
      }
    } finally {
      setLoading(false);
    }
  };

  const matchedCount = devices.filter((d) => d.status === 'matched').length;
  const unmatchedCount = devices.filter((d) => d.status === 'unmatched').length;

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <DeviceIcon color="primary" />
          <Typography variant="h6">RDM Device Discovery</Typography>
        </Box>

        <Stack direction="row" spacing={1}>
          {!discovering ? (
            <Button
              variant="contained"
              startIcon={<StartIcon />}
              onClick={handleStartDiscovery}
              disabled={loading}
            >
              Start Discovery
            </Button>
          ) : (
            <Button
              variant="outlined"
              color="error"
              startIcon={<StopIcon />}
              onClick={handleStopDiscovery}
            >
              Stop Discovery
            </Button>
          )}
          <Tooltip title="Refresh device list">
            <IconButton onClick={handleRefresh} disabled={loading}>
              <RefreshIcon />
            </IconButton>
          </Tooltip>
        </Stack>
      </Box>

      {discovering && (
        <Box sx={{ mb: 2 }}>
          <LinearProgress />
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
            Scanning for RDM devices on the network...
          </Typography>
        </Box>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {/* Summary chips */}
      {devices.length > 0 && (
        <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
          <Chip
            label={`${devices.length} device${devices.length !== 1 ? 's' : ''} found`}
            color="primary"
            variant="outlined"
            size="small"
          />
          {matchedCount > 0 && (
            <Chip
              icon={<MatchedIcon />}
              label={`${matchedCount} matched`}
              color="success"
              variant="outlined"
              size="small"
            />
          )}
          {unmatchedCount > 0 && (
            <Chip
              icon={<UnmatchedIcon />}
              label={`${unmatchedCount} unmatched`}
              color="warning"
              variant="outlined"
              size="small"
            />
          )}
        </Stack>
      )}

      {/* Devices table */}
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell padding="checkbox">
                <Checkbox
                  indeterminate={selectedUids.size > 0 && selectedUids.size < devices.length}
                  checked={devices.length > 0 && selectedUids.size === devices.length}
                  onChange={handleSelectAll}
                  disabled={devices.length === 0}
                />
              </TableCell>
              <TableCell>UID</TableCell>
              <TableCell>Manufacturer</TableCell>
              <TableCell>Model</TableCell>
              <TableCell align="center">DMX Footprint</TableCell>
              <TableCell align="center">Status</TableCell>
              <TableCell align="center">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {devices.map((device) => (
              <TableRow
                key={device.uid}
                hover
                selected={selectedUids.has(device.uid)}
                sx={{
                  bgcolor: identifyingUid === device.uid ? 'action.selected' : undefined,
                }}
              >
                <TableCell padding="checkbox">
                  <Checkbox
                    checked={selectedUids.has(device.uid)}
                    onChange={() => handleToggleSelect(device.uid)}
                  />
                </TableCell>
                <TableCell>
                  <Typography variant="body2" fontFamily="monospace" fontSize="0.8rem">
                    {device.uid}
                  </Typography>
                </TableCell>
                <TableCell>{device.manufacturer || 'Unknown'}</TableCell>
                <TableCell>{device.model || 'Unknown'}</TableCell>
                <TableCell align="center">{device.dmx_footprint || '-'}</TableCell>
                <TableCell align="center">
                  <Chip
                    label={device.status === 'matched' ? 'Matched' : 'Unmatched'}
                    color={device.status === 'matched' ? 'success' : 'warning'}
                    size="small"
                    variant="outlined"
                  />
                </TableCell>
                <TableCell align="center">
                  <Tooltip title="Identify device (flash)">
                    <IconButton
                      size="small"
                      onClick={() => handleIdentify(device.uid)}
                      disabled={identifyingUid !== null}
                      color={identifyingUid === device.uid ? 'primary' : 'default'}
                    >
                      <IdentifyIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
            {devices.length === 0 && !discovering && (
              <TableRow>
                <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                  <Typography color="text.secondary">
                    No devices found. Click "Start Discovery" to scan for RDM devices.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
            {devices.length === 0 && discovering && (
              <TableRow>
                <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                  <Typography color="text.secondary">
                    Scanning... Devices will appear here as they are discovered.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Import button */}
      {rigId !== undefined && devices.length > 0 && (
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 2 }}>
          <Button
            variant="contained"
            startIcon={<ImportIcon />}
            onClick={handleImportSelected}
            disabled={selectedUids.size === 0 || loading}
          >
            {loading
              ? 'Importing...'
              : `Import Selected (${selectedUids.size})`}
          </Button>
        </Box>
      )}

      {!rigId && devices.length > 0 && (
        <Alert severity="info" sx={{ mt: 2 }}>
          Select or create a rig to import discovered devices.
        </Alert>
      )}
    </Box>
  );
}
