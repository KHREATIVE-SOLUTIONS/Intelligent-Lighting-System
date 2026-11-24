// The 2D layout view while a scanned room's items are arranged on it: each
// raised area, truss line and ring can be pressed and dragged, a drag is one
// call when it ends and none under 5 pixels, the selected item has handles
// and answers the arrow keys, and fixtures take no press meanwhile.
// docs/ROOM_SCAN.md.
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

// 20 m by 16 m round a 10 m by 8 m stage, with a stage, a truss and a ring in it.
const ROOM: RoomShell = {
  source: 'scan',
  suggested: true,
  room: { width: 20, depth: 16, height: 6 },
  risers: [
    // Not drawn, but it has a place in the list: the stage is the second raised area.
    { center_x: 0, center_z: 0, name: 'Ghost' } as never,
    { center_x: 0, center_z: -5, width: 6, depth: 3, height: 0.6, name: 'Stage', kind: 'stage' },
  ],
  truss_lines: [{ name: 'Truss 1', x1: -4, z1: 2, x2: 4, z2: 2, height: 4.2 }],
  truss_rings: [{ name: 'Ring 1', center_x: 6, center_z: -4, radius: 1.5, height: 4 }],
};

type Props = Parameters<typeof StageView2D>[0];

/** The plan drawn at 10 pixels to the metre, so a pointer position is easy to read. */
function plan(extra: Partial<Props> = {}, roomShell: RoomShell | null = ROOM) {
  const props = { width: 10, depth: 8, height: 5, fixtures: [spot(1, 0, 2)], selectedIds: new Set<number>(), ...extra };
  const { container } = render(<StageView2D {...props} roomShell={roomShell} />);
  const svg = container.querySelector('svg')!;
  const [, , w, h] = svg.getAttribute('viewBox')!.split(' ').map(Number);
  svg.getBoundingClientRect = () => ({
    left: 0, top: 0, right: w * 10, bottom: h * 10, width: w * 10, height: h * 10, x: 0, y: 0, toJSON: () => ({}),
  });
  return svg;
}

// The view is 22 m by 18 m from (-5, -4): stage (x, z) is at ((x + 11) * 10,
// (z + 9) * 10) on screen, and is drawn at (x + 6, z + 5) in the SVG.
const inRoom = (x: number, z: number) => ({ clientX: (x + 11) * 10, clientY: (z + 9) * 10 });
const shape = (key: string) => screen.getByTestId(`room-item-shape-${key}`);
const grip = (name: string) => screen.getByTestId(`room-item-handle-${name}`);
const at = (element: Element) =>
  element.getAttribute('transform')!.match(/-?\d+(\.\d+)?/g)!.map(Number);
const flush = () => act(async () => {});
const press = (key: string, more: Record<string, unknown> = {}) => fireEvent.keyDown(document.body, { key, ...more });

