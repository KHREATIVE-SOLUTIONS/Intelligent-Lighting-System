// The 2D layout view and a rig's scanned room: drawn when there is one, under
// the fixtures, and nothing at all changed when there is not. docs/ROOM_SCAN.md.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, createEvent, fireEvent, render, screen } from '@testing-library/react';
import StageView2D from '../components/rig/StageView2D';
import { FIXTURE_DRAG_MIME } from '../stores/rigEditorStore';
import type { RigFixture, RoomShell } from '../types';

const fixture = {
  id: 1,
  name: 'Spot 1',
  dmx_address: 1,
  position_x: 0,
  position_y: 4,
  position_z: 0,
  rotation_y: 0,
} as unknown as RigFixture;

// 20 m by 16 m round a 10 m by 8 m stage, an L with a corner walled off.
const OUTLINE = [
  { x: -10, z: -8 }, { x: 10, z: -8 }, { x: 10, z: 2 }, { x: 4, z: 2 }, { x: 4, z: 8 }, { x: -10, z: 8 },
];

const SCANNED: RoomShell = {
  source: 'scan',
  suggested: true,
  room: { width: 20, depth: 16, height: 6 },
  risers: [
    { center_x: 0, center_z: -6, width: 8, depth: 3, height: 0.9, name: 'Stage', kind: 'stage' },
    { center_x: -7, center_z: 5, width: 2, depth: 1, height: 1, kind: 'booth' },
  ],
  truss_lines: [
    { name: 'Truss 1', x1: -4, z1: -3, x2: 4, z2: -3, height: 4.2, across: 0.3 },
    { name: 'Truss 2', x1: -6, z1: 0, x2: -2, z2: 4, height: 5, across: 0.3, heading_deg: 45 },
  ],
  truss_rings: [{ name: 'Ring 1', center_x: 5, center_z: -2, radius: 2, height: 4.8, across: 0.3 }],
};

const PRESET: RoomShell = {
  dome: { radius: 8, center_x: 0, center_z: 0, rim_height: 6, apex_height: 9 },
  dj_booth: { center_x: 0, center_z: -3, width: 3, depth: 1, height: 1 },
};

function view(roomShell?: RoomShell | null, extra: Partial<Parameters<typeof StageView2D>[0]> = {}) {
  const props = { width: 10, depth: 8, height: 5, fixtures: [fixture], selectedIds: new Set<number>(), ...extra };
  return roomShell === undefined
    ? render(<StageView2D {...props} />)
    : render(<StageView2D {...props} roomShell={roomShell} />);
}

describe('StageView2D with no scanned room', () => {
  afterEach(cleanup);

  it('draws no room layer and keeps the stage\'s own view box', () => {
    const { container } = view();
    expect(screen.queryByTestId('room-plan')).toBeNull();
    expect(screen.queryByTestId('room-plan-floor')).toBeNull();
    expect(container.querySelector('svg')!.getAttribute('viewBox')).toBe('0 0 12 10');
    expect(container.querySelectorAll('title')).toHaveLength(0);
  });

  it('draws the same thing for no shell, a null shell and a shell that is not from a scan', () => {
    const none = view().container.innerHTML;
    cleanup();
    const empty = view(null).container.innerHTML;
    cleanup();
    const preset = view(PRESET).container.innerHTML;
    cleanup();
    const hollow = view({ source: 'scan' }).container.innerHTML;
    expect(empty).toBe(none);
    expect(preset).toBe(none);
    expect(hollow).toBe(none);
  });
});

