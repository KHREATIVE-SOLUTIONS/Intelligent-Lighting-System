import { create } from 'zustand';
import type {
  Genre,
  SongSection,
  ProEffect,
  KeyLightingZone,
  EmotionVector,
  ProLightingState,
  OperatorIntentControls,
  ActiveIntentProfile,
  IntentDecisionWeights,
} from '../types';

// Fixture state from effects engine
interface FixtureState {
  id: string;
  pan: number;
  tilt: number;
  dimmer: number;
  r: number;
  g: number;
  b: number;
}

const MAX_SECTION_HISTORY = 50;

interface DMXState {
  // Connection status
  isConnected: boolean;
  fps: number;
  packetsSent: number;

  // Universe data
  universes: Map<number, number[]>;

  // Fixture states from effects engine
  fixtureStates: Map<string, FixtureState>;

  // Effects engine state
  effectsState: string;
  movementPattern: string;
  dimmerEffect: string;

  // Blackout state
  isBlackout: boolean;

  // Professional lighting state
  proLighting: ProLightingState;

  // Actions
  setConnected: (connected: boolean) => void;
  setStatus: (fps: number, packetsSent: number) => void;
  setUniverse: (universe: number, data: number[]) => void;
  setChannel: (universe: number, channel: number, value: number) => void;
  setFixtureStates: (fixtures: FixtureState[]) => void;
  setEffectsInfo: (state: string, movement: string, dimmer: string) => void;
  setBlackout: (blackout: boolean) => void;
  setGenre: (genre: Genre | null) => void;
  setSection: (section: SongSection, intensity: number) => void;
  setActiveEffects: (effects: Partial<ProEffect>) => void;
  setKeyLightingZones: (zones: KeyLightingZone[]) => void;
  setEmotionVector: (emotion: EmotionVector | null) => void;
  setBeatPhrase: (phrase: number, beatsPerPhrase: number) => void;
  updateProLighting: (data: Partial<ProLightingState>) => void;
  setOperatorIntentControls: (controls: Partial<OperatorIntentControls>) => void;
  setAutoRecommendIntent: (enabled: boolean) => void;
  setDecisionWeights: (weights: Partial<IntentDecisionWeights>) => void;
  setActiveIntentProfile: (profile: Partial<ActiveIntentProfile>) => void;
  clearAll: () => void;
}



const defaultOperatorIntentControls: OperatorIntentControls = {
  beamAggression: 'medium',
  movementDensity: 0.5,
  colorVolatility: 0.5,
  transitionStrictness: 0.5,
  autoRecommend: false,
};

const defaultIntentDecisionWeights: IntentDecisionWeights = {
  movement: 0.5,
  color: 0.5,
  transition: 0.5,
  sectionFidelity: 0.6,
};

const defaultActiveIntentProfile: ActiveIntentProfile = {
  label: 'Manual Neutral',
  source: 'manual',
  genre: null,
  section: 'UNKNOWN',
  notes: 'Balanced defaults',
};
const defaultProEffect: ProEffect = {
  strobeMode: 'off',
  chaseType: 'off',
  movementType: 'none',
  colorWash: null,
  intensity: 0,
  speed: 0,
};

const defaultProLighting: ProLightingState = {
  genre: null,
  section: 'UNKNOWN',
  sectionIntensity: 0,
  sectionHistory: [],
  activeEffects: { ...defaultProEffect },
  keyLightingZones: [],
  emotionVector: null,
  beatPhrase: 0,
  beatsPerPhrase: 4,
  operatorIntentControls: { ...defaultOperatorIntentControls },
  decisionWeights: { ...defaultIntentDecisionWeights },
  activeIntentProfile: { ...defaultActiveIntentProfile },
};

