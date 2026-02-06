import { useEffect, useCallback } from 'react';
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  Button,
  LinearProgress,
} from '@mui/material';
import {
  PlayArrow as PlayIcon,
  Stop as StopIcon,
  MusicNote as MusicIcon,
  Mood as MoodIcon,
  Equalizer as EqualizerIcon,
} from '@mui/icons-material';
import { useAudioStore } from '../../stores/audioStore';
import { useDMXStore } from '../../stores/dmxStore';
import { audioWebSocket, audioStreamer } from '../../services/websocket';
import AudioVisualizer from './AudioVisualizer';
import MoodDisplay from './MoodDisplay';
import FrequencyBands from './FrequencyBands';

export default function Dashboard() {
  const {
    isStreaming,
    setStreaming,
    setConnected,
    updateAnalysis,
    beat,
    mood,
    frequency,
  } = useAudioStore();

  const { setUniverse, setFixtureStates, setEffectsInfo } = useDMXStore();

  const handleAnalysisUpdate = useCallback(
    (data: unknown) => {
      const analysisData = data as any;
      updateAnalysis(analysisData);

      // Update DMX store with lighting data from effects engine
      if (analysisData.lighting) {
        if (analysisData.lighting.dmx_frame) {
          setUniverse(0, analysisData.lighting.dmx_frame);
        }
        if (analysisData.lighting.fixtures) {
          setFixtureStates(analysisData.lighting.fixtures);
        }
        if (analysisData.lighting.state) {
          setEffectsInfo(
            analysisData.lighting.state,
            analysisData.lighting.movement || 'none',
            analysisData.lighting.dimmer || 'none'
          );
        }
      }
    },
    [updateAnalysis, setUniverse, setFixtureStates, setEffectsInfo]
  );

  useEffect(() => {
    audioWebSocket.on('analysis', handleAnalysisUpdate);

    return () => {
      audioWebSocket.off('analysis', handleAnalysisUpdate);
    };
  }, [handleAnalysisUpdate]);

  const handleStartListening = async () => {
    try {
      await audioStreamer.start();
      setStreaming(true);
      setConnected(true);
    } catch (error) {
      console.error('Failed to start audio:', error);
    }
  };

  const handleStopListening = () => {
    audioStreamer.stop();
    setStreaming(false);
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Real-Time Audio Analysis
      </Typography>

      {/* Control Panel */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            {!isStreaming ? (
              <Button
                variant="contained"
                color="primary"
                startIcon={<PlayIcon />}
                onClick={handleStartListening}
              >
                Start Listening
              </Button>
            ) : (
              <Button
                variant="contained"
                color="error"
                startIcon={<StopIcon />}
                onClick={handleStopListening}
              >
                Stop Listening
              </Button>
            )}

            <Typography variant="body2" color="text.secondary">
              {isStreaming
                ? 'Analyzing audio from microphone...'
                : 'Click to start audio analysis'}
            </Typography>
          </Box>
        </CardContent>
      </Card>

      <Grid container spacing={3}>
        {/* BPM Card */}
        <Grid item xs={12} md={4}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <MusicIcon sx={{ mr: 1 }} color="primary" />
                <Typography variant="h6">Beat Detection</Typography>
              </Box>

              <Typography variant="h2" color="primary" align="center">
                {beat?.bpm.toFixed(0) || '--'}
              </Typography>
              <Typography variant="subtitle1" align="center" color="text.secondary">
                BPM
              </Typography>

              <Box sx={{ mt: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  Confidence
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={(beat?.beat_confidence || 0) * 100}
                  sx={{ height: 8, borderRadius: 4 }}
                />
              </Box>

              <Box
                sx={{
                  mt: 2,
                  display: 'flex',
                  justifyContent: 'space-around',
                  alignItems: 'center',
                }}
              >
                {[1, 2, 3, 4].map((pos) => (
                  <Box
                    key={pos}
                    sx={{
                      width: 24,
                      height: 24,
                      borderRadius: '50%',
                      bgcolor:
                        beat?.beat_position === pos
                          ? beat?.is_downbeat && pos === 1
                            ? 'secondary.main'
                            : 'primary.main'
                          : 'grey.800',
                      transition: 'background-color 0.1s',
                    }}
                  />
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Mood Card */}
        <Grid item xs={12} md={4}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <MoodIcon sx={{ mr: 1 }} color="secondary" />
                <Typography variant="h6">Mood Classification</Typography>
              </Box>

              <MoodDisplay mood={mood} />
            </CardContent>
          </Card>
        </Grid>

        {/* Energy Card */}
        <Grid item xs={12} md={4}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <EqualizerIcon sx={{ mr: 1 }} color="info" />
                <Typography variant="h6">Audio Energy</Typography>
              </Box>

              <Typography variant="h3" color="info.main" align="center">
                {((frequency?.rms_energy || 0) * 100).toFixed(0)}%
              </Typography>
              <Typography variant="subtitle1" align="center" color="text.secondary">
                RMS Energy
              </Typography>

              <Box sx={{ mt: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  Peak Amplitude
                </Typography>
                <LinearProgress
                  variant="determinate"
                  value={(frequency?.peak_amplitude || 0) * 100}
                  color="warning"
                  sx={{ height: 8, borderRadius: 4 }}
                />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Audio Visualizer */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Audio Waveform
              </Typography>
              <Box sx={{ height: 200 }}>
                <AudioVisualizer />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Frequency Bands */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Frequency Bands
              </Typography>
              <FrequencyBands bands={frequency?.bands || []} />
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
