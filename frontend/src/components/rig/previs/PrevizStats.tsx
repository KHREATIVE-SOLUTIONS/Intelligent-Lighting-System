/**
 * Frame rate and renderer numbers for the 3D previz (docs/PREVIZ_PERFORMANCE.md).
 *
 * `StatsSampler` sits inside the Canvas. Every frame it reads what the renderer
 * drew in the last frame (gl.info.render: draw calls and triangles, shadow
 * passes included) and every 500 ms it publishes the averages on
 * `window.__previzStats`, whether or not the overlay is shown, so a script can
 * read them. `StatsOverlay` is a plain DOM box over the canvas; it is written
 * through a ref, twice a second, and never re-renders.
 *
 * three.js clears gl.info.render at the start of every render call when
 * autoReset is on, so with shadow maps (several render calls a frame) it only
 * shows the last pass. The sampler turns autoReset off, reads the totals for
 * the whole of the last frame at the start of the next, then resets them
 * itself; and puts autoReset back when it unmounts.
 */
import { useEffect, useRef } from 'react';
import type { MutableRefObject } from 'react';
import { useFrame, useThree } from '@react-three/fiber';

export type PrevizStatsSample = {
  fps: number;
  frameMs: number;
  calls: number;
  triangles: number;
  geometries: number;
  textures: number;
};

declare global {
  interface Window {
    __previzStats?: PrevizStatsSample;
  }
}

/** How often the numbers are published. */
export const STATS_INTERVAL_MS = 500;

export type StatsAccumulator = {
  start: number;
  frames: number;
  calls: number;
  triangles: number;
};

export function createStatsAccumulator(): StatsAccumulator {
  return { start: -1, frames: 0, calls: 0, triangles: 0 };
}

/**
 * Count one frame that drew `calls` draw calls and `triangles` triangles,
 * ending at `now` (ms). Returns the averages once `intervalMs` has passed since
 * the window began, and starts a new window; null otherwise. The first call
 * only starts the clock.
 */
export function recordFrame(
  acc: StatsAccumulator,
  now: number,
  calls: number,
  triangles: number,
  geometries: number,
  textures: number,
  intervalMs = STATS_INTERVAL_MS,
): PrevizStatsSample | null {
  if (acc.start < 0) {
    acc.start = now;
    return null;
  }
  acc.frames += 1;
  acc.calls += calls;
  acc.triangles += triangles;
  const elapsed = now - acc.start;
  if (elapsed < intervalMs || acc.frames === 0) return null;
  const sample: PrevizStatsSample = {
    fps: (acc.frames * 1000) / elapsed,
    frameMs: elapsed / acc.frames,
    calls: Math.round(acc.calls / acc.frames),
    triangles: Math.round(acc.triangles / acc.frames),
    geometries,
    textures,
  };
  acc.start = now;
  acc.frames = 0;
  acc.calls = 0;
  acc.triangles = 0;
  return sample;
}

/** One line of text for the overlay. */
export function formatStats(s: PrevizStatsSample): string {
  const tris = s.triangles >= 1e6 ? `${(s.triangles / 1e6).toFixed(2)}M` : `${(s.triangles / 1e3).toFixed(0)}k`;
  return `${s.fps.toFixed(0)} fps  ${s.frameMs.toFixed(1)} ms  ${s.calls} calls  ${tris} tris  ${s.geometries} geo  ${s.textures} tex`;
}

/** Where the sampler sends each sample: the overlay's writer, or nothing. */
export type StatsSink = MutableRefObject<((sample: PrevizStatsSample) => void) | null>;

/** Inside the Canvas. Always mounted: it is what publishes window.__previzStats. */
export function StatsSampler({ sink }: { sink: StatsSink }) {
  const gl = useThree((state) => state.gl);
  const acc = useRef<StatsAccumulator>(createStatsAccumulator());

  useEffect(() => {
    const previous = gl.info.autoReset;
    gl.info.autoReset = false;
    gl.info.reset();
    return () => {
      gl.info.autoReset = previous;
    };
  }, [gl]);

  // Priority 0: a positive priority would take the render over from R3F.
  useFrame(() => {
    const info = gl.info;
    const sample = recordFrame(
      acc.current,
      performance.now(),
      info.render.calls,
      info.render.triangles,
      info.memory.geometries,
      info.memory.textures,
    );
    info.reset();
    if (sample) {
      window.__previzStats = sample;
      sink.current?.(sample);
    }
  });
  return null;
}

/** The overlay over the canvas, top left. Its parent must be positioned. */
export function StatsOverlay({ sink }: { sink: StatsSink }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    sink.current = (sample) => {
      if (box.current) box.current.textContent = formatStats(sample);
    };
    if (box.current && window.__previzStats) box.current.textContent = formatStats(window.__previzStats);
    return () => {
      sink.current = null;
    };
  }, [sink]);
  return (
    <div
      ref={box}
      data-testid="previz-stats"
      style={{
        position: 'absolute',
        top: 8,
        left: 8,
        zIndex: 2,
        padding: '3px 8px',
        borderRadius: 4,
        background: 'rgba(0,0,0,0.7)',
        color: '#b9f6ca',
        font: '12px Consolas, monospace',
        whiteSpace: 'pre',
        pointerEvents: 'none',
      }}
    >
      measuring…
    </div>
  );
}
