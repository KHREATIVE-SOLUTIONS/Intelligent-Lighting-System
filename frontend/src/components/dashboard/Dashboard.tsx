import { useEffect, useCallback } from 'react';
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  LinearProgress,
} from '@mui/material';
import {
  MusicNote as MusicIcon,
  Mood as MoodIcon,
  Equalizer as EqualizerIcon,
  Lightbulb as LightingIcon,
  Timeline as TimelineIcon,
} from '@mui/icons-material';
import { useAudioStore } from '../../stores/audioStore';
import { useDMXStore } from '../../stores/dmxStore';
import { audioWebSocket } from '../../services/websocket';
import AudioVisualizer from './AudioVisualizer';
import MoodDisplay from './MoodDisplay';
import FrequencyBands from './FrequencyBands';
import ProLightingPanel from './ProLightingPanel';
import SectionTimeline from './SectionTimeline';
import AudioDeviceChooser from '../common/AudioDeviceChooser';

export default function Dashboard() {
  const {
    updateAnalysis,
    beat,
    mood,
    frequency,
  } = useAudioStore();

  const {
    setUniverse,
    setFixtureStates,
    setEffectsInfo,
    setGenre,
    setSection,
    setActiveEffects,
    setKeyLightingZones,
    setEmotionVector,
    setBeatPhrase,
  } = useDMXStore();

  const handleAnalysisUpdate = useCallback(
    (data: unknown) => {
      const analysisData = data as any;
      if (analysisData?.beat && analysisData?.mood && analysisData?.frequency) {
        updateAnalysis(analysisData);
      }

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

        // Professional lighting state updates
        if (analysisData.lighting.genre) {
          setGenre(analysisData.lighting.genre);
        }
        if (analysisData.lighting.section) {
          setSection(
            analysisData.lighting.section,
            analysisData.lighting.section_intensity ?? 0
          );
        }
        if (analysisData.lighting.pro_effects) {
          setActiveEffects(analysisData.lighting.pro_effects);
        }
        if (analysisData.lighting.key_zones) {
          setKeyLightingZones(analysisData.lighting.key_zones);
        }
        if (analysisData.lighting.emotion_vector) {
          setEmotionVector(analysisData.lighting.emotion_vector);
        }
        if (analysisData.lighting.beat_phrase !== undefined) {
          setBeatPhrase(
            analysisData.lighting.beat_phrase,
            analysisData.lighting.beats_per_phrase ?? 4
          );
        }
      }
    },
    [
      updateAnalysis, setUniverse, setFixtureStates, setEffectsInfo,
      setGenre, setSection, setActiveEffects, setKeyLightingZones,
      setEmotionVector, setBeatPhrase,
    ]
  );

  useEffect(() => {
    audioWebSocket.on('analysis', handleAnalysisUpdate);
    audioWebSocket.connect().catch((err: any) => {
      console.warn('WebSocket connect failed, will retry:', err);
    });

    return () => {
      audioWebSocket.off('analysis', handleAnalysisUpdate);
    };
  }, [handleAnalysisUpdate]);

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Real-Time Audio Analysis
      </Typography>

      {/* Audio Capture Control */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <AudioDeviceChooser />
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

        {/* Professional Lighting Panel */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <LightingIcon sx={{ mr: 1 }} color="warning" />
                <Typography variant="h6">Professional Lighting</Typography>
              </Box>
              <ProLightingPanel />
            </CardContent>
          </Card>
        </Grid>

        {/* Section Timeline */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <TimelineIcon sx={{ mr: 1 }} color="info" />
                <Typography variant="h6">Section Timeline</Typography>
              </Box>
              <SectionTimeline />
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
