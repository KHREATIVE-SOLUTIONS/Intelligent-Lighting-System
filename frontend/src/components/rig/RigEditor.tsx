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
} from '@mui/material';
import {
  ArrowBack as BackIcon,
  Add as AddIcon,
  Delete as DeleteIcon,
  Save as SaveIcon,
  Visibility as ViewIcon,
} from '@mui/icons-material';
import { rigsApi, fixturesApi } from '../../services/api';
import type { Rig, Fixture, RigFixtureCreate } from '../../types';

export default function RigEditor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [rig, setRig] = useState<Rig | null>(null);
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [loading, setLoading] = useState(true);
  const [addFixtureOpen, setAddFixtureOpen] = useState(false);
  const [newFixture, setNewFixture] = useState<RigFixtureCreate>({
    fixture_id: 0,
    dmx_address: 1,
    universe: 0,
    position_x: 0,
    position_y: 4,
    position_z: 0,
    name: '',
  });

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

  const handleAddFixture = async () => {
    if (!rig || !newFixture.fixture_id) return;

    try {
      await rigsApi.addFixture(rig.id, newFixture);
      setAddFixtureOpen(false);
      setNewFixture({
        fixture_id: 0,
        dmx_address: 1,
        universe: 0,
        position_x: 0,
        position_y: 4,
        position_z: 0,
        name: '',
      });
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

  const getNextAddress = (): number => {
    if (!rig?.fixtures?.length) return 1;
    const maxAddress = Math.max(...rig.fixtures.map((f) => f.dmx_address));
    return Math.min(maxAddress + 16, 512);
  };

  if (loading) {
    return <Typography>Loading...</Typography>;
  }

  if (!rig) {
    return <Typography>Rig not found</Typography>;
  }

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
          startIcon={<ViewIcon />}
          onClick={() => navigate(`/rigs/${rig.id}/visualizer`)}
        >
          3D View
        </Button>
        <Button startIcon={<SaveIcon />} variant="contained" onClick={handleSave}>
          Save
        </Button>
      </Box>

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
                    onChange={(e) =>
                      setRig({ ...rig, stage_width: Number(e.target.value) })
                    }
                  />
                </Grid>
                <Grid item xs={4}>
                  <TextField
                    label="Depth (m)"
                    type="number"
                    fullWidth
                    value={rig.stage_depth}
                    onChange={(e) =>
                      setRig({ ...rig, stage_depth: Number(e.target.value) })
                    }
                  />
                </Grid>
                <Grid item xs={4}>
                  <TextField
                    label="Height (m)"
                    type="number"
                    fullWidth
                    value={rig.stage_height}
                    onChange={(e) =>
                      setRig({ ...rig, stage_height: Number(e.target.value) })
                    }
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
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <Typography variant="h6">Fixtures ({rig.fixtures?.length || 0})</Typography>
                <Button
                  startIcon={<AddIcon />}
                  onClick={() => {
                    setNewFixture({ ...newFixture, dmx_address: getNextAddress() });
                    setAddFixtureOpen(true);
                  }}
                >
                  Add Fixture
                </Button>
              </Box>

              <List>
                {rig.fixtures?.map((fixture) => (
                  <ListItem key={fixture.id} divider>
                    <ListItemText
                      primary={fixture.name || fixture.fixture?.model || `Fixture ${fixture.id}`}
                      secondary={
                        <>
                          Universe {fixture.universe}, Address {fixture.dmx_address}
                          <br />
                          Position: ({fixture.position_x.toFixed(1)}, {fixture.position_y.toFixed(1)},{' '}
                          {fixture.position_z.toFixed(1)})
                          {fixture.group_name && ` - Group: ${fixture.group_name}`}
                        </>
                      }
                    />
                    <ListItemSecondaryAction>
                      <IconButton
                        onClick={() => handleRemoveFixture(fixture.id)}
                        color="error"
                        size="small"
                      >
                        <DeleteIcon />
                      </IconButton>
                    </ListItemSecondaryAction>
                  </ListItem>
                ))}
                {(!rig.fixtures || rig.fixtures.length === 0) && (
                  <ListItem>
                    <ListItemText
                      primary="No fixtures"
                      secondary="Click 'Add Fixture' to add fixtures to this rig"
                    />
                  </ListItem>
                )}
              </List>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Add Fixture Dialog */}
      <Dialog
        open={addFixtureOpen}
        onClose={() => setAddFixtureOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Add Fixture to Rig</DialogTitle>
        <DialogContent>
          <FormControl fullWidth margin="normal">
            <InputLabel>Fixture Type</InputLabel>
            <Select
              value={newFixture.fixture_id}
              onChange={(e) =>
                setNewFixture({ ...newFixture, fixture_id: Number(e.target.value) })
              }
              label="Fixture Type"
            >
              {fixtures.map((f) => (
                <MenuItem key={f.id} value={f.id}>
                  {f.manufacturer} {f.model}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

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
                onChange={(e) =>
                  setNewFixture({ ...newFixture, universe: Number(e.target.value) })
                }
                inputProps={{ min: 0, max: 15 }}
              />
            </Grid>
            <Grid item xs={6}>
              <TextField
                label="DMX Address"
                type="number"
                fullWidth
                value={newFixture.dmx_address}
                onChange={(e) =>
                  setNewFixture({ ...newFixture, dmx_address: Number(e.target.value) })
                }
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
                onChange={(e) =>
                  setNewFixture({ ...newFixture, position_x: Number(e.target.value) })
                }
                inputProps={{ step: 0.1 }}
              />
            </Grid>
            <Grid item xs={4}>
              <TextField
                label="Y (Height)"
                type="number"
                fullWidth
                value={newFixture.position_y}
                onChange={(e) =>
                  setNewFixture({ ...newFixture, position_y: Number(e.target.value) })
                }
                inputProps={{ step: 0.1 }}
              />
            </Grid>
            <Grid item xs={4}>
              <TextField
                label="Z (Depth)"
                type="number"
                fullWidth
                value={newFixture.position_z}
                onChange={(e) =>
                  setNewFixture({ ...newFixture, position_z: Number(e.target.value) })
                }
                inputProps={{ step: 0.1 }}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddFixtureOpen(false)}>Cancel</Button>
          <Button
            onClick={handleAddFixture}
            variant="contained"
            disabled={!newFixture.fixture_id}
          >
            Add
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
