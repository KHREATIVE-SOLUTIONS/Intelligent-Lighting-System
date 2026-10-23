import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  Grid,
  InputAdornment,
  InputLabel,
  List,
  ListItemButton,
  ListItemText,
  MenuItem,
  Select,
  TextField,
  Typography,
} from '@mui/material';
import { Search as SearchIcon } from '@mui/icons-material';
import axios from 'axios';
import { fixturesApi, rigsApi } from '../../services/api';
import type {
  CatalogFixture,
  LibraryPatchResult,
  OfflineLibraryInfo,
} from '../../services/api';

const TYPE_FILTERS: Array<{ value: string; label: string }> = [
  { value: '', label: 'All' },
  { value: 'moving_head', label: 'Movers' },
  { value: 'wash', label: 'Washes / pars' },
  { value: 'led_bar', label: 'LED bars' },
  { value: 'strobe', label: 'Strobes' },
  { value: 'spot', label: 'Spots / scanners' },
  { value: 'effect', label: 'Effects' },
  { value: 'laser', label: 'Lasers' },
  { value: 'dimmer', label: 'Dimmers' },
];

const MOUNTING_POSITIONS: Array<{ value: string; label: string }> = [
  { value: '', label: 'Auto (by fixture type)' },
  { value: 'front_truss', label: 'Front truss' },
  { value: 'mid_truss', label: 'Mid truss' },
  { value: 'back_truss', label: 'Back truss' },
  { value: 'floor', label: 'Floor' },
  { value: 'side_left', label: 'Side left' },
  { value: 'side_right', label: 'Side right' },
  { value: 'ceiling', label: 'Ceiling' },
];

const typeLabel = (type: string): string =>
  TYPE_FILTERS.find((t) => t.value === type)?.label ?? type.replace(/_/g, ' ');

const errorText = (error: unknown, fallback: string): string => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') return detail;
  }
  return fallback;
};

interface LibraryFixturePickerProps {
  open: boolean;
  rigId: number;
  onClose: () => void;
  onPatched: (result: LibraryPatchResult) => void;
}

/**
 * Find a fixture by make and model and patch any number of them in one go.
 *
 * Searches the app's own library and the bundled Open Fixture Library, so it
 * works with no internet at load-in. The mode a programmer would pick is
 * preselected and addresses are found automatically unless a start is given.
 */
