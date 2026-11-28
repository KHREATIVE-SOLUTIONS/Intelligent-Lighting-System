/**
 * Word that a rig's focus targets changed, from the hook that changed them to
 * every other one showing the same rig (docs/FOCUS_PRESETS.md, "In the app"):
 * a target added or removed in the Focus presets panel appears on, or goes
 * from, the 3D view without a reload. The same scheme as stagePlotSync.ts: a
 * window event in this tab, the storage event of a localStorage write in the
 * others.
 */

const EVENT = 'focus-targets-changed';
const KEY = 'focusTargetsChanged';

interface Detail { rigId: number; source: object }

export function announceFocusTargetsChange(rigId: number, source: object): void {
  window.dispatchEvent(new CustomEvent<Detail>(EVENT, { detail: { rigId, source } }));
  try {
    // A new value each time, or a second change the same as the first would raise no event.
    window.localStorage.setItem(KEY, JSON.stringify({ rigId, at: `${Date.now()}-${Math.random()}` }));
  } catch {
    // No storage: the other tabs read it when they next open the view.
  }
}

// ---------------------------------------------------------------------------
// The rig itself changed: a fixture moved, turned, retagged, added or removed,
// or the room edited. Who reaches a target is worked out on the server from
// all of that, so the focus table is read again (debounced, in the hook).
// Announced by the app's client for every rig write that succeeds
// (services/api.ts), so a 2D plan drag, a 3D drag and any rig save are all
// heard without each screen having to remember to say so.
// ---------------------------------------------------------------------------

const RIG_EVENT = 'rig-changed';
const RIG_KEY = 'rigChanged';

/**
 * Writes that leave who-reaches-what as it was: lighting a fixture to find
 * it, the identify session's keep-alive, the focus targets (announced above
 * with their own source) and the stage plot drawing.
 */
const NOT_A_RIG_CHANGE = /\/(test|test-all|set-channels|heartbeat|focus-presets|stage-plot|activate)(\/|$|\?)/;

/** The rig a successful request changed, or null when it changed none. */
export function rigChangedBy(method: string | undefined, url: string | undefined): number | null {
  const verb = (method ?? 'get').toLowerCase();
  if (verb === 'get' || verb === 'head' || verb === 'options' || !url) return null;
  const match = /^(?:.*?\/api)?\/rigs\/(\d+)(\/[^?]*)?/.exec(url);
  if (!match) return null;
  const rest = match[2] ?? '';
  // Deleting the whole rig leaves nothing to read again.
  if (!rest && verb === 'delete') return null;
  if (NOT_A_RIG_CHANGE.test(rest)) return null;
  return Number(match[1]);
}

export function announceRigChange(rigId: number): void {
  window.dispatchEvent(new CustomEvent<{ rigId: number }>(RIG_EVENT, { detail: { rigId } }));
  try {
    window.localStorage.setItem(RIG_KEY, JSON.stringify({ rigId, at: `${Date.now()}-${Math.random()}` }));
  } catch {
    // No storage: the other tabs read it when they next open the view.
  }
}

/** Calls back on any change to the rig, in this tab or another. Returns the unsubscribe. */
export function onRigChange(rigId: number, listener: () => void): () => void {
  const here = (event: Event) => {
    const detail = (event as CustomEvent<{ rigId: number }>).detail;
    if (detail && detail.rigId === rigId) listener();
  };
  const elsewhere = (event: StorageEvent) => {
    if (event.key !== RIG_KEY || !event.newValue) return;
    try {
      const told = JSON.parse(event.newValue) as { rigId?: unknown };
      if (told.rigId === rigId) listener();
    } catch {
      // Not ours to read.
    }
  };
  window.addEventListener(RIG_EVENT, here);
  window.addEventListener('storage', elsewhere);
  return () => {
    window.removeEventListener(RIG_EVENT, here);
    window.removeEventListener('storage', elsewhere);
  };
}

/** Calls back on a change to the rig's targets made anywhere but by source. Returns the unsubscribe. */
export function onFocusTargetsChange(rigId: number, source: object, listener: () => void): () => void {
  const here = (event: Event) => {
    const detail = (event as CustomEvent<Detail>).detail;
    if (detail && detail.rigId === rigId && detail.source !== source) listener();
  };
  const elsewhere = (event: StorageEvent) => {
    if (event.key !== KEY || !event.newValue) return;
    try {
      const told = JSON.parse(event.newValue) as { rigId?: unknown };
      if (told.rigId === rigId) listener();
    } catch {
      // Not ours to read.
    }
  };
  window.addEventListener(EVENT, here);
  window.addEventListener('storage', elsewhere);
  return () => {
    window.removeEventListener(EVENT, here);
    window.removeEventListener('storage', elsewhere);
  };
}
