/**
 * Which raised area of a scanned room is the DJ's booth (docs/ROOM_SCAN.md,
 * slice 28).
 *
 * A scan calls a bar counter a "Booth or counter" too, so the first raised
 * area of that kind is not always the DJ's. A person can say which one is
 * (`is_dj_booth`, set in Edit Room), and that one wins. With nobody having
 * said, the choice is what it always was: the first raised area the room
 * calls a booth, and in a room with none, a guess on its first stage.
 *
 * One function, so the 3D view (scanFloor.ts) and the 2D plan (roomPlan2d.ts)
 * cannot disagree about which raised area it is. No React, nothing drawn.
 */
import type { RoomShellBox } from '../../../types';

/**
 * How the booth was chosen.
 * - 'marked': somebody said this raised area is the DJ's booth.
 * - 'scan': nobody did, and it is the first raised area the room calls a booth.
 * - 'guess': the room has no booth, and it was put on the first stage.
 */
export type BoothSource = 'marked' | 'scan' | 'guess';

export type BoothPick = {
  /** Its place in the list given. */
  index: number;
  source: BoothSource;
};

type Pickable = Pick<RoomShellBox, 'kind' | 'is_dj_booth'> | null | undefined;

/** Whether a raised area is marked as the DJ's booth. Only a stored `true` is a mark, as on the server. */
export function isDjBooth(shape: Pickable): boolean {
  return shape?.is_dj_booth === true;
}

/**
 * The raised area the DJ's booth is on, and how it was chosen: the marked
 * one; else the first of kind `booth`; else the first stage, as a guess. Null
 * for a room with none of the three.
 *
 * `risers` is the list the caller draws from, and `index` is a place in that
 * list. Should two be marked (a shell written by hand), the first is the one.
 */
export function pickDjBooth(risers: Pickable[]): BoothPick | null {
  const marked = risers.findIndex((riser) => isDjBooth(riser));
  if (marked >= 0) return { index: marked, source: 'marked' };
  const booth = risers.findIndex((riser) => riser?.kind === 'booth');
  if (booth >= 0) return { index: booth, source: 'scan' };
  const stage = risers.findIndex((riser) => riser?.kind === 'stage');
  if (stage >= 0) return { index: stage, source: 'guess' };
  return null;
}
