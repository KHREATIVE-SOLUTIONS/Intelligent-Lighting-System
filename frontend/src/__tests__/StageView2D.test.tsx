// The 2D layout view and a rig's scanned room: drawn when there is one, under
// the fixtures, and nothing at all changed when there is not. docs/ROOM_SCAN.md.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import StageView2D from '../components/rig/StageView2D';
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
