import { describe, expect, it } from 'vitest';
import {
  DRAG_START_PX,
  MAX_DRAG_REACH_M,
  SNAP_RADIUS_M,
  pointerTravelled,
  beginDrag,
  clampPosition,
  dragStep,
  hasMoved,
  isRealMove,
  nearestOnSegment,
  nudgePosition,
  positionLimits,
  positionText,
  rayHeight,
  rayOnHorizontalPlane,
  roundMm,
  settleDrag,
  snapLines,
  snapToLines,
  withFixturePosition,
  withSavedFixture,
} from '../components/rig/previs/fixtureDrag';
import type { Ray, SnapLine } from '../components/rig/previs/fixtureDrag';
import type { RigFixture, RoomShell } from '../types';

const down = (x: number, z: number, y = 10): Ray => ({ origin: { x, y, z }, direction: { x: 0, y: -1, z: 0 } });
/** A level ray along -X at height `y`, from stage left of everything. */
const level = (y: number, z = 0): Ray => ({ origin: { x: 13, y, z }, direction: { x: -1, y: 0, z: 0 } });

const shell = {
  source: 'scan',
  room: { width: 20, depth: 12, height: 7 },
  truss_lines: [{ x1: -3, z1: -2, x2: 3, z2: -2, height: 5, name: 'Back truss' }],
  risers: [{ center_x: 0, center_z: -3, width: 6, depth: 2, height: 1, name: 'Stage' }],
} as unknown as RoomShell;

const truss: SnapLine = { x1: -3, z1: -2, x2: 3, z2: -2, height: 5, kind: 'truss', name: 'Back truss' };
const lines = snapLines(shell);
const limits = { halfX: 7, halfZ: 6, top: 8 };

describe('rays', () => {
  it('finds where a ray meets the plane at a height', () => {
    expect(rayOnHorizontalPlane(down(2, -1), 4)).toEqual({ x: 2, z: -1 });
    const slanted = rayOnHorizontalPlane({ origin: { x: 0, y: 10, z: 0 }, direction: { x: 1, y: -1, z: 0 } }, 0);
    expect(slanted?.x).toBeCloseTo(10);
    expect(slanted?.z).toBeCloseTo(0);
  });

  it('gives nothing for a ray that never reaches the plane', () => {
    // Level with it, pointing away from it, and grazing off to the horizon.
    expect(rayOnHorizontalPlane(level(10), 4)).toBeNull();
    expect(rayOnHorizontalPlane({ origin: { x: 0, y: 10, z: 0 }, direction: { x: 0, y: 1, z: 0 } }, 4)).toBeNull();
    const grazing: Ray = { origin: { x: 0, y: 10, z: 0 }, direction: { x: 1, y: -0.01, z: 0 } };
    expect(10 / 0.01).toBeGreaterThan(MAX_DRAG_REACH_M);
    expect(rayOnHorizontalPlane(grazing, 0)).toBeNull();
  });

  it('reads a height off the vertical line through a fixture', () => {
    expect(rayHeight(level(5), { x: 0, z: 0 })).toBeCloseTo(5);
    // Looking straight down the line, or with the line behind the camera.
    expect(rayHeight(down(0, 0), { x: 0, z: 0 })).toBeNull();
    expect(rayHeight({ origin: { x: 13, y: 5, z: 0 }, direction: { x: 1, y: 0, z: 0 } }, { x: 0, z: 0 })).toBeNull();
  });
});

