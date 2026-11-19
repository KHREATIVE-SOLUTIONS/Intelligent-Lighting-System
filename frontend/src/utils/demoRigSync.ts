import type { LinkState } from './showHealth';

// Keeps the 3D view on the demo rig the engine is running.
//
// The view is sent state for whatever rig the engine runs, so it has to draw
// that rig and no other. The engine's rig can change without the view asking,
// in two ways:
//
// - A restarted backend boots on its default demo rig, whatever was picked
//   before. The live socket drops and comes back: see onLinkRestored.
// - Another tab, or a script, puts a different demo rig on the engine. Nothing
//   drops; the status poll's next reading names the new rig: see
//   onEngineOnAnotherRig.
//
// Either way an open view that carried on drawing its old pick showed one rig
// while being sent another's state, and re-picking it did nothing, because
// the chooser already said that name.
//
// Plain functions, no React: the view supplies how to fetch and how to draw.

/** The part of the live socket this needs. */
export interface LinkSource {
  readonly linkState: LinkState;
  onStateChange(listener: (state: LinkState) => void): () => void;
}

const isDown = (state: LinkState): boolean => state === 'reconnecting' || state === 'lost';

/**
 * Calls back each time the link to the backend comes back after dropping.
 *
 * The first connection of a page load does not count: the page fetches its
 * rig as it mounts. A page that mounts in the middle of an outage does count
 * when the link arrives, because that first fetch failed.
 *
 * Returns the function that stops listening.
 */
export function onLinkRestored(link: LinkSource, callback: () => void): () => void {
  let dropped = isDown(link.linkState);
  return link.onStateChange((state) => {
    if (isDown(state)) {
      dropped = true;
    } else if (state === 'idle') {
      // Closed on purpose (logout). The next connection is a first one again.
      dropped = false;
    } else if (state === 'connected' && dropped) {
      dropped = false;
      callback();
    }
  });
}

/** What a status reading says about the rig the engine is running. */
export interface EngineRigReport {
  live_rig_name?: string | null;
  live_rig_demo?: boolean;
}

/**
 * True when the engine reports a demo rig other than the one drawn.
 *
 * False while a patched rig is live: the demo view cannot draw that one, and
 * asking for "the engine's demo rig" would only fetch the default. False
 * while nothing is drawn: loading the first rig is the page's own job.
 */
export function engineLeftDrawnRig(report: EngineRigReport | null, drawnVenue: string | null): boolean {
  if (!report || !report.live_rig_demo || !report.live_rig_name) return false;
  if (!drawnVenue) return false;
  return report.live_rig_name !== drawnVenue;
}

/** The part of the health store this needs: the latest engine status reading. */
export interface EngineReportStore {
  subscribe(
    listener: (state: { effects: EngineRigReport | null }, previous: { effects: EngineRigReport | null }) => void
  ): () => void;
}

/**
 * Calls back each time a new status reading shows the engine on a demo rig
 * other than the one drawn: the rig was switched from another tab or by a
 * script, with no drop in the link.
 *
 * It calls back on every such reading, not only the first, so an ask that
 * failed is made again at the next poll. The name in the reading is only the
 * reason to ask; what gets drawn is the answer to the ask.
 *
 * Returns the function that stops listening.
 */
export function onEngineOnAnotherRig(
  store: EngineReportStore,
  drawnVenue: () => string | null,
  callback: () => void
): () => void {
  return store.subscribe((state, previous) => {
    // The store changes many times a second for other reasons (every analysis
    // message stamps it). Only a new status reading is of interest, and each
    // poll that reaches the box stores a new one.
    if (state.effects === previous.effects) return;
    if (engineLeftDrawnRig(state.effects, drawnVenue())) callback();
  });
}

/**
 * The rig to hold once an answer arrives: the one already drawn if the answer
 * describes the same rig, so a blip in the link does not rebuild the scene.
 * Compared in full, not by name, because a restarted backend can serve a
 * changed rig under the same name.
 */
export function settleRig<R>(drawn: R | null, answer: R): R {
  if (drawn !== null && JSON.stringify(drawn) === JSON.stringify(answer)) return drawn;
  return answer;
}

export interface DemoRigSource<R> {
  /** With no preset named: the demo rig the engine is running. */
  getRig(preset?: string): Promise<R>;
  /** Puts a demo rig on the engine. */
  applyPreset(name: string): Promise<void>;
}

