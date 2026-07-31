import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Tabs,
  Tab,
  TextField,
  Grid,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Pagination,
  InputAdornment,
  Chip,
  Stack,
  Alert,
  CircularProgress,
} from '@mui/material';
import { Search as SearchIcon, Add as AddIcon } from '@mui/icons-material';
import axios from 'axios';
import { fixturesApi } from '../../services/api';
import type { OnlineFixtureResult } from '../../services/api';
import FixtureCard from './FixtureCard';
import type { Fixture } from '../../types';

const FIXTURE_TYPES = [
  'moving_head', 'led_par', 'led_bar', 'wash', 'spot',
  'beam', 'strobe', 'laser', 'effect', 'dimmer',
];

const prettifyKey = (key: string): string =>
  key
    .split('-')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

export default function FixtureLibrary() {
  const navigate = useNavigate();
  const [tab, setTab] = useState(0);
  const [search, setSearch] = useState('');
  const [manufacturer, setManufacturer] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [manufacturers, setManufacturers] = useState<string[]>([]);

  // Local library state
  const [localFixtures, setLocalFixtures] = useState<Fixture[]>([]);
  const [localTotal, setLocalTotal] = useState(0);
  const [localPage, setLocalPage] = useState(1);
  const [localPages, setLocalPages] = useState(1);
  const [localError, setLocalError] = useState('');

  // Online search state
  const [onlineResults, setOnlineResults] = useState<OnlineFixtureResult[]>([]);
  const [onlineSearch, setOnlineSearch] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchedFor, setSearchedFor] = useState('');
  const [onlineError, setOnlineError] = useState('');
  const [importing, setImporting] = useState<Set<string>>(new Set());
  const [imported, setImported] = useState<Set<string>>(new Set());
  const [importError, setImportError] = useState('');

  // Fetch local manufacturers on mount
  useEffect(() => {
    fixturesApi.getManufacturers().then(setManufacturers).catch(() => {});
  }, []);

  // Fetch local fixtures
  const fetchLocal = useCallback(async () => {
    try {
      const data = await fixturesApi.list(localPage, 24, search || undefined, manufacturer || undefined);
      setLocalFixtures(data.items);
      setLocalTotal(data.total);
      setLocalPages(data.pages);
      setLocalError('');
    } catch (err) {
      setLocalFixtures([]);
      setLocalError(
        (axios.isAxiosError(err) && err.response?.data?.detail) ||
          'Could not load your fixture library.'
      );
    }
  }, [localPage, search, manufacturer]);

  useEffect(() => {
    if (tab === 0) fetchLocal();
  }, [tab, fetchLocal]);

  // Search online
  const handleOnlineSearch = async () => {
    const query = onlineSearch.trim();
    if (!query) return;
    setSearching(true);
    setOnlineError('');
    try {
      const data = await fixturesApi.searchOnline(query);
      setOnlineResults(data.results);
      setOnlineError(data.error || '');
    } catch (err) {
      setOnlineResults([]);
      setOnlineError(
        (axios.isAxiosError(err) && err.response?.data?.detail) ||
          'Could not reach the Open Fixture Library. Check your connection and try again.'
      );
    } finally {
      setSearchedFor(query);
      setSearching(false);
    }
  };

  // Import from OFL
  const handleImport = async (mfrKey: string, fixKey: string) => {
    const key = `${mfrKey}/${fixKey}`;
    setImporting((prev) => new Set(prev).add(key));
    setImportError('');
    try {
      await fixturesApi.importFromLibrary(mfrKey, fixKey);
      setImported((prev) => new Set(prev).add(key));
      // Refresh local list if on that tab
      if (tab === 0) fetchLocal();
    } catch (err: any) {
      setImportError(err.response?.data?.detail || 'Import failed');
    } finally {
      setImporting((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  };

  // Filter local by type
  const filteredLocal = typeFilter
    ? localFixtures.filter((f) => f.fixture_type === typeFilter)
    : localFixtures;

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Typography variant="h5">Fixture Library</Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => navigate('/fixtures/new')}
        >
          Create Fixture
        </Button>
      </Box>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label={`My Library (${localTotal})`} />
        <Tab label="Browse Online (OFL)" />
      </Tabs>

      {importError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setImportError('')}>
          {importError}
        </Alert>
      )}

      {tab === 0 && (
        <>
          <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
            <TextField
              size="small"
              placeholder="Search fixtures..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setLocalPage(1); }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon />
                  </InputAdornment>
                ),
              }}
              sx={{ minWidth: 250 }}
            />
            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel>Manufacturer</InputLabel>
              <Select
                value={manufacturer}
                label="Manufacturer"
                onChange={(e) => { setManufacturer(e.target.value); setLocalPage(1); }}
              >
                <MenuItem value="">All</MenuItem>
                {manufacturers.map((m) => (
                  <MenuItem key={m} value={m}>{m}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>

          <Stack direction="row" spacing={0.5} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
            <Chip
              label="All"
              size="small"
              variant={typeFilter === '' ? 'filled' : 'outlined'}
              onClick={() => setTypeFilter('')}
            />
            {FIXTURE_TYPES.map((t) => (
              <Chip
                key={t}
                label={t.replace('_', ' ')}
                size="small"
                variant={typeFilter === t ? 'filled' : 'outlined'}
                onClick={() => setTypeFilter(typeFilter === t ? '' : t)}
              />
            ))}
          </Stack>

          <Grid container spacing={2}>
            {filteredLocal.map((fixture) => (
              <Grid item xs={12} sm={6} md={4} lg={3} key={fixture.id}>
                <FixtureCard
                  fixture={fixture}
                  onClick={() => navigate(`/fixtures/${fixture.id}`)}
                />
              </Grid>
            ))}
          </Grid>

          {localError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {localError}
            </Alert>
          )}

          {!localError && filteredLocal.length === 0 && (
            <Typography color="text.secondary" sx={{ mt: 4, textAlign: 'center' }}>
              No fixtures found. Import from the Online tab or create a new fixture.
            </Typography>
          )}

          {localPages > 1 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
              <Pagination
                count={localPages}
                page={localPage}
                onChange={(_, p) => setLocalPage(p)}
              />
            </Box>
          )}
        </>
      )}

      {tab === 1 && (
        <>
          <Box sx={{ display: 'flex', gap: 2, mb: 3 }}>
            <TextField
              size="small"
              placeholder="Search Open Fixture Library..."
              value={onlineSearch}
              onChange={(e) => setOnlineSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleOnlineSearch()}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon />
                  </InputAdornment>
                ),
              }}
              sx={{ minWidth: 350 }}
            />
            <Button variant="contained" onClick={handleOnlineSearch} disabled={searching}>
              Search
            </Button>
          </Box>

          {onlineError && (
            <Alert severity="error" sx={{ mb: 2 }} onClose={() => setOnlineError('')}>
              {onlineError}
            </Alert>
          )}

          {searching && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
              <CircularProgress />
            </Box>
          )}

          <Grid container spacing={2}>
            {onlineResults.map((result) => {
              const key = `${result.manufacturer_key}/${result.fixture_key}`;
              const isImporting = importing.has(key);

              return (
                <Grid item xs={12} sm={6} md={4} lg={3} key={key}>
                  <Box sx={{ opacity: isImporting ? 0.5 : 1, pointerEvents: isImporting ? 'none' : 'auto' }}>
                    <FixtureCard
                      fixture={{
                        manufacturer: result.manufacturer || prettifyKey(result.manufacturer_key),
                        model: result.name || prettifyKey(result.fixture_key),
                        fixture_type:
                          result.categories?.[0]?.toLowerCase().replace(' ', '_') || 'other',
                        categories: result.categories,
                        manufacturer_key: result.manufacturer_key,
                        fixture_key: result.fixture_key,
                      }}
                      isOnline
                      isImported={imported.has(key)}
                      onImport={() => handleImport(result.manufacturer_key, result.fixture_key)}
                    />
                  </Box>
                </Grid>
              );
            })}
          </Grid>

          {!searching && !onlineError && onlineResults.length === 0 && (
            <Typography color="text.secondary" sx={{ mt: 4, textAlign: 'center' }}>
              {searchedFor
                ? `No fixtures on the Open Fixture Library match "${searchedFor}".`
                : 'Search for fixtures on the Open Fixture Library.'}
            </Typography>
          )}
        </>
      )}
    </Box>
  );
}
