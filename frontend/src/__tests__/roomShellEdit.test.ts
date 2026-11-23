// Editing a stored room by hand: which items the Edit Room dialog lists, what
// a row's fields would change, and how it words what happened. No server and
// no screen. docs/ROOM_SCAN.md.
import { describe, expect, it } from 'vitest';
import { roomPlan } from '../components/rig/roomPlan2d';
import { roomShellItemPath } from '../utils/roomScan';
import {
  SHELL_NAME_MAX,
  deleteQuestionText,
  draftOf,
  editResultText,
  positionText,
  readDraft,
  shellEditErrorText,
  shellItemKey,
  shellItemTitle,
  shellItems,
} from '../utils/roomShellEdit';
import type { ShellItem } from '../utils/roomShellEdit';
import type { RoomShell } from '../types';

// A 12 m by 10 m room: a stage, a booth nobody named, a truss across the room,
// a stub too short to draw, an angled truss somebody has moved, and a ring.
const shell = (): RoomShell => ({
  source: 'scan',
  suggested: true,
  room: { width: 12, depth: 10, height: 6 },
  risers: [
    { center_x: 0, center_z: -3.5, width: 6, depth: 3, height: 0.6, base_height: 0, name: 'Stage', kind: 'stage', suggested: true },
    { center_x: 4, center_z: 3, width: 2, depth: 1, height: 1, kind: 'booth' },
  ],
  truss_lines: [
    { name: 'Overhead line 1', x1: -4, z1: -2, x2: 4, z2: -2, height: 4.2 },
    { name: 'Stub', x1: 0, z1: 0, x2: 0.1, z2: 0, height: 4.2 },
    { name: 'Overhead line 3', x1: -3, z1: 1, x2: 1, z2: 4, height: 4.25, suggested: false },
  ],
  truss_rings: [{ name: 'Overhead ring 1', center_x: 3, center_z: 2, radius: 1.5, height: 4.2 }],
});

const item = (kind: string, index: number, from: RoomShell = shell()): ShellItem => {
  const found = shellItems(from).find((entry) => entry.kind === kind && entry.index === index);
  if (!found) throw new Error(`no ${kind} ${index}`);
  return found;
};

describe('shellItems', () => {
  it('lists raised areas, then lines, then rings, each with its place in the stored list', () => {
    expect(shellItems(shell()).map((entry) => [entry.kind, entry.index, shellItemTitle(entry)])).toEqual([
      ['risers', 0, 'Stage'],
      ['risers', 1, 'Booth or counter'],
      ['truss_lines', 0, 'Overhead line 1'],
      ['truss_lines', 1, 'Stub'],
      ['truss_lines', 2, 'Overhead line 3'],
      ['truss_rings', 0, 'Overhead ring 1'],
    ]);
  });

  it('goes by the stored place, which is not always the place on the plan', () => {
    // The plan leaves the stub out, so the angled truss is its second line.
    const plan = roomPlan(shell());
    expect(plan?.trussLines.map((line) => line.tooltip.split(':')[0])).toEqual(['Overhead line 1', 'Overhead line 3']);
    // The server counts every stored line: it is the third.
    expect(item('truss_lines', 2).name).toBe('Overhead line 3');
    expect(item('truss_lines', 1).drawn).toBe(false);
    expect(item('truss_lines', 1).detail).toMatch(/^Not drawn/);
  });

  it('says what each one is and where its middle is', () => {
    expect(item('risers', 0)).toMatchObject({
      name: 'Stage', detail: '6.0 m by 3.0 m, top 0.60 m above the floor', centre: { x: 0, z: -3.5 }, drawn: true,
    });
    expect(item('truss_lines', 0)).toMatchObject({
      detail: '8.0 m long, underside 4.20 m up, running across the room', centre: { x: 0, z: -2 },
    });
    // A line's middle is half way between its ends.
    expect(item('truss_lines', 2).centre).toEqual({ x: -1, z: 2.5 });
    expect(item('truss_rings', 0)).toMatchObject({
      detail: 'A ring 3.0 m across, underside 4.20 m up', centre: { x: 3, z: 2 },
    });
  });

  it('gives an unnamed item the name the plan gives it, and keeps its own name empty', () => {
    const booth = item('risers', 1);
    expect(booth.name).toBe('');
    expect(booth.fallbackName).toBe('Booth or counter');
    expect(shellItemTitle(booth)).toBe('Booth or counter');
  });

  it('knows which have been moved by hand', () => {
    expect(item('truss_lines', 2).suggested).toBe(false);
    expect(item('truss_lines', 0).suggested).toBe(true);
  });

  it('has nothing for no room, or for a room that is not from a scan', () => {
    expect(shellItems(null)).toEqual([]);
    expect(shellItems(undefined)).toEqual([]);
    expect(shellItems({ dome: { radius: 9, center_x: 0, center_z: 0, rim_height: 5, apex_height: 8 } })).toEqual([]);
    expect(shellItems({ ...shell(), source: 'preset' })).toEqual([]);
    expect(shellItems({ source: 'scan', room: { width: 12, depth: 10, height: 6 } })).toEqual([]);
  });

  it('skips a hole in a stored list without losing the places after it', () => {
    const holed = { ...shell(), risers: [null, shell().risers![1]] } as unknown as RoomShell;
    expect(shellItems(holed).filter((entry) => entry.kind === 'risers').map((entry) => entry.index)).toEqual([1]);
  });

  it('lists an item whose position is missing, with nowhere to move it from', () => {
    const broken = shell();
    (broken.risers![0] as unknown as Record<string, unknown>).center_x = null;
    expect(item('risers', 0, broken).centre).toBeNull();
    expect(draftOf(item('risers', 0, broken))).toMatchObject({ name: 'Stage', x: '', z: '' });
  });
});