describe('a drag, step by step', () => {
  it('takes the grip on the first move, so a fixture picked up off-centre does not jump', () => {
    const start = beginDrag({ x: 1, y: 4, z: 2 });
    const gripped = dragStep(start, down(1.3, 2.2), false);
    expect(gripped).toMatchObject({ x: 1, y: 4, z: 2, mode: 'plan' });
    const moved = dragStep(gripped, down(3.3, 2.2), false);
    expect(moved.x).toBeCloseTo(3);
    expect(moved.z).toBeCloseTo(2);
    expect(moved.y).toBe(4);
  });

  it('moves straight up and down with the height modifier, keeping its place on the plan', () => {
    const onPlan = dragStep(dragStep(beginDrag({ x: 0, y: 4, z: 0 }), down(0, 0), false), down(0, 0), false);
    const gripped = dragStep(onPlan, level(6), true);
    expect(gripped).toMatchObject({ x: 0, y: 4, z: 0, mode: 'height' });
    const raised = dragStep(gripped, level(7), true);
    expect(raised.y).toBeCloseTo(5);
    expect(raised.x).toBe(0);
    expect(raised.z).toBe(0);
    // Letting go of the modifier takes a fresh grip on the plan at the new height.
    const back = dragStep(raised, down(0.4, 0), false);
    expect(back).toMatchObject({ x: 0, z: 0, mode: 'plan' });
    expect(back.y).toBeCloseTo(5);
  });

  it('stays where it is when the ray misses', () => {
    const state = dragStep(beginDrag({ x: 1, y: 4, z: 2 }), down(1, 2), false);
    expect(dragStep(state, level(10), false)).toBe(state);
    expect(dragStep(state, down(1, 2), true)).toBe(state);
  });
});

describe('snapping to what a room scan found', () => {
  it('offers the truss lines and the four edges of each raised area of a scanned room only', () => {
    expect(lines).toHaveLength(5);
    expect(lines[0]).toEqual(truss);
    const downstage = lines.find((line) => line.name === 'Stage, downstage edge');
    expect(downstage).toMatchObject({ x1: -3, x2: 3, z1: -2, z2: -2, height: 1, kind: 'edge' });
    expect(snapLines(null)).toEqual([]);
    expect(snapLines({ ...shell, source: 'template' } as unknown as RoomShell)).toEqual([]);
  });

  it('skips a line with a number missing', () => {
    const broken = { source: 'scan', truss_lines: [{ x1: 0, z1: 0, x2: NaN, z2: 0, height: 5 }] } as unknown as RoomShell;
    expect(snapLines(broken)).toEqual([]);
  });

  it('finds the nearest point on a line that ends at its ends', () => {
    expect(nearestOnSegment(1, -1.8, truss)).toMatchObject({ x: 1, z: -2 });
    expect(nearestOnSegment(1, -1.8, truss).distance).toBeCloseTo(0.2);
    expect(nearestOnSegment(9, -2, truss)).toMatchObject({ x: 3, z: -2, distance: 6 });
    expect(nearestOnSegment(1, 1, { x1: 0, z1: 0, x2: 0, z2: 0 })).toMatchObject({ x: 0, z: 0 });
  });

  it('puts a fixture near a truss onto it, at the height it hangs at', () => {
    const snapped = snapToLines({ x: 1, y: 4.8, z: -1.8 }, lines);
    expect(snapped).toMatchObject({ x: 1, y: 5, z: -2 });
    expect(snapped.snappedTo?.name).toBe('Back truss');
  });

  it('puts a fixture near a stage edge onto it and keeps its own height', () => {
    const snapped = snapToLines({ x: 1, y: 1.2, z: -1.8 }, lines);
    expect(snapped).toMatchObject({ x: 1, y: 1.2, z: -2 });
    expect(snapped.snappedTo?.name).toBe('Stage, downstage edge');
  });

  it('leaves a fixture alone outside the radius or the height window', () => {
    const far = { x: 1, y: 4.8, z: -2 + SNAP_RADIUS_M + 0.1 };
    expect(snapToLines(far, lines)).toEqual({ ...far, snappedTo: null });
    // Between the truss (5 m) and the stage top (1 m), in reach of neither.
    const between = { x: 1, y: 3, z: -2 };
    expect(snapToLines(between, lines).snappedTo).toBeNull();
    expect(snapToLines(far, [])).toEqual({ ...far, snappedTo: null });
  });

  it('prefers the nearer line, and a truss over an edge at the same distance', () => {
    const edge: SnapLine = { ...truss, kind: 'edge', name: 'Edge' };
    const at = { x: 0, y: 5, z: -1.9 };
    expect(snapToLines(at, [edge, truss]).snappedTo?.kind).toBe('truss');
    expect(snapToLines(at, [truss, edge]).snappedTo?.kind).toBe('truss');
    const nearerEdge: SnapLine = { ...edge, z1: -1.85, z2: -1.85 };
    expect(snapToLines(at, [truss, nearerEdge]).snappedTo?.name).toBe('Edge');
  });
});

