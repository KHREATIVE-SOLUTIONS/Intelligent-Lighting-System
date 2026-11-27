/**
 * Word that a rig's stage plot changed, from the hook that changed it to every
 * other one showing the same rig (docs/STAGE_PLOT.md, "In the 3D view"): the
 * 3D view hears of a plot removed or replaced in the 2D plan's Stage plot
 * control without a reload.
 *
 * In the same tab a window event carries it; to other tabs of the app, the
 * storage event of a localStorage write. Nothing is left open to close.
 *
 * - image: uploaded, replaced or removed. Read the info and the image again.
 * - calibration: calibrated, or the opacity saved. Read the info again.
 */

export type StagePlotChange = 'image' | 'calibration';

const EVENT = 'stage-plot-changed';
const KEY = 'stagePlotChanged';

interface Detail { rigId: number; change: StagePlotChange; source: object }

export function announceStagePlotChange(rigId: number, change: StagePlotChange, source: object): void {
  window.dispatchEvent(new CustomEvent<Detail>(EVENT, { detail: { rigId, change, source } }));
  try {
    // A new value each time, or a second change the same as the first would raise no event.
    window.localStorage.setItem(KEY, JSON.stringify({ rigId, change, at: `${Date.now()}-${Math.random()}` }));
  } catch {
    // No storage: the other tabs read it when they next open the view.
  }
}

/** Calls back on a change to the rig's plot made anywhere but by source. Returns the unsubscribe. */
export function onStagePlotChange(
  rigId: number,
  source: object,
  listener: (change: StagePlotChange) => void,
): () => void {
  const here = (event: Event) => {
    const detail = (event as CustomEvent<Detail>).detail;
    if (detail && detail.rigId === rigId && detail.source !== source) listener(detail.change);
  };
  const elsewhere = (event: StorageEvent) => {
    if (event.key !== KEY || !event.newValue) return;
    try {
      const told = JSON.parse(event.newValue) as { rigId?: unknown; change?: unknown };
      if (told.rigId === rigId && (told.change === 'image' || told.change === 'calibration')) listener(told.change);
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
