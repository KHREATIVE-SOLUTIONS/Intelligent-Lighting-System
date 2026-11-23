/**
 * The 2D plan under a finger or a pen, at the venue: when a press that is
 * held becomes a long-press (the touch for Shift), how far a tap on the
 * on-screen nudge pad carries the selection, and when to say that the keys
 * are going somewhere else.
 *
 * Numbers and words only: no React and no drawing. docs/ROOM_SCAN.md.
 */
import { DRAG_THRESHOLD_PX, keysBelongElsewhere, nudgeShift, pastDragThreshold } from './planSelect2d';
import type { ScreenPoint } from './planSelect2d';
import type { RowShift } from './rowMove2d';

// ---------------------------------------------------------------------------
// A long-press
// ---------------------------------------------------------------------------

/** A finger or pen held still this long is a long-press. */
export const LONG_PRESS_MS = 500;

/**
 * Whether a pointer is one with no modifier keys to hold: a finger or a pen.
 * A mouse is not, and neither is a pointer that does not say what it is, so
 * anything unknown is left to the mouse's own handling.
 */
export function isTouchPointer(pointerType: string | null | undefined): boolean {
  return pointerType === 'touch' || pointerType === 'pen';
}

/**
 * What a press is so far. `press`: not yet decided, and let go now it is a
 * tap. `drag`: the pointer went 5 pixels from where it went down before the
 * long-press was due. `long-press`: it was held for 500 ms without that.
 */
export type PressPhase = 'press' | 'drag' | 'long-press';

/**
 * What a held press has become, `heldMs` after it went down at `down`, with
 * the pointer now at `now`.
 *
 * Once decided it stays decided: a drag held still for a second is still a
 * drag, and a long-press that then wanders is still a long-press, which is
 * what keeps a long-press from ever moving anything. Undecided, travel is
 * asked about first, so a finger that is 5 pixels away when the time is up
 * is dragging, not long-pressing.
 */
export function pressPhase(
  was: PressPhase, down: ScreenPoint, now: ScreenPoint, heldMs: number,
  holdMs: number = LONG_PRESS_MS, threshold: number = DRAG_THRESHOLD_PX,
): PressPhase {
  if (was !== 'press') return was;
  if (pastDragThreshold(down, now, threshold)) return 'drag';
  return heldMs >= holdMs ? 'long-press' : 'press';
}

// ---------------------------------------------------------------------------
// The nudge pad
// ---------------------------------------------------------------------------

/** Every button of the nudge pad is at least this many pixels each way: a fingertip. */
export const NUDGE_PAD_BUTTON_PX = 44;

/** The pad's four arrows, named by where they point on the plan. */
export type PadDirection = 'up' | 'down' | 'left' | 'right';

/** The key each arrow of the pad stands for. */
export const PAD_KEYS: Record<PadDirection, string> = {
  up: 'ArrowUp',
  down: 'ArrowDown',
  left: 'ArrowLeft',
  right: 'ArrowRight',
};

/** What each arrow is called, for a screen reader: up the plan is upstage. */
export const PAD_LABELS: Record<PadDirection, string> = {
  up: 'Nudge upstage',
  down: 'Nudge downstage',
  left: 'Nudge left',
  right: 'Nudge right',
};

/**
 * The shift a tap on one of the pad's arrows asks for: exactly the matching
 * arrow key's (`nudgeShift`), with the pad's 10x switch standing for Shift.
 * One grid step, or ten.
 */
export function padShift(direction: PadDirection, gridSize: number, tenfold = false): RowShift | null {
  return nudgeShift(PAD_KEYS[direction], gridSize, tenfold);
}

// ---------------------------------------------------------------------------
// The focus cue
// ---------------------------------------------------------------------------

/** What the plan says when the keys are going somewhere else. */
export const KEYS_HINT_TEXT = 'Click the plan to use the keys';

/**
 * Whether to say on the plan that a click on it brings the keys back: the
 * focus is somewhere the plan leaves the keys to (`keysBelongElsewhere`: the
 * rig's name being typed, the snap mode's drop-down after a choice). Not for
 * a dialog, which is in front of the plan: a click on the plan is not the
 * way out of one.
 */
export function keysHintDue(focus: unknown): boolean {
  if (!keysBelongElsewhere(focus)) return false;
  return !(focus as Element).closest('[role="dialog"]');
}
