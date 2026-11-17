import { describe, expect, it, vi } from 'vitest';
import {
  createDemoRigFollower,
  engineLeftDrawnRig,
  onEngineOnAnotherRig,
  onLinkRestored,
  settleRig,
} from '../utils/demoRigSync';
import type { DemoRigSource, EngineRigReport, LinkSource } from '../utils/demoRigSync';
import type { LinkState } from '../utils/showHealth';

// A stand-in for the live socket: holds a state and tells its listeners.
function fakeLink(initial: LinkState = 'idle') {
  const listeners = new Set<(state: LinkState) => void>();
  const link: LinkSource & { go(state: LinkState): void; listening(): number } = {
    linkState: initial,
    onStateChange(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    go(state) {
      (link as { linkState: LinkState }).linkState = state;
      listeners.forEach((listener) => listener(state));
    },
    listening: () => listeners.size,
  };
  return link;
}

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
    subscribe(listener: (state: State, previous: State) => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    // A status poll that reached the box: a new reading each time.
    poll(report: EngineRigReport | null) {
      set({ ...state, effects: report ? { ...report } : null });
    },
    // An analysis message arrived: the store changes, the reading does not.
    analysis() {
      set({ ...state, lastAnalysisAt: state.lastAnalysisAt + 1 });
    },
    listening: () => listeners.size,
  };
}

const demoReading = (name: string): EngineRigReport => ({ live_rig_name: name, live_rig_demo: true });

type DemoRig = { venue: string; fixtures: number[] };
const rigOf = (venue: string, count = 2): DemoRig => ({
  venue,
  fixtures: Array.from({ length: count }, (_, i) => i + 1),
});

// A promise the test settles by hand, to put answers in a chosen order.
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// Lets every promise callback queued so far run.
const settle = async () => {
  for (let i = 0; i < 8; i += 1) await Promise.resolve();
};

// A backend with an engine that runs one demo rig at a time.
function fakeBackend(running: string) {
  const engine = { running };
  const source: DemoRigSource<DemoRig> = {
    getRig: vi.fn(async (preset?: string) => rigOf(preset ?? engine.running)),
    applyPreset: vi.fn(async (name: string) => {
      engine.running = name;
    }),
  };
  return { engine, source };
}

describe('onLinkRestored', () => {
  it('does not fire on the first connection of a page load', () => {
    const link = fakeLink('idle');
    const restored = vi.fn();
    onLinkRestored(link, restored);

    link.go('connecting');
    link.go('connected');

    expect(restored).not.toHaveBeenCalled();
  });

  it('fires once each time the link comes back after dropping', () => {
    const link = fakeLink('connected');
    const restored = vi.fn();
    onLinkRestored(link, restored);

    link.go('reconnecting');
    link.go('lost');
    expect(restored).not.toHaveBeenCalled();
    link.go('connected');
    expect(restored).toHaveBeenCalledTimes(1);

    link.go('reconnecting');
    link.go('connected');
    expect(restored).toHaveBeenCalledTimes(2);
  });

  it('fires for a page that mounted while the box was down', () => {
    const link = fakeLink('lost');
    const restored = vi.fn();
    onLinkRestored(link, restored);

    link.go('connected');

    expect(restored).toHaveBeenCalledTimes(1);
  });

  it('treats the connection after a logout as a first one', () => {
    const link = fakeLink('connected');
    const restored = vi.fn();
    onLinkRestored(link, restored);

    link.go('reconnecting');
    link.go('idle');
    link.go('connecting');
    link.go('connected');

    expect(restored).not.toHaveBeenCalled();
  });

  it('stops listening when asked to', () => {
    const link = fakeLink('connected');
    const restored = vi.fn();
    const stop = onLinkRestored(link, restored);
    expect(link.listening()).toBe(1);

    stop();
    link.go('reconnecting');
    link.go('connected');

    expect(link.listening()).toBe(0);
    expect(restored).not.toHaveBeenCalled();
  });
});

describe('engineLeftDrawnRig', () => {
  it('is true when the engine reports another demo rig', () => {
    expect(engineLeftDrawnRig(demoReading('small_nightclub'), 'club_night')).toBe(true);
  });

  it('is false when the engine reports the rig that is drawn', () => {
    expect(engineLeftDrawnRig(demoReading('club_night'), 'club_night')).toBe(false);
  });

  it('is false while a patched rig is live', () => {
    expect(engineLeftDrawnRig({ live_rig_name: 'Main room', live_rig_demo: false }, 'club_night')).toBe(false);
  });

  it('is false with no reading, no name, or nothing drawn', () => {
    expect(engineLeftDrawnRig(null, 'club_night')).toBe(false);
    expect(engineLeftDrawnRig({ live_rig_demo: true, live_rig_name: null }, 'club_night')).toBe(false);
    expect(engineLeftDrawnRig(demoReading('club_night'), null)).toBe(false);
  });
});