export default function LibraryFixturePicker({ open, rigId, onClose, onPatched }: LibraryFixturePickerProps) {
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [results, setResults] = useState<CatalogFixture[]>([]);
  const [library, setLibrary] = useState<OfflineLibraryInfo | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');

  const [selected, setSelected] = useState<CatalogFixture | null>(null);
  const [modeName, setModeName] = useState('');
  const [quantity, setQuantity] = useState(1);
  const [universe, setUniverse] = useState(0);
  const [startAddress, setStartAddress] = useState('');
  const [mounting, setMounting] = useState('');
  const [groupName, setGroupName] = useState('');

  const [patching, setPatching] = useState(false);
  const [patchError, setPatchError] = useState('');
  const [lastResult, setLastResult] = useState<LibraryPatchResult | null>(null);

  // Search as the operator types, a beat after they stop.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setSearching(true);
      setSearchError('');
      try {
        const data = await fixturesApi.searchCatalog(query.trim(), typeFilter || undefined);
        if (cancelled) return;
        setResults(data.results);
        setLibrary(data.offline_library);
      } catch (error) {
        if (!cancelled) setSearchError(errorText(error, 'The fixture library could not be searched.'));
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, query, typeFilter]);

  const selectFixture = (fixture: CatalogFixture) => {
    setSelected(fixture);
    setModeName(fixture.recommended_mode ?? fixture.modes[0]?.name ?? '');
    setGroupName(fixture.name);
    setPatchError('');
  };

  const mode = useMemo(
    () => selected?.modes.find((m) => m.name === modeName) ?? null,
    [selected, modeName]
  );

  const handlePatch = async () => {
    if (!selected) return;
    setPatching(true);
    setPatchError('');
    try {
      const result = await rigsApi.patchFromLibrary(rigId, {
        ...(selected.fixture_id != null
          ? { fixture_id: selected.fixture_id }
          : { library_key: selected.key }),
        ...(modeName && modeName !== selected.recommended_mode ? { mode_name: modeName } : {}),
        quantity,
        universe,
        ...(startAddress.trim() ? { start_address: Number(startAddress) } : {}),
        ...(mounting ? { mounting_position: mounting } : {}),
        group_name: groupName,
      });
      setLastResult(result);
      // The profile is in the library now; patch more of it without importing again.
      setSelected({ ...selected, fixture_id: result.fixture.id, in_library: true });
      setStartAddress('');
      onPatched(result);
    } catch (error) {
      setPatchError(errorText(error, 'The fixtures could not be patched.'));
    } finally {
      setPatching(false);
    }
  };

  const handleClose = () => {
    setLastResult(null);
    setPatchError('');
    onClose();
  };

  const first = lastResult?.patched[0];
  const last = lastResult?.patched[lastResult.patched.length - 1];

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
      <DialogTitle>Add fixtures from the library</DialogTitle>
      <DialogContent>
        <TextField
          autoFocus
          fullWidth
          placeholder="Make and model, e.g. intimidator 260, rogue r2, adj mega hex"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          margin="dense"
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
            endAdornment: searching ? (
              <InputAdornment position="end">
                <CircularProgress size={18} />
              </InputAdornment>
            ) : undefined,
          }}
        />
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, my: 1 }}>
          {TYPE_FILTERS.map((t) => (
            <Chip
              key={t.value || 'all'}
              label={t.label}
              size="small"
              color={typeFilter === t.value ? 'primary' : 'default'}
              onClick={() => setTypeFilter(t.value)}
            />
          ))}
        </Box>
        {library && (
          <Typography variant="caption" color="text.secondary">
            {library.available
              ? `Works offline: ${library.fixture_count} fixtures from the Open Fixture Library` +
                (library.generated ? ` (updated ${library.generated})` : '')
              : 'The offline fixture library is not installed; only your own library is searched.'}
          </Typography>
        )}
        {searchError && <Alert severity="error" sx={{ mt: 1 }}>{searchError}</Alert>}

        <Grid container spacing={2} sx={{ mt: 0.5 }}>
          <Grid item xs={12} md={6}>
            <List dense sx={{ maxHeight: 360, overflow: 'auto', border: 1, borderColor: 'divider', borderRadius: 1 }}>
              {results.map((fixture) => (
                <ListItemButton
                  key={fixture.key}
                  selected={selected?.key === fixture.key}
                  onClick={() => selectFixture(fixture)}
                >
                  <ListItemText
                    primary={`${fixture.manufacturer} ${fixture.name}`}
                    secondary={
                      <Box component="span" sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
                        <Chip component="span" size="small" label={typeLabel(fixture.fixture_type)} />
                        {fixture.recommended_mode && (
                          <Chip
                            component="span"
                            size="small"
                            variant="outlined"
                            label={`${fixture.modes.find((m) => m.recommended)?.channel_count ?? '?'} ch`}
                          />
                        )}
                        {fixture.in_library && (
                          <Chip component="span" size="small" color="success" variant="outlined" label="In library" />
                        )}
                      </Box>
                    }
                  />
                </ListItemButton>
              ))}
              {!searching && results.length === 0 && (
                <Box sx={{ p: 2 }}>
                  <Typography variant="body2" color="text.secondary">
                    Nothing matches. Try fewer words, or import a GDTF file from the fixture library page.
                  </Typography>
                </Box>
              )}
            </List>
          </Grid>

          <Grid item xs={12} md={6}>
            {!selected ? (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                Pick a fixture to choose its mode and how many to patch.
              </Typography>
            ) : (
              <Box>
                <Typography variant="subtitle1">
                  {selected.manufacturer} {selected.name}
                </Typography>
                <FormControl fullWidth margin="dense" size="small">
                  <InputLabel>DMX mode</InputLabel>
                  <Select value={modeName} label="DMX mode" onChange={(e) => setModeName(e.target.value)}>
                    {selected.modes.map((m) => (
                      <MenuItem key={m.name} value={m.name}>
                        {m.name} ({m.channel_count} ch){m.recommended ? ' - recommended' : ''}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                {mode && (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, my: 1 }}>
                    {mode.features.map((f) => (
                      <Chip key={f} size="small" label={f} variant="outlined" />
                    ))}
                    {mode.features.length === 0 && (
                      <Typography variant="caption" color="warning.main">
                        The show cannot drive anything in this mode.
                      </Typography>
                    )}
                  </Box>
                )}
                <Grid container spacing={1}>
                  <Grid item xs={4}>
                    <TextField
                      label="How many"
                      type="number"
                      size="small"
                      fullWidth
                      margin="dense"
                      value={quantity}
                      inputProps={{ min: 1, max: 96 }}
                      onChange={(e) => setQuantity(Math.max(1, Math.min(96, Number(e.target.value) || 1)))}
                    />
                  </Grid>
                  <Grid item xs={4}>
                    <TextField
                      label="Universe"
                      type="number"
                      size="small"
                      fullWidth
                      margin="dense"
                      value={universe}
                      inputProps={{ min: 0, max: 15 }}
                      onChange={(e) => setUniverse(Math.max(0, Math.min(15, Number(e.target.value) || 0)))}
                    />
                  </Grid>
                  <Grid item xs={4}>
                    <TextField
                      label="Start address"
                      placeholder="Auto"
                      type="number"
                      size="small"
                      fullWidth
                      margin="dense"
                      value={startAddress}
                      inputProps={{ min: 1, max: 512 }}
                      onChange={(e) => setStartAddress(e.target.value)}
                    />
                  </Grid>
                </Grid>
                <FormControl fullWidth margin="dense" size="small">
                  <InputLabel>Hung on</InputLabel>
                  <Select value={mounting} label="Hung on" onChange={(e) => setMounting(e.target.value)}>
                    {MOUNTING_POSITIONS.map((p) => (
                      <MenuItem key={p.value || 'auto'} value={p.value}>
                        {p.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <TextField
                  label="Group"
                  size="small"
                  fullWidth
                  margin="dense"
                  value={groupName}
                  onChange={(e) => setGroupName(e.target.value)}
                />
              </Box>
            )}
          </Grid>
        </Grid>

        {patchError && <Alert severity="error" sx={{ mt: 2 }}>{patchError}</Alert>}
        {lastResult && first && last && (
          <Alert severity="success" sx={{ mt: 2 }}>
            Patched {lastResult.patched.length} x {lastResult.fixture.manufacturer} {lastResult.fixture.model} in{' '}
            {lastResult.mode.name} mode, universe {first.universe} address {first.dmx_address}
            {last !== first ? ` to universe ${last.universe} address ${last.last_address}` : `-${first.last_address}`}.
            {lastResult.applied_live ? ' The running show is using them now.' : ''}
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose}>Done</Button>
        <Button variant="contained" onClick={handlePatch} disabled={!selected || patching}>
          {patching ? 'Patching...' : `Patch ${quantity}`}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
