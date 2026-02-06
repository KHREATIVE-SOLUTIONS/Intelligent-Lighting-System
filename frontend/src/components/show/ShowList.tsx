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
  ContentCopy as DuplicateIcon,
  PlayArrow as PlayIcon,
} from '@mui/icons-material';
import { showsApi } from '../../services/api';
import type { Show, ShowCreate } from '../../types';

export default function ShowList() {
  const navigate = useNavigate();
  const [shows, setShows] = useState<Show[]>([]);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newShow, setNewShow] = useState<ShowCreate>({
    name: '',
    description: '',
    bpm: 120,
  });

  const fetchShows = async () => {
    try {
      const response = await showsApi.list(page, 12, search || undefined);
      setShows(response.items);
      setTotalPages(response.pages);
    } catch (error) {
      console.error('Failed to fetch shows:', error);
    }
  };

  useEffect(() => {
    fetchShows();
  }, [page, search]);

  const handleCreate = async () => {
    try {
      const show = await showsApi.create(newShow);
      setCreateDialogOpen(false);
      setNewShow({ name: '', description: '', bpm: 120 });
      navigate(`/shows/${show.id}`);
    } catch (error) {
      console.error('Failed to create show:', error);
    }
  };

  const handleDelete = async (id: number) => {
    if (window.confirm('Are you sure you want to delete this show?')) {
      try {
        await showsApi.delete(id);
        fetchShows();
      } catch (error) {
        console.error('Failed to delete show:', error);
      }
    }
  };

  const handleDuplicate = async (id: number, name: string) => {
    try {
      const show = await showsApi.duplicate(id, `${name} (Copy)`);
      navigate(`/shows/${show.id}`);
    } catch (error) {
      console.error('Failed to duplicate show:', error);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'ready':
        return 'success';
      case 'playing':
        return 'primary';
      case 'paused':
        return 'warning';
      default:
        return 'default';
    }
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="h4">Shows</Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setCreateDialogOpen(true)}
        >
          New Show
        </Button>
      </Box>

      <TextField
        fullWidth
        placeholder="Search shows..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        sx={{ mb: 3 }}
      />

      <Grid container spacing={3}>
        {shows.map((show) => (
          <Grid item xs={12} sm={6} md={4} key={show.id}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                  <Typography variant="h6" noWrap>
                    {show.name}
                  </Typography>
                  <Chip
                    size="small"
                    label={show.status}
                    color={getStatusColor(show.status) as any}
                  />
                </Box>
                <Typography variant="body2" color="text.secondary" noWrap>
                  {show.description || 'No description'}
                </Typography>
                <Box sx={{ mt: 2, display: 'flex', gap: 2 }}>
                  <Typography variant="body2">
                    {show.bpm ? `${show.bpm} BPM` : 'No BPM'}
                  </Typography>
                  <Typography variant="body2">
                    {show.duration ? `${show.duration.toFixed(0)}s` : 'No duration'}
                  </Typography>
                  <Typography variant="body2">{show.cues?.length || 0} cues</Typography>
                </Box>
              </CardContent>
              <CardActions>
                <IconButton
                  size="small"
                  onClick={() => navigate(`/shows/${show.id}`)}
                  title="Edit"
                >
                  <EditIcon />
                </IconButton>
                <IconButton
                  size="small"
                  onClick={() => handleDuplicate(show.id, show.name)}
                  title="Duplicate"
                >
                  <DuplicateIcon />
                </IconButton>
                <IconButton
                  size="small"
                  onClick={() => handleDelete(show.id)}
                  title="Delete"
                  color="error"
                >
                  <DeleteIcon />
                </IconButton>
                <Box sx={{ flexGrow: 1 }} />
                <Button size="small" startIcon={<PlayIcon />} disabled>
                  Play
                </Button>
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
        <DialogTitle>Create New Show</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Show Name"
            fullWidth
            value={newShow.name}
            onChange={(e) => setNewShow({ ...newShow, name: e.target.value })}
          />
          <TextField
            margin="dense"
            label="Description"
            fullWidth
            multiline
            rows={2}
            value={newShow.description}
            onChange={(e) => setNewShow({ ...newShow, description: e.target.value })}
          />
          <TextField
            margin="dense"
            label="BPM"
            type="number"
            fullWidth
            value={newShow.bpm}
            onChange={(e) => setNewShow({ ...newShow, bpm: Number(e.target.value) })}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleCreate} variant="contained" disabled={!newShow.name}>
            Create
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
