import { Box, Typography, Chip } from '@mui/material';
import type { MoodInfo } from '../../types';

interface MoodDisplayProps {
  mood: MoodInfo | null;
}

const emotionColors: Record<string, string> = {
  happy: '#ffeb3b',
  excited: '#ff9800',
  energetic: '#f44336',
  angry: '#d32f2f',
  sad: '#2196f3',
  calm: '#4caf50',
  relaxed: '#8bc34a',
  melancholic: '#9c27b0',
  neutral: '#9e9e9e',
};

export default function MoodDisplay({ mood }: MoodDisplayProps) {
  if (!mood) {
    return (
      <Box component="div" sx={{ textAlign: 'center', py: 4 }}>
        <Typography color="text.secondary">No mood data available</Typography>
      </Box>
    );
  }

  const emotion = mood.primary_emotion;
  const color = emotionColors[emotion] || emotionColors.neutral;

  return (
    <Box component="div">
      {/* Primary emotion */}
      <Box component="div" sx={{ textAlign: 'center', mb: 3 }}>
        <Chip
          label={emotion.charAt(0).toUpperCase() + emotion.slice(1)}
          sx={{
            bgcolor: color,
            color: 'black',
            fontWeight: 'bold',
            fontSize: '1.2rem',
            py: 2,
            px: 1,
          }}
        />
      </Box>

      {/* Valence-Arousal plot */}
      <Box
        component="div"
        sx={{
          position: 'relative',
          width: '100%',
          paddingTop: '100%',
          bgcolor: 'grey.900',
          borderRadius: 2,
          overflow: 'hidden',
        }}
      >
        {/* Quadrant labels */}
        <Typography
          variant="caption"
          sx={{ position: 'absolute', top: 8, left: 8, color: 'grey.600' }}
        >
          Tense
        </Typography>
        <Typography
          variant="caption"
          sx={{ position: 'absolute', top: 8, right: 8, color: 'grey.600' }}
        >
          Excited
        </Typography>
        <Typography
          variant="caption"
          sx={{ position: 'absolute', bottom: 8, left: 8, color: 'grey.600' }}
        >
          Sad
        </Typography>
        <Typography
          variant="caption"
          sx={{ position: 'absolute', bottom: 8, right: 8, color: 'grey.600' }}
        >
          Calm
        </Typography>

        {/* Axes */}
        <Box
          component="div"
          sx={{
            position: 'absolute',
            top: '50%',
            left: 0,
            right: 0,
            height: 1,
            bgcolor: 'grey.700',
          }}
        />
        <Box
          component="div"
          sx={{
            position: 'absolute',
            top: 0,
            bottom: 0,
            left: '50%',
            width: 1,
            bgcolor: 'grey.700',
          }}
        />

        {/* Mood point */}
        <Box
          component="div"
          sx={{
            position: 'absolute',
            left: `${(mood.valence + 1) * 50}%`,
            top: `${(1 - mood.arousal) * 50}%`,
            transform: 'translate(-50%, -50%)',
            width: 20,
            height: 20,
            borderRadius: '50%',
            bgcolor: color,
            boxShadow: `0 0 20px ${color}`,
            transition: 'all 0.3s ease-out',
          }}
        />
      </Box>

      {/* Values */}
      <Box component="div" sx={{ mt: 2, display: 'flex', justifyContent: 'space-between' }}>
        <Box component="div">
          <Typography variant="caption" color="text.secondary">
            Valence
          </Typography>
          <Typography variant="body2">{mood.valence.toFixed(2)}</Typography>
        </Box>
        <Box component="div">
          <Typography variant="caption" color="text.secondary">
            Arousal
          </Typography>
          <Typography variant="body2">{mood.arousal.toFixed(2)}</Typography>
        </Box>
        <Box component="div">
          <Typography variant="caption" color="text.secondary">
            Confidence
          </Typography>
          <Typography variant="body2">{(mood.confidence * 100).toFixed(0)}%</Typography>
        </Box>
      </Box>
    </Box>
  );
}
