import { create } from 'zustand';
import type { BoxHealthPayload, CaptureStatusPayload, DmxStatusPayload, LinkState } from '../utils/showHealth';
import type { EffectsStatus } from '../services/api';

// What the status bar reads. One poller (useShowHealth, mounted by Layout)
// writes it, so every page shows the same truth instead of each panel
// guessing on its own.
interface HealthState {
  reachable: boolean;
  dmx: DmxStatusPayload | null;
  capture: CaptureStatusPayload | null;
  effects: EffectsStatus | null;
  box: BoxHealthPayload | null;
  link: LinkState;
  lastAnalysisAt: number | null;
  lastPollAt: number | null;

  setPoll: (result: {
    reachable: boolean;
    dmx: DmxStatusPayload | null;
    capture: CaptureStatusPayload | null;
    effects: EffectsStatus | null;
    box?: BoxHealthPayload | null;
  }) => void;
  setLink: (link: LinkState) => void;
  markAnalysis: (at: number) => void;
}

export const useHealthStore = create<HealthState>((set) => ({
  reachable: true,
  dmx: null,
  capture: null,
  effects: null,
  box: null,
  link: 'idle',
  lastAnalysisAt: null,
  lastPollAt: null,

  setPoll: ({ reachable, dmx, capture, effects, box = null }) =>
    set((state) => ({
      reachable,
      // Keep the last good reading while the box is unreachable so the detail
      // text still says what was last known.
      dmx: reachable ? dmx : state.dmx,
      capture: reachable ? capture : state.capture,
      effects: reachable ? effects : state.effects,
      // One missed health read should not flip "Waiting for rig" back to
      // "stalled" for a poll, so keep the last report until a new one lands.
      box: box ?? state.box,
      lastPollAt: Date.now(),
    })),

  setLink: (link) => set({ link }),

  markAnalysis: (at) => set({ lastAnalysisAt: at }),
}));
