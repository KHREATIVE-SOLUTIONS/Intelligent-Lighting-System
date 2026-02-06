import { create } from 'zustand';
import type { AudioAnalysis, BeatInfo, MoodInfo, FrequencyInfo } from '../types';

interface AudioState {
  // Connection status
  isConnected: boolean;
  isStreaming: boolean;

  // Current analysis
  currentAnalysis: AudioAnalysis | null;
  beat: BeatInfo | null;
  mood: MoodInfo | null;
  frequency: FrequencyInfo | null;

  // History for visualization
  bpmHistory: number[];
  valenceHistory: number[];
  arousalHistory: number[];
  energyHistory: number[];

  // Actions
  setConnected: (connected: boolean) => void;
  setStreaming: (streaming: boolean) => void;
  updateAnalysis: (analysis: AudioAnalysis) => void;
  updateBeat: (beat: BeatInfo) => void;
  updateMood: (mood: MoodInfo) => void;
  updateFrequency: (frequency: FrequencyInfo) => void;
  clearHistory: () => void;
}

const MAX_HISTORY_LENGTH = 100;

export const useAudioStore = create<AudioState>((set) => ({
  // Initial state
  isConnected: false,
  isStreaming: false,
  currentAnalysis: null,
  beat: null,
  mood: null,
  frequency: null,
  bpmHistory: [],
  valenceHistory: [],
  arousalHistory: [],
  energyHistory: [],

  // Actions
  setConnected: (connected) => set({ isConnected: connected }),

  setStreaming: (streaming) => set({ isStreaming: streaming }),

  updateAnalysis: (analysis) =>
    set((state) => ({
      currentAnalysis: analysis,
      beat: analysis.beat,
      mood: analysis.mood,
      frequency: analysis.frequency,
      bpmHistory: [...state.bpmHistory, analysis.beat.bpm].slice(-MAX_HISTORY_LENGTH),
      valenceHistory: [...state.valenceHistory, analysis.mood.valence].slice(-MAX_HISTORY_LENGTH),
      arousalHistory: [...state.arousalHistory, analysis.mood.arousal].slice(-MAX_HISTORY_LENGTH),
      energyHistory: [...state.energyHistory, analysis.frequency.rms_energy].slice(
        -MAX_HISTORY_LENGTH
      ),
    })),

  updateBeat: (beat) =>
    set((state) => ({
      beat,
      bpmHistory: [...state.bpmHistory, beat.bpm].slice(-MAX_HISTORY_LENGTH),
    })),

  updateMood: (mood) =>
    set((state) => ({
      mood,
      valenceHistory: [...state.valenceHistory, mood.valence].slice(-MAX_HISTORY_LENGTH),
      arousalHistory: [...state.arousalHistory, mood.arousal].slice(-MAX_HISTORY_LENGTH),
    })),

  updateFrequency: (frequency) =>
    set((state) => ({
      frequency,
      energyHistory: [...state.energyHistory, frequency.rms_energy].slice(-MAX_HISTORY_LENGTH),
    })),

  clearHistory: () =>
    set({
      bpmHistory: [],
      valenceHistory: [],
      arousalHistory: [],
      energyHistory: [],
    }),
}));
