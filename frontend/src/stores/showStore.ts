import { create } from 'zustand';
import type { Show, Cue } from '../types';

type PlaybackState = 'stopped' | 'playing' | 'paused';

interface ShowState {
  // Current show
  currentShow: Show | null;
  playbackState: PlaybackState;
  currentTime: number;
  activeCues: Cue[];

  // Editing state
  selectedTrackId: number | null;
  selectedCueId: number | null;

  // Actions
  setCurrentShow: (show: Show | null) => void;
  setPlaybackState: (state: PlaybackState) => void;
  setCurrentTime: (time: number) => void;
  setActiveCues: (cues: Cue[]) => void;
  selectTrack: (trackId: number | null) => void;
  selectCue: (cueId: number | null) => void;
  play: () => void;
  pause: () => void;
  stop: () => void;
  seek: (time: number) => void;
}

export const useShowStore = create<ShowState>((set) => ({
  // Initial state
  currentShow: null,
  playbackState: 'stopped',
  currentTime: 0,
  activeCues: [],
  selectedTrackId: null,
  selectedCueId: null,

  // Actions
  setCurrentShow: (show) =>
    set({
      currentShow: show,
      playbackState: 'stopped',
      currentTime: 0,
      activeCues: [],
      selectedTrackId: null,
      selectedCueId: null,
    }),

  setPlaybackState: (state) => set({ playbackState: state }),

  setCurrentTime: (time) =>
    set((state) => {
      // Find active cues at this time
      const activeCues =
        state.currentShow?.cues.filter(
          (cue) => cue.start_time <= time && cue.start_time + cue.duration > time
        ) || [];
      return { currentTime: time, activeCues };
    }),

  setActiveCues: (cues) => set({ activeCues: cues }),

  selectTrack: (trackId) => set({ selectedTrackId: trackId }),

  selectCue: (cueId) => set({ selectedCueId: cueId }),

  play: () => set({ playbackState: 'playing' }),

  pause: () => set({ playbackState: 'paused' }),

  stop: () =>
    set({
      playbackState: 'stopped',
      currentTime: 0,
      activeCues: [],
    }),

  seek: (time) =>
    set((state) => {
      const activeCues =
        state.currentShow?.cues.filter(
          (cue) => cue.start_time <= time && cue.start_time + cue.duration > time
        ) || [];
      return { currentTime: time, activeCues };
    }),
}));