describe('StageView2D with a scanned room', () => {
  afterEach(cleanup);

  it('draws the box room\'s four walls', () => {
    view(SCANNED);
    const walls = screen.getByTestId('room-plan-walls');
    expect(walls.getAttribute('data-outlined')).toBe('false');
    // Room corners at x = -10..10, z = -8..8, in the view's units (x + 6, z + 5).
    expect(walls.getAttribute('points')).toBe('-4,-3 16,-3 16,13 -4,13');
    expect(walls.querySelector('title')!.textContent).toBe('Scanned room: 20.0 m wide, 16.0 m deep, 6.0 m high');
    expect(screen.getByTestId('room-plan-floor').getAttribute('points')).toBe('-4,-3 16,-3 16,13 -4,13');
  });

  it('draws the floor outline in place of the box when the room has one', () => {
    view({ ...SCANNED, room: { width: 20, depth: 16, height: 6, outline: OUTLINE } });
    const walls = screen.getByTestId('room-plan-walls');
    expect(walls.getAttribute('data-outlined')).toBe('true');
    expect(walls.getAttribute('points')).toBe('-4,-3 16,-3 16,7 10,7 10,13 -4,13');
  });

  it('grows the view to take the room in', () => {
    const { container } = view(SCANNED);
    expect(container.querySelector('svg')!.getAttribute('viewBox')).toBe('-5 -4 22 18');
  });

  it('labels each raised area with what it is and how high', () => {
    view(SCANNED);
    const raised = screen.getAllByTestId('room-plan-raised');
    expect(raised).toHaveLength(2);
    expect(raised[0].getAttribute('data-kind')).toBe('stage');
    expect(raised[0].querySelector('text')!.textContent).toBe('Stage · 0.90 m high');
    expect(raised[0].querySelector('rect')!.getAttribute('width')).toBe('8');
    expect(raised[1].querySelector('text')!.textContent).toBe('Booth or counter · 1.00 m high');
    expect(raised[1].querySelector('title')!.textContent).toContain('top 1.00 m above the floor');
  });

  it('draws truss lines end to end at any heading, with the height they hang at', () => {
    view(SCANNED);
    const lines = screen.getAllByTestId('room-plan-truss-line');
    expect(lines).toHaveLength(2);
    const angled = lines[1].querySelector('line')!;
    expect([angled.getAttribute('x1'), angled.getAttribute('y1'), angled.getAttribute('x2'), angled.getAttribute('y2')])
      .toEqual(['0', '5', '4', '9']);
    expect(lines[0].querySelector('text')!.textContent).toBe('Truss 1 · hangs at 4.20 m');
    expect(lines[1].querySelector('title')!.textContent)
      .toBe('Truss 2: 5.7 m long, underside 5.00 m up, running at 45 degrees to the room');
  });

  it('draws a ring of truss as a circle, with the height it hangs at', () => {
    view(SCANNED);
    const ring = screen.getByTestId('room-plan-truss-ring');
    const circle = ring.querySelector('circle')!;
    expect([circle.getAttribute('cx'), circle.getAttribute('cy'), circle.getAttribute('r')]).toEqual(['11', '3', '2']);
    expect(ring.querySelector('text')!.textContent).toBe('Ring 1 · hangs at 4.80 m');
    expect(ring.querySelector('title')!.textContent).toBe('Ring 1: a ring 4.0 m across, underside 4.80 m up');
  });

  it('keeps the fixtures where they were and on top of the room', () => {
    view(SCANNED);
    const room = screen.getByTestId('room-plan');
    const spot = screen.getByText('Spot 1').parentElement!;
    expect(spot.getAttribute('transform')).toBe('translate(6, 5)');
    // Later in the document is nearer the eye in an SVG.
    expect(room.compareDocumentPosition(spot) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(room.contains(spot)).toBe(false);
  });

  it('still reads a drag in stage metres with the view grown round the room', () => {
    const onFixtureDrag = vi.fn();
    const { container } = view(SCANNED, { snapMode: 'none', onFixtureDrag });
    const svg = container.querySelector('svg')!;
    // The view is 22 m by 18 m from (-5, -4); drawn at 10 pixels to the metre.
    svg.getBoundingClientRect = () => ({
      left: 0, top: 0, right: 220, bottom: 180, width: 220, height: 180, x: 0, y: 0, toJSON: () => ({}),
    });
    // Centre stage is at (6, 5) in the view's units: 110, 90 on screen.
    fireEvent.mouseDown(screen.getByText('Spot 1').parentElement!, { clientX: 110, clientY: 90 });
    fireEvent.mouseMove(svg, { clientX: 130, clientY: 80 });
    expect(onFixtureDrag).toHaveBeenCalledTimes(1);
    const [id, x, z] = onFixtureDrag.mock.calls[0];
    expect(id).toBe(1);
    expect(x).toBeCloseTo(2);
    expect(z).toBeCloseTo(-1);
  });
});

// ---------------------------------------------------------------------------
// Dragging and dropping: held to the room when there is one, else to the deck
// ---------------------------------------------------------------------------

/** Draw the plan at 10 pixels to the metre, so a pointer position is easy to read. */
function drawnAtTenPixelsAMetre(svg: SVGSVGElement) {
  const [, , w, h] = svg.getAttribute('viewBox')!.split(' ').map(Number);
  const width = w * 10;
  const height = h * 10;
  svg.getBoundingClientRect = () => ({
    left: 0, top: 0, right: width, bottom: height, width, height, x: 0, y: 0, toJSON: () => ({}),
  });
}

/**
 * A palette drag or drop over the plan. The pointer position is set on the
 * event itself: a test DOM that has no DragEvent builds a plain event, which
 * would otherwise carry none.
 */
function paletteEvent(kind: 'drop' | 'dragOver', svg: SVGSVGElement, clientX: number, clientY: number, payload = '7') {
  const event = createEvent[kind](svg, {
    dataTransfer: { types: [FIXTURE_DRAG_MIME], getData: () => payload },
  });
  Object.defineProperty(event, 'clientX', { value: clientX });
  Object.defineProperty(event, 'clientY', { value: clientY });
  fireEvent(svg, event);
}

const at = (x: number, z: number) => ({ ...fixture, position_x: x, position_z: z }) as RigFixture;

// With the SCANNED room round a 10 m by 8 m deck the view is 22 m by 18 m from
// (-5, -4), so stage (x, z) is at ((x + 11) * 10, (z + 9) * 10) on screen.
const onScreen = (x: number, z: number) => ({ clientX: (x + 11) * 10, clientY: (z + 9) * 10 });

describe('StageView2D: a drag in a scanned room', () => {
  afterEach(cleanup);

  it('does not bring a fixture hung beyond the deck onto the deck (grid snap, the default)', () => {
    const onFixtureDrag = vi.fn();
    // The deck ends at x = 5 and z = 4.
    const { container } = view(SCANNED, { fixtures: [at(8, 6)], onFixtureDrag });
    const svg = container.querySelector('svg')!;
    drawnAtTenPixelsAMetre(svg);
    fireEvent.mouseDown(screen.getByText('Spot 1').parentElement!, onScreen(8, 6));
    // Half a metre stage left.
    fireEvent.mouseMove(svg, onScreen(8.5, 6));
    expect(onFixtureDrag).toHaveBeenCalledTimes(1);
    const [, x, z] = onFixtureDrag.mock.calls[0];
    expect(x).toBeCloseTo(8.5);
    expect(z).toBeCloseTo(6);
  });

  it('does not bring it onto the deck with snapping off or on truss either', () => {
    for (const snapMode of ['none', 'truss'] as const) {
      const onFixtureDrag = vi.fn();
      const { container } = view(SCANNED, { fixtures: [at(8, 6)], snapMode, onFixtureDrag });
      const svg = container.querySelector('svg')!;
      drawnAtTenPixelsAMetre(svg);
      fireEvent.mouseDown(screen.getByText('Spot 1').parentElement!, onScreen(8, 6));
      fireEvent.mouseMove(svg, onScreen(8.3, 6));
      const [, x, z] = onFixtureDrag.mock.calls[0];
      expect(x).toBeCloseTo(8.3);
      // On truss it stays on its own depth, which is a truss line while it is held.
      expect(z).toBeCloseTo(6);
      cleanup();
    }
  });

  it('holds a drag at the wall of a box room', () => {
    const onFixtureDrag = vi.fn();
    const { container } = view(SCANNED, { fixtures: [at(8, 6)], snapMode: 'none', onFixtureDrag });
    const svg = container.querySelector('svg')!;
    drawnAtTenPixelsAMetre(svg);
    fireEvent.mouseDown(screen.getByText('Spot 1').parentElement!, onScreen(8, 6));
    // Past the walls at x = 10 and z = 8, into the margin round the room.
    fireEvent.mouseMove(svg, onScreen(10.6, 8.7));
    const [, x, z] = onFixtureDrag.mock.calls[0];
    expect(x).toBeCloseTo(10);
    expect(z).toBeCloseTo(8);
  });

  it('holds a drag to an L-shaped outline: the notch is outside the room', () => {
    const onFixtureDrag = vi.fn();
    // OUTLINE walls off x > 4 with z > 2.
    const shell = { ...SCANNED, room: { width: 20, depth: 16, height: 6, outline: OUTLINE } };
    const { container } = view(shell, { fixtures: [at(3, 5)], snapMode: 'none', onFixtureDrag });
    const svg = container.querySelector('svg')!;
    drawnAtTenPixelsAMetre(svg);
    fireEvent.mouseDown(screen.getByText('Spot 1').parentElement!, onScreen(3, 5));
    // Into the notch, 2 m past its wall at x = 4 and 3 m past the one at z = 2.
    fireEvent.mouseMove(svg, onScreen(6, 5));
    let [, x, z] = onFixtureDrag.mock.calls[0];
    expect(x).toBeCloseTo(4);
    expect(z).toBeCloseTo(5);
    // Along inside the room it follows the pointer.
    fireEvent.mouseMove(svg, onScreen(-8, 7));
    [, x, z] = onFixtureDrag.mock.calls[1];
    expect(x).toBeCloseTo(-8);
    expect(z).toBeCloseTo(7);
    // The other arm of the L, beyond the deck, is in the room too.
    fireEvent.mouseMove(svg, onScreen(9, -1));
    [, x, z] = onFixtureDrag.mock.calls[2];
    expect(x).toBeCloseTo(9);
    expect(z).toBeCloseTo(-1);
  });
});

describe('StageView2D: a palette drop in a scanned room', () => {
  afterEach(cleanup);

  it('lands out in the room where it was dropped, not on the deck\'s edge', () => {
    const onDropFromPalette = vi.fn();
    const { container } = view(SCANNED, { onDropFromPalette });
    const svg = container.querySelector('svg')!;
    drawnAtTenPixelsAMetre(svg);
    const where = onScreen(8.1, 5.9);
    paletteEvent('drop', svg, where.clientX, where.clientY);
    expect(onDropFromPalette).toHaveBeenCalledTimes(1);
    const [id, x, z] = onDropFromPalette.mock.calls[0];
    expect(id).toBe(7);
    // On the grid, which carries on past the deck.
    expect(x).toBeCloseTo(8);
    expect(z).toBeCloseTo(6);
  });

  it('lands on the wall when dropped beyond it, and in the room when dropped in a notch', () => {
    const onDropFromPalette = vi.fn();
    const shell = { ...SCANNED, room: { width: 20, depth: 16, height: 6, outline: OUTLINE } };
    const { container } = view(shell, { snapMode: 'none', onDropFromPalette });
    const svg = container.querySelector('svg')!;
    drawnAtTenPixelsAMetre(svg);
    let where = onScreen(-10.8, 0);
    paletteEvent('drop', svg, where.clientX, where.clientY);
    expect(onDropFromPalette.mock.calls[0][1]).toBeCloseTo(-10);
    expect(onDropFromPalette.mock.calls[0][2]).toBeCloseTo(0);
    where = onScreen(9, 3);
    paletteEvent('drop', svg, where.clientX, where.clientY);
    // 1 m into the notch from its wall at z = 2.
    expect(onDropFromPalette.mock.calls[1][1]).toBeCloseTo(9);
    expect(onDropFromPalette.mock.calls[1][2]).toBeCloseTo(2);
  });

  it('shows the landing spot out in the room while the fixture is held over it', () => {
    const { container } = view(SCANNED, { onDropFromPalette: vi.fn() });
    const svg = container.querySelector('svg')!;
    drawnAtTenPixelsAMetre(svg);
    const where = onScreen(8, 6);
    paletteEvent('dragOver', svg, where.clientX, where.clientY);
    expect(screen.getByText('8.0, 6.0')).toBeTruthy();
  });
});

describe('StageView2D: a drag and a drop with no scanned room', () => {
  afterEach(cleanup);

  // The view is 12 m by 10 m from the origin: stage (x, z) is at ((x + 6) * 10, (z + 5) * 10).
  const onDeckScreen = (x: number, z: number) => ({ clientX: (x + 6) * 10, clientY: (z + 5) * 10 });

  it('still holds a drag to the deck, on the deck\'s grid', () => {
    for (const shell of [undefined, null, PRESET]) {
      const onFixtureDrag = vi.fn();
      const { container } = view(shell, { onFixtureDrag });
      const svg = container.querySelector('svg')!;
      drawnAtTenPixelsAMetre(svg);
      fireEvent.mouseDown(screen.getByText('Spot 1').parentElement!, onDeckScreen(0, 0));
      // Into the margin beyond the deck's edges at x = 5 and z = 4.
      fireEvent.mouseMove(svg, onDeckScreen(5.9, 4.9));
      expect(onFixtureDrag.mock.calls[0]).toEqual([1, 5, 4]);
      cleanup();
    }
  });

  it('still holds a palette drop to the deck', () => {
    const onDropFromPalette = vi.fn();
    const { container } = view(undefined, { onDropFromPalette });
    const svg = container.querySelector('svg')!;
    drawnAtTenPixelsAMetre(svg);
    const where = onDeckScreen(5.9, 4.9);
    paletteEvent('drop', svg, where.clientX, where.clientY);
    expect(onDropFromPalette.mock.calls[0]).toEqual([7, 5, 4]);
  });

  it('holds to the deck when a scan found truss but no room to hold to', () => {
    const onFixtureDrag = vi.fn();
    const shell: RoomShell = {
      source: 'scan',
      truss_lines: [{ name: 'Truss 1', x1: -4, z1: -3, x2: 4, z2: -3, height: 4.2, across: 0.3 }],
    };
    const { container } = view(shell, { onFixtureDrag });
    const svg = container.querySelector('svg')!;
    expect(svg.getAttribute('viewBox')).toBe('0 0 12 10');
    drawnAtTenPixelsAMetre(svg);
    fireEvent.mouseDown(screen.getByText('Spot 1').parentElement!, onDeckScreen(0, 0));
    fireEvent.mouseMove(svg, onDeckScreen(5.9, 4.9));
    expect(onFixtureDrag.mock.calls[0]).toEqual([1, 5, 4]);
  });
});

// ---------------------------------------------------------------------------
// Labels
// ---------------------------------------------------------------------------

const numbers = (element: Element, ...names: string[]) => names.map((name) => Number(element.getAttribute(name)));

describe('StageView2D: the plan\'s own labels', () => {
  afterEach(cleanup);

  it('are set against the deck with no scanned room, where they always were', () => {
    view();
    const [upX, upY] = numbers(screen.getByText('UPSTAGE — BACK WALL'), 'x', 'y');
    expect(upX).toBeCloseTo(6);
    expect(upY).toBeCloseTo(0.75);
    const [audienceX, audienceY] = numbers(screen.getByText('AUDIENCE'), 'x', 'y');
    expect(audienceX).toBeCloseTo(6);
    expect(audienceY).toBeCloseTo(9.9);
    const [scaleX, scaleY] = numbers(screen.getByText('1m'), 'x', 'y');
    expect(scaleX).toBeCloseTo(1.7);
    expect(scaleY).toBeCloseTo(0.4);
  });

  it('go by the scanned room\'s walls when one is drawn, outside its floor', () => {
    view(SCANNED);
    // The room's walls are at -4..16 across and -3..13 down the view.
    const [upX, upY] = numbers(screen.getByText('UPSTAGE — BACK WALL'), 'x', 'y');
    expect(upX).toBeCloseTo(6);
    expect(upY).toBeCloseTo(-3.25);
    const [audienceX, audienceY] = numbers(screen.getByText('AUDIENCE'), 'x', 'y');
    expect(audienceX).toBeCloseTo(6);
    expect(audienceY).toBeCloseTo(13.9);
    const [scaleX, scaleY] = numbers(screen.getByText('1m'), 'x', 'y');
    expect(scaleX).toBeCloseTo(-3.3);
    expect(scaleY).toBeCloseTo(-3.6);
  });
});

describe('StageView2D: the room layer\'s labels', () => {
  afterEach(cleanup);

  it('keeps a level label, unturned, on a truss straight across', () => {
    view(SCANNED);
    const label = screen.getByText('Truss 1 · hangs at 4.20 m');
    expect(label.getAttribute('transform')).toBeNull();
    // Over the middle of the line at z = -3: 0.25 m above it, at x = 0.
    const [x, y] = numbers(label, 'x', 'y');
    expect(x).toBeCloseTo(6);
    expect(y).toBeCloseTo(1.75);
  });

  it('turns a truss label along an angled line, about its own middle', () => {
    view(SCANNED);
    const label = screen.getByText('Truss 2 · hangs at 5.00 m');
    // From (-6, 0) to (-2, 4): 45 degrees, reading down the plan left to right.
    const [x, y] = numbers(label, 'x', 'y');
    expect(label.getAttribute('transform')).toBe(`rotate(45 ${label.getAttribute('x')} ${label.getAttribute('y')})`);
    // 0.25 m off the middle of the line at (-4, 2), square to it.
    expect(x).toBeCloseTo(6 - 4 + 0.25 * Math.SQRT1_2);
    expect(y).toBeCloseTo(5 + 2 - 0.25 * Math.SQRT1_2);
  });

  it('nudges one of two truss labels that would print over each other', () => {
    view({
      source: 'scan',
      room: { width: 20, depth: 16, height: 6 },
      truss_lines: [
        { name: 'Truss 1', x1: -4, z1: -3, x2: 4, z2: -3, height: 4.2, across: 0.3 },
        { name: 'Truss 2', x1: -4, z1: -3.2, x2: 4, z2: -3.2, height: 4.2, across: 0.3 },
      ],
    });
    const [, firstY] = numbers(screen.getByText('Truss 1 · hangs at 4.20 m'), 'x', 'y');
    const [, secondY] = numbers(screen.getByText('Truss 2 · hangs at 4.20 m'), 'x', 'y');
    // The first where it always is; the second a step further from its line.
    expect(firstY).toBeCloseTo(1.75);
    expect(secondY).toBeCloseTo(5 - 3.758);
    expect(firstY - secondY).toBeGreaterThan(0.22);
  });
});
