/**
 * Setting the heights of a scanned room's items by dragging (slice 22): what
 * the height strip beside the 2D plan shows for the selected raised area,
 * truss line or ring, where its handles stand, and what a drag of one asks
 * the server to change.
 *
 * Numbers and words only: no React and no drawing. The plan is seen from
 * above and has no height, so the strip is an elevation of one item: the
 * floor at the bottom, the ceiling at the top. The server makes the change
 * and has the last word on what fits (PATCH
 * /api/rigs/{id}/room-shell/{kind}/{index}, `height` and `base_height`);
 * docs/ROOM_SCAN.md.
 */
import type { RoomShell } from '../../types';
import { SHELL_LIMITS, shellItemKey, shellItemTitle } from '../../utils/roomShellEdit';
import type { ShellItem, ShellItemChanges, ShellItemKind } from '../../utils/roomShellEdit';

/**
 * What a press in the strip has hold of: the top of a raised area (its deck
 * above the floor), its underside (its base height: 0 stands on the floor,
 * more floats), or the underside of a truss line or ring (its trim height).
 */
export type HeightGrip = 'top' | 'base' | 'trim';

/** A height goes to this many metres. */
export const HEIGHT_SNAP_M = 0.05;
/** And to this many with Shift held, or with the strip's coarse step chosen. */
export const HEIGHT_SHIFT_SNAP_M = 0.25;
/** The most a truss or ring hangs at in a room that stores no ceiling (edit.ANY_ROOM_HEIGHT_MAX_M). */
export const NO_CEILING_HANG_MOST_M = 30;
/** The least the strip shows of a room, floor to top, in metres. */
const SCALE_LEAST_M = 3;

const roundMm = (value: number) => Math.round(value * 1000) / 1000 + 0;
const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

/** One handle of the strip: what it sets, where it stands above the floor and how far it may go. */
export interface HeightHandle {
  grip: HeightGrip;
  /** Where it stands, in metres above the floor. */
  value: number;
  /** The least and the most it can be dragged to, in metres above the floor. */
  least: number;
  most: number;
}

/** The selected item as the strip shows it. */
export interface HeightGauge {
  /** The list and the place in it: `shellItemKey`. */
  key: string;
  kind: ShellItemKind;
  /** Its place in the stored list, from 0: what the server knows it by. */
  index: number;
  /** Its name, or what it is. */
  title: string;
  /** The room's ceiling above the floor, or null for a room that stores none. */
  ceiling: number | null;
  /** How many metres the strip shows, from the floor up: the ceiling, or enough to take the item in. */
  scaleTop: number;
  /** A raised area's underside above the floor; null for a line or a ring. */
  base: number | null;
  /** A raised area's top above the floor (its base and its deck), or the underside of a line or ring. */
  top: number;
  /** A raised area has `top` then `base`; a line or a ring has `trim`. */
  handles: HeightHandle[];
}

/**
 * The strip for one item of the room, or null for one with no height stored
 * (it cannot be drawn in an elevation, and its row cannot set it either).
 *
 * The limits are the server's (`edit.height_limits`): a raised area's deck is
 * 0.05 to 3 m above its base with its top under the ceiling, its base is 0 to
 * 10 m with its top under the ceiling, and a line or ring hangs from 0.5 m to
 * the ceiling (30 m where the room stores none).
 */
export function heightGauge(item: ShellItem | null | undefined, shell: RoomShell | null | undefined): HeightGauge | null {
  if (!item) return null;
  const height = item.sizes.height;
  if (!isNumber(height)) return null;
  const stored = shell?.room?.height;
  const ceiling = isNumber(stored) && stored > 0 ? stored : null;
  const common = { key: shellItemKey(item), kind: item.kind, index: item.index, title: shellItemTitle(item), ceiling };

  if (item.kind === 'risers') {
    const base = isNumber(item.baseHeight) && item.baseHeight > 0 ? item.baseHeight : 0;
    const top = roundMm(base + height);
    const deckMost = ceiling === null ? SHELL_LIMITS.deckMost : Math.min(SHELL_LIMITS.deckMost, ceiling - base);
    const topLeast = roundMm(base + SHELL_LIMITS.deck);
    const baseMost = ceiling === null ? SHELL_LIMITS.baseMost : Math.min(SHELL_LIMITS.baseMost, ceiling - height);
    return {
      ...common,
      scaleTop: scaleFor(ceiling, top),
      base,
      top,
      handles: [
        { grip: 'top', value: top, least: topLeast, most: Math.max(topLeast, roundMm(base + deckMost)) },
        { grip: 'base', value: base, least: 0, most: Math.max(0, roundMm(baseMost)) },
      ],
    };
  }

  const most = ceiling === null ? NO_CEILING_HANG_MOST_M : ceiling;
  return {
    ...common,
    scaleTop: scaleFor(ceiling, height),
    base: null,
    top: height,
    handles: [{ grip: 'trim', value: height, least: SHELL_LIMITS.hang, most: Math.max(SHELL_LIMITS.hang, most) }],
  };
}

