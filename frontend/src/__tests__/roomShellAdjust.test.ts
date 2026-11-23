// Correcting a stored room by hand, the helpers: the sizes, height and heading
// a row holds and what it would send, a quarter turn, what the Add form would
// add, what the Undo button says, and the words for each. No server and no
// screen. docs/ROOM_SCAN.md.
import { describe, expect, it } from 'vitest';
import { roomShellListPath, roomShellUndoPath } from '../utils/roomScan';
import {
  NEW_ITEM_CHOICES,
  SHELL_NAME_MAX,
  SHELL_SIZE_FIELDS,
  draftOf,
  editResultText,
  lineHeading,
  newItemDraft,
  newItemKind,
  quarterTurned,
  readDraft,
  readNewItem,
  shellEditErrorText,
  shellItems,
  shellUndoCount,
  sizeProblem,
  undoButtonText,
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

const stage = () => item('risers', 0);
const truss = () => item('truss_lines', 0);
const ring = () => item('truss_rings', 0);

describe('the sizes a row holds', () => {
  it('has a width, a depth and a height for a raised area', () => {
    expect(stage().sizes).toEqual({ width: 6, depth: 3, height: 0.6 });
    expect(SHELL_SIZE_FIELDS.risers).toEqual(['width', 'depth', 'height']);
  });

  it('reads a line\'s length and heading from its two ends', () => {
    expect(truss().sizes).toEqual({ length: 8, heading_deg: 0, height: 4.2 });
    // 3-4-5: (-3, 1) to (1, 4).
    const angled = item('truss_lines', 2).sizes;
    expect(angled.length).toBeCloseTo(5, 9);
    expect(angled.heading_deg).toBe(36.9);
    expect(angled.height).toBe(4.25);
  });

  it('has a radius and a height for a ring', () => {
    expect(ring().sizes).toEqual({ radius: 1.5, height: 4.2 });
  });

  it('leaves out a size that is not stored as a number', () => {
    const broken = shell();
    (broken.risers![0] as unknown as Record<string, unknown>).width = null;
    (broken.truss_lines![0] as unknown as Record<string, unknown>).x2 = 'far';
    expect(item('risers', 0, broken).sizes).toEqual({ depth: 3, height: 0.6 });
    // With an end missing there is no length and no heading, only the height.
    expect(item('truss_lines', 0, broken).sizes).toEqual({ height: 4.2 });
  });

  it('starts a row at what is stored', () => {
    expect(draftOf(truss())).toEqual({
      name: 'Overhead line 1', x: '0', z: '-2', length: '8', heading_deg: '0', height: '4.2',
    });
    expect(draftOf(item('truss_lines', 2))).toEqual({
      name: 'Overhead line 3', x: '-1', z: '2.5', length: '5', heading_deg: '36.9', height: '4.25',
    });
    expect(draftOf(ring())).toEqual({ name: 'Overhead ring 1', x: '3', z: '2', radius: '1.5', height: '4.2' });
  });
});

describe('lineHeading', () => {
  const heading = (x1: number, z1: number, x2: number, z2: number) => lineHeading({ x1, z1, x2, z2 });

  it('is degrees clockwise from across the room, over -90 and up to 90', () => {
    expect(heading(-4, 0, 4, 0)).toBe(0);
    expect(heading(0, 0, 0, 5)).toBe(90);
    expect(heading(0, 0, 1, 1)).toBe(45);
    expect(heading(0, 0, 1, -1)).toBe(-45);
  });

  it('is the same whichever end is written first', () => {
    expect(heading(4, 0, -4, 0)).toBe(0);
    expect(heading(0, 5, 0, 0)).toBe(90);
    expect(heading(1, 1, 0, 0)).toBe(45);
  });

  it('has none for a line with both ends at one point, or an end missing', () => {
    expect(heading(1, 1, 1, 1)).toBeNull();
    expect(lineHeading({ x1: 0, z1: 0, x2: Number.NaN, z2: 1 })).toBeNull();
  });
});

describe('who set it', () => {
  const marks = (more: Record<string, unknown>) => {
    const marked = shell();
    marked.risers![0] = { ...marked.risers![0], ...more };
    return item('risers', 0, marked).marks;
  };

  it('has no mark for what the scan found', () => {
    expect(stage().marks).toEqual([]);
  });

  it('says what a person did, from what the server leaves on the item', () => {
    expect(marks({ suggested: false, basis: 'scan: a level area. Moved by hand.' })).toEqual(['Moved by hand']);
    expect(marks({ suggested: false, basis: 'scan: a level area. Resized by hand.' })).toEqual(['Resized by hand']);
    expect(marks({ suggested: false, basis: 'scan: a level area. Moved by hand. Resized by hand.' })).toEqual([
      'Moved by hand', 'Resized by hand',
    ]);
  });

  it('marks an added item as added by hand, not as the scan\'s', () => {
    expect(marks({ suggested: false, added_by_hand: true, basis: 'Added by hand.' })).toEqual(['Added by hand']);
    expect(marks({ suggested: false, added_by_hand: true, basis: 'Added by hand. Resized by hand.' })).toEqual([
      'Added by hand', 'Resized by hand',
    ]);
  });

  it('still marks one moved before the marks were told apart', () => {
    expect(item('truss_lines', 2).marks).toEqual(['Moved by hand']);
  });
});

describe('readDraft: sizes, heights and headings', () => {
  it('has nothing to send for a row as it is stored', () => {
    for (const stored of [stage(), truss(), item('truss_lines', 2), ring()]) {
      expect(readDraft(stored, draftOf(stored))).toEqual({ changes: null, problem: null });
    }
  });

  it('sends only the size that changed', () => {
    expect(readDraft(stage(), { ...draftOf(stage()), width: '7.5' }).changes).toEqual({ width: 7.5 });
    expect(readDraft(stage(), { ...draftOf(stage()), depth: ' 2,5 ' }).changes).toEqual({ depth: 2.5 });
    expect(readDraft(stage(), { ...draftOf(stage()), height: '0.9' }).changes).toEqual({ height: 0.9 });
    expect(readDraft(ring(), { ...draftOf(ring()), radius: '2' }).changes).toEqual({ radius: 2 });
  });

  it('sends a line\'s length, heading and height', () => {
    expect(readDraft(truss(), { ...draftOf(truss()), length: '6', heading_deg: '90', height: '3,5' }).changes).toEqual({
      length: 6, heading_deg: 90, height: 3.5,
    });
    expect(readDraft(truss(), { ...draftOf(truss()), heading_deg: '-30' }).changes).toEqual({ heading_deg: -30 });
  });

  it('does not call the same size written another way a change', () => {
    expect(readDraft(stage(), { ...draftOf(stage()), width: '6.0', height: '0.60' }).changes).toBeNull();
    expect(readDraft(stage(), { ...draftOf(stage()), width: '6.0004' }).changes).toBeNull();
    // A heading is kept to a tenth of a degree.
    const angled = item('truss_lines', 2);
    expect(readDraft(angled, { ...draftOf(angled), heading_deg: '36.92' }).changes).toBeNull();
    expect(readDraft(angled, { ...draftOf(angled), heading_deg: '37' }).changes).toEqual({ heading_deg: 37 });
  });

  it('sends a name, a move and a size together, and only those', () => {
    expect(readDraft(stage(), { ...draftOf(stage()), name: 'Deck', x: '1', width: '8' }).changes).toEqual({
      name: 'Deck', center_x: 1, width: 8,
    });
  });

  it('keeps a size the row was never given', () => {
    // A draft from before the row had size fields: a name and a place only.
    expect(readDraft(stage(), { name: 'Stage', x: '0', z: '-3.5' })).toEqual({ changes: null, problem: null });
  });

  it('says which size is too small, too big or not a number', () => {
    const problem = (stored: ShellItem, typed: Record<string, string>) =>
      readDraft(stored, { ...draftOf(stored), ...typed });

    expect(problem(stage(), { width: '0.2' })).toEqual({ changes: null, problem: 'Width must be at least 0.3 m.' });
    expect(problem(stage(), { width: 'wide' }).problem).toBe('Width must be a number of metres, at least 0.3.');
    expect(problem(stage(), { depth: '' }).problem).toBe('Front to back must be a number of metres, at least 0.3.');
    expect(problem(stage(), { depth: '-3' }).problem).toBe('Front to back must be at least 0.3 m.');
    expect(problem(stage(), { height: '0.01' }).problem).toBe('Height must be at least 0.05 m.');
    expect(problem(stage(), { height: '3.5' }).problem).toBe('Height of a raised area can be at most 3 m.');
    expect(problem(stage(), { height: 'Infinity' }).problem).toMatch(/^Height must be a number/);
    expect(problem(truss(), { length: '0.4' }).problem).toBe('Length must be at least 0.5 m.');
    expect(problem(truss(), { height: '0.4' }).problem).toBe('Height must be at least 0.5 m.');
    // A truss can hang higher than a deck can stand: the room's ceiling is the server's to check.
    expect(problem(truss(), { height: '5.5' })).toEqual({ changes: { height: 5.5 }, problem: null });
    expect(problem(truss(), { heading_deg: '400' }).problem).toBe('Heading must be between -360 and 360 degrees.');
    expect(problem(truss(), { heading_deg: 'north' }).problem).toBe(
      'Heading must be a number of degrees, such as 45 or -30.',
    );
    expect(problem(ring(), { radius: '0.1' }).problem).toBe('Radius must be at least 0.3 m.');
  });

  it('names the name or the place first when they are wrong too', () => {
    expect(readDraft(stage(), { ...draftOf(stage()), name: ' ', width: '0' }).problem).toMatch(/^A name needs/);
    expect(readDraft(stage(), { ...draftOf(stage()), x: 'left', width: '0' }).problem).toMatch(/^Across must be/);
  });

  it('never sends a size for an item that has no number stored for it', () => {
    const broken = shell();
    (broken.risers![0] as unknown as Record<string, unknown>).width = null;
    const stored = item('risers', 0, broken);
    expect(readDraft(stored, { ...draftOf(stored), width: '5' })).toEqual({ changes: null, problem: null });
    expect(readDraft(stored, { ...draftOf(stored), width: 'wide', depth: '4' }).changes).toEqual({ depth: 4 });
  });

  it('checks a size the same way wherever it is typed', () => {
    expect(sizeProblem('risers', 'width', 0.3)).toBeNull();
    expect(sizeProblem('truss_lines', 'length', 0.5)).toBeNull();
    expect(sizeProblem('truss_rings', 'radius', 0.3)).toBeNull();
    expect(sizeProblem('truss_rings', 'height', 0.5)).toBeNull();
    expect(sizeProblem('risers', 'height', 3)).toBeNull();
    expect(sizeProblem('truss_lines', 'heading_deg', -360)).toBeNull();
    expect(sizeProblem('truss_lines', 'heading_deg', null)).toMatch(/^Heading must be a number of degrees/);
  });
});

describe('a quarter turn', () => {
  it('swaps a raised area\'s width and its front-to-back', () => {
    const turned = quarterTurned(stage(), draftOf(stage()));
    expect(turned).toMatchObject({ width: '3', depth: '6', name: 'Stage', x: '0', z: '-3.5', height: '0.6' });
    expect(readDraft(stage(), turned).changes).toEqual({ width: 3, depth: 6 });
  });

  it('turned twice is as it was', () => {
    const twice = quarterTurned(stage(), quarterTurned(stage(), draftOf(stage())));
    expect(readDraft(stage(), twice)).toEqual({ changes: null, problem: null });
  });

  it('turns what is typed, not what is stored', () => {
    const turned = quarterTurned(stage(), { ...draftOf(stage()), width: '8' });
    expect(turned).toMatchObject({ width: '3', depth: '8' });
  });

  it('turns a row that was never given its sizes', () => {
    expect(quarterTurned(stage(), { name: 'Stage', x: '0', z: '-3.5' })).toMatchObject({ width: '3', depth: '6' });
  });
});

describe('wording a resize', () => {
  it('says what size it now is, and that no fixture went with it', () => {
    const after = shell();
    after.risers![0].width = 8;
    expect(editResultText(stage(), { width: 8 }, after)).toBe(
      'Stage is now 8.0 m by 3.0 m, top 0.60 m above the floor. No fixture was moved with it.',
    );
  });

  it('says it of a ring and of a turned line', () => {
    const wider = shell();
    wider.truss_rings![0].radius = 2;
    expect(editResultText(ring(), { radius: 2 }, wider)).toBe(
      'Overhead ring 1 is now a ring 4.0 m across, underside 4.20 m up. No fixture was moved with it.',
    );
    const turned = shell();
    turned.truss_lines![0] = { ...turned.truss_lines![0], x1: 0, z1: -6, x2: 0, z2: 2 };
    expect(editResultText(truss(), { heading_deg: 90 }, turned)).toBe(
      'Overhead line 1 is now 8.0 m long, underside 4.20 m up, running upstage to downstage. '
      + 'No fixture was moved with it.',
    );
  });

  it('says so when the room brought its middle in to keep the whole of it inside', () => {
    const after = shell();
    after.risers![1] = { ...after.risers![1], width: 10, center_x: 3 };
    expect(editResultText(item('risers', 1), { width: 10 }, after)).toBe(
      'Booth or counter is now 10.0 m by 1.0 m, top 1.00 m above the floor. '
      + 'Its middle was brought in to 3, 3, to keep the whole of it inside the room and the 2 m round it. '
      + 'No fixture was moved with it.',
    );
  });

  it('says both for a move and a resize together, and no fixture once', () => {
    const after = shell();
    after.risers![0] = { ...after.risers![0], center_x: 1, width: 8 };
    expect(editResultText(stage(), { center_x: 1, width: 8 }, after)).toBe(
      'Stage was moved to 1, -3.5. Stage is now 8.0 m by 3.0 m, top 0.60 m above the floor. '
      + 'No fixture was moved with it.',
    );
  });
});

describe('adding an item by hand', () => {
  it('offers a stage, a riser, a booth, a truss line and a ring', () => {
    expect(NEW_ITEM_CHOICES.map((choice) => choice.what)).toEqual(['stage', 'riser', 'booth', 'truss_line', 'truss_ring']);
    expect(NEW_ITEM_CHOICES.map((choice) => newItemKind(choice.what))).toEqual([
      'risers', 'risers', 'risers', 'truss_lines', 'truss_rings',
    ]);
  });

  it('starts each kind in the middle of the floor at a usual size', () => {
    expect(newItemDraft('stage')).toEqual({
      what: 'stage', name: '', x: '0', z: '0', width: '4', depth: '3', length: '6', radius: '1.5', height: '0.6',
      heading_deg: '0',
    });
    expect(newItemDraft('riser')).toMatchObject({ width: '2', depth: '2', height: '0.3' });
    expect(newItemDraft('booth')).toMatchObject({ width: '2', depth: '1', height: '1' });
  });

  it('offers a truss a height the room has', () => {
    expect(newItemDraft('truss_line', shell()).height).toBe('4');
    expect(newItemDraft('truss_ring').height).toBe('4');
    expect(newItemDraft('truss_ring', null).height).toBe('4');
    // Half a metre under a low ceiling, and never under the least a truss can hang at.
    expect(newItemDraft('truss_line', { ...shell(), room: { width: 12, depth: 10, height: 3 } }).height).toBe('2.5');
    expect(newItemDraft('truss_line', { ...shell(), room: { width: 12, depth: 10, height: 0.8 } }).height).toBe('0.5');
  });

  it('sends a raised area with what it is, and only its own sizes', () => {
    expect(readNewItem(newItemDraft('stage'))).toEqual({
      kind: 'risers',
      body: { center_x: 0, center_z: 0, width: 4, depth: 3, height: 0.6, riser_kind: 'stage' },
      problem: null,
    });
    expect(readNewItem(newItemDraft('booth')).body?.riser_kind).toBe('booth');
    expect(readNewItem(newItemDraft('riser')).body?.riser_kind).toBe('riser');
  });

  it('sends a truss line and a ring with theirs', () => {
    expect(readNewItem(newItemDraft('truss_line'))).toEqual({
      kind: 'truss_lines',
      body: { center_x: 0, center_z: 0, length: 6, heading_deg: 0, height: 4 },
      problem: null,
    });
    expect(readNewItem(newItemDraft('truss_ring'))).toEqual({
      kind: 'truss_rings',
      body: { center_x: 0, center_z: 0, radius: 1.5, height: 4 },
      problem: null,
    });
  });

  it('sends a name only when one is typed, trimmed to one line', () => {
    expect(readNewItem({ ...newItemDraft('booth'), name: '  DJ   booth ' }).body?.name).toBe('DJ booth');
    expect('name' in (readNewItem({ ...newItemDraft('booth'), name: '   ' }).body ?? {})).toBe(false);
  });

  it('takes what is typed, with a comma for a decimal point', () => {
    const typed = { ...newItemDraft('truss_line'), x: '-1,5', z: '2', length: '7.5', heading_deg: '45', height: '3,8' };
    expect(readNewItem(typed).body).toEqual({ center_x: -1.5, center_z: 2, length: 7.5, heading_deg: 45, height: 3.8 });
  });

  it('says which field cannot be sent and sends nothing', () => {
    const problem = (typed: Record<string, string>, what: 'stage' | 'truss_line' | 'truss_ring' = 'stage') =>
      readNewItem({ ...newItemDraft(what), ...typed });

    expect(problem({ x: 'left' })).toEqual({
      kind: 'risers', body: null, problem: 'Across must be a number of metres, such as -1.5.',
    });
    expect(problem({ z: '' }).problem).toBe('Depth must be a number of metres, such as -1.5.');
    expect(problem({ width: '0.1' }).problem).toBe('Width must be at least 0.3 m.');
    expect(problem({ height: '4' }).problem).toBe('Height of a raised area can be at most 3 m.');
    expect(problem({ radius: '0.1' }, 'truss_ring').problem).toBe('Radius must be at least 0.3 m.');
    expect(problem({ length: 'long' }, 'truss_line').problem).toBe('Length must be a number of metres, at least 0.5.');
    expect(problem({ heading_deg: '720' }, 'truss_line').problem).toBe('Heading must be between -360 and 360 degrees.');
    const long = problem({ name: 'x'.repeat(SHELL_NAME_MAX + 1) });
    expect(long.body).toBeNull();
    expect(long.problem).toContain(`${SHELL_NAME_MAX} characters`);
  });

  it('does not read a size the kind does not have', () => {
    // A stage has no length or radius: rubbish left in those fields is not its problem.
    expect(readNewItem({ ...newItemDraft('stage'), length: 'long', radius: '' }).problem).toBeNull();
    expect(readNewItem({ ...newItemDraft('truss_ring'), width: 'wide' }).problem).toBeNull();
  });

  it('names the routes', () => {
    expect(roomShellListPath(7, 'truss_rings')).toBe('/rigs/7/room-shell/truss_rings');
    expect(roomShellUndoPath(7)).toBe('/rigs/7/room-shell/undo');
  });
});

describe('undo', () => {
  it('counts the edits that can be undone', () => {
    expect(shellUndoCount({ available: 3, label: 'Stage renamed' })).toBe(3);
    expect(shellUndoCount({ available: 0, label: null })).toBe(0);
    expect(shellUndoCount({ available: -1 })).toBe(0);
    expect(shellUndoCount(null)).toBe(0);
    expect(shellUndoCount(undefined)).toBe(0);
  });

  it('says what the next undo takes back, and how many there are after it', () => {
    expect(undoButtonText({ available: 1, label: 'Stage renamed' })).toBe('Undo: Stage renamed');
    expect(undoButtonText({ available: 3, label: 'Overhead line 1 deleted' })).toBe(
      'Undo: Overhead line 1 deleted (2 more)',
    );
    expect(undoButtonText({ available: 2, label: null })).toBe('Undo: the last room edit (1 more)');
  });

  it('says so when there is nothing to undo', () => {
    expect(undoButtonText(null)).toBe('Nothing to undo');
    expect(undoButtonText(undefined)).toBe('Nothing to undo');
    expect(undoButtonText({ available: 0, label: 'Stage renamed' })).toBe('Nothing to undo');
  });

  it('uses the server\'s words when a locate walkthrough is running', () => {
    const words = 'A locate walkthrough is running on this rig. Finish or end it, then edit the room.';
    expect(shellEditErrorText(409, words)).toBe(words);
    expect(shellEditErrorText(409, undefined)).toMatch(/cannot be changed just now/);
  });
});
