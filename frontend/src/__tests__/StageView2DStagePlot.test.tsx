// The 2D plan with a stage plot underlay: the image drawn under the fixtures by
// its matrix, a guessed fixture ringed in amber, and calibrate mode, where a
// click picks a point in plan metres and fixtures take no press. docs/STAGE_PLOT.md.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import StageView2D from '../components/rig/StageView2D';
import type { PlanUnderlay } from '../components/rig/StageView2D';
import type { RigFixture } from '../types';

const spot = (id: number, x: number, z: number, tags: string[] = []) => ({
  id,
  name: `Spot ${id}`,
  dmx_address: id,
  position_x: x,
  position_y: 4,
  position_z: z,
  rotation_y: 0,
  tags,
}) as unknown as RigFixture;

type Props = Parameters<typeof StageView2D>[0];

/** A 10 m by 8 m stage drawn at 10 pixels to the metre: the view is 12 by 10 m from (0, 0). */
function plan(extra: Partial<Props> = {}) {
  const props = { width: 10, depth: 8, height: 5, fixtures: [spot(1, 0, 0)], selectedIds: new Set<number>(), ...extra };
  const { container } = render(<StageView2D {...props} />);
  const svg = container.querySelector('svg')!;
  svg.getBoundingClientRect = () => ({
    left: 0, top: 0, right: 120, bottom: 100, width: 120, height: 100, x: 0, y: 0, toJSON: () => ({}),
  });
  return { svg, container };
}

// Stage (x, z) is at ((x + 6) * 10, (z + 5) * 10) on screen.
const onStage = (x: number, z: number) => ({ clientX: (x + 6) * 10, clientY: (z + 5) * 10 });

const UNDERLAY: PlanUnderlay = {
  href: 'blob:plot', widthPx: 1000, heightPx: 500, matrix: [0.01, 0, 0, 0.01, -5, -2.5], opacity: 0.4,
};

describe('StageView2D: the stage plot underlay', () => {
  afterEach(cleanup);

  it('draws nothing of a stage plot without one', () => {
    plan();
    expect(screen.queryByTestId('stage-plot-underlay')).toBeNull();
  });

  it('draws the image by its matrix about the middle of the stage, at its opacity, under the fixtures', () => {
    const { container } = plan({ underlay: UNDERLAY });
    const image = screen.getByTestId('stage-plot-underlay');
    expect(image.getAttribute('href')).toBe('blob:plot');
    expect(image.getAttribute('width')).toBe('1000');
    expect(image.getAttribute('height')).toBe('500');
    expect(image.getAttribute('opacity')).toBe('0.4');
    // The stage's (0, 0) is at (6, 5) in the SVG.
    expect(image.parentElement!.getAttribute('transform')).toBe('translate(6 5) matrix(0.01 0 0 0.01 -5 -2.5)');
    expect(image.parentElement!.getAttribute('pointer-events')).toBe('none');
    // Beneath the fixtures: earlier in the drawing.
    const fixture = container.querySelector('g[transform="translate(6, 5)"]')!;
    expect(image.compareDocumentPosition(fixture) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('rings a fixture whose position is still a guess, and no other', () => {
    plan({ fixtures: [spot(1, 0, 0, ['position_unconfirmed', 'position_source:template']), spot(2, 2, 0, ['position_source:tap'])] });
    expect(screen.getByTestId('plan-guess-ring-1')).toBeTruthy();
    expect(screen.queryByTestId('plan-guess-ring-2')).toBeNull();
  });

  it('still lets a fixture be dragged over the underlay', () => {
    const onFixtureDragStart = vi.fn();
    const { container } = plan({ underlay: UNDERLAY, onFixtureDragStart, onFixtureDrag: vi.fn() });
    const fixture = container.querySelector('g[transform="translate(6, 5)"]')!;
    fireEvent.mouseDown(fixture, { ...onStage(0, 0), button: 0 });
    expect(onFixtureDragStart).toHaveBeenCalledWith(1);
  });

  it('in calibrate mode gives a click as a point in plan metres, and selects nothing', () => {
    const onPlanPick = vi.fn();
    const onFixtureClick = vi.fn();
    const { svg } = plan({ underlay: UNDERLAY, onPlanPick, onFixtureClick });
    fireEvent.click(svg, onStage(2, 1));
    expect(onPlanPick).toHaveBeenCalledTimes(1);
    const [x, z] = onPlanPick.mock.calls[0];
    expect(x).toBeCloseTo(2, 9);
    expect(z).toBeCloseTo(1, 9);
    expect(onFixtureClick).not.toHaveBeenCalled();
  });

  it('in calibrate mode a fixture takes no press', () => {
    const onFixtureDragStart = vi.fn();
    const { container } = plan({ underlay: UNDERLAY, onPlanPick: vi.fn(), onFixtureDragStart });
    const fixture = container.querySelector('g[transform="translate(6, 5)"]')!;
    fireEvent.mouseDown(fixture, { ...onStage(0, 0), button: 0 });
    expect(onFixtureDragStart).not.toHaveBeenCalled();
  });

  it('draws the points picked so far where they are on the plan', () => {
    plan({ underlay: UNDERLAY, pickMarks: [{ x: 2, z: 1, label: 'A' }, { x: 0, z: 0, label: 'O' }] });
    expect(screen.getByTestId('stage-plot-mark-A').getAttribute('transform')).toBe('translate(8, 6)');
    expect(screen.getByTestId('stage-plot-mark-O').textContent).toBe('O');
  });
});