describe('onEngineOnAnotherRig', () => {
  it('fires when a new reading names a demo rig other than the one drawn', () => {
    const store = fakeHealthStore(demoReading('club_night'));
    const changed = vi.fn();
    onEngineOnAnotherRig(store, () => 'club_night', changed);

    store.poll(demoReading('club_night'));
    expect(changed).not.toHaveBeenCalled();

    store.poll(demoReading('small_nightclub'));
    expect(changed).toHaveBeenCalledTimes(1);
  });

  it('ignores store changes that are not a new reading', () => {
    // The reading already disagrees with what is drawn, so only the "is this
    // a new reading" check keeps the 45 messages a second from asking.
    const store = fakeHealthStore(demoReading('small_nightclub'));
    const changed = vi.fn();
    onEngineOnAnotherRig(store, () => 'club_night', changed);

    for (let i = 0; i < 45; i += 1) store.analysis();

    expect(changed).not.toHaveBeenCalled();
  });

  it('fires on every reading while the view is still behind', () => {
    const store = fakeHealthStore();
    const changed = vi.fn();
    onEngineOnAnotherRig(store, () => 'club_night', changed);

    store.poll(demoReading('small_nightclub'));
    store.poll(demoReading('small_nightclub'));

    expect(changed).toHaveBeenCalledTimes(2);
  });

  it('compares with what is drawn at the time of the reading', () => {
    const store = fakeHealthStore();
    const changed = vi.fn();
    let drawn = 'club_night';
    onEngineOnAnotherRig(store, () => drawn, changed);

    drawn = 'small_nightclub';
    store.poll(demoReading('small_nightclub'));

    expect(changed).not.toHaveBeenCalled();
  });

  it('stays quiet while a patched rig is live', () => {
    const store = fakeHealthStore();
    const changed = vi.fn();
    onEngineOnAnotherRig(store, () => 'club_night', changed);

    store.poll({ live_rig_name: 'Main room', live_rig_demo: false });

    expect(changed).not.toHaveBeenCalled();
  });

  it('stops listening when asked to', () => {
    const store = fakeHealthStore();
    const changed = vi.fn();
    const stop = onEngineOnAnotherRig(store, () => 'club_night', changed);
    expect(store.listening()).toBe(1);

    stop();
    store.poll(demoReading('small_nightclub'));

    expect(store.listening()).toBe(0);
    expect(changed).not.toHaveBeenCalled();
  });
});

describe('settleRig', () => {
  it('keeps the rig already drawn when the answer is the same rig', () => {
    const drawn = rigOf('club_night', 34);
    expect(settleRig(drawn, rigOf('club_night', 34))).toBe(drawn);
  });

  it('takes the answer when the engine is running another rig', () => {
    const answer = rigOf('pro_beam_room', 52);
    expect(settleRig(rigOf('club_night', 34), answer)).toBe(answer);
  });

  it('takes the answer when the rig changed under the same name', () => {
    const answer = rigOf('club_night', 36);
    expect(settleRig(rigOf('club_night', 34), answer)).toBe(answer);
  });

  it('takes the answer when nothing is drawn yet', () => {
    const answer = rigOf('pro_beam_room');
    expect(settleRig(null, answer)).toBe(answer);
  });
});