describe('keys and paths', () => {
  it('keys a row by its list and place', () => {
    expect(shellItemKey(item('truss_lines', 2))).toBe('truss_lines:2');
  });

  it('names the route', () => {
    expect(roomShellItemPath(7, 'truss_lines', 2)).toBe('/rigs/7/room-shell/truss_lines/2');
  });
});

describe('positionText and draftOf', () => {
  it('shows a position to the millimetre with no trailing noughts and no -0', () => {
    expect(positionText(1.23456)).toBe('1.235');
    expect(positionText(-3.5)).toBe('-3.5');
    expect(positionText(2)).toBe('2');
    expect(positionText(-0.0001)).toBe('0');
  });

  it('starts a row at what is stored', () => {
    expect(draftOf(item('risers', 0))).toEqual({
      name: 'Stage', x: '0', z: '-3.5', width: '6', depth: '3', height: '0.6',
    });
    expect(draftOf(item('risers', 1))).toEqual({ name: '', x: '4', z: '3', width: '2', depth: '1', height: '1' });
  });
});

describe('readDraft', () => {
  const stage = () => item('risers', 0);

  it('has nothing to send for a row as it is stored', () => {
    expect(readDraft(stage(), draftOf(stage()))).toEqual({ changes: null, problem: null });
  });

  it('sends a new name, trimmed to one line, and no position with it', () => {
    expect(readDraft(stage(), { ...draftOf(stage()), name: '  Main   stage ' })).toEqual({
      changes: { name: 'Main stage' }, problem: null,
    });
  });

  it('does not send a name retyped the same', () => {
    expect(readDraft(stage(), { ...draftOf(stage()), name: ' Stage ' }).changes).toBeNull();
  });

  it('refuses a name wiped out, and one too long', () => {
    expect(readDraft(stage(), { ...draftOf(stage()), name: '   ' })).toEqual({
      changes: null, problem: 'A name needs at least one letter or number.',
    });
    const long = readDraft(stage(), { ...draftOf(stage()), name: 'x'.repeat(SHELL_NAME_MAX + 1) });
    expect(long.changes).toBeNull();
    expect(long.problem).toContain(`${SHELL_NAME_MAX} characters`);
    expect(readDraft(stage(), { ...draftOf(stage()), name: 'x'.repeat(SHELL_NAME_MAX) }).problem).toBeNull();
  });

  it('leaves an unnamed item unnamed when nothing is typed', () => {
    const booth = item('risers', 1);
    expect(readDraft(booth, draftOf(booth))).toEqual({ changes: null, problem: null });
    expect(readDraft(booth, { ...draftOf(booth), name: 'The bar' }).changes).toEqual({ name: 'The bar' });
  });

  it('sends only the axis that changed', () => {
    expect(readDraft(stage(), { ...draftOf(stage()), x: '1.5' }).changes).toEqual({ center_x: 1.5 });
    expect(readDraft(stage(), { ...draftOf(stage()), z: ' -4 ' }).changes).toEqual({ center_z: -4 });
    expect(readDraft(stage(), { name: 'Deck', x: '1', z: '-4' }).changes).toEqual({
      name: 'Deck', center_x: 1, center_z: -4,
    });
  });

  it('takes a comma for a decimal point', () => {
    expect(readDraft(stage(), { ...draftOf(stage()), x: '1,5' }).changes).toEqual({ center_x: 1.5 });
  });

  it('does not call the same place written another way a move', () => {
    expect(readDraft(stage(), { ...draftOf(stage()), x: '0.0', z: '-3.50' })).toEqual({ changes: null, problem: null });
    expect(readDraft(stage(), { ...draftOf(stage()), x: '0.0004' }).changes).toBeNull();
  });

  it('says which field is not a number', () => {
    expect(readDraft(stage(), { ...draftOf(stage()), x: 'left' })).toEqual({
      changes: null, problem: 'Across must be a number of metres, such as -1.5.',
    });
    expect(readDraft(stage(), { ...draftOf(stage()), z: '' }).problem).toMatch(/^Depth must be a number/);
    expect(readDraft(stage(), { ...draftOf(stage()), z: 'Infinity' }).problem).toMatch(/^Depth/);
  });

  it('moves a line by its middle', () => {
    const angled = item('truss_lines', 2);
    expect(draftOf(angled)).toMatchObject({ name: 'Overhead line 3', x: '-1', z: '2.5' });
    expect(readDraft(angled, { ...draftOf(angled), z: '0' }).changes).toEqual({ center_z: 0 });
  });

  it('never sends a position for an item that has none stored', () => {
    const broken = shell();
    (broken.risers![0] as unknown as Record<string, unknown>).center_z = 'far';
    const stored = item('risers', 0, broken);
    expect(readDraft(stored, { name: 'Stage', x: '2', z: '2' })).toEqual({ changes: null, problem: null });
    expect(readDraft(stored, { name: 'Deck', x: '2', z: '2' }).changes).toEqual({ name: 'Deck' });
  });
});

