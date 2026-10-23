import { useEffect } from 'react';
import { audioApi, dmxApi, effectsApi } from '../services/api';
import { audioWebSocket } from '../services/websocket';
import { useHealthStore } from '../stores/healthStore';
import { useAudioStore } from '../stores/audioStore';
import { useDMXStore } from '../stores/dmxStore';

export const HEALTH_POLL_MS = 2000;

// One round of status reads. Exported so a control can refresh right after
// the operator acts instead of waiting for the next tick.
export async function pollShowHealth(): Promise<void> {
  const [dmx, capture, effects] = await Promise.allSettled([
    dmxApi.getStatus(),
    audioApi.getCaptureStatus(),
    effectsApi.getStatus(),
  ]);
  // Every read failing means the box itself is gone, not one subsystem.
  const reachable = [dmx, capture, effects].some((r) => r.status === 'fulfilled');
  const dmxValue = dmx.status === 'fulfilled' ? dmx.value : null;
  const captureValue = capture.status === 'fulfilled' ? capture.value : null;
  const effectsValue = effects.status === 'fulfilled' ? effects.value : null;
  useHealthStore.getState().setPoll({
    reachable,
    dmx: dmxValue,
    capture: captureValue,
    effects: effectsValue,
  });

  // Older panels read these flags; keep them honest too.
  if (dmxValue) {
    useDMXStore.getState().setConnected(dmxValue.status === 'connected');
    useDMXStore.getState().setStatus(dmxValue.fps ?? 0, dmxValue.packets_sent ?? 0);
  }
  if (captureValue) {
    useAudioStore.getState().setStreaming(!!captureValue.running);
  }
}

// Mounted once, by Layout. Polls DMX, audio and engine status and watches the
// live socket so the status bar is right on every page, not just the dashboard.
export function useShowHealth(): void {
  useEffect(() => {
    let cancelled = false;
    const { setLink, markAnalysis } = useHealthStore.getState();

    const tick = () => {
      if (!cancelled) void pollShowHealth();
    };
    tick();
    const timer = window.setInterval(tick, HEALTH_POLL_MS);

    // The pinned autopilot strip reads section and genre on every page, not
    // only while the dashboard is open.
    const onAnalysis = (data: unknown) => {
      markAnalysis(Date.now());
      const lighting = (data as { lighting?: Record<string, unknown> } | null)?.lighting;
      if (!lighting) return;
      const dmx = useDMXStore.getState();
      if (typeof lighting.genre === 'string') dmx.setGenre(lighting.genre);
      if (typeof lighting.section === 'string') {
        const intensity = typeof lighting.section_intensity === 'number' ? lighting.section_intensity : 0;
        dmx.setSection(lighting.section, intensity);
      }
    };
    audioWebSocket.on('analysis', onAnalysis);
    setLink(audioWebSocket.linkState);
    const stopWatching = audioWebSocket.onStateChange(setLink);
    audioWebSocket.connect().catch(() => {
      // The socket schedules its own retries; the status bar shows the state.
    });

    return () => {
      cancelled = true;
      window.clearInterval(timer);
      audioWebSocket.off('analysis', onAnalysis);
      stopWatching();
    };
  }, []);
}
