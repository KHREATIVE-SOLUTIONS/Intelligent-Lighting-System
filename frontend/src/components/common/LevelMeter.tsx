import { useEffect, useRef, useState } from 'react';
import { Box, Typography } from '@mui/material';
import { audioWebSocket } from '../../services/websocket';
import {
  FLOOR_DB,
  LOW_SIGNAL_DB,
  dbToFraction,
  meterFromMessage,
  meterHint,
  type MeterBlock,
} from './levelMeterLogic';

/**
 * Input level meter plus BPM / beat indicator.
 *
 * Reads the `meter` block the backend adds to every `analysis` message
 * (backend/app/services/audio/meter.py). Messages arrive at ~30 per second, so
 * nothing here sets React state per message: the latest block is kept in a
 * ref, a requestAnimationFrame loop writes the bar widths and the beat dot
 * straight to the DOM, and the BPM text and hint are refreshed at most four
 * times a second, only when they change.
 */

const TEXT_REFRESH_MS = 250;
const BEAT_FLASH_MS = 120;
const STALE_MS = 2000;

interface Props {
  compact?: boolean;
}

const LevelMeter = ({ compact = false }: Props) => {
  const meterRef = useRef<MeterBlock | null>(null);
  const receivedAtRef = useRef<number>(0);
  const lowSinceRef = useRef<number | null>(null);
  const lastBeatRef = useRef<number | null>(null);
  const beatAtRef = useRef<number>(0);
  const rmsBarRef = useRef<HTMLDivElement | null>(null);
  const peakBarRef = useRef<HTMLDivElement | null>(null);
  const dotRef = useRef<HTMLDivElement | null>(null);

  const [bpmText, setBpmText] = useState<string>('--');
  const [hint, setHint] = useState<string | null>('Waiting for audio data');

  useEffect(() => {
    const onAnalysis = (data: unknown) => {
      const meter = meterFromMessage(data);
      if (!meter) return;
      const now = performance.now();
      meterRef.current = meter;
      receivedAtRef.current = now;
      const db = typeof meter.rms_dbfs === 'number' ? meter.rms_dbfs : FLOOR_DB * 2;
      if (meter.running && db < LOW_SIGNAL_DB) {
        if (lowSinceRef.current === null) lowSinceRef.current = now;
      } else {
        lowSinceRef.current = null;
      }
      const count = typeof meter.beat_count === 'number' ? meter.beat_count : null;
      if (count !== null && lastBeatRef.current !== null && count !== lastBeatRef.current) {
        beatAtRef.current = now;
      }
      lastBeatRef.current = count;
    };
    audioWebSocket.on('analysis', onAnalysis);

    let frame = 0;
    const draw = () => {
      const now = performance.now();
      const fresh = now - receivedAtRef.current < STALE_MS;
      const meter = fresh ? meterRef.current : null;
      if (rmsBarRef.current) {
        rmsBarRef.current.style.width = `${(dbToFraction(meter?.rms_dbfs) * 100).toFixed(1)}%`;
      }
      if (peakBarRef.current) {
        peakBarRef.current.style.left = `${(dbToFraction(meter?.peak_dbfs) * 100).toFixed(1)}%`;
      }
      if (dotRef.current) {
        const lit = fresh && now - beatAtRef.current < BEAT_FLASH_MS;
        dotRef.current.style.opacity = lit ? '1' : '0.18';
        dotRef.current.style.transform = lit ? 'scale(1.25)' : 'scale(1)';
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);

    const timer = setInterval(() => {
      const now = performance.now();
      const fresh = now - receivedAtRef.current < STALE_MS;
      const meter = fresh ? meterRef.current : null;
      const bpm = meter && typeof meter.bpm === 'number' && meter.bpm > 0 ? meter.bpm.toFixed(0) : '--';
      setBpmText((prev) => (prev === bpm ? prev : bpm));
      const next = meterHint(meter, lowSinceRef.current, now);
      setHint((prev) => (prev === next ? prev : next));
    }, TEXT_REFRESH_MS);

    return () => {
      audioWebSocket.off('analysis', onAnalysis);
      cancelAnimationFrame(frame);
      clearInterval(timer);
    };
  }, []);

  return (
    <Box
      data-testid="level-meter"
      sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: compact ? 180 : 260 }}
    >
      <Box
        aria-label="input level"
        sx={{
          position: 'relative',
          flex: 1,
          height: 10,
          borderRadius: 1,
          bgcolor: 'rgba(255,255,255,0.12)',
          overflow: 'hidden',
        }}
      >
        <Box
          ref={rmsBarRef}
          sx={{
            position: 'absolute', left: 0, top: 0, bottom: 0, width: '0%',
            background: 'linear-gradient(90deg, #2e7d32 0%, #9ccc65 70%, #fbc02d 88%, #e53935 100%)',
          }}
        />
        <Box
          ref={peakBarRef}
          sx={{ position: 'absolute', top: 0, bottom: 0, width: 2, left: '0%', bgcolor: '#fff' }}
        />
      </Box>
      <Box
        ref={dotRef}
        aria-label="beat"
        sx={{
          width: 12, height: 12, borderRadius: '50%', bgcolor: '#ff4081', opacity: 0.18,
          transition: 'opacity 60ms linear, transform 60ms linear',
        }}
      />
      <Typography variant="caption" sx={{ fontVariantNumeric: 'tabular-nums', minWidth: 56 }}>
        {bpmText} BPM
      </Typography>
      {hint && (
        <Typography variant="caption" color="warning.main" sx={{ whiteSpace: 'nowrap' }}>
          {hint}
        </Typography>
      )}
    </Box>
  );
};

export default LevelMeter;
