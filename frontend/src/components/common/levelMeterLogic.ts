/** Pure helpers for LevelMeter: the backend's `meter` block and how it reads. */

export interface MeterBlock {
  rms?: number;
  peak?: number;
  rms_dbfs?: number;
  peak_dbfs?: number;
  bpm?: number | null;
  beat_count?: number;
  seconds_since_beat?: number | null;
  beat_phase?: number | null;
  running?: boolean;
  silent?: boolean;
  device_name?: string | null;
  clock_locked?: boolean;
}

export const FLOOR_DB = -60;
export const LOW_SIGNAL_DB = -50;
export const LOW_SIGNAL_HOLD_MS = 1500;

export function meterFromMessage(data: unknown): MeterBlock | null {
  if (!data || typeof data !== 'object') return null;
  const meter = (data as { meter?: unknown }).meter;
  if (!meter || typeof meter !== 'object') return null;
  return meter as MeterBlock;
}

/** 0..1 position on the meter for a dBFS value. */
export function dbToFraction(db: number | undefined): number {
  if (typeof db !== 'number' || !Number.isFinite(db)) return 0;
  return Math.max(0, Math.min(1, (db - FLOOR_DB) / -FLOOR_DB));
}

export function meterHint(meter: MeterBlock | null, lowSinceMs: number | null, nowMs: number): string | null {
  if (!meter) return 'Waiting for audio data';
  if (!meter.running) return 'Audio capture is not running';
  if (lowSinceMs !== null && nowMs - lowSinceMs >= LOW_SIGNAL_HOLD_MS) {
    return 'Signal too low - check the output device / volume';
  }
  return null;
}
