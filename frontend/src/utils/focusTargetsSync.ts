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