export interface DemoRigFollowerOptions<R> {
  source: DemoRigSource<R>;
  /** Draw this rig: the engine's answer, or the operator's pick once applied. */
  draw(rig: R): void;
  /** Waits between failed asks. After the last one the ask gives up. */
  retryDelaysMs?: number[];
  wait?(ms: number): Promise<void>;
  /** How long an ask may be out before a new one is allowed to replace it. */
  askTimeoutMs?: number;
  now?(): number;
}

export interface DemoRigFollower {
  /**
   * Ask the engine which demo rig it is running and draw that. Resolves true
   * if the answer was drawn, false if it was dropped or never came.
   */
  follow(): Promise<boolean>;
  /**
   * The operator picked a rig: put it on the engine, then draw it. Rejects if
   * the switch failed. A pick that failed, or that overlapped another pick,
   * ends by asking the engine what it is running and drawing that instead.
   */
  pick(name: string): Promise<void>;
}

const DEFAULT_RETRY_DELAYS_MS = [1000, 3000];
// The shared HTTP client sets no timeout, so a request can hang for minutes.
const DEFAULT_ASK_TIMEOUT_MS = 8000;

export function createDemoRigFollower<R>({
  source,
  draw,
  retryDelaysMs = DEFAULT_RETRY_DELAYS_MS,
  wait = (ms) => new Promise<void>((resolve) => setTimeout(resolve, ms)),
  askTimeoutMs = DEFAULT_ASK_TIMEOUT_MS,
  now = () => Date.now(),
}: DemoRigFollowerOptions<R>): DemoRigFollower {
  let picks = 0;
  let picksRunning = 0;
  let asks = 0;
  // The ask on its way, if there is one.
  let out: { picksAtStart: number; startedAt: number; done: Promise<boolean> } | null = null;

  function follow(): Promise<boolean> {
    // An ask already on its way is joined, not replaced. While the view is
    // behind, a status reading asks again every two seconds; if each new ask
    // dropped the one before, an answer slower than that would never be
    // drawn. Two things do call for a fresh ask: a pick since it left, which
    // makes its answer worthless, and its having been out too long.
    if (out && out.picksAtStart === picks && now() - out.startedAt < askTimeoutMs) {
      return out.done;
    }

    const ask = ++asks;
    const picksAtStart = picks;
    // A pick outranks an ask. An ask sent just before a pick's apply can come
    // back with the rig the engine has since left, and "latest request wins"
    // would draw it over the pick. So an answer is dropped if a pick began
    // after the ask or is still running, and if a fresh ask replaced it.
    const superseded = () => ask !== asks || picks !== picksAtStart || picksRunning > 0;

    const run = async (): Promise<boolean> => {
      for (let attempt = 0; ; attempt += 1) {
        try {
          const rig = await source.getRig();
          if (superseded()) return false;
          draw(rig);
          return true;
        } catch {
          // Keep what is drawn. The backend can accept the socket a moment
          // before it answers requests, so try again before giving up; the
          // next reconnect or status reading asks afresh either way.
          if (superseded() || attempt >= retryDelaysMs.length) return false;
          await wait(retryDelaysMs[attempt]);
          if (superseded()) return false;
        }
      }
    };

    const entry = { picksAtStart, startedAt: now(), done: run() };
    out = entry;
    const clear = () => {
      if (out === entry) out = null;
    };
    void entry.done.then(clear, clear);
    return entry.done;
  }

  async function pick(name: string): Promise<void> {
    const mine = ++picks;
    const startedAlone = picksRunning === 0;
    picksRunning += 1;
    let rig: R | undefined;
    let failure: { error: unknown } | null = null;
    try {
      // The order matters: drawing a rig the engine is not running would
      // animate it with another rig's state.
      await source.applyPreset(name);
      rig = await source.getRig(name);
    } catch (error) {
      failure = { error };
    }
    picksRunning -= 1;

    // A pick that ran start to finish with no other pick beside it, and
    // worked, knows what the engine is on: the rig it applied.
    if (!failure && startedAlone && mine === picks) {
      draw(rig as R);
      return;
    }
    // Otherwise nobody here knows. A failed pick's apply may have landed or
    // not, and two picks that overlapped can have reached the engine in
    // either order. So once the last of them is done, ask the engine.
    if (picksRunning === 0) void follow();
    if (failure) throw failure.error;
  }

  return { follow, pick };
}
