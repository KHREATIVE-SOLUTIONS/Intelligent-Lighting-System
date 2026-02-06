import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Card,
  CardContent,
  CardActions,
  Button,
  Grid,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Chip,
  Pagination,
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  CheckCircle as ActiveIcon,
  Visibility as ViewIcon,
} from '@mui/icons-material';
import { rigsApi } from '../../services/api';
import type { Rig, RigCreate } from '../../types';

export default function RigList() {
  const navigate = useNavigate();
  const [rigs, setRigs] = useState<Rig[]>([]);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newRig, setNewRig] = useState<RigCreate>({
    name: '',
    description: '',
    venue: '',
    stage_width: 10,
    stage_depth: 8,
    stage_height: 6,
  });

  const fetchRigs = async () => {
    try {
      const response = await rigsApi.list(page, 12, search || undefined);
      setRigs(response.items);
      setTotalPages(response.pages);
    } catch (error) {
      console.error('Failed to fetch rigs:', error);
    }
  };

  useEffect(() => {
    fetchRigs();
  }, [page, search]);

  const handleCreate = async () => {
    try {
      const rig = await rigsApi.create(newRig);
      setCreateDialogOpen(false);
      setNewRig({
        name: '',
        description: '',
        venue: '',
        stage_width: 10,
        stage_depth: 8,
        stage_height: 6,
      });
      navigate(`/rigs/${rig.id}`);
    } catch (error) {
      console.error('Failed to create rig:', error);
    }
  };

  const handleDelete = async (id: number) => {
    if (window.confirm('Are you sure you want to delete this rig?')) {
      try {
        await rigsApi.delete(id);
        fetchRigs();
      } catch (error) {
        console.error('Failed to delete rig:', error);
      }
    }
  };

  const handleActivate = async (id: number) => {
    try {
      await rigsApi.activate(id);
      fetchRigs();
    } catch (error) {
      console.error('Failed to activate rig:', error);
    }
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="h4">Rigs</Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreateDialogOpen(true)}
        >
          New Rig
        </Button>
      </Box>

      <TextField
        fullWidth
        placeholder="Search rigs..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        sx={{ mb: 3 }}
      />

      <Grid container spacing={3}>
        {rigs.map((rig) => (
          <Grid item xs={12} sm={6} md={4} key={rig.id}>
            <Card sx={{ border: rig.is_active ? 2 : 0, borderColor: 'primary.main' }}>
              <CardContent>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                  <Typography variant="h6" noWrap>
                    {rig.name}
                  </Typography>
                  {rig.is_active && (
                    <Chip
                      size="small"
                      label="Active"
                      color="primary"
                      icon={<ActiveIcon />}
                    />
                  )}
                </Box>
                <Typography variant="body2" color="text.secondary" noWrap>
                  {rig.venue || 'No venue'}
                </Typography>
                <Box sx={{ mt: 2, display: 'flex', gap: 2 }}>
                  <Typography variant="body2">
                    {rig.stage_width}m x {rig.stage_depth}m x {rig.stage_height}m
                  </Typography>
                </Box>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                  {rig.fixtures?.length || 0} fixtures
                </Typography>
              </CardContent>
              <CardActions>
                <IconButton
                  size="small"
                  onClick={() => navigate(`/rigs/${rig.id}`)}
                  title="Edit"
                >
                  <EditIcon />
                </IconButton>
                <IconButton
                  size="small"
                  onClick={() => navigate(`/rigs/${rig.id}/visualizer`)}
                  title="3D View"
                >
                  <ViewIcon />
                </IconButton>
                <IconButton
                  size="small"
                  onClick={() => handleDelete(rig.id)}
                  title="Delete"
                  color="error"
                >
                  <DeleteIcon />
                </IconButton>
                <Box sx={{ flexGrow: 1 }} />
                {!rig.is_active && (
                  <Button size="small" onClick={() => handleActivate(rig.id)}>
                    Activate
                  </Button>
                )}
              </CardActions>
            </Card>
          </Grid>
        ))}
      </Grid>

      {totalPages > 1 && (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
          <Pagination
            count={totalPages}
            page={page}
            onChange={(_, value) => setPage(value)}
            color="primary"
          />
        </Box>
      )}

      {/* Create Dialog */}
      <Dialog
        open={createDialogOpen}
        onClose={() => setCreateDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Create New Rig</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Rig Name"
            fullWidth
            value={newRig.name}
            onChange={(e) => setNewRig({ ...newRig, name: e.target.value })}
          />
          <TextField
            margin="dense"
            label="Venue"
            fullWidth
            value={newRig.venue}
            onChange={(e) => setNewRig({ ...newRig, venue: e.target.value })}
          />
          <TextField
            margin="dense"
            label="Description"
            fullWidth
            multiline
            rows={2}
            value={newRig.description}
            onChange={(e) => setNewRig({ ...newRig, description: e.target.value })}
          />
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={4}>
              <TextField
                label="Width (m)"
                type="number"
                fullWidth
                value={newRig.stage_width}
                onChange={(e) =>
                  setNewRig({ ...newRig, stage_width: Number(e.target.value) })
                }
              />
            </Grid>
            <Grid item xs={4}>
              <TextField
                label="Depth (m)"
                type="number"
                fullWidth
                value={newRig.stage_depth}
                onChange={(e) =>
                  setNewRig({ ...newRig, stage_depth: Number(e.target.value) })
                }
              />
            </Grid>
            <Grid item xs={4}>
              <TextField
                label="Height (m)"
                type="number"
                fullWidth
                value={newRig.stage_height}
                onChange={(e) =>
                  setNewRig({ ...newRig, stage_height: Number(e.target.value) })
                }
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleCreate} variant="contained" disabled={!newRig.name}>
            Create
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
