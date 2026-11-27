// Heights by dragging (slice 22), the numbers: what the height strip shows
// for a raised area, a truss line and a ring, how far each handle may go,
// and what a drag of one sends. docs/ROOM_SCAN.md.
import { describe, expect, it } from 'vitest';
import {
  HEIGHT_SHIFT_SNAP_M, HEIGHT_SNAP_M, dragHeight, heightGauge, heightGripHint, heightGripLabel,
} from '../components/rig/roomItemHeight';
import type { HeightGauge } from '../components/rig/roomItemHeight';
import { shellItems, withCarry } from '../utils/roomShellEdit';
import type { RoomShell } from '../types';

/**
 * A scanned room 12 m by 10 m and 6 m high: a stage on the floor, a balcony
 * floating 2.7 m up, 8 m of truss at 4.2 m and a ring at 5 m.
 */
const SHELL = (room: Record<string, number> = { width: 12, depth: 10, height: 6 }): RoomShell => ({
  source: 'scan',
  room,
  risers: [
    { center_x: 0, center_z: -3.5, width: 6, depth: 3, height: 0.6, name: 'Stage', kind: 'stage' },
    { center_x: 0, center_z: 4, width: 4, depth: 2, height: 0.3, base_height: 2.7, name: 'Balcony', kind: 'riser' },
  ],
  truss_lines: [{ name: 'Truss 1', x1: -4, z1: 1, x2: 4, z2: 1, height: 4.2, across: 0.3 }],
  truss_rings: [{ name: 'Ring 1', center_x: 0, center_z: 0, radius: 2, height: 5, across: 0.3 }],
}) as unknown as RoomShell;

const gaugeOf = (key: string, shell: RoomShell = SHELL()): HeightGauge => {
  const [kind, index] = key.split(':');
  const item = shellItems(shell).find((entry) => entry.kind === kind && entry.index === Number(index));
  return heightGauge(item, shell)!;
};

describe('heightGauge', () => {
  it('gives a raised area on the floor a top and a base, each held to what the server takes', () => {
    const gauge = gaugeOf('risers:0');
    expect(gauge).toMatchObject({
      key: 'risers:0', kind: 'risers', index: 0, title: 'Stage', ceiling: 6, scaleTop: 6, base: 0, top: 0.6,
    });
    expect(gauge.handles).toEqual([
      // The deck is 0.05 to 3 m above its base.
      { grip: 'top', value: 0.6, least: 0.05, most: 3 },
      // The base goes up until the top is at the ceiling.
      { grip: 'base', value: 0, least: 0, most: 5.4 },
    ]);
  });

  it('stands a floating platform\'s handles at its base and at its base and deck together', () => {
    const gauge = gaugeOf('risers:1');
    expect(gauge).toMatchObject({ title: 'Balcony', base: 2.7, top: 3 });
    expect(gauge.handles).toEqual([
      { grip: 'top', value: 3, least: 2.75, most: 5.7 },
      { grip: 'base', value: 2.7, least: 0, most: 5.7 },
    ]);
  });

  it('holds a deck under a low ceiling, not only under 3 m', () => {
    const gauge = gaugeOf('risers:1', SHELL({ width: 12, depth: 10, height: 4 }));
    expect(gauge.handles[0]).toEqual({ grip: 'top', value: 3, least: 2.75, most: 4 });
    expect(gauge.handles[1].most).toBe(3.7);
  });

  it('gives a truss line and a ring one trim handle, from 0.5 m to the ceiling', () => {
    expect(gaugeOf('truss_lines:0')).toMatchObject({ kind: 'truss_lines', title: 'Truss 1', base: null, top: 4.2 });
    expect(gaugeOf('truss_lines:0').handles).toEqual([{ grip: 'trim', value: 4.2, least: 0.5, most: 6 }]);
    expect(gaugeOf('truss_rings:0').handles).toEqual([{ grip: 'trim', value: 5, least: 0.5, most: 6 }]);
  });

  it('shows a room with no ceiling stored up to a metre over the item, and lets a truss go to 30 m', () => {
    const open = SHELL({ width: 12, depth: 10 });
    const truss = gaugeOf('truss_lines:0', open);
    expect(truss.ceiling).toBeNull();
    expect(truss.scaleTop).toBe(6);
    expect(truss.handles[0].most).toBe(30);
    const stage = gaugeOf('risers:0', open);
    expect(stage.scaleTop).toBe(3);
    expect(stage.handles).toEqual([
      { grip: 'top', value: 0.6, least: 0.05, most: 3 },
      { grip: 'base', value: 0, least: 0, most: 10 },
    ]);
  });

  it('is nothing for no item, and for one that stores no height', () => {
    expect(heightGauge(null, SHELL())).toBeNull();
    expect(heightGauge(undefined, SHELL())).toBeNull();
    const shell = SHELL();
    delete (shell.truss_lines![0] as unknown as Record<string, unknown>).height;
    const item = shellItems(shell).find((entry) => entry.kind === 'truss_lines');
    expect(item).toBeTruthy();
    expect(heightGauge(item, shell)).toBeNull();
  });
});

