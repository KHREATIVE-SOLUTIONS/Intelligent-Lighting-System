import { useRef, useEffect } from 'react';
import { Box } from '@mui/material';
import { useAudioStore } from '../../stores/audioStore';

export default function AudioVisualizer() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>();
  const energyHistory = useAudioStore((state) => state.energyHistory);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const draw = () => {
      const { width, height } = canvas;

      // Clear canvas
      ctx.fillStyle = '#1e1e1e';
      ctx.fillRect(0, 0, width, height);

      // Draw waveform
      if (energyHistory.length > 0) {
        ctx.beginPath();
        ctx.strokeStyle = '#00bcd4';
        ctx.lineWidth = 2;

        const step = width / (energyHistory.length - 1 || 1);

        energyHistory.forEach((energy, index) => {
          const x = index * step;
          const y = height / 2 - energy * height * 0.4;

          if (index === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        });

        ctx.stroke();

        // Draw mirrored waveform
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(0, 188, 212, 0.5)';

        energyHistory.forEach((energy, index) => {
          const x = index * step;
          const y = height / 2 + energy * height * 0.4;

          if (index === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        });

        ctx.stroke();

        // Draw center line
        ctx.beginPath();
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
        ctx.lineWidth = 1;
        ctx.moveTo(0, height / 2);
        ctx.lineTo(width, height / 2);
        ctx.stroke();
      }

      animationRef.current = requestAnimationFrame(draw);
    };

    // Handle resize
    const handleResize = () => {
      const parent = canvas.parentElement;
      if (parent) {
        canvas.width = parent.clientWidth;
        canvas.height = parent.clientHeight;
      }
    };

    handleResize();
    window.addEventListener('resize', handleResize);

    draw();

    return () => {
      window.removeEventListener('resize', handleResize);
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [energyHistory]);

  return (
    <Box component="div" sx={{ width: '100%', height: '100%' }}>
      <canvas
        ref={canvasRef}
        style={{ display: 'block', width: '100%', height: '100%' }}
      />
    </Box>
  );
}