describe('StageView2D: arranging the room\'s items', () => {
  afterEach(cleanup);

  it('has nothing to pick up unless the mode is on, or on a plan that cannot be edited', () => {
    plan();
    expect(screen.queryByTestId('room-items')).toBeNull();
    cleanup();
    plan({ itemsEdit: true, readonly: true });
    expect(screen.queryByTestId('room-items')).toBeNull();
    cleanup();
    plan({ itemsEdit: true }, null);
    expect(screen.queryByTestId('room-items')).toBeNull();
  });

  it('offers each item the plan draws, by its place in the stored list', () => {
    plan({ itemsEdit: true });
    expect(screen.getByTestId('room-item-risers-1')).toBeTruthy();
    expect(screen.queryByTestId('room-item-risers-0')).toBeNull();
    expect(screen.getByTestId('room-item-truss_lines-0')).toBeTruthy();
    expect(screen.getByTestId('room-item-truss_rings-0')).toBeTruthy();
    // A stage 6 m by 3 m about (0, -5).
    expect(shape('risers-1').getAttribute('x')).toBe('3');
    expect(shape('risers-1').getAttribute('y')).toBe('-1.5');
  });

  it('selects an item on a press, and moves nothing on a click or a wobble under 5 pixels', () => {
    const onItemSelect = vi.fn();
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, snapMode: 'none', onItemSelect, onItemChange });
    fireEvent.mouseDown(shape('risers-1'), inRoom(0, -5));
    fireEvent.mouseUp(svg, inRoom(0, -5));
    expect(onItemSelect).toHaveBeenCalledWith('risers:1');
    // 3 across and 3 down: 4.24 pixels.
    fireEvent.mouseDown(shape('risers-1'), inRoom(0, -5));
    fireEvent.mouseMove(svg, { clientX: 113, clientY: 43 });
    fireEvent.mouseUp(svg, { clientX: 113, clientY: 43 });
    expect(onItemChange).not.toHaveBeenCalled();
    expect(screen.queryByTestId('room-item-readout')).toBeNull();
  });

  it('is one call for a whole drag, made when it is let go, with the middle alone', async () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, gridSize: 0.5, onItemChange });
    // Picked up 1 m stage left of its middle: the stage does not jump to the pointer.
    fireEvent.mouseDown(shape('risers-1'), inRoom(1, -5));
    fireEvent.mouseMove(svg, inRoom(2, -4.5));
    fireEvent.mouseMove(svg, inRoom(3.2, -3.9));
    // Nothing is sent while it is carried; it is drawn where the drag has it, on the grid.
    expect(onItemChange).not.toHaveBeenCalled();
    expect(shape('risers-1').getAttribute('x')).toBe('5');
    expect(shape('risers-1').getAttribute('y')).toBe('-0.5');
    expect(screen.getByTestId('room-item-readout').textContent).toBe('2.00, -4.00');

    fireEvent.mouseUp(svg, inRoom(3.2, -3.9));

    expect(onItemChange).toHaveBeenCalledTimes(1);
    expect(onItemChange).toHaveBeenCalledWith('risers', 1, { center_x: 2, center_z: -4 });
    await flush();
  });

  it('lets go of the grid with Alt held or the snap set to none', () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, gridSize: 0.5, onItemChange });
    fireEvent.mouseDown(shape('risers-1'), inRoom(0, -5));
    fireEvent.mouseMove(svg, { ...inRoom(1.3, -4.8), altKey: true });
    fireEvent.mouseUp(svg, inRoom(1.3, -4.8));
    expect(onItemChange.mock.calls[0][2].center_x).toBeCloseTo(1.3);
    expect(onItemChange.mock.calls[0][2].center_z).toBeCloseTo(-4.8);
  });

  it('sends nothing for a drag brought back to where it began', () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, gridSize: 0.5, onItemChange });
    fireEvent.mouseDown(shape('risers-1'), inRoom(0, -5));
    fireEvent.mouseMove(svg, inRoom(2, -5));
    fireEvent.mouseMove(svg, inRoom(0.1, -5.1));
    fireEvent.mouseUp(svg, inRoom(0.1, -5.1));
    expect(onItemChange).not.toHaveBeenCalled();
    expect(shape('risers-1').getAttribute('x')).toBe('3');
  });

  it('keeps the item where it was dropped until the change is answered, then draws the room it has', async () => {
    let answered: () => void = () => {};
    const onItemChange = vi.fn(() => new Promise<void>((resolve) => { answered = resolve; }));
    const svg = plan({ itemsEdit: true, snapMode: 'none', onItemChange });
    fireEvent.mouseDown(shape('truss_lines-0'), inRoom(0, 2));
    fireEvent.mouseMove(svg, inRoom(1, 4));
    fireEvent.mouseUp(svg, inRoom(1, 4));
    await flush();
    expect(shape('truss_lines-0').getAttribute('y1')).toBe('9');
    expect(shape('truss_lines-0').getAttribute('x2')).toBe('11');

    // Refused: the room given is the one it had, and the truss goes back.
    await act(async () => { answered(); });
    await flush();
    expect(shape('truss_lines-0').getAttribute('y1')).toBe('7');
    expect(shape('truss_lines-0').getAttribute('x2')).toBe('10');
  });

  it('carries an item dragged off the plan to where the drag had it', () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, snapMode: 'none', onItemChange });
    fireEvent.mouseDown(shape('risers-1'), inRoom(0, -5));
    fireEvent.mouseMove(svg, inRoom(1, -5));
    fireEvent.mouseLeave(svg);
    expect(onItemChange).toHaveBeenCalledTimes(1);
    expect(onItemChange.mock.calls[0][2]).toEqual({ center_x: 1, center_z: -5 });
  });

  it('shows handles on the selected item only', () => {
    plan({ itemsEdit: true });
    expect(screen.queryByTestId('room-item-handle-length')).toBeNull();
    cleanup();

    plan({ itemsEdit: true, selectedItemKey: 'truss_lines:0' });
    expect(screen.getByTestId('room-item-truss_lines-0').getAttribute('data-selected')).toBe('true');
    expect(at(grip('length'))).toEqual([10, 7]);
    expect(at(grip('rotate'))[0]).toBeCloseTo(1.4);
    expect(at(grip('rotate'))[1]).toBeCloseTo(7);
    expect(screen.queryByTestId('room-item-handle-radius')).toBeNull();
    cleanup();

    plan({ itemsEdit: true, selectedItemKey: 'truss_rings:0' });
    expect(at(grip('radius'))).toEqual([13.5, 1]);
    cleanup();

    // A raised area: a handle on each corner and each edge, and since slice 21 one to turn it.
    plan({ itemsEdit: true, selectedItemKey: 'risers:1' });
    expect(screen.getAllByTestId(/^room-item-handle-/).map((handle) => handle.getAttribute('data-testid'))).toEqual(
      ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w', 'rotate'].map((name) => `room-item-handle-${name}`),
    );
    // The stage is 6 m by 3 m about (0, -5), drawn at (x + 6, z + 5).
    expect(at(grip('nw'))).toEqual([3, -1.5]);
    expect(at(grip('e'))).toEqual([9, 0]);
    expect(at(grip('s'))).toEqual([6, 1.5]);
    // The rotate handle stands 0.6 m past the middle of its upstage edge.
    expect(at(grip('rotate'))[0]).toBeCloseTo(6);
    expect(at(grip('rotate'))[1]).toBeCloseTo(-2.1);
  });

  it('has no resize handles on a raised area that is not selected', () => {
    plan({ itemsEdit: true, selectedItemKey: 'truss_lines:0' });
    expect(screen.queryByTestId('room-item-handle-e')).toBeNull();
    expect(screen.queryByTestId('room-item-handle-nw')).toBeNull();
  });

  it('makes a raised area wider from an edge handle: drawn as it goes, one call with the width when let go', async () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'risers:1', onItemChange });
    fireEvent.mouseDown(grip('e'), inRoom(3, -5));
    fireEvent.mouseMove(svg, inRoom(3.6, -5));
    fireEvent.mouseMove(svg, inRoom(4.1, -4));
    // About its middle, to the grid's step: 8 m wide, and no deeper for a pointer that wandered downstage.
    expect(onItemChange).not.toHaveBeenCalled();
    expect(shape('risers-1').getAttribute('width')).toBe('8');
    expect(shape('risers-1').getAttribute('x')).toBe('2');
    expect(shape('risers-1').getAttribute('height')).toBe('3');
    expect(screen.getByTestId('room-item-readout').textContent).toBe('8.00 by 3.00 m');
    // The handle goes with the edge it has hold of.
    expect(at(grip('e'))).toEqual([10, 0]);

    fireEvent.mouseUp(svg, inRoom(4.1, -4));

    expect(onItemChange).toHaveBeenCalledTimes(1);
    expect(onItemChange).toHaveBeenCalledWith('risers', 1, { width: 8 });
    await flush();
  });

  it('changes the width and the front to back together from a corner handle, in one call', async () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'risers:1', onItemChange });
    fireEvent.mouseDown(grip('se'), inRoom(3, -3.5));
    fireEvent.mouseMove(svg, inRoom(4, -3));
    expect(shape('risers-1').getAttribute('width')).toBe('8');
    expect(shape('risers-1').getAttribute('height')).toBe('4');
    expect(shape('risers-1').getAttribute('y')).toBe('-2');
    fireEvent.mouseUp(svg, inRoom(4, -3));
    expect(onItemChange).toHaveBeenCalledTimes(1);
    expect(onItemChange).toHaveBeenCalledWith('risers', 1, { width: 8, depth: 4 });
    await flush();
  });

  it('makes it shallower from the upstage edge, and sends the front to back alone', async () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'risers:1', onItemChange });
    fireEvent.mouseDown(grip('n'), inRoom(0, -6.5));
    fireEvent.mouseMove(svg, inRoom(0, -5.5));
    fireEvent.mouseUp(svg, inRoom(0, -5.5));
    expect(onItemChange).toHaveBeenCalledWith('risers', 1, { depth: 1 });
    await flush();
  });

  it('sends nothing for a press on a resize handle that stays within 5 pixels, or is brought back', () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'risers:1', onItemChange });
    // The east handle is at (140, 40) on screen: 3 across and 2 down is 3.6 pixels.
    fireEvent.mouseDown(grip('e'), inRoom(3, -5));
    fireEvent.mouseMove(svg, { clientX: 143, clientY: 42 });
    fireEvent.mouseUp(svg, { clientX: 143, clientY: 42 });
    expect(onItemChange).not.toHaveBeenCalled();
    expect(screen.queryByTestId('room-item-readout')).toBeNull();

    fireEvent.mouseDown(grip('e'), inRoom(3, -5));
    fireEvent.mouseMove(svg, inRoom(5, -5));
    fireEvent.mouseMove(svg, inRoom(3.1, -5));
    fireEvent.mouseUp(svg, inRoom(3.1, -5));
    expect(onItemChange).not.toHaveBeenCalled();
    expect(shape('risers-1').getAttribute('width')).toBe('6');
  });

  it('keeps a resized raised area as it was dropped until the change is answered, then puts it back if it was refused', async () => {
    let answered: () => void = () => {};
    const onItemChange = vi.fn(() => new Promise<void>((resolve) => { answered = resolve; }));
    const svg = plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'risers:1', onItemChange });
    fireEvent.mouseDown(grip('w'), inRoom(-3, -5));
    fireEvent.mouseMove(svg, inRoom(-5, -5));
    fireEvent.mouseUp(svg, inRoom(-5, -5));
    await flush();
    expect(shape('risers-1').getAttribute('width')).toBe('10');

    // Refused: the room given is the one it had, and the stage is 6 m wide again with its handles round it.
    await act(async () => { answered(); });
    await flush();
    expect(shape('risers-1').getAttribute('width')).toBe('6');
    expect(shape('risers-1').getAttribute('x')).toBe('3');
    expect(at(grip('w'))).toEqual([3, 0]);
  });

  it('still moves a selected raised area by its body, with its handles on it', async () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'risers:1', onItemChange });
    fireEvent.mouseDown(shape('risers-1'), inRoom(1, -5));
    fireEvent.mouseMove(svg, inRoom(3, -5));
    fireEvent.mouseUp(svg, inRoom(3, -5));
    expect(onItemChange).toHaveBeenCalledWith('risers', 1, { center_x: 2, center_z: -5 });
    await flush();
  });

  it('changes a line\'s length from the handle on its end, about its middle', () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'truss_lines:0', onItemChange });
    fireEvent.mouseDown(grip('length'), inRoom(4, 2));
    fireEvent.mouseMove(svg, inRoom(5, 2.3));
    expect(shape('truss_lines-0').getAttribute('x1')).toBe('1');
    expect(shape('truss_lines-0').getAttribute('x2')).toBe('11');
    expect(screen.getByTestId('room-item-readout').textContent).toBe('10.00 m long');
    fireEvent.mouseUp(svg, inRoom(5, 2.3));
    expect(onItemChange).toHaveBeenCalledTimes(1);
    expect(onItemChange).toHaveBeenCalledWith('truss_lines', 0, { length: 10 });
  });

  it('turns a line from the handle past its other end', () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'truss_lines:0', onItemChange });
    fireEvent.mouseDown(grip('rotate'), inRoom(-4.6, 2));
    fireEvent.mouseMove(svg, inRoom(-3, -1));
    expect(screen.getByTestId('room-item-readout').textContent).toBe('45 deg');
    fireEvent.mouseUp(svg, inRoom(-3, -1));
    expect(onItemChange).toHaveBeenCalledTimes(1);
    expect(onItemChange).toHaveBeenCalledWith('truss_lines', 0, { heading_deg: 45 });
  });

  it('changes a ring\'s radius from the handle on its side', () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'truss_rings:0', onItemChange });
    fireEvent.mouseDown(grip('radius'), inRoom(7.5, -4));
    fireEvent.mouseMove(svg, inRoom(8.2, -4));
    expect(shape('truss_rings-0').getAttribute('r')).toBe('2');
    fireEvent.mouseUp(svg, inRoom(8.2, -4));
    expect(onItemChange).toHaveBeenCalledWith('truss_rings', 0, { radius: 2 });
  });

  it('sends nothing for a press on a handle that stays within 5 pixels', () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, selectedItemKey: 'truss_lines:0', onItemChange });
    fireEvent.mouseDown(grip('length'), inRoom(4, 2));
    fireEvent.mouseMove(svg, { clientX: 153, clientY: 112 });
    fireEvent.mouseUp(svg, { clientX: 153, clientY: 112 });
    expect(onItemChange).not.toHaveBeenCalled();
  });

  it('nudges the selected item by the grid step for each arrow key press, ten with Shift', () => {
    const onItemNudge = vi.fn();
    plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'risers:1', onItemNudge });
    press('ArrowRight');
    press('ArrowUp');
    press('ArrowLeft', { shiftKey: true });
    expect(onItemNudge.mock.calls).toEqual([
      ['risers', 1, 0.5, 0],
      ['risers', 1, 0, -0.5],
      ['risers', 1, -5, 0],
    ]);
  });

  it('does not repeat for a key held down, and leaves the arrows alone with nothing selected', () => {
    const onItemNudge = vi.fn();
    plan({ itemsEdit: true, selectedItemKey: 'risers:1', onItemNudge });
    press('ArrowRight', { repeat: true });
    press('ArrowRight', { ctrlKey: true });
    expect(onItemNudge).not.toHaveBeenCalled();
    cleanup();

    plan({ itemsEdit: true, onItemNudge });
    press('ArrowRight');
    expect(onItemNudge).not.toHaveBeenCalled();
  });

  it('takes no arrow key unless the mode is on, or while a field has the keys', () => {
    const onItemNudge = vi.fn();
    plan({ selectedItemKey: 'risers:1', onItemNudge });
    press('ArrowRight');
    expect(onItemNudge).not.toHaveBeenCalled();
    cleanup();

    plan({ itemsEdit: true, selectedItemKey: 'risers:1', onItemNudge });
    const input = document.createElement('input');
    document.body.appendChild(input);
    fireEvent.keyDown(input, { key: 'ArrowRight' });
    expect(onItemNudge).not.toHaveBeenCalled();
    input.remove();
  });

  it('lets go of the item on Escape and on a click on empty floor', () => {
    const onItemSelect = vi.fn();
    const onFixtureClick = vi.fn();
    const svg = plan({ itemsEdit: true, selectedItemKey: 'risers:1', onItemSelect, onFixtureClick });
    press('Escape');
    expect(onItemSelect).toHaveBeenLastCalledWith(null);
    fireEvent.click(svg);
    expect(onItemSelect).toHaveBeenCalledTimes(2);
    // Empty floor lets go of the item, not of a fixture.
    expect(onFixtureClick).not.toHaveBeenCalled();
  });

  it('keeps the item selected through the click that ends its drag', () => {
    const onItemSelect = vi.fn();
    const svg = plan({ itemsEdit: true, snapMode: 'none', selectedItemKey: 'risers:1', onItemSelect, onItemChange: vi.fn() });
    fireEvent.mouseDown(shape('risers-1'), inRoom(0, -5));
    fireEvent.mouseMove(svg, inRoom(2, -5));
    fireEvent.mouseUp(svg, inRoom(2, -5));
    fireEvent.click(svg);
    expect(onItemSelect).not.toHaveBeenCalled();
  });

  it('lets no fixture be picked up, selected or boxed while items are arranged', () => {
    const onFixtureDrag = vi.fn();
    const onFixtureDragStart = vi.fn();
    const onFixtureClick = vi.fn();
    const onSelectFixtures = vi.fn();
    const svg = plan({
      itemsEdit: true, snapMode: 'none', onFixtureDrag, onFixtureDragStart, onFixtureClick, onSelectFixtures,
    });
    const fixture = screen.getByText('Spot 1').parentElement!;
    fireEvent.mouseDown(fixture, inRoom(0, 2));
    fireEvent.mouseMove(svg, inRoom(2, 4));
    fireEvent.mouseUp(svg, inRoom(2, 4));
    fireEvent.mouseDown(svg, inRoom(-8, 6));
    fireEvent.mouseMove(svg, inRoom(-6, 7));
    fireEvent.mouseUp(svg, inRoom(-6, 7));
    expect(onFixtureDrag).not.toHaveBeenCalled();
    expect(onFixtureDragStart).not.toHaveBeenCalled();
    expect(onFixtureClick).not.toHaveBeenCalled();
    expect(onSelectFixtures).not.toHaveBeenCalled();
    expect(screen.queryByTestId('selection-box')).toBeNull();
  });

  it('is drawn over the fixtures, so a truss under its own lights can still be pressed', () => {
    plan({ itemsEdit: true });
    const layer = screen.getByTestId('room-items');
    const fixture = screen.getByText('Spot 1').parentElement!;
    // Later in the document is nearer the front.
    expect(fixture.compareDocumentPosition(layer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

// Slice 21: a raised area stands at any heading. It is drawn turned, its
// handles stand on it as it is turned, and a rotate handle turns it.
describe('StageView2D: a raised area at a heading', () => {
  afterEach(cleanup);

  const turnedRoom = (heading: number): RoomShell => ({
    ...ROOM,
    risers: [ROOM.risers![0], { ...ROOM.risers![1], heading_deg: heading }],
  });
  const raisedRect = () => screen.getByTestId('room-plan-raised').querySelector('rect')!;

  it('draws one that stands square as it always was, and a turned one turned about its middle', () => {
    plan({ itemsEdit: true, selectedItemKey: 'risers:1' });
    expect(raisedRect().getAttribute('transform')).toBeNull();
    expect(shape('risers-1').getAttribute('transform')).toBeNull();
    cleanup();

    // The stage's middle, (0, -5), is drawn at (6, 0). The rectangle itself is the one it was.
    plan({ itemsEdit: true, selectedItemKey: 'risers:1' }, turnedRoom(30));
    expect(raisedRect().getAttribute('transform')).toBe('rotate(30 6 0)');
    expect(raisedRect().getAttribute('width')).toBe('6');
    expect(raisedRect().getAttribute('x')).toBe('3');
    expect(shape('risers-1').getAttribute('transform')).toBe('rotate(30 6 0)');
    expect(shape('risers-1').getAttribute('width')).toBe('6');
    // Its handles stand on it as it is turned: the middle of its own stage left edge is 3 m along 30 degrees.
    expect(at(grip('e'))[0]).toBeCloseTo(6 + 3 * Math.cos(Math.PI / 6));
    expect(at(grip('e'))[1]).toBeCloseTo(1.5);
    expect(at(grip('rotate'))[0]).toBeCloseTo(6 + 2.1 * Math.sin(Math.PI / 6));
    expect(at(grip('rotate'))[1]).toBeCloseTo(-2.1 * Math.cos(Math.PI / 6));
  });

  it('draws a turned one turned on a plan that is not being arranged too', () => {
    plan({}, turnedRoom(-20));
    expect(raisedRect().getAttribute('transform')).toBe('rotate(-20 6 0)');
    expect(screen.queryByTestId('room-items')).toBeNull();
  });

  it('turns it from the rotate handle: drawn as it goes, one call with the heading when let go', async () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'risers:1', onItemChange });
    // The handle is at (0, -7.1). Up and stage left of the middle is 45 degrees clockwise.
    fireEvent.mouseDown(grip('rotate'), inRoom(0, -7.1));
    fireEvent.mouseMove(svg, inRoom(1, -8));
    fireEvent.mouseMove(svg, inRoom(3, -8));
    expect(shape('risers-1').getAttribute('transform')).toBe('rotate(45 6 0)');
    expect(screen.getByTestId('room-item-readout').textContent).toBe('45 deg');
    // The handle goes round with it, and the one under the fixtures is left until the answer.
    expect(at(grip('rotate'))[0]).toBeGreaterThan(6);
    expect(raisedRect().getAttribute('transform')).toBeNull();
    expect(onItemChange).not.toHaveBeenCalled();

    fireEvent.mouseUp(svg, inRoom(3, -8));
    expect(onItemChange).toHaveBeenCalledTimes(1);
    expect(onItemChange).toHaveBeenCalledWith('risers', 1, { heading_deg: 45 });
    await flush();
  });

  it('turns in steps of 5 degrees on the grid, and of 15 with Shift held', async () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'risers:1', onItemChange });
    // 18.4 degrees clockwise of straight upstage.
    fireEvent.mouseDown(grip('rotate'), inRoom(0, -7.1));
    fireEvent.mouseMove(svg, inRoom(1, -8));
    expect(screen.getByTestId('room-item-readout').textContent).toBe('20 deg');
    fireEvent.mouseMove(svg, { ...inRoom(1, -8), shiftKey: true });
    expect(screen.getByTestId('room-item-readout').textContent).toBe('15 deg');
    expect(shape('risers-1').getAttribute('transform')).toBe('rotate(15 6 0)');
    fireEvent.mouseUp(svg, { ...inRoom(1, -8), shiftKey: true });
    expect(onItemChange).toHaveBeenCalledTimes(1);
    expect(onItemChange).toHaveBeenCalledWith('risers', 1, { heading_deg: 15 });
    await flush();
  });

  it('turns in steps of 15 with Shift held when the snap is off as well', async () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, snapMode: 'none', selectedItemKey: 'risers:1', onItemChange });
    fireEvent.mouseDown(grip('rotate'), inRoom(0, -7.1));
    fireEvent.mouseMove(svg, { ...inRoom(1, -8), shiftKey: true });
    fireEvent.mouseUp(svg, { ...inRoom(1, -8), shiftKey: true });
    expect(onItemChange).toHaveBeenCalledWith('risers', 1, { heading_deg: 15 });
    await flush();
  });

  it('sends nothing for a press on the rotate handle that stays within 5 pixels, or is brought back', () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'risers:1', onItemChange });
    // The handle is at (110, 19) on screen.
    fireEvent.mouseDown(grip('rotate'), inRoom(0, -7.1));
    fireEvent.mouseMove(svg, { clientX: 113, clientY: 21 });
    fireEvent.mouseUp(svg, { clientX: 113, clientY: 21 });
    expect(onItemChange).not.toHaveBeenCalled();

    fireEvent.mouseDown(grip('rotate'), inRoom(0, -7.1));
    fireEvent.mouseMove(svg, inRoom(3, -8));
    fireEvent.mouseMove(svg, inRoom(0.05, -7.5));
    fireEvent.mouseUp(svg, inRoom(0.05, -7.5));
    expect(onItemChange).not.toHaveBeenCalled();
    expect(shape('risers-1').getAttribute('transform')).toBeNull();
  });

  it('keeps a turned raised area as it was dropped until the change is answered, then puts it back if it was refused', async () => {
    let answered: () => void = () => {};
    const onItemChange = vi.fn(() => new Promise<void>((resolve) => { answered = resolve; }));
    const svg = plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'risers:1', onItemChange });
    fireEvent.mouseDown(grip('rotate'), inRoom(0, -7.1));
    fireEvent.mouseMove(svg, inRoom(3, -8));
    fireEvent.mouseUp(svg, inRoom(3, -8));
    await flush();
    expect(shape('risers-1').getAttribute('transform')).toBe('rotate(45 6 0)');

    // Refused: the room given is the one it had, and the stage stands square again with its handle upstage of it.
    await act(async () => { answered(); });
    await flush();
    expect(shape('risers-1').getAttribute('transform')).toBeNull();
    expect(at(grip('rotate'))[0]).toBeCloseTo(6);
    expect(at(grip('rotate'))[1]).toBeCloseTo(-2.1);
    expect(screen.queryByTestId('room-item-readout')).toBeNull();
  });

  it('resizes a turned raised area along its own sides, with the arrow turned too', async () => {
    const onItemChange = vi.fn();
    // A quarter turn: the stage's width now runs downstage, and its 'e' edge is at (0, -2), drawn at (6, 3).
    const svg = plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'risers:1', onItemChange }, turnedRoom(90));
    expect(at(grip('e'))[0]).toBeCloseTo(6);
    expect(at(grip('e'))[1]).toBeCloseTo(3);
    expect(grip('e').getAttribute('style')).toContain('ns-resize');
    expect(grip('n').getAttribute('style')).toContain('ew-resize');

    fireEvent.mouseDown(grip('e'), inRoom(0, -2));
    fireEvent.mouseMove(svg, inRoom(0, -1));
    // Wider about its middle, and still turned: the rectangle is 8 m wide before it is turned.
    expect(shape('risers-1').getAttribute('width')).toBe('8');
    expect(shape('risers-1').getAttribute('height')).toBe('3');
    expect(shape('risers-1').getAttribute('transform')).toBe('rotate(90 6 0)');
    expect(screen.getByTestId('room-item-readout').textContent).toBe('8.00 by 3.00 m');
    fireEvent.mouseUp(svg, inRoom(0, -1));
    expect(onItemChange).toHaveBeenCalledTimes(1);
    expect(onItemChange).toHaveBeenCalledWith('risers', 1, { width: 8 });
    await flush();
  });

  it('does not widen a turned raised area for a pull across the room', async () => {
    const onItemChange = vi.fn();
    const svg = plan({ itemsEdit: true, gridSize: 0.5, selectedItemKey: 'risers:1', onItemChange }, turnedRoom(90));
    fireEvent.mouseDown(grip('e'), inRoom(0, -2));
    fireEvent.mouseMove(svg, inRoom(4, -2));
    fireEvent.mouseUp(svg, inRoom(4, -2));
    expect(onItemChange).not.toHaveBeenCalled();
    await flush();
  });
});