describe('dragHeight', () => {
  it('goes to 0.05 m, and to 0.25 m when coarse', () => {
    expect(HEIGHT_SNAP_M).toBe(0.05);
    expect(HEIGHT_SHIFT_SNAP_M).toBe(0.25);
    const truss = gaugeOf('truss_lines:0');
    expect(dragHeight(truss, 'trim', 4.53)).toEqual({
      value: 4.55, base: null, top: 4.55, changes: { height: 4.55 }, readout: 'trim 4.55 m',
    });
    expect(dragHeight(truss, 'trim', 4.53, true)).toEqual({
      value: 4.5, base: null, top: 4.5, changes: { height: 4.5 }, readout: 'trim 4.50 m',
    });
  });

  it('sends a number to the millimetre, with no rounding dust', () => {
    // Three steps of 0.05 are 0.15000000000000002 before they are rounded.
    expect(dragHeight(gaugeOf('risers:0'), 'top', 0.16).changes).toEqual({ height: 0.15 });
  });

  it('sends nothing for a handle let go where it stood', () => {
    expect(dragHeight(gaugeOf('truss_lines:0'), 'trim', 4.21).changes).toBeNull();
    expect(dragHeight(gaugeOf('risers:0'), 'top', 0.61).changes).toBeNull();
    // Pushed at the floor it already stands on.
    expect(dragHeight(gaugeOf('risers:0'), 'base', -3).changes).toBeNull();
  });

  it('holds a truss between 0.5 m and the ceiling', () => {
    const truss = gaugeOf('truss_lines:0');
    expect(dragHeight(truss, 'trim', 40).changes).toEqual({ height: 6 });
    expect(dragHeight(truss, 'trim', 0).changes).toEqual({ height: 0.5 });
  });

  it('reaches a ceiling that is not on the step', () => {
    const truss = gaugeOf('truss_lines:0', SHELL({ width: 12, depth: 10, height: 5.37 }));
    expect(dragHeight(truss, 'trim', 9).changes).toEqual({ height: 5.37 });
  });

  it('sets a raised area\'s deck above its base from its top, and leaves the base alone', () => {
    const stage = gaugeOf('risers:0');
    expect(dragHeight(stage, 'top', 0.93)).toEqual({
      value: 0.95, base: 0, top: 0.95, changes: { height: 0.95 }, readout: 'top 0.95 m',
    });
    expect(dragHeight(stage, 'top', 0.93, true).changes).toEqual({ height: 1 });
    // Never over 3 m of deck, never under 0.05 m.
    expect(dragHeight(stage, 'top', 9).changes).toEqual({ height: 3 });
    expect(dragHeight(stage, 'top', -1).changes).toEqual({ height: 0.05 });
    // A floating one: the top is above the floor, and what is sent is above its base.
    const balcony = gaugeOf('risers:1');
    expect(dragHeight(balcony, 'top', 3.5)).toEqual({
      value: 3.5, base: 2.7, top: 3.5, changes: { height: 0.8 }, readout: 'top 3.50 m',
    });
    expect(dragHeight(balcony, 'top', 1).changes).toEqual({ height: 0.05 });
  });

  it('raises and lowers the whole of a raised area from its base, as thick as it was', () => {
    const stage = gaugeOf('risers:0');
    expect(dragHeight(stage, 'base', 2.69)).toEqual({
      value: 2.7, base: 2.7, top: 3.3, changes: { base_height: 2.7 }, readout: 'base 2.70 m',
    });
    // No higher than leaves its top under the ceiling.
    expect(dragHeight(stage, 'base', 99).changes).toEqual({ base_height: 5.4 });
    // A floating one brought down stands on the floor.
    expect(dragHeight(gaugeOf('risers:1'), 'base', 0.01)).toEqual({
      value: 0, base: 0, top: 0.3, changes: { base_height: 0 }, readout: 'on the floor',
    });
  });

  it('changes nothing for a grip the item does not have, or a height that is not a number', () => {
    expect(dragHeight(gaugeOf('risers:0'), 'trim', 2).changes).toBeNull();
    expect(dragHeight(gaugeOf('truss_lines:0'), 'top', 2).changes).toBeNull();
    expect(dragHeight(gaugeOf('truss_lines:0'), 'trim', Number.NaN).changes).toBeNull();
  });

  it('sends what the carry box goes with: a height and a base height can each move a fixture', () => {
    expect(withCarry({ kind: 'truss_lines' }, { height: 4.5 }, true)).toEqual({ height: 4.5, carry_fixtures: true });
    expect(withCarry({ kind: 'risers' }, { base_height: 2.7 }, false)).toEqual({ base_height: 2.7, carry_fixtures: false });
  });
});

describe('the words on a height handle', () => {
  it('names each handle and says what a drag of it does', () => {
    expect(heightGripLabel('top')).toBe('Top');
    expect(heightGripLabel('base')).toBe('Base');
    expect(heightGripLabel('trim')).toBe('Trim');
    expect(heightGripHint('top', 'Stage')).toBe('Stage: drag to raise or lower its top (hold Shift for steps of 0.25 m)');
    expect(heightGripHint('base', 'Stage')).toContain('0 stands on the floor, more floats');
    expect(heightGripHint('trim', 'Truss 1')).toBe(
      'Truss 1: drag to raise or lower its trim height (hold Shift for steps of 0.25 m)',
    );
  });
});