describe('the demo rig follows the engine', () => {
  it('draws the rig the engine is running after a backend restart', async () => {
    // The operator picked Club Night; the view draws it.
    const { engine, source } = fakeBackend('pro_beam_room');
    const link = fakeLink('connected');
    let drawn: DemoRig | null = null;
    const follower = createDemoRigFollower<DemoRig>({ source, draw: (rig) => { drawn = settleRig(drawn, rig); } });
    onLinkRestored(link, () => void follower.follow());
    await follower.pick('club_night');
    expect(drawn).toEqual(rigOf('club_night'));

    // The backend restarts: the engine boots on its default rig.
    link.go('reconnecting');
    engine.running = 'pro_beam_room';
    link.go('connected');
    await settle();

    // The view asked which rig is running, naming none, and draws the answer.
    expect(source.getRig).toHaveBeenLastCalledWith();
    expect(drawn).toEqual(rigOf('pro_beam_room'));
    // It did not put its old pick back on the engine.
    expect(source.applyPreset).toHaveBeenCalledTimes(1);
    expect(engine.running).toBe('pro_beam_room');

    // Picking the rig that showed before the restart works again.
    await follower.pick('club_night');
    expect(engine.running).toBe('club_night');
    expect(drawn).toEqual(rigOf('club_night'));
  });

  it('draws a rig put on the engine from another tab, with no drop in the link', async () => {
    const { engine, source } = fakeBackend('pro_beam_room');
    const store = fakeHealthStore(demoReading('pro_beam_room'));
    let drawn: DemoRig | null = null;
    const follower = createDemoRigFollower<DemoRig>({ source, draw: (rig) => { drawn = settleRig(drawn, rig); } });
    onEngineOnAnotherRig(store, () => (drawn ? drawn.venue : null), () => void follower.follow());
    await follower.pick('club_night');
    store.poll(demoReading('club_night'));
    await settle();
    expect(drawn).toEqual(rigOf('club_night'));
    const asksSoFar = vi.mocked(source.getRig).mock.calls.length;

    // Another tab switches the engine. The next status poll says so.
    engine.running = 'small_nightclub';
    store.poll(demoReading('small_nightclub'));
    await settle();

    expect(source.getRig).toHaveBeenLastCalledWith();
    expect(drawn).toEqual(rigOf('small_nightclub'));
    // This view applied nothing: the only apply is its own earlier pick.
    expect(source.applyPreset).toHaveBeenCalledTimes(1);
    expect(engine.running).toBe('small_nightclub');

    // Once the view has caught up, later readings ask nothing.
    store.poll(demoReading('small_nightclub'));
    await settle();
    expect(vi.mocked(source.getRig).mock.calls.length).toBe(asksSoFar + 1);

    // And the rig that showed before can be picked again.
    await follower.pick('club_night');
    expect(engine.running).toBe('club_night');
    expect(drawn).toEqual(rigOf('club_night'));
  });

  it('draws once when a restart is seen by the socket and the poll together', async () => {
    const { engine, source } = fakeBackend('pro_beam_room');
    const link = fakeLink('connected');
    const store = fakeHealthStore(demoReading('pro_beam_room'));
    const draws: DemoRig[] = [];
    let drawn: DemoRig | null = null;
    const follower = createDemoRigFollower<DemoRig>({
      source,
      draw: (rig) => {
        drawn = settleRig(drawn, rig);
        draws.push(rig);
      },
    });
    onLinkRestored(link, () => void follower.follow());
    onEngineOnAnotherRig(store, () => (drawn ? drawn.venue : null), () => void follower.follow());
    await follower.pick('club_night');
    draws.length = 0;

    link.go('reconnecting');
    engine.running = 'pro_beam_room';
    link.go('connected');
    store.poll(demoReading('pro_beam_room'));
    await settle();

    expect(draws).toEqual([rigOf('pro_beam_room')]);
    expect(drawn).toEqual(rigOf('pro_beam_room'));
  });

  it('leaves the drawn rig alone after a blip with no restart', async () => {
    const { source } = fakeBackend('pro_beam_room');
    const link = fakeLink('connected');
    let drawn: DemoRig | null = null;
    const follower = createDemoRigFollower<DemoRig>({ source, draw: (rig) => { drawn = settleRig(drawn, rig); } });
    onLinkRestored(link, () => void follower.follow());
    await follower.pick('club_night');
    const before = drawn;

    link.go('reconnecting');
    link.go('connected');
    await settle();

    // Same object: nothing downstream rebuilds.
    expect(drawn).toBe(before);
  });

  it('puts the pick on the engine before fetching it', async () => {
    const order: string[] = [];
    const source: DemoRigSource<DemoRig> = {
      getRig: vi.fn(async (preset?: string) => {
        order.push(`get ${preset}`);
        return rigOf(preset ?? 'none');
      }),
      applyPreset: vi.fn(async (name: string) => {
        order.push(`apply ${name}`);
      }),
    };
    const draw = vi.fn();
    await createDemoRigFollower<DemoRig>({ source, draw }).pick('festival');

    expect(order).toEqual(['apply festival', 'get festival']);
    expect(draw).toHaveBeenCalledWith(rigOf('festival'));
  });

  it('drops an answer that a pick has overtaken', async () => {
    // The ask leaves before the pick; its answer (the rig the engine has
    // since left) arrives after the pick is drawn.
    const stale = deferred<DemoRig>();
    const source: DemoRigSource<DemoRig> = {
      getRig: vi.fn((preset?: string) => (preset ? Promise.resolve(rigOf(preset)) : stale.promise)),
      applyPreset: vi.fn(async () => {}),
    };
    const draw = vi.fn();
    const follower = createDemoRigFollower<DemoRig>({ source, draw });

    const asking = follower.follow();
    await follower.pick('club_night');
    stale.resolve(rigOf('pro_beam_room'));

    expect(await asking).toBe(false);
    expect(draw).toHaveBeenCalledTimes(1);
    expect(draw).toHaveBeenLastCalledWith(rigOf('club_night'));
  });

  it('drops an answer that arrives while a pick is still running', async () => {
    const applying = deferred<void>();
    const source: DemoRigSource<DemoRig> = {
      getRig: vi.fn(async (preset?: string) => rigOf(preset ?? 'pro_beam_room')),
      applyPreset: vi.fn(() => applying.promise),
    };
    const draw = vi.fn();
    const follower = createDemoRigFollower<DemoRig>({ source, draw });

    const picking = follower.pick('club_night');
    expect(await follower.follow()).toBe(false);
    expect(draw).not.toHaveBeenCalled();

    applying.resolve();
    await picking;
    expect(draw).toHaveBeenCalledTimes(1);
    expect(draw).toHaveBeenLastCalledWith(rigOf('club_night'));
  });

  it('ends on the rig the engine took last when two picks overlap', async () => {
    // Club Night is picked first but its apply is slow, so the engine takes
    // Festival and then Club Night. The later pick is not the later apply.
    const slow = deferred<void>();
    const engine = { running: 'pro_beam_room' };
    const source: DemoRigSource<DemoRig> = {
      getRig: vi.fn(async (preset?: string) => rigOf(preset ?? engine.running)),
      applyPreset: vi.fn(async (name: string) => {
        if (name === 'club_night') await slow.promise;
        engine.running = name;
      }),
    };
    const draw = vi.fn();
    const follower = createDemoRigFollower<DemoRig>({ source, draw });

    const first = follower.pick('club_night');
    await follower.pick('festival');
    await settle();
    // Nothing is drawn while the first pick is still out.
    expect(draw).not.toHaveBeenCalled();

    slow.resolve();
    await first;
    await settle();

    expect(engine.running).toBe('club_night');
    expect(draw).toHaveBeenCalledTimes(1);
    expect(draw).toHaveBeenLastCalledWith(rigOf('club_night'));
  });

  it('asks the engine what it is running when a pick fails', async () => {
    const refusal = new Error('409: a patched rig is live');
    const source: DemoRigSource<DemoRig> = {
      getRig: vi.fn(async (preset?: string) => rigOf(preset ?? 'pro_beam_room')),
      applyPreset: vi.fn(async () => {
        throw refusal;
      }),
    };
    const draw = vi.fn();
    const follower = createDemoRigFollower<DemoRig>({ source, draw });

    await expect(follower.pick('club_night')).rejects.toBe(refusal);
    await settle();

    expect(source.getRig).toHaveBeenLastCalledWith();
    expect(draw).toHaveBeenCalledTimes(1);
    expect(draw).toHaveBeenLastCalledWith(rigOf('pro_beam_room'));
  });

  it('asks again when the backend is not answering yet', async () => {
    const waits: number[] = [];
    let calls = 0;
    const source: DemoRigSource<DemoRig> = {
      getRig: vi.fn(async () => {
        calls += 1;
        if (calls < 3) throw new Error('503');
        return rigOf('pro_beam_room');
      }),
      applyPreset: vi.fn(async () => {}),
    };
    const draw = vi.fn();
    const follower = createDemoRigFollower<DemoRig>({
      source,
      draw,
      retryDelaysMs: [1000, 3000],
      wait: async (ms) => {
        waits.push(ms);
      },
    });

    expect(await follower.follow()).toBe(true);
    expect(waits).toEqual([1000, 3000]);
    expect(draw).toHaveBeenCalledWith(rigOf('pro_beam_room'));
  });

  it('gives up after its retries and keeps what is drawn', async () => {
    const source: DemoRigSource<DemoRig> = {
      getRig: vi.fn(async () => {
        throw new Error('offline');
      }),
      applyPreset: vi.fn(async () => {}),
    };
    const draw = vi.fn();
    const follower = createDemoRigFollower<DemoRig>({ source, draw, retryDelaysMs: [1, 1], wait: async () => {} });

    expect(await follower.follow()).toBe(false);
    expect(source.getRig).toHaveBeenCalledTimes(3);
    expect(draw).not.toHaveBeenCalled();
  });

  it('lets a newer ask replace one still waiting to retry', async () => {
    const gate = deferred<void>();
    let calls = 0;
    const source: DemoRigSource<DemoRig> = {
      getRig: vi.fn(async () => {
        calls += 1;
        if (calls === 1) throw new Error('503');
        return rigOf('pro_beam_room');
      }),
      applyPreset: vi.fn(async () => {}),
    };
    const draw = vi.fn();
    const follower = createDemoRigFollower<DemoRig>({ source, draw, retryDelaysMs: [1000], wait: () => gate.promise });

    const first = follower.follow();
    await settle();
    expect(await follower.follow()).toBe(true);
    gate.resolve();

    expect(await first).toBe(false);
    expect(source.getRig).toHaveBeenCalledTimes(2);
    expect(draw).toHaveBeenCalledTimes(1);
  });
});
