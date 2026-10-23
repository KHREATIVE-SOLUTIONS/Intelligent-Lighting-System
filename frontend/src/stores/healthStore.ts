import { create } from 'zustand';
import type { CaptureStatusPayload, DmxStatusPayload, LinkState } from '../utils/showHealth';
import type { EffectsStatus } from '../services/api';

// What the status bar reads. One poller (useShowHealth, mounted by Layout)
// writes it, so every page shows the same truth instead of each panel
// guessing on its own.
interface HealthState {
  reachable: boolean;
  dmx: DmxStatusPayload | null;
  capture: CaptureStatusPayload | null;
  effects: EffectsStatus | null;
  link: LinkState;
  lastAnalysisAt: number | null;
  lastPollAt: number | null;

  setPoll: (result: {
    reachable: boolean;
    dmx: DmxStatusPayload | null;
    capture: CaptureStatusPayload | null;
    effects: EffectsStatus | null;
  }) => void;
  setLink: (link: LinkState) => void;
  markAnalysis: (at: number) => void;
}

export const useHealthStore = create<HealthState>((set) => ({
  reachable: true,
  dmx: null,
  capture: null,
  effects: null,
  link: 'idle',
  lastAnalysisAt: null,
  lastPollAt: null,

  setPoll: ({ reachable, dmx, capture, effects }) =>
    set((state) => ({
      reachable,
      // Keep the last good reading while the box is unreachable so the detail
      // text still says what was last known.
      dmx: reachable ? dmx : state.dmx,
      capture: reachable ? capture : state.capture,
      effects: reachable ? effects : state.effects,
      lastPollAt: Date.now(),
    })),

  setLink: (link) => set({ link }),

  markAnalysis: (at) => set({ lastAnalysisAt: at }),
}));
