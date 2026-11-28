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
import { rdmApi, rigsApi } from '../../services/api';
import type { RdmSavedDevice } from '../../services/api';

/** One row of the table: a device a scan has stored, so the import can name it by id. */
export interface RDMDeviceRow {
  id: number;
  uid: string;
  manufacturer: string;
  model: string;
  dmx_footprint: number | null;
  universe: number | null;
  dmx_address: number | null;
  status: 'matched' | 'unmatched';
  imported: boolean;
}

/** The stored devices from `GET /rdm/devices`, as rows. Live ones carry no id yet and are left out. */
export function deviceRows(saved: RdmSavedDevice[]): RDMDeviceRow[] {
  return saved.map((d) => ({
    id: d.id,
    uid: d.uid,
    manufacturer: d.manufacturer ?? '',
    model: d.model ?? d.label ?? '',
    dmx_footprint: d.dmx_footprint,
    universe: d.universe,
    dmx_address: d.dmx_address,
    status: d.matched_fixture_id != null ? 'matched' : 'unmatched',
    imported: d.is_imported,
  }));
}

interface RDMDiscoveryProps {
  rigId?: number;
  /** After an import that added at least one device: the ids sent, and how many were added. */
  onImport?: (deviceIds: number[], imported: number) => void;
}

export default function RDMDiscovery({ rigId, onImport }: RDMDiscoveryProps) {
  const [discovering, setDiscovering] = useState(false);
  const [devices, setDevices] = useState<RDMDeviceRow[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [identifyingUid, setIdentifyingUid] = useState<string | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDevices = useCallback(async () => {
    try {
      const answer = await rdmApi.devices();
      setDevices(deviceRows(answer.saved_devices ?? []));
      // The scan ends by itself: stop polling once the server says so.
      if (!answer.scanning && pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
        setDiscovering(false);
      }
    } catch (err) {
      // During discovery, failed polls are expected sometimes
      if (!discovering) {
        console.error('Failed to fetch RDM devices:', err);
      }
    }
  }, [discovering]);

  // What was stored by an earlier scan is shown as soon as the panel opens.
  useEffect(() => { void fetchDevices(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

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
    setSelectedIds(new Set());

    try {
      await rdmApi.start();
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
      await rdmApi.stop();
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
      const answer = await rdmApi.identify(uid);
      // The route answers 200 with an error for a device the scan under way has not seen.
      if (answer?.error) setError(`Could not identify ${uid}: ${answer.error}.`);
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

  // A device already imported is shown, but cannot be picked again.
  const importable = devices.filter((d) => !d.imported);

  const handleToggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    if (importable.length > 0 && selectedIds.size === importable.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(importable.map((d) => d.id)));
    }
  };

  const handleImportSelected = async () => {
    if (selectedIds.size === 0 || !rigId) return;

    setLoading(true);
    setError(null);
    setSuccess(null);

    const ids = Array.from(selectedIds);

    try {
      // Through the app's client, which announces the rig change.
      const { imported } = await rigsApi.importRdmDevices(rigId, ids);
      const skipped = ids.length - imported;
      setSuccess(
        `Added ${imported} device${imported === 1 ? '' : 's'} to the rig.` +
          (skipped > 0 ? ` ${skipped} skipped: already imported or no longer stored.` : ''),
      );
      setSelectedIds(new Set());
      await fetchDevices();
      if (imported > 0) onImport?.(ids, imported);
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
                  inputProps={{ 'aria-label': 'Select every device not yet imported' }}
                  indeterminate={selectedIds.size > 0 && selectedIds.size < importable.length}
                  checked={importable.length > 0 && selectedIds.size === importable.length}
                  onChange={handleSelectAll}
                  disabled={importable.length === 0}
                />
              </TableCell>
              <TableCell>UID</TableCell>
              <TableCell>Manufacturer</TableCell>
              <TableCell>Model</TableCell>
              <TableCell align="center">Address</TableCell>
              <TableCell align="center">DMX Footprint</TableCell>
              <TableCell align="center">Status</TableCell>
              <TableCell align="center">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {devices.map((device) => (
              <TableRow
                key={device.id}
                hover
                selected={selectedIds.has(device.id)}
                sx={{
                  bgcolor: identifyingUid === device.uid ? 'action.selected' : undefined,
                  opacity: device.imported ? 0.6 : undefined,
                }}
              >
                <TableCell padding="checkbox">
                  <Checkbox
                    inputProps={{ 'aria-label': `Select ${device.uid}` }}
                    checked={selectedIds.has(device.id)}
                    disabled={device.imported}
                    onChange={() => handleToggleSelect(device.id)}
                  />
                </TableCell>
                <TableCell>
                  <Typography variant="body2" fontFamily="monospace" fontSize="0.8rem">
                    {device.uid}
                  </Typography>
                </TableCell>
                <TableCell>{device.manufacturer || 'Unknown'}</TableCell>
                <TableCell>{device.model || 'Unknown'}</TableCell>
                <TableCell align="center">
                  {device.dmx_address ? `${device.universe ?? 0}.${device.dmx_address}` : '-'}
                </TableCell>
                <TableCell align="center">{device.dmx_footprint || '-'}</TableCell>
                <TableCell align="center">
                  {device.imported ? (
                    <Chip label="Imported" size="small" variant="outlined" />
                  ) : (
                    <Chip
                      label={device.status === 'matched' ? 'Matched' : 'Unmatched'}
                      color={device.status === 'matched' ? 'success' : 'warning'}
                      size="small"
                      variant="outlined"
                    />
                  )}
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
                <TableCell colSpan={8} align="center" sx={{ py: 4 }}>
                  <Typography color="text.secondary">
                    No RDM devices stored. Click "Start Discovery" to scan.
                  </Typography>
                  {/* Said plainly: the backend's scan is a placeholder with no RDM
                      interface driver (services/discovery/rdm_service.py). */}
                  <Typography variant="caption" color="text.secondary" component="p" sx={{ mt: 1 }}>
                    Finding devices needs an RDM-capable USB DMX interface, and this
                    build cannot talk to one yet: a scan here finds nothing. Patch by
                    make and model, or scan the fixtures' QR labels, instead.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
            {devices.length === 0 && discovering && (
              <TableRow>
                <TableCell colSpan={8} align="center" sx={{ py: 4 }}>
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
            disabled={selectedIds.size === 0 || loading}
          >
            {loading
              ? 'Importing...'
              : `Import Selected (${selectedIds.size})`}
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
