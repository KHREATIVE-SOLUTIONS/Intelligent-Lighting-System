import { useRef, useEffect } from 'react';
import { Box, Typography } from '@mui/material';
import { useDMXStore } from '../../stores/dmxStore';
import type { SongSection } from '../../types';

const SECTION_COLORS: Record<SongSection, string> = {
  INTRO: '#78909c',
  VERSE: '#42a5f5',
  PRE_CHORUS: '#ab47bc',
  CHORUS: '#66bb6a',
  DROP: '#ef5350',
  BREAKDOWN: '#7e57c2',
  BRIDGE: '#ffa726',
  BUILDUP: '#ffca28',
  OUTRO: '#78909c',
  INSTRUMENTAL: '#26c6da',
  SOLO: '#ec407a',
  UNKNOWN: '#616161',
};

const SECTION_SHORT_LABELS: Record<SongSection, string> = {
  INTRO: 'Int',
  VERSE: 'Vs',
  PRE_CHORUS: 'PC',
  CHORUS: 'Ch',
  DROP: 'Dr',
  BREAKDOWN: 'Bd',
  BRIDGE: 'Br',
  BUILDUP: 'BU',
  OUTRO: 'Out',
  INSTRUMENTAL: 'Ins',
  SOLO: 'Sol',
  UNKNOWN: '?',
};

export default function SectionTimeline() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>();
  const sectionHistory = useDMXStore((state) => state.proLighting.sectionHistory);
  const currentSection = useDMXStore((state) => state.proLighting.section);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const draw = () => {
      const parent = canvas.parentElement;
      if (parent) {
        canvas.width = parent.clientWidth;
        canvas.height = parent.clientHeight;
      }

      const { width, height } = canvas;
      const now = Date.now();

      // Clear
      ctx.fillStyle = '#121212';
      ctx.fillRect(0, 0, width, height);

      if (sectionHistory.length === 0) {
        ctx.fillStyle = '#666';
        ctx.font = '12px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('No section data yet', width / 2, height / 2);
        animationRef.current = requestAnimationFrame(draw);
        return;
      }

      // Show last 60 seconds of history
      const timeWindow = 60000;
      const startTime = now - timeWindow;
      const barHeight = height * 0.5;
      const barY = 10;
      const graphY = barY + barHeight + 8;
      const graphHeight = height - graphY - 5;

      // Draw section bars
      for (const entry of sectionHistory) {
        const entryStart = Math.max(entry.startTime, startTime);
        const entryEnd = entry.endTime || now;

        if (entryEnd < startTime) continue;

        const x1 = ((entryStart - startTime) / timeWindow) * width;
        const x2 = ((entryEnd - startTime) / timeWindow) * width;
        const barWidth = Math.max(x2 - x1, 2);

        // Section color bar
        ctx.fillStyle = SECTION_COLORS[entry.section] || SECTION_COLORS.UNKNOWN;
        ctx.fillRect(x1, barY, barWidth, barHeight);

        // Section label (only if bar is wide enough)
        if (barWidth > 20) {
          ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
          ctx.font = 'bold 10px sans-serif';
          ctx.textAlign = 'center';
          const label = SECTION_SHORT_LABELS[entry.section] || '?';
          ctx.fillText(label, x1 + barWidth / 2, barY + barHeight / 2 + 4);
        }
      }

      // Draw intensity graph overlay
      ctx.beginPath();
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.6)';
      ctx.lineWidth = 1.5;

      let first = true;
      for (const entry of sectionHistory) {
        const entryStart = Math.max(entry.startTime, startTime);
        const entryEnd = entry.endTime || now;

        if (entryEnd < startTime) continue;

        const x1 = ((entryStart - startTime) / timeWindow) * width;
        const x2 = ((entryEnd - startTime) / timeWindow) * width;
        const y = graphY + graphHeight - entry.intensity * graphHeight;

        if (first) {
          ctx.moveTo(x1, y);
          first = false;
        } else {
          ctx.lineTo(x1, y);
        }
        ctx.lineTo(x2, y);
      }
      ctx.stroke();

      // Draw time markers
      ctx.fillStyle = 'rgba(255, 255, 255, 0.3)';
      ctx.font = '9px sans-serif';
      ctx.textAlign = 'center';
      for (let t = 0; t <= 60; t += 10) {
        const x = (t / 60) * width;
        ctx.fillText(`-${60 - t}s`, x, height - 1);
      }

      // Draw beat markers (thin vertical lines at current position)
      const currentX = width;
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 4]);
      ctx.beginPath();
      ctx.moveTo(currentX - 1, 0);
      ctx.lineTo(currentX - 1, height);
      ctx.stroke();
      ctx.setLineDash([]);

      animationRef.current = requestAnimationFrame(draw);
    };

    draw();

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [sectionHistory, currentSection]);

  // Legend
  const activeSections = new Set(sectionHistory.map((e) => e.section));

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <Box sx={{ height: 120, bgcolor: '#121212', borderRadius: 1, overflow: 'hidden' }}>
        <canvas
          ref={canvasRef}
          style={{ display: 'block', width: '100%', height: '100%' }}
        />
      </Box>

      {/* Legend */}
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
        {Array.from(activeSections).map((section) => (
          <Box
            key={section}
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 0.5,
            }}
          >
            <Box
              sx={{
                width: 10,
                height: 10,
                borderRadius: 0.5,
                bgcolor: SECTION_COLORS[section] || SECTION_COLORS.UNKNOWN,
              }}
            />
            <Typography variant="caption" color="text.secondary">
              {SECTION_SHORT_LABELS[section]}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
