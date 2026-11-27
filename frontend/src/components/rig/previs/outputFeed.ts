/**
 * The frames the 3D view draws from, as they come off the socket.
 *
 * The backend sends, about thirty times a second, the frame per universe that
 * its engine outputs (grand master and blackout applied) and an `output`
 * block saying what stands between the look and the wire. This holds the
 * latest of those in a plain object the render loop reads. It is deliberately
 * not React state and not the store: a new frame must not re-render anything.
 *
 * Read-only by construction. Nothing here, and nothing in the view, sends a
 * DMX value anywhere.
 */

export type OutputFeed = {
  /** Universe -> 512 values, the first channel at index 0. */
  frames: Map<number, ArrayLike<number>>;
  /** The grand master, 0-1. Null when the backend did not say. */
  master: number | null;
  /** The operator's blackout latch. */
  blackout: boolean;
  /**
   * Whether these frames are reaching the DMX controller. False for a demo
   * rig held off the wire and while the identify walkthrough has the output.
   * Null when the backend did not say.
   */
  onWire: boolean | null;
  /** When the last frames arrived, on the caller's clock. 0 is never. */
  receivedAt: number;
};

/** With no frames for this long, what is drawn is no longer what is being sent. */
export const FEED_STALE_AFTER_MS = 2000;

export function createOutputFeed(): OutputFeed {
  return { frames: new Map(), master: null, blackout: false, onWire: null, receivedAt: 0 };
}

export function clearOutputFeed(feed: OutputFeed): void {
  feed.frames.clear();
  feed.master = null;
  feed.blackout = false;
  feed.onWire = null;
  feed.receivedAt = 0;
}

type LightingMessage = {
  dmx_frames?: Record<string, ArrayLike<number>> | null;
  dmx_frame?: ArrayLike<number> | null;
  dmx_universe?: number | string | null;
  output?: { master?: number | null; blackout?: boolean | null; on_wire?: boolean | null } | null;
};

const isFrame = (value: unknown): value is ArrayLike<number> =>
  Boolean(value) && typeof (value as ArrayLike<number>).length === 'number' && (value as ArrayLike<number>).length > 0;

/**
 * Take the frames out of one `lighting` message. Returns false, and changes
 * nothing, when the message carries none.
 */
export function ingestOutput(feed: OutputFeed, lighting: LightingMessage | null | undefined, now: number): boolean {
  if (!lighting) return false;
  let took = false;
  if (lighting.dmx_frames && typeof lighting.dmx_frames === 'object') {
    const seen = new Set<number>();
    for (const [key, frame] of Object.entries(lighting.dmx_frames)) {
      const universe = Number(key);
      if (!Number.isFinite(universe) || !isFrame(frame)) continue;
      feed.frames.set(universe, frame);
      seen.add(universe);
    }
    if (seen.size > 0) {
      // A universe the rig no longer occupies must not keep its last frame.
      for (const universe of [...feed.frames.keys()]) {
        if (!seen.has(universe)) feed.frames.delete(universe);
      }
      took = true;
    }
  } else if (isFrame(lighting.dmx_frame)) {
    feed.frames.set(Number(lighting.dmx_universe) || 0, lighting.dmx_frame);
    took = true;
  }
  if (!took) return false;

  const output = lighting.output;
  feed.master = typeof output?.master === 'number' && Number.isFinite(output.master) ? output.master : null;
  feed.blackout = Boolean(output?.blackout);
  feed.onWire = typeof output?.on_wire === 'boolean' ? output.on_wire : null;
  feed.receivedAt = now;
  return true;
}

export type FeedSummary = {
  kind: 'none' | 'stale' | 'blackout' | 'held' | 'live' | 'unknown';
  label: string;
  detail: string;
};

/** One line for the header: what the picture is being drawn from. */
export function summariseFeed(feed: OutputFeed, now: number): FeedSummary {
  if (feed.receivedAt === 0) {
    return { kind: 'none', label: 'No output yet', detail: 'Waiting for the engine. Nothing is being drawn from a frame.' };
  }
  if (now - feed.receivedAt > FEED_STALE_AFTER_MS) {
    return {
      kind: 'stale',
      label: 'Output lost',
      detail: 'No frames for over two seconds. The picture is the last frame received, not what is being sent now.',
    };
  }
  const master = feed.master !== null && feed.master < 0.995 ? `, master ${Math.round(feed.master * 100)}%` : '';
  if (feed.blackout) {
    return { kind: 'blackout', label: 'Blackout', detail: 'The blackout is latched: the engine is sending zero intensity.' };
  }
  if (feed.onWire === false) {
    return {
      kind: 'held',
      label: `Preview only${master}`,
      detail: 'Drawn from the frames the engine outputs. They are not being sent: a demo rig is held off the wire, or a fixture check has the output.',
    };
  }
  if (feed.onWire === true) {
    return { kind: 'live', label: `On the wire${master}`, detail: 'Drawn from the frames being sent to the DMX output.' };
  }
  return { kind: 'unknown', label: `Engine output${master}`, detail: 'Drawn from the frames the engine outputs.' };
}