describe('limits', () => {
  it('allows the larger of the stage and the scanned room, and a margin', () => {
    const stage = { stage_width: 10, stage_depth: 8, stage_height: 6, room_shell: null };
    expect(positionLimits(stage)).toEqual({ halfX: 7, halfZ: 6, top: 8 });
    expect(positionLimits({ ...stage, room_shell: shell })).toEqual({ halfX: 12, halfZ: 8, top: 9 });
    expect(positionLimits({ ...stage, stage_width: 0, stage_depth: NaN })).toEqual({ halfX: 7, halfZ: 6, top: 8 });
  });

  it('holds a position inside them and above the floor', () => {
    expect(clampPosition({ x: 100, y: -1, z: -100 }, limits)).toEqual({ x: 7, y: 0, z: -6 });
    expect(clampPosition({ x: 1, y: 99, z: 2 }, limits)).toEqual({ x: 1, y: 8, z: 2 });
  });
});

describe('where a drag puts the fixture', () => {
  const dragged = (x: number, y: number, z: number, mode: 'plan' | 'height') => ({
    ...beginDrag({ x, y, z }), mode,
  });

  it('takes the drawn lift off again, snaps along the plan, and rounds to the millimetre', () => {
    const settled = settleDrag(dragged(1.00049, 5.3, -1.8, 'plan'), 0.5, limits, lines);
    expect(settled).toMatchObject({ x: 1, y: 5, z: -2 });
    expect(settled.snappedTo?.name).toBe('Back truss');
    expect(roundMm(1.23456)).toBe(1.235);
  });

  it('does not snap with snapping off, or while the height is being changed', () => {
    expect(settleDrag(dragged(1, 5.3, -1.8, 'plan'), 0.5, limits, null)).toEqual({
      x: 1, y: 4.8, z: -1.8, snappedTo: null,
    });
    expect(settleDrag(dragged(1, 5.3, -1.8, 'height'), 0.5, limits, lines)).toEqual({
      x: 1, y: 4.8, z: -1.8, snappedTo: null,
    });
  });

  it('holds the result inside the limits', () => {
    expect(settleDrag(dragged(50, 20, 0, 'plan'), 0, limits, null)).toMatchObject({ x: 7, y: 8, z: 0 });
  });

  it('tells a click from a move', () => {
    expect(hasMoved({ x: 0, y: 0, z: 0 }, { x: 0.01, y: 0, z: 0 })).toBe(false);
    expect(hasMoved({ x: 0, y: 0, z: 0 }, { x: 0.02, y: 0, z: 0 })).toBe(true);
  });

  it('calls a press a drag only once the pointer has travelled on screen', () => {
    const down = { x: 400, y: 300 };
    expect(DRAG_START_PX).toBe(5);
    expect(pointerTravelled(down, { x: 400, y: 300 })).toBe(false);
    // Two pixels of wobble: centimetres on the floor from across the room, still a click.
    expect(pointerTravelled(down, { x: 402, y: 299 })).toBe(false);
    expect(pointerTravelled(down, { x: 403, y: 304 })).toBe(true);
    expect(pointerTravelled(down, { x: 400, y: 290 })).toBe(true);
    expect(pointerTravelled(down, { x: 402, y: 299 }, 2)).toBe(true);
  });

  it('does not let a click next to a truss line snap, move and confirm the fixture', () => {
    // Stored 0.2 m off the truss; pressed and released with a millimetre of wobble.
    const stored = { x: 1, y: 4.8, z: -1.8 };
    const wobble = dragged(1.001, 4.8, -1.8, 'plan');
    const settled = settleDrag(wobble, 0, limits, lines);
    expect(hasMoved(settled, stored)).toBe(true); // the snap alone looks like a move
    expect(isRealMove(wobble, stored, settled, stored)).toBe(false);
    // Carried a real distance, it is one.
    const carried = dragged(1.3, 4.8, -1.8, 'plan');
    expect(isRealMove(carried, stored, settleDrag(carried, 0, limits, lines), stored)).toBe(true);
    // Carried out against the limit it already stands on, nothing changes.
    const atEdge = { x: 7, y: 4, z: 0 };
    const pushed = dragged(9, 4, 0, 'plan');
    expect(isRealMove(pushed, atEdge, settleDrag(pushed, 0, limits, null), atEdge)).toBe(false);
  });
});