export const useDMXStore = create<DMXState>((set) => ({
  // Initial state
  isConnected: false,
  fps: 0,
  packetsSent: 0,
  universes: new Map(),
  fixtureStates: new Map(),
  effectsState: 'intro',
  movementPattern: 'none',
  dimmerEffect: 'none',
  isBlackout: false,
  proLighting: { ...defaultProLighting },

  // Actions
  setConnected: (connected) => set({ isConnected: connected }),

  setStatus: (fps, packetsSent) => set({ fps, packetsSent }),

  setUniverse: (universe, data) =>
    set((state) => {
      const newUniverses = new Map(state.universes);
      newUniverses.set(universe, data);
      return { universes: newUniverses };
    }),

  // BUG-032 fix: channel is 1-based DMX standard (1-512), converted to 0-based array index
  setChannel: (universe, channel, value) =>
    set((state) => {
      const newUniverses = new Map(state.universes);
      const data = newUniverses.get(universe) || new Array(512).fill(0);
      const index = channel - 1;
      if (index >= 0 && index < 512) {
        data[index] = Math.max(0, Math.min(255, value));
      }
      newUniverses.set(universe, [...data]);
      return { universes: newUniverses };
    }),

  setFixtureStates: (fixtures) =>
    set(() => {
      const newStates = new Map<string, FixtureState>();
      for (const fixture of fixtures) {
        newStates.set(fixture.id, fixture);
      }
      return { fixtureStates: newStates };
    }),

  setEffectsInfo: (state, movement, dimmer) =>
    set({
      effectsState: state,
      movementPattern: movement,
      dimmerEffect: dimmer,
    }),

  setBlackout: (blackout) => set({ isBlackout: blackout }),

  setGenre: (genre) =>
    set((state) => ({
      proLighting: { ...state.proLighting, genre },
    })),

  setSection: (section, intensity) =>
    set((state) => {
      const now = Date.now();
      const history = [...state.proLighting.sectionHistory];

      // Close the previous section entry
      if (history.length > 0 && !history[history.length - 1].endTime) {
        history[history.length - 1].endTime = now;
      }

      // Add new section entry
      history.push({ section, startTime: now, intensity });

      // Trim history
      const trimmed = history.slice(-MAX_SECTION_HISTORY);

      return {
        proLighting: {
          ...state.proLighting,
          section,
          sectionIntensity: intensity,
          sectionHistory: trimmed,
        },
      };
    }),

  setActiveEffects: (effects) =>
    set((state) => ({
      proLighting: {
        ...state.proLighting,
        activeEffects: { ...state.proLighting.activeEffects, ...effects },
      },
    })),

  setKeyLightingZones: (zones) =>
    set((state) => ({
      proLighting: { ...state.proLighting, keyLightingZones: zones },
    })),

  setEmotionVector: (emotion) =>
    set((state) => ({
      proLighting: { ...state.proLighting, emotionVector: emotion },
    })),

  setBeatPhrase: (phrase, beatsPerPhrase) =>
    set((state) => ({
      proLighting: { ...state.proLighting, beatPhrase: phrase, beatsPerPhrase },
    })),

  updateProLighting: (data) =>
    set((state) => ({
      proLighting: { ...state.proLighting, ...data },
    })),

  setOperatorIntentControls: (controls) =>
    set((state) => ({
      proLighting: {
        ...state.proLighting,
        operatorIntentControls: { ...state.proLighting.operatorIntentControls, ...controls },
      },
    })),

  setAutoRecommendIntent: (enabled) =>
    set((state) => ({
      proLighting: {
        ...state.proLighting,
        operatorIntentControls: { ...state.proLighting.operatorIntentControls, autoRecommend: enabled },
      },
    })),

  setDecisionWeights: (weights) =>
    set((state) => ({
      proLighting: {
        ...state.proLighting,
        decisionWeights: { ...state.proLighting.decisionWeights, ...weights },
      },
    })),

  setActiveIntentProfile: (profile) =>
    set((state) => ({
      proLighting: {
        ...state.proLighting,
        activeIntentProfile: { ...state.proLighting.activeIntentProfile, ...profile },
      },
    })),

  clearAll: () =>
    set({
      universes: new Map(),
      fixtureStates: new Map(),
      isBlackout: false,
      proLighting: { ...defaultProLighting },
    }),
}));
