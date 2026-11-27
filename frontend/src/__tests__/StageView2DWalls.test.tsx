// The 2D layout view in Edit Room's walls mode: a numbered handle on each
// corner of the scanned room's walls, a drag that is one call when it ends
// and none under 5 pixels, the walls drawn where the drag has them, and
// fixtures that take no press meanwhile. docs/ROOM_SCAN.md.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import StageView2D from '../components/rig/StageView2D';
import type { RigFixture, RoomShell } from '../types';

const spot = (id: number, x: number, z: number, y = 4) => ({
  id,
  name: `Spot ${id}`,
  dmx_address: id,
  position_x: x,
  position_y: y,
  position_z: z,
  rotation_y: 0,
}) as unknown as RigFixture;

// 20 m by 16 m round a 10 m by 8 m stage.
const SCANNED: RoomShell = { source: 'scan', suggested: true, room: { width: 20, depth: 16, height: 6 } };
// The same room as an L: x > 4 with z > 2 is walled off.
const L_SHAPED: RoomShell = {
  ...SCANNED,
  room: {
    width: 20, depth: 16, height: 6,
    outline: [
      { x: -10, z: -8 }, { x: 10, z: -8 }, { x: 10, z: 2 }, { x: 4, z: 2 }, { x: 4, z: 8 }, { x: -10, z: 8 },
    ],
  },
};

type Props = Parameters<typeof StageView2D>[0];

/** The plan drawn at 10 pixels to the metre, so a pointer position is easy to read. */
function plan(roomShell: RoomShell | null, extra: Partial<Props> = {}) {
  const props = { width: 10, depth: 8, height: 5, fixtures: [spot(1, 0, 0)], selectedIds: new Set<number>(), ...extra };
  const { container } = render(<StageView2D {...props} roomShell={roomShell} />);
  const svg = container.querySelector('svg')!;
  const [, , w, h] = svg.getAttribute('viewBox')!.split(' ').map(Number);
  svg.getBoundingClientRect = () => ({
    left: 0, top: 0, right: w * 10, bottom: h * 10, width: w * 10, height: h * 10, x: 0, y: 0, toJSON: () => ({}),
  });
  return svg;
}

// With the 20 m by 16 m room the view is 22 m by 18 m from (-5, -4): stage
// (x, z) is at ((x + 11) * 10, (z + 9) * 10) on screen.
const inRoom = (x: number, z: number) => ({ clientX: (x + 11) * 10, clientY: (z + 9) * 10 });
const handle = (index: number) => screen.getByTestId(`wall-corner-${index}`);
const handles = () => screen.queryAllByTestId(/^wall-corner-\d+$/);
const wallsDrawn = () => screen.getByTestId('room-plan-walls').getAttribute('points');
const flush = () => act(async () => {});

// The box's walls as the plan draws them: a corner at (x, z) is at (x + 6, z + 5) in the SVG.
const BOX_DRAWN = '-4,-3 16,-3 16,13 -4,13';

