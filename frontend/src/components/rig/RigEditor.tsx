import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Button,
  TextField,
  Grid,
  IconButton,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Tooltip,
  Chip,
  Switch,
  FormControlLabel,
  Alert,
} from '@mui/material';
import {
  ArrowBack as BackIcon,
  Add as AddIcon,
  Delete as DeleteIcon,
  Save as SaveIcon,
  Visibility as ViewIcon,
  FlashOn as TestIcon,
  Lock as LockIcon,
  LockOpen as LockOpenIcon,
  AutoFixHigh as AutoPatchIcon,
  Warning as WarningIcon,
  ViewInAr as BuilderIcon,
} from '@mui/icons-material';
import { rigsApi, fixturesApi } from '../../services/api';
import FixtureTestPanel from './FixtureTestPanel';
import LibraryFixturePicker from './LibraryFixturePicker';
import type { Rig, Fixture, RigFixtureCreate, PatchConflict, FixtureChannel } from '../../types';

export default function RigEditor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [rig, setRig] = useState<Rig | null>(null);
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [loading, setLoading] = useState(true);
  const [addFixtureOpen, setAddFixtureOpen] = useState(false);
  const [libraryPickerOpen, setLibraryPickerOpen] = useState(false);
  const [conflicts, setConflicts] = useState<PatchConflict[]>([]);
  const [autoPatching, setAutoPatching] = useState(false);

  // Test panel state
  const [testAnchor, setTestAnchor] = useState<HTMLElement | null>(null);
  const [testFixtureId, setTestFixtureId] = useState<number | null>(null);

  const [newFixture, setNewFixture] = useState<RigFixtureCreate>({
    fixture_id: 0,
    dmx_address: 1,
    universe: 0,
    mode_id: undefined,
    position_x: 0,
    position_y: 4,
    position_z: 0,
    name: '',
  });

  // Selected fixture's available modes
  const [selectedFixtureModes, setSelectedFixtureModes] = useState<Fixture['modes']>([]);

  useEffect(() => {
    if (id) {
      fetchRig(Number(id));
      fetchFixtureLibrary();
    }
  }, [id]);

  const fetchRig = async (rigId: number) => {
    setLoading(true);
    try {
      const data = await rigsApi.get(rigId);
      setRig(data);
      // Check for conflicts
      checkConflicts(rigId);
    } catch (error) {
      console.error('Failed to fetch rig:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchFixtureLibrary = async () => {
    try {
      const response = await fixturesApi.list(1, 100);
      setFixtures(response.items);
    } catch (error) {
      console.error('Failed to fetch fixtures:', error);
    }
  };

  const checkConflicts = async (rigId: number) => {
    try {
      const data = await rigsApi.getConflicts(rigId);
      setConflicts(data.conflicts || []);
    } catch {
      // Silently ignore - conflicts are informational
    }
  };

  const handleSave = async () => {
    if (!rig) return;
    try {
      await rigsApi.update(rig.id, {
        name: rig.name,
        description: rig.description,
        venue: rig.venue,
        stage_width: rig.stage_width,
        stage_depth: rig.stage_depth,
        stage_height: rig.stage_height,
      });
    } catch (error) {
      console.error('Failed to save rig:', error);
    }
  };

  const handleFixtureSelect = (fixtureId: number) => {
    const f = fixtures.find((fix) => fix.id === fixtureId);
    setSelectedFixtureModes(f?.modes || []);
    const firstMode = f?.modes?.[0];
    setNewFixture({
      ...newFixture,
      fixture_id: fixtureId,
      mode_id: firstMode?.id,
    });
  };

  const handleAddFixture = async () => {
    if (!rig || !newFixture.fixture_id) return;
    try {
      await rigsApi.addFixture(rig.id, newFixture);
      setAddFixtureOpen(false);
      setNewFixture({
        fixture_id: 0,
        dmx_address: 1,
        universe: 0,
        mode_id: undefined,
        position_x: 0,
        position_y: 4,
        position_z: 0,
        name: '',
      });
      setSelectedFixtureModes([]);
      fetchRig(rig.id);
    } catch (error) {
      console.error('Failed to add fixture:', error);
    }
  };

  const handleRemoveFixture = async (fixtureId: number) => {
    if (!rig) return;
    try {
      await rigsApi.removeFixture(rig.id, fixtureId);
      fetchRig(rig.id);
    } catch (error) {
      console.error('Failed to remove fixture:', error);
    }
  };

  const handleAutoPatch = async () => {
    if (!rig) return;
    setAutoPatching(true);
    try {
      await rigsApi.autoPatch(rig.id);
      await fetchRig(rig.id);
    } catch (error) {
      console.error('Auto-patch failed:', error);
    } finally {
      setAutoPatching(false);
    }
  };

  const handleToggleLock = async (fixtureId: number, currentLocked: boolean) => {
    if (!rig) return;
    try {
      await rigsApi.updateFixture(rig.id, fixtureId, { is_address_locked: !currentLocked });
      fetchRig(rig.id);
    } catch (error) {
      console.error('Failed to toggle lock:', error);
    }
  };

  const handleOpenTest = (event: React.MouseEvent<HTMLElement>, fixtureId: number) => {
    setTestAnchor(event.currentTarget);
    setTestFixtureId(fixtureId);
  };

  const handleTestAll = async () => {
    if (!rig) return;
    try {
      await rigsApi.testAll(rig.id);
    } catch (error) {
      console.error('Test all failed:', error);
    }
  };

  const getNextAddress = async (): Promise<number> => {
    if (!rig) return 1;
    try {
      const data = await rigsApi.getNextAddress(rig.id, newFixture.universe || 0);
      return data.address || 1;
    } catch {
      // Fallback
      if (!rig.fixtures?.length) return 1;
      const maxAddress = Math.max(...rig.fixtures.map((f) => f.dmx_address));
      return Math.min(maxAddress + 16, 512);
    }
  };

  const isFixtureConflicting = (fixtureId: number): boolean => {
    return conflicts.some(
      (c) => c.fixture_a_id === fixtureId || c.fixture_b_id === fixtureId
    );
  };

  // Get channels for the test panel fixture
  const getTestFixtureChannels = (): FixtureChannel[] => {
    if (!testFixtureId || !rig) return [];
    const rf = rig.fixtures.find((f) => f.id === testFixtureId);
    if (!rf?.fixture?.modes) return [];
    const mode = rf.fixture.modes.find((m) => m.id === rf.mode_id);
    return mode?.channels || [];
  };

  if (loading) return <Typography>Loading...</Typography>;
  if (!rig) return <Typography>Rig not found</Typography>;

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3, gap: 2 }}>
        <IconButton onClick={() => navigate('/rigs')}>
          <BackIcon />
        </IconButton>
        <TextField
          value={rig.name}
          onChange={(e) => setRig({ ...rig, name: e.target.value })}
          variant="standard"
          sx={{ flexGrow: 1 }}
          InputProps={{ style: { fontSize: '1.5rem' } }}
        />
        <Button
          startIcon={<BuilderIcon />}
          onClick={() => navigate(`/rigs/${rig.id}/builder`)}
        >
          2D Builder
        </Button>
        <Button
          startIcon={<ViewIcon />}
          onClick={() => navigate(`/rigs/${rig.id}/visualizer`)}
        >
          3D View
        </Button>
        <Button startIcon={<SaveIcon />} variant="contained" onClick={handleSave}>
          Save
        </Button>
      </Box>

      {conflicts.length > 0 && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {conflicts.length} DMX address conflict{conflicts.length > 1 ? 's' : ''} detected.
          <Button size="small" onClick={handleAutoPatch} sx={{ ml: 1 }}>
            Auto-fix
          </Button>
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Rig Settings */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Stage Settings
              </Typography>
              <TextField
                fullWidth
                label="Venue"
                value={rig.venue || ''}
                onChange={(e) => setRig({ ...rig, venue: e.target.value })}
                margin="normal"
              />
              <TextField
                fullWidth
                label="Description"
                multiline
                rows={2}
                value={rig.description || ''}
                onChange={(e) => setRig({ ...rig, description: e.target.value })}
                margin="normal"
              />
              <Grid container spacing={2} sx={{ mt: 1 }}>
                <Grid item xs={4}>
                  <TextField
                    label="Width (m)"
                    type="number"
                    fullWidth
                    value={rig.stage_width}
                    onChange={(e) => setRig({ ...rig, stage_width: Number(e.target.value) })}
                  />
                </Grid>
                <Grid item xs={4}>
                  <TextField
                    label="Depth (m)"
                    type="number"
                    fullWidth
                    value={rig.stage_depth}
                    onChange={(e) => setRig({ ...rig, stage_depth: Number(e.target.value) })}
                  />
                </Grid>
                <Grid item xs={4}>
                  <TextField
                    label="Height (m)"
                    type="number"
                    fullWidth
                    value={rig.stage_height}
                    onChange={(e) => setRig({ ...rig, stage_height: Number(e.target.value) })}
                  />
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Fixtures */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Typography variant="h6">Fixtures ({rig.fixtures?.length || 0})</Typography>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <Button
                    size="small"
                    startIcon={<AutoPatchIcon />}
                    onClick={handleAutoPatch}
                    disabled={autoPatching}
                  >
                    Auto-Patch
                  </Button>
                  <Button
                    size="small"
                    startIcon={<TestIcon />}
                    onClick={handleTestAll}
                  >
                    Test All
                  </Button>
                  <Button
                    size="small"
                    onClick={async () => {
                      const addr = await getNextAddress();
                      setNewFixture({ ...newFixture, dmx_address: addr });
                      setAddFixtureOpen(true);
                    }}
                  >
                    Add Manually
                  </Button>
                  <Button
                    variant="contained"
                    startIcon={<AddIcon />}
                    onClick={() => setLibraryPickerOpen(true)}
                  >
                    Add Fixtures
                  </Button>
                </Box>
              </Box>

              <List>
                {rig.fixtures?.map((fixture) => {
                  const hasConflict = isFixtureConflicting(fixture.id);
                  return (
                    <ListItem
                      key={fixture.id}
                      divider
                      sx={{
                        borderLeft: hasConflict ? '3px solid #f44336' : 'none',
                        bgcolor: hasConflict ? 'rgba(244,67,54,0.04)' : 'inherit',
                      }}
                    >
                      <ListItemText
                        primary={
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <span>{fixture.name || fixture.fixture?.model || `Fixture ${fixture.id}`}</span>
                            {hasConflict && (
                              <Tooltip title="DMX address conflict">
                                <WarningIcon color="error" fontSize="small" />
                              </Tooltip>
                            )}
                            {fixture.is_address_locked && (
                              <Chip label="Locked" size="small" icon={<LockIcon />} />
                            )}
                          </Box>
                        }
                        secondary={
                          <>
                            Universe {fixture.universe}, Address {fixture.dmx_address}
                            {fixture.mode_id && ` | Mode ID: ${fixture.mode_id}`}
                            <br />
                            Position: ({fixture.position_x.toFixed(1)}, {fixture.position_y.toFixed(1)},{' '}
                            {fixture.position_z.toFixed(1)})
                            {fixture.group_name && ` - Group: ${fixture.group_name}`}
                          </>
                        }
                      />
                      <ListItemSecondaryAction>
                        <Tooltip title={fixture.is_address_locked ? 'Unlock address' : 'Lock address'}>
                          <IconButton
                            size="small"
                            onClick={() => handleToggleLock(fixture.id, fixture.is_address_locked)}
                          >
                            {fixture.is_address_locked ? <LockIcon fontSize="small" /> : <LockOpenIcon fontSize="small" />}
                          </IconButton>
                        </Tooltip>
                        <Tooltip title="Test fixture">
                          <IconButton
                            size="small"
                            onClick={(e) => handleOpenTest(e, fixture.id)}
                          >
                            <TestIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <IconButton
                          onClick={() => handleRemoveFixture(fixture.id)}
                          color="error"
                          size="small"
                        >
                          <DeleteIcon />
                        </IconButton>
                      </ListItemSecondaryAction>
                    </ListItem>
                  );
                })}
                {(!rig.fixtures || rig.fixtures.length === 0) && (
                  <ListItem>
                    <ListItemText
                      primary="No fixtures"
                      secondary="Click 'Add Fixtures' to find your lights by make and model"
                    />
                  </ListItem>
                )}
              </List>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Test Panel Popover */}
      {testFixtureId && rig.fixtures.find((f) => f.id === testFixtureId) && (
        <FixtureTestPanel
          rigId={rig.id}
          fixture={rig.fixtures.find((f) => f.id === testFixtureId)!}
          channels={getTestFixtureChannels()}
          anchorEl={testAnchor}
          onClose={() => { setTestAnchor(null); setTestFixtureId(null); }}
        />
      )}

      <LibraryFixturePicker
        open={libraryPickerOpen}
        rigId={rig.id}
        onClose={() => setLibraryPickerOpen(false)}
        onPatched={() => {
          fetchRig(rig.id);
          fetchFixtureLibrary();
        }}
      />

      {/* Add Fixture Dialog */}
      <Dialog open={addFixtureOpen} onClose={() => setAddFixtureOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add Fixture to Rig</DialogTitle>
        <DialogContent>
          <FormControl fullWidth margin="normal">
            <InputLabel>Fixture Type</InputLabel>
            <Select
              value={newFixture.fixture_id}
              onChange={(e) => handleFixtureSelect(Number(e.target.value))}
              label="Fixture Type"
            >
              {fixtures.map((f) => (
                <MenuItem key={f.id} value={f.id}>
                  {f.manufacturer} {f.model}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {selectedFixtureModes.length > 0 && (
            <FormControl fullWidth margin="normal">
              <InputLabel>Mode</InputLabel>
              <Select
                value={newFixture.mode_id || ''}
                onChange={(e) => setNewFixture({ ...newFixture, mode_id: Number(e.target.value) || undefined })}
                label="Mode"
              >
                {selectedFixtureModes.map((m) => (
                  <MenuItem key={m.id} value={m.id}>
                    {m.name} ({m.channel_count} channels)
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}

          <TextField
            margin="normal"
            label="Name"
            fullWidth
            value={newFixture.name}
            onChange={(e) => setNewFixture({ ...newFixture, name: e.target.value })}
          />

          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={6}>
              <TextField
                label="Universe"
                type="number"
                fullWidth
                value={newFixture.universe}
                onChange={(e) => setNewFixture({ ...newFixture, universe: Number(e.target.value) })}
                inputProps={{ min: 0, max: 15 }}
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                label="DMX Address"
                type="number"
                fullWidth
                value={newFixture.dmx_address}
                onChange={(e) => setNewFixture({ ...newFixture, dmx_address: Number(e.target.value) })}
                inputProps={{ min: 1, max: 512 }}
              />
            </Grid>
          </Grid>

          <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>
            Position (meters)
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={4}>
              <TextField
                label="X"
                type="number"
                fullWidth
                value={newFixture.position_x}
                onChange={(e) => setNewFixture({ ...newFixture, position_x: Number(e.target.value) })}
                inputProps={{ step: 0.1 }}
              />
            </Grid>
            <Grid item xs={4}>
              <TextField
                label="Y (Height)"
                type="number"
                fullWidth
                value={newFixture.position_y}
                onChange={(e) => setNewFixture({ ...newFixture, position_y: Number(e.target.value) })}
                inputProps={{ step: 0.1 }}
              />
            </Grid>
            <Grid item xs={4}>
              <TextField
                label="Z (Depth)"
                type="number"
                fullWidth
                value={newFixture.position_z}
                onChange={(e) => setNewFixture({ ...newFixture, position_z: Number(e.target.value) })}
                inputProps={{ step: 0.1 }}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddFixtureOpen(false)}>Cancel</Button>
          <Button onClick={handleAddFixture} variant="contained" disabled={!newFixture.fixture_id}>
            Add
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
