// The 2D plan under a finger or a pen, with no drawing: when a held press is
// a long-press, what a tap on the nudge pad asks for, and when the plan says
// the keys are going somewhere else. docs/ROOM_SCAN.md.
import { afterEach, describe, expect, it } from 'vitest';
import { nudgeShift } from '../components/rig/planSelect2d';
import {
  KEYS_HINT_TEXT, LONG_PRESS_MS, NUDGE_PAD_BUTTON_PX, PAD_KEYS, PAD_LABELS, isTouchPointer, keysHintDue, padShift,
  pressPhase,
} from '../components/rig/planTouch2d';
import type { PadDirection } from '../components/rig/planTouch2d';

// ---------------------------------------------------------------------------
// A long-press
// ---------------------------------------------------------------------------

describe('isTouchPointer', () => {
  it('is a finger or a pen', () => {
    expect(isTouchPointer('touch')).toBe(true);
    expect(isTouchPointer('pen')).toBe(true);
  });

  it('is not a mouse, or a pointer that does not say what it is', () => {
    expect(isTouchPointer('mouse')).toBe(false);
    expect(isTouchPointer('')).toBe(false);
    expect(isTouchPointer(undefined)).toBe(false);
    expect(isTouchPointer(null)).toBe(false);
  });
});

describe('pressPhase', () => {
  const down = { clientX: 100, clientY: 200 };
  const still = down;
  // 3 across and 3 down is 4.24 pixels: a wobble.
  const wobble = { clientX: 103, clientY: 203 };
  // 3 across and 4 down is exactly 5.
  const away = { clientX: 103, clientY: 204 };

  it('is half a second', () => {
    expect(LONG_PRESS_MS).toBe(500);
  });

  it('is undecided while the press is short and has not gone 5 pixels', () => {
    expect(pressPhase('press', down, still, 0)).toBe('press');
    expect(pressPhase('press', down, still, 499)).toBe('press');
    expect(pressPhase('press', down, wobble, 499)).toBe('press');
  });

  it('is a long-press from 500 ms, held still or with a wobble under 5 pixels', () => {
    expect(pressPhase('press', down, still, 500)).toBe('long-press');
    expect(pressPhase('press', down, still, 2000)).toBe('long-press');
    expect(pressPhase('press', down, wobble, 500)).toBe('long-press');
  });

  it('is a drag from 5 pixels, however short the press', () => {
    expect(pressPhase('press', down, away, 0)).toBe('drag');
    expect(pressPhase('press', down, { clientX: 95, clientY: 200 }, 120)).toBe('drag');
  });

  it('is a drag, not a long-press, for a pointer that is 5 pixels away when the time is up', () => {
    expect(pressPhase('press', down, away, 500)).toBe('drag');
    expect(pressPhase('press', down, away, 5000)).toBe('drag');
  });

  it('stays what it was once decided', () => {
    // A drag held still for a second, back where it began, is still a drag.
    expect(pressPhase('drag', down, still, 1500)).toBe('drag');
    // A long-press that then wanders moves nothing: it is still a long-press.
    expect(pressPhase('long-press', down, { clientX: 180, clientY: 260 }, 900)).toBe('long-press');
  });

  it('goes by the hold time and the threshold it is given', () => {
    expect(pressPhase('press', down, still, 300, 250)).toBe('long-press');
    expect(pressPhase('press', down, still, 200, 250)).toBe('press');
    expect(pressPhase('press', down, wobble, 0, 500, 4)).toBe('drag');
  });
});

// ---------------------------------------------------------------------------
// The nudge pad
// ---------------------------------------------------------------------------

describe('padShift', () => {
  const directions: PadDirection[] = ['up', 'down', 'left', 'right'];

  it('is one grid step: left and right across the plan, up upstage, down downstage', () => {
    expect(padShift('left', 0.5)).toEqual({ dx: -0.5, dz: 0 });
    expect(padShift('right', 0.5)).toEqual({ dx: 0.5, dz: 0 });
    expect(padShift('up', 0.5)).toEqual({ dx: 0, dz: -0.5 });
    expect(padShift('down', 0.5)).toEqual({ dx: 0, dz: 0.5 });
  });

  it('is ten steps with the 10x switch on', () => {
    expect(padShift('right', 0.5, true)).toEqual({ dx: 5, dz: 0 });
    expect(padShift('up', 0.25, true)).toEqual({ dx: 0, dz: -2.5 });
  });

  it('is exactly what the matching arrow key gives, with 10x for Shift', () => {
    for (const direction of directions) {
      for (const grid of [0.25, 0.5, 1]) {
        expect(padShift(direction, grid)).toEqual(nudgeShift(PAD_KEYS[direction], grid, false));
        expect(padShift(direction, grid, true)).toEqual(nudgeShift(PAD_KEYS[direction], grid, true));
      }
    }
  });

  it('is nothing for a grid with no step', () => {
    expect(padShift('left', 0)).toBeNull();
  });

  it('names every arrow, and asks for a fingertip of 44 pixels', () => {
    expect(PAD_LABELS).toEqual({
      up: 'Nudge upstage', down: 'Nudge downstage', left: 'Nudge left', right: 'Nudge right',
    });
    expect(NUDGE_PAD_BUTTON_PX).toBeGreaterThanOrEqual(44);
  });
});

// ---------------------------------------------------------------------------
// The focus cue
// ---------------------------------------------------------------------------

describe('keysHintDue', () => {
  afterEach(() => { document.body.innerHTML = ''; });

  const made = (html: string) => {
    document.body.innerHTML = html;
    return document.body.querySelector('#it')!;
  };

  it('says to click the plan', () => {
    expect(KEYS_HINT_TEXT).toBe('Click the plan to use the keys');
  });

  it('is due with the focus in a field or a drop-down, where the plan leaves the keys alone', () => {
    expect(keysHintDue(made('<input id="it" />'))).toBe(true);
    expect(keysHintDue(made('<textarea id="it"></textarea>'))).toBe(true);
    expect(keysHintDue(made('<select id="it"><option>Grid</option></select>'))).toBe(true);
    // The snap mode's drop-down, as it is drawn, after a choice.
    expect(keysHintDue(made('<div id="it" role="combobox" tabindex="0">Grid</div>'))).toBe(true);
  });

  it('is not due where the plan has the keys: no focus, the page, a button, the plan itself', () => {
    expect(keysHintDue(null)).toBe(false);
    expect(keysHintDue(undefined)).toBe(false);
    expect(keysHintDue(document.body)).toBe(false);
    expect(keysHintDue(made('<button id="it">Select row</button>'))).toBe(false);
    expect(keysHintDue(made('<div id="it" tabindex="-1"><svg></svg></div>'))).toBe(false);
  });

  it('is not due in a dialog: a click on the plan is not the way out of one', () => {
    expect(keysHintDue(made('<div role="dialog"><input id="it" /></div>'))).toBe(false);
    expect(keysHintDue(made('<div role="dialog"><button id="it">Close</button></div>'))).toBe(false);
  });
});