/** How many metres the strip shows: the ceiling where there is one, and never less than the item needs. */
function scaleFor(ceiling: number | null, top: number): number {
  if (ceiling !== null) return Math.max(ceiling, top, 1);
  // No ceiling stored: a metre of air over the item, to the whole metre, so there is somewhere to drag it up to.
  return Math.max(SCALE_LEAST_M, Math.ceil(top + 1));
}

/** What a drag in the strip has the item at. */
export interface HeightDrag {
  /** Where the handle now stands, in metres above the floor. */
  value: number;
  /** The item as the strip draws it meanwhile. */
  base: number | null;
  top: number;
  /** What to send, or null when the drag has it where it already is. */
  changes: ShellItemChanges | null;
  /** The live value, in words. */
  readout: string;
}

/**
 * Where a drag of one handle has its item, with the handle `metres` above
 * the floor.
 *
 * The height goes to 0.05 m, or to 0.25 m when `coarse` (Shift, or the
 * strip's coarse step), and is then held between the handle's least and
 * most, so a limit that is not on the step (a ceiling at 5.37 m) can still
 * be reached.
 *
 * - **top**: the raised area's deck goes up or down and its underside stays:
 *   `height` is sent, which is the deck above its base.
 * - **base**: the whole raised area goes up or down, as thick as it was:
 *   `base_height` is sent, and 0 stands it on the floor.
 * - **trim**: the underside of a line or ring: `height` is sent.
 *
 * A grip the item does not have changes nothing.
 */
export function dragHeight(gauge: HeightGauge, grip: HeightGrip, metres: number, coarse = false): HeightDrag {
  const handle = gauge.handles.find((entry) => entry.grip === grip);
  if (!handle || !isNumber(metres)) {
    return { value: handle?.value ?? gauge.top, base: gauge.base, top: gauge.top, changes: null, readout: '' };
  }
  const step = coarse ? HEIGHT_SHIFT_SNAP_M : HEIGHT_SNAP_M;
  const snapped = roundMm(Math.round(metres / step) * step);
  const value = roundMm(Math.min(Math.max(snapped, handle.least), handle.most));
  const changed = Math.abs(value - handle.value) >= 0.0005;

  if (grip === 'top') {
    const base = gauge.base ?? 0;
    return {
      value,
      base: gauge.base,
      top: value,
      changes: changed ? { height: roundMm(value - base) } : null,
      readout: `top ${value.toFixed(2)} m`,
    };
  }
  if (grip === 'base') {
    const deck = gauge.top - (gauge.base ?? 0);
    return {
      value,
      base: value,
      top: roundMm(value + deck),
      changes: changed ? { base_height: value } : null,
      readout: value < 0.0005 ? 'on the floor' : `base ${value.toFixed(2)} m`,
    };
  }
  return {
    value,
    base: null,
    top: value,
    changes: changed ? { height: value } : null,
    readout: `trim ${value.toFixed(2)} m`,
  };
}

/** What a handle is for, for its tooltip. */
export function heightGripHint(grip: HeightGrip, title: string): string {
  switch (grip) {
    case 'top': return `${title}: drag to raise or lower its top (hold Shift for steps of 0.25 m)`;
    case 'base': return `${title}: drag to raise or lower the whole of it: 0 stands on the floor, more floats (hold Shift for steps of 0.25 m)`;
    default: return `${title}: drag to raise or lower its trim height (hold Shift for steps of 0.25 m)`;
  }
}

/** What a handle is called on the strip. */
export function heightGripLabel(grip: HeightGrip): string {
  return grip === 'top' ? 'Top' : grip === 'base' ? 'Base' : 'Trim';
}
