import { describe, expect, it, vi } from 'vitest';
import {
  fetchEngineRig,
  livePatchedRigId,
  onPatchedRigActivated,
  patchedRigMark,
} from '../utils/demoRigSync';
import type { EngineRigReport } from '../utils/demoRigSync';

// The 3D view following a rig put on the engine by Activate, with no restart.

// A stand-in for the health store: holds the latest engine status reading,
// and changes for other reasons too, as the real one does.
function fakeHealthStore(initial: EngineRigReport | null = null) {
  type State = { effects: EngineRigReport | null; lastAnalysisAt: number };
  let state: State = { effects: initial, lastAnalysisAt: 0 };
  const listeners = new Set<(state: State, previous: State) => void>();
  const set = (next: State) => {
    const previous = state;
    state = next;
    listeners.forEach((listener) => listener(state, previous));
  };
  return {
    getState: () => state,
    subscribe(listener: (state: State, previous: State) => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    // A status poll that reached the box: a new reading each time.
    poll(report: EngineRigReport) {
      set({ ...state, effects: { ...report } });
    },
    // An analysis message arrived: the store changes, the reading does not.
    analysis() {
      set({ ...state, lastAnalysisAt: state.lastAnalysisAt + 1 });
    },
    listening: () => listeners.size,
  };
}

const demoReading = (name: string): EngineRigReport => ({ live_rig_name: name, live_rig_demo: true });

const patchedReading = (id: number, version: number, name = 'Main room'): EngineRigReport => ({
  live_rig_id: id,
  live_rig_name: name,
  live_rig_demo: false,
  live_rig_version: version,
});

describe('livePatchedRigId and patchedRigMark', () => {
  it('name the patched rig on the engine', () => {
    expect(livePatchedRigId(patchedReading(5, 100))).toBe(5);
    expect(patchedRigMark(patchedReading(5, 100))).toBe('5:100');
  });

  it('are null while a demo rig runs, or nothing is known', () => {
    expect(livePatchedRigId(demoReading('club_night'))).toBeNull();
    expect(patchedRigMark(demoReading('club_night'))).toBeNull();
    expect(livePatchedRigId(null)).toBeNull();
    expect(patchedRigMark({ live_rig_demo: false, live_rig_id: null })).toBeNull();
  });

  it('tell the same rig applied again from the install before it', () => {
    expect(patchedRigMark(patchedReading(5, 101))).not.toBe(patchedRigMark(patchedReading(5, 100)));
  });
});

describe('onPatchedRigActivated', () => {
  it('fires when a patched rig replaces the demo rig', () => {
    const store = fakeHealthStore(demoReading('club_night'));
    const activated = vi.fn();
    onPatchedRigActivated(store, activated);

    store.poll(patchedReading(5, 100));

    expect(activated).toHaveBeenCalledTimes(1);
    expect(activated).toHaveBeenCalledWith(expect.objectContaining({ live_rig_id: 5 }));
  });

  it('fires when another rig is activated, and when the same rig is applied again', () => {
    const store = fakeHealthStore(patchedReading(5, 100));
    const activated = vi.fn();
    onPatchedRigActivated(store, activated);

    store.poll(patchedReading(8, 101, 'Patio'));
    store.poll(patchedReading(8, 102, 'Patio'));

    expect(activated).toHaveBeenCalledTimes(2);
  });

  it('stays quiet for readings that repeat the last one', () => {
    const store = fakeHealthStore(patchedReading(5, 100));
    const activated = vi.fn();
    onPatchedRigActivated(store, activated);

    store.poll(patchedReading(5, 100));
    store.poll(patchedReading(5, 100));
    for (let i = 0; i < 45; i += 1) store.analysis();

    expect(activated).not.toHaveBeenCalled();
  });

  it('does not count the first reading a page sees', () => {
    // The page has just loaded its rig; this reading describes that rig.
    const store = fakeHealthStore(null);
    const activated = vi.fn();
    onPatchedRigActivated(store, activated);

    store.poll(patchedReading(5, 100));
    expect(activated).not.toHaveBeenCalled();

    store.poll(patchedReading(5, 101));
    expect(activated).toHaveBeenCalledTimes(1);
  });

  it('leaves a demo rig coming on to the demo follower', () => {
    const store = fakeHealthStore(patchedReading(5, 100));
    const activated = vi.fn();
    onPatchedRigActivated(store, activated);

    store.poll(demoReading('club_night'));

    expect(activated).not.toHaveBeenCalled();
  });

  it('stops listening when asked to', () => {
    const store = fakeHealthStore(patchedReading(5, 100));
    const activated = vi.fn();
    const stop = onPatchedRigActivated(store, activated);

    stop();
    store.poll(patchedReading(8, 101));

    expect(store.listening()).toBe(0);
    expect(activated).not.toHaveBeenCalled();
  });
});

describe('fetchEngineRig', () => {
  const apis = (report: EngineRigReport) => ({
    getStatus: vi.fn(async () => report),
    getPatchedRig: vi.fn(async (id: number) => ({ venue: `patched-${id}` })),
    getDemoRig: vi.fn(async () => ({ venue: 'club_night' })),
  });

  it('draws the patched rig once one is live', async () => {
    const sources = apis(patchedReading(5, 100));

    expect(await fetchEngineRig(sources)).toEqual({ venue: 'patched-5' });
    expect(sources.getPatchedRig).toHaveBeenCalledWith(5);
    expect(sources.getDemoRig).not.toHaveBeenCalled();
  });

  it("draws the engine's demo rig until then", async () => {
    const sources = apis(demoReading('club_night'));

    expect(await fetchEngineRig(sources)).toEqual({ venue: 'club_night' });
    expect(sources.getDemoRig).toHaveBeenCalledWith();
    expect(sources.getPatchedRig).not.toHaveBeenCalled();
  });
});
