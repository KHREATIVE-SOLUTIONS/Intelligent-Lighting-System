import { create } from 'zustand';

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

  // Actions
  setConnected: (connected: boolean) => void;
  setStatus: (fps: number, packetsSent: number) => void;
  setUniverse: (universe: number, data: number[]) => void;
  setChannel: (universe: number, channel: number, value: number) => void;
  setFixtureStates: (fixtures: FixtureState[]) => void;
  setEffectsInfo: (state: string, movement: string, dimmer: string) => void;
  setBlackout: (blackout: boolean) => void;
  clearAll: () => void;
}

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

  clearAll: () =>
    set({
      universes: new Map(),
      fixtureStates: new Map(),
      isBlackout: false,
    }),
}));