describe('wording', () => {
  it('says what a rename did', () => {
    const after = shell();
    after.risers![0].name = 'Main stage';
    expect(editResultText(item('risers', 0), { name: 'Main stage' }, after)).toBe('Stage is now called Main stage.');
  });

  it('says where a move put it, and that no fixture went with it', () => {
    const after = shell();
    after.risers![0].center_x = 1.5;
    expect(editResultText(item('risers', 0), { center_x: 1.5 }, after)).toBe(
      'Stage was moved to 1.5, -3.5. No fixture was moved with it.',
    );
  });

  it('says so when the room held it short of where it was sent', () => {
    const after = shell();
    after.risers![0].center_x = 8;
    const text = editResultText(item('risers', 0), { center_x: 500 }, after);
    expect(text).toContain('Stage was moved to 8, -3.5, as far as the room and 2 m round it allow.');
  });

  it('says both for a rename and a move together', () => {
    const after = shell();
    after.truss_rings![0] = { ...after.truss_rings![0], name: 'Centre ring', center_x: 0, center_z: 0 };
    expect(editResultText(item('truss_rings', 0), { name: 'Centre ring', center_x: 0, center_z: 0 }, after)).toBe(
      'Overhead ring 1 is now called Centre ring. Centre ring was moved to 0, 0. No fixture was moved with it.',
    );
  });

  it('asks before a delete, and says what a deleted truss leaves behind', () => {
    const truss = deleteQuestionText(item('truss_lines', 0));
    expect(truss).toMatch(/^Take Overhead line 1 out of the stored room\?/);
    expect(truss).toContain('Fixtures hung on it stay where they are');
    // A delete can be taken back now, for as long as the scan is not read again.
    expect(truss).toContain('Undo here brings it back, until the scan is read again.');
    expect(truss).not.toContain('cannot be undone');
    const stage = deleteQuestionText(item('risers', 0));
    expect(stage).not.toContain('Fixtures hung on it');
    expect(stage).toContain('Undo here brings it back');
  });

  it('uses the server\'s words for a refusal where it gave any', () => {
    expect(shellEditErrorText(404, 'The stored room has no overhead line number 4 (it has 2).')).toBe(
      'The stored room has no overhead line number 4 (it has 2).',
    );
    expect(shellEditErrorText(422, [{ msg: 'Input should be a valid number' }])).toBe('Input should be a valid number');
    expect(shellEditErrorText(404, undefined)).toMatch(/no longer there/);
    expect(shellEditErrorText(401, undefined)).toMatch(/Sign in again/);
    expect(shellEditErrorText(undefined, undefined)).toMatch(/could not be reached/);
    expect(shellEditErrorText(500, '')).toBe('The room could not be changed. Nothing was stored.');
  });
});