describe('keyboard nudges', () => {
  const at = { x: 0, y: 4, z: 0 };

  it('moves a step on the plan or in height, a metre with the big step', () => {
    expect(nudgePosition(at, 'ArrowLeft', false, limits)).toEqual({ x: -0.1, y: 4, z: 0 });
    expect(nudgePosition(at, 'ArrowRight', true, limits)).toEqual({ x: 1, y: 4, z: 0 });
    expect(nudgePosition(at, 'ArrowUp', false, limits)).toEqual({ x: 0, y: 4, z: -0.1 });
    expect(nudgePosition(at, 'ArrowDown', false, limits)).toEqual({ x: 0, y: 4, z: 0.1 });
    expect(nudgePosition(at, 'PageUp', false, limits)).toEqual({ x: 0, y: 4.1, z: 0 });
    expect(nudgePosition(at, 'PageDown', true, limits)).toEqual({ x: 0, y: 3, z: 0 });
  });

  it('ignores other keys and stops at the limits', () => {
    expect(nudgePosition(at, 'a', false, limits)).toBeNull();
    expect(nudgePosition({ x: 7, y: 0, z: 0 }, 'ArrowRight', true, limits)).toEqual({ x: 7, y: 0, z: 0 });
    expect(nudgePosition({ x: 7, y: 0, z: 0 }, 'PageDown', false, limits)).toEqual({ x: 7, y: 0, z: 0 });
  });
});

describe('the rig with one fixture moved', () => {
  const fixture = (id: number, tags: string[]) => ({
    id, name: `F${id}`, position_x: 0, position_y: 4, position_z: 0, tags,
  }) as unknown as RigFixture;
  const rig = { name: 'Rig', fixtures: [fixture(1, ['position_unconfirmed']), fixture(2, [])] };

  it('moves only that fixture, and is the same rig when the fixture is not in it', () => {
    const moved = withFixturePosition(rig, 1, { x: 2, y: 5, z: -1 });
    expect(moved.fixtures[0]).toMatchObject({ position_x: 2, position_y: 5, position_z: -1 });
    expect(moved.fixtures[0].tags).toEqual(['position_unconfirmed']);
    expect(moved.fixtures[1]).toBe(rig.fixtures[1]);
    expect(withFixturePosition(rig, 99, { x: 2, y: 5, z: -1 })).toBe(rig);
  });

  it('takes the position and the tags the server stored, so the fixture stops being a guess', () => {
    const saved = withSavedFixture(rig, { id: 1, position_x: 2, position_y: 5, position_z: -1, tags: [] });
    expect(saved.fixtures[0]).toMatchObject({ name: 'F1', position_x: 2, position_y: 5, position_z: -1, tags: [] });
    expect(withSavedFixture(rig, { id: 99, position_x: 0, position_y: 0, position_z: 0, tags: [] })).toBe(rig);
  });

  it('writes a position out, and what it snapped to', () => {
    expect(positionText({ x: -3, y: 4.5, z: 0.5 })).toBe('x -3.00, height 4.50, z 0.50 m');
    expect(positionText({ x: -3, y: 5, z: -2 }, truss)).toBe('x -3.00, height 5.00, z -2.00 m - on Back truss');
  });
});