describe('StageView2D: dragging the corners of the walls', () => {
  afterEach(cleanup);

  it('has no handles unless walls mode is on', () => {
    plan(SCANNED);
    expect(handles()).toHaveLength(0);
    expect(screen.queryByTestId('wall-corners')).toBeNull();
  });

  it('puts a numbered handle on each corner of a box room and of an outlined one', () => {
    plan(SCANNED, { wallsEdit: true });
    expect(handles()).toHaveLength(4);
    // Corner 1 is upstage stage right, and the rest go clockwise seen from above.
    expect(handle(0).getAttribute('transform')).toBe('translate(-4, -3)');
    expect(handle(2).getAttribute('transform')).toBe('translate(16, 13)');
    expect(handle(2).querySelector('text')!.textContent).toBe('3');
    cleanup();

    plan(L_SHAPED, { wallsEdit: true });
    expect(handles()).toHaveLength(6);
    expect(handle(3).getAttribute('transform')).toBe('translate(10, 7)');
  });

  it('has none with no scanned room, or on a plan that cannot be edited', () => {
    plan(null, { wallsEdit: true });
    expect(handles()).toHaveLength(0);
    cleanup();
    plan(SCANNED, { wallsEdit: true, readonly: true });
    expect(handles()).toHaveLength(0);
  });

  it('moves nothing on a click, or on a press that wobbles under 5 pixels', () => {
    const onWallCornerMove = vi.fn();
    const svg = plan(SCANNED, { wallsEdit: true, snapMode: 'none', onWallCornerMove });
    // A plain click.
    fireEvent.mouseDown(handle(2), inRoom(10, 8));
    fireEvent.mouseUp(svg, inRoom(10, 8));
    // 4 pixels across, then 3 across and 3 down (4.24 pixels), then back.
    fireEvent.mouseDown(handle(2), inRoom(10, 8));
    fireEvent.mouseMove(svg, { clientX: 214, clientY: 170 });
    fireEvent.mouseMove(svg, { clientX: 213, clientY: 173 });
    fireEvent.mouseUp(svg, { clientX: 213, clientY: 173 });
    expect(onWallCornerMove).not.toHaveBeenCalled();
    expect(wallsDrawn()).toBe(BOX_DRAWN);
    expect(screen.queryByTestId('wall-corner-readout')).toBeNull();
  });

  it('is one call for a whole drag, made when it is let go', async () => {
    const onWallCornerMove = vi.fn();
    const svg = plan(SCANNED, { wallsEdit: true, snapMode: 'none', onWallCornerMove });
    fireEvent.mouseDown(handle(2), inRoom(10, 8));
    fireEvent.mouseMove(svg, inRoom(11, 8));
    fireEvent.mouseMove(svg, inRoom(11.5, 8.5));
    fireEvent.mouseMove(svg, inRoom(12, 8));
    // Nothing is sent while it is being carried; the walls are drawn where the drag has them.
    expect(onWallCornerMove).not.toHaveBeenCalled();
    expect(wallsDrawn()).toBe('-4,-3 16,-3 18,13 -4,13');
    expect(screen.getByTestId('room-plan-floor').getAttribute('points')).toBe('-4,-3 16,-3 18,13 -4,13');
    expect(screen.getByTestId('wall-corner-readout').textContent).toBe('12.00, 8.00');

    fireEvent.mouseUp(svg, inRoom(12, 8));

    expect(onWallCornerMove).toHaveBeenCalledTimes(1);
    const [index, x, z] = onWallCornerMove.mock.calls[0];
    expect(index).toBe(2);
    expect(x).toBeCloseTo(12);
    expect(z).toBeCloseTo(8);
    await flush();
  });

  it('goes to the grid, and Alt or the snap set to none lets go of it', () => {
    const onWallCornerMove = vi.fn();
    const svg = plan(SCANNED, { wallsEdit: true, gridSize: 0.5, onWallCornerMove });
    fireEvent.mouseDown(handle(2), inRoom(10, 8));
    fireEvent.mouseMove(svg, inRoom(12.3, 8.2));
    fireEvent.mouseUp(svg, inRoom(12.3, 8.2));
    expect(onWallCornerMove.mock.calls[0][1]).toBeCloseTo(12.5);
    expect(onWallCornerMove.mock.calls[0][2]).toBeCloseTo(8);

    fireEvent.mouseDown(handle(2), inRoom(10, 8));
    fireEvent.mouseMove(svg, { ...inRoom(12.3, 8.2), altKey: true });
    fireEvent.mouseUp(svg, inRoom(12.3, 8.2));
    expect(onWallCornerMove.mock.calls[1][1]).toBeCloseTo(12.3);
    expect(onWallCornerMove.mock.calls[1][2]).toBeCloseTo(8.2);
  });

  it('keeps the corner where it was dropped until the move is answered, then draws the room it has', async () => {
    let answered: () => void = () => {};
    const onWallCornerMove = vi.fn(() => new Promise<void>((resolve) => { answered = resolve; }));
    const svg = plan(SCANNED, { wallsEdit: true, snapMode: 'none', onWallCornerMove });
    fireEvent.mouseDown(handle(1), inRoom(10, -8));
    fireEvent.mouseMove(svg, inRoom(12, -8));
    fireEvent.mouseUp(svg, inRoom(12, -8));
    await flush();
    expect(wallsDrawn()).toBe('-4,-3 18,-3 16,13 -4,13');

    // Refused: the room given is the one it had, and the wall goes back.
    await act(async () => { answered(); });
    await flush();
    expect(wallsDrawn()).toBe(BOX_DRAWN);
    expect(handle(1).getAttribute('transform')).toBe('translate(16, -3)');
  });

  it('carries a corner dragged off the plan to where the drag had it', () => {
    const onWallCornerMove = vi.fn();
    const svg = plan(SCANNED, { wallsEdit: true, snapMode: 'none', onWallCornerMove });
    fireEvent.mouseDown(handle(0), inRoom(-10, -8));
    fireEvent.mouseMove(svg, inRoom(-10.5, -8.5));
    fireEvent.mouseLeave(svg);
    expect(onWallCornerMove).toHaveBeenCalledTimes(1);
    expect(onWallCornerMove.mock.calls[0][0]).toBe(0);
    expect(onWallCornerMove.mock.calls[0][1]).toBeCloseTo(-10.5);
  });

  it('lets no fixture be picked up, selected or boxed while the walls are being dragged', () => {
    const onFixtureDrag = vi.fn();
    const onFixtureDragStart = vi.fn();
    const onFixtureClick = vi.fn();
    const onSelectFixtures = vi.fn();
    const svg = plan(SCANNED, {
      wallsEdit: true, snapMode: 'none', onFixtureDrag, onFixtureDragStart, onFixtureClick, onSelectFixtures,
    });
    const fixture = screen.getByText('Spot 1').parentElement!;
    fireEvent.mouseDown(fixture, inRoom(0, 0));
    fireEvent.mouseMove(svg, inRoom(2, 2));
    fireEvent.mouseUp(svg, inRoom(2, 2));
    expect(onFixtureDrag).not.toHaveBeenCalled();
    expect(onFixtureDragStart).not.toHaveBeenCalled();
    expect(onFixtureClick).not.toHaveBeenCalled();
    expect(onSelectFixtures).not.toHaveBeenCalled();
    expect(screen.queryByTestId('selection-box')).toBeNull();
  });

  it('drags a fixture as ever once walls mode is off', () => {
    const onFixtureDrag = vi.fn();
    const svg = plan(SCANNED, { snapMode: 'none', onFixtureDrag });
    fireEvent.mouseDown(screen.getByText('Spot 1').parentElement!, inRoom(0, 0));
    fireEvent.mouseMove(svg, inRoom(1, 0));
    expect(onFixtureDrag).toHaveBeenCalledTimes(1);
  });
});
