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
  Slider,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Paper,
} from '@mui/material';
import {
  ArrowBack as BackIcon,
  Add as AddIcon,
  Delete as DeleteIcon,
  Save as SaveIcon,
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  Stop as StopIcon,
} from '@mui/icons-material';
import { showsApi, cuesApi, tracksApi } from '../../services/api';
import type { Show, CueCreate, TrackCreate } from '../../types';
import { useShowStore } from '../../stores/showStore';

export default function ShowEditor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [show, setShow] = useState<Show | null>(null);
  const [loading, setLoading] = useState(true);
  const [editedName, setEditedName] = useState('');
  const [editedBpm, setEditedBpm] = useState(120);

  const { playbackState, currentTime, play, pause, stop, seek } = useShowStore();

  useEffect(() => {
    if (id) {
      fetchShow(Number(id));
    }
  }, [id]);

  const fetchShow = async (showId: number) => {
    setLoading(true);
    try {
      const data = await showsApi.get(showId);
      setShow(data);
      setEditedName(data.name);
      setEditedBpm(data.bpm || 120);
    } catch (error) {
      console.error('Failed to fetch show:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!show) return;

    try {
      const updated = await showsApi.update(show.id, {
        name: editedName,
        bpm: editedBpm,
      });
      setShow(updated);
    } catch (error) {
      console.error('Failed to save show:', error);
    }
  };

  const handleAddTrack = async () => {
    if (!show) return;

    const trackData: TrackCreate = {
      name: `Track ${(show.tracks?.length || 0) + 1}`,
      track_type: 'fixture',
      order: show.tracks?.length || 0,
    };

    try {
      await tracksApi.create(show.id, trackData);
      fetchShow(show.id);
    } catch (error) {
      console.error('Failed to add track:', error);
    }
  };

  const handleAddCue = async (trackId?: number) => {
    if (!show) return;

    const cueData: CueCreate = {
      name: `Cue ${(show.cues?.length || 0) + 1}`,
      start_time: currentTime,
      duration: 2,
      fade_in: 0.5,
      fade_out: 0.5,
      cue_type: 'fade',
      track_id: trackId,
    };

    try {
      await cuesApi.create(show.id, cueData);
      fetchShow(show.id);
    } catch (error) {
      console.error('Failed to add cue:', error);
    }
  };

  const handleDeleteCue = async (cueId: number) => {
    if (!show) return;

    try {
      await cuesApi.delete(show.id, cueId);
      fetchShow(show.id);
    } catch (error) {
      console.error('Failed to delete cue:', error);
    }
  };

  const handleDeleteTrack = async (trackId: number) => {
    if (!show) return;

    try {
      await tracksApi.delete(show.id, trackId);
      fetchShow(show.id);
    } catch (error) {
      console.error('Failed to delete track:', error);
    }
  };

  if (loading) {
    return <Typography>Loading...</Typography>;
  }

  if (!show) {
    return <Typography>Show not found</Typography>;
  }

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3, gap: 2 }}>
        <IconButton onClick={() => navigate('/shows')}>
          <BackIcon />
        </IconButton>
        <TextField
          value={editedName}
          onChange={(e) => setEditedName(e.target.value)}
          variant="standard"
          sx={{ flexGrow: 1 }}
          InputProps={{ style: { fontSize: '1.5rem' } }}
        />
        <Button startIcon={<SaveIcon />} variant="contained" onClick={handleSave}>
          Save
        </Button>
      </Box>

      <Grid container spacing={3}>
        {/* Show Settings */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Settings
              </Typography>

              <TextField
                fullWidth
                label="BPM"
                type="number"
                value={editedBpm}
                onChange={(e) => setEditedBpm(Number(e.target.value))}
                margin="normal"
              />

              <Typography gutterBottom sx={{ mt: 2 }}>
                Valence: {show.base_valence.toFixed(2)}
              </Typography>
              <Slider
                value={show.base_valence}
                min={0}
                max={1}
                step={0.01}
                disabled
              />

              <Typography gutterBottom>
                Arousal: {show.base_arousal.toFixed(2)}
              </Typography>
              <Slider
                value={show.base_arousal}
                min={0}
                max={1}
                step={0.01}
                disabled
              />
            </CardContent>
          </Card>
        </Grid>

        {/* Playback Controls */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Playback
              </Typography>

              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                <IconButton onClick={playbackState === 'playing' ? pause : play}>
                  {playbackState === 'playing' ? <PauseIcon /> : <PlayIcon />}
                </IconButton>
                <IconButton onClick={stop}>
                  <StopIcon />
                </IconButton>

                <Box sx={{ flexGrow: 1, mx: 2 }}>
                  <Slider
                    value={currentTime}
                    min={0}
                    max={show.duration || 60}
                    onChange={(_, value) => seek(value as number)}
                  />
                </Box>

                <Typography>
                  {currentTime.toFixed(1)}s / {(show.duration || 60).toFixed(1)}s
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Tracks */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <Typography variant="h6">Tracks</Typography>
                <Button startIcon={<AddIcon />} onClick={handleAddTrack}>
                  Add Track
                </Button>
              </Box>

              <List>
                {show.tracks?.map((track) => (
                  <ListItem key={track.id}>
                    <ListItemText
                      primary={track.name}
                      secondary={`${track.track_type} - ${track.cues?.length || 0} cues`}
                    />
                    <ListItemSecondaryAction>
                      <IconButton onClick={() => handleAddCue(track.id)} size="small">
                        <AddIcon />
                      </IconButton>
                      <IconButton
                        onClick={() => handleDeleteTrack(track.id)}
                        size="small"
                        color="error"
                      >
                        <DeleteIcon />
                      </IconButton>
                    </ListItemSecondaryAction>
                  </ListItem>
                ))}
              </List>
            </CardContent>
          </Card>
        </Grid>

        {/* Cues */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <Typography variant="h6">Cues</Typography>
                <Button startIcon={<AddIcon />} onClick={() => handleAddCue()}>
                  Add Cue
                </Button>
              </Box>

              <List>
                {show.cues
                  ?.sort((a, b) => a.start_time - b.start_time)
                  .map((cue) => (
                    <ListItem key={cue.id}>
                      <ListItemText
                        primary={cue.name || `Cue at ${cue.start_time}s`}
                        secondary={`${cue.cue_type} - ${cue.start_time}s - ${cue.duration}s`}
                      />
                      <ListItemSecondaryAction>
                        <IconButton
                          onClick={() => handleDeleteCue(cue.id)}
                          size="small"
                          color="error"
                        >
                          <DeleteIcon />
                        </IconButton>
                      </ListItemSecondaryAction>
                    </ListItem>
                  ))}
              </List>
            </CardContent>
          </Card>
        </Grid>

        {/* Timeline */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Timeline
              </Typography>

              <Paper
                sx={{
                  height: 200,
                  bgcolor: 'grey.900',
                  p: 2,
                  position: 'relative',
                  overflow: 'hidden',
                }}
              >
                {/* Time markers */}
                {Array.from({ length: 10 }).map((_, i) => (
                  <Box
                    key={i}
                    sx={{
                      position: 'absolute',
                      left: `${(i / 10) * 100}%`,
                      top: 0,
                      bottom: 0,
                      borderLeft: '1px solid',
                      borderColor: 'grey.800',
                    }}
                  >
                    <Typography
                      variant="caption"
                      sx={{ position: 'absolute', top: 4, left: 4, color: 'grey.600' }}
                    >
                      {((show.duration || 60) * i / 10).toFixed(0)}s
                    </Typography>
                  </Box>
                ))}

                {/* Cue blocks */}
                {show.cues?.map((cue) => {
                  const duration = show.duration || 60;
                  const left = (cue.start_time / duration) * 100;
                  const width = (cue.duration / duration) * 100;

                  return (
                    <Box
                      key={cue.id}
                      sx={{
                        position: 'absolute',
                        left: `${left}%`,
                        width: `${width}%`,
                        top: 40,
                        height: 30,
                        bgcolor: 'primary.main',
                        borderRadius: 1,
                        opacity: 0.8,
                        display: 'flex',
                        alignItems: 'center',
                        px: 1,
                        cursor: 'pointer',
                        '&:hover': { opacity: 1 },
                      }}
                    >
                      <Typography variant="caption" noWrap>
                        {cue.name}
                      </Typography>
                    </Box>
                  );
                })}

                {/* Playhead */}
                <Box
                  sx={{
                    position: 'absolute',
                    left: `${(currentTime / (show.duration || 60)) * 100}%`,
                    top: 0,
                    bottom: 0,
                    width: 2,
                    bgcolor: 'secondary.main',
                    zIndex: 10,
                  }}
                />
              </Paper>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
