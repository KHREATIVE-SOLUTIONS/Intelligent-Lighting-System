import type { LinkState } from './showHealth';

// Keeps the 3D view on the demo rig the engine is running.
//
// The view is sent state for whatever rig the engine runs, so it has to draw
// that rig and no other. The engine's rig can change without the view asking:
// a restarted backend boots on its default demo rig, whatever was picked
// before. An open view that carried on drawing the old pick showed one rig
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

export function createDemoRigFollower<R>({
  source,
  draw,
  retryDelaysMs = DEFAULT_RETRY_DELAYS_MS,
  wait = (ms) => new Promise<void>((resolve) => setTimeout(resolve, ms)),
}: DemoRigFollowerOptions<R>): DemoRigFollower {
  let asks = 0;
  let picks = 0;
  let picksRunning = 0;

  async function follow(): Promise<boolean> {
    const ask = ++asks;
    const picksAtStart = picks;
    // A pick outranks an ask. An ask sent just before a pick's apply can come
    // back with the rig the engine has since left, and "latest request wins"
    // would draw it over the pick. So an answer is dropped if a pick began
    // after the ask or is still running, and if a newer ask replaced it.
    const superseded = () => ask !== asks || picks !== picksAtStart || picksRunning > 0;

    for (let attempt = 0; ; attempt += 1) {
      try {
        const rig = await source.getRig();
        if (superseded()) return false;
        draw(rig);
        return true;
      } catch {
        // Keep what is drawn. The backend can accept the socket a moment
        // before it answers requests, so try again before giving up; the next
        // reconnect asks afresh either way.
        if (superseded() || attempt >= retryDelaysMs.length) return false;
        await wait(retryDelaysMs[attempt]);
        if (superseded()) return false;
      }
    }
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
