// The 2D layout view asking for a row's symmetry and spacing to be fixed:
// the M key, and the nudge pad's Mirror and Even buttons and its spacing
// choice for Lay on truss. The plan only asks; the editor makes the move
// (RigBuilderRespace.test.tsx). docs/ROOM_SCAN.md.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import StageView2D from '../components/rig/StageView2D';
import type { RigFixture } from '../types';

const spot = (id: number, x: number, z: number, y = 4) => ({
  id,
  name: `Spot ${id}`,
  dmx_address: id,
  position_x: x,
  position_y: y,
  position_z: z,
  rotation_y: 0,
}) as unknown as RigFixture;

type Props = Parameters<typeof StageView2D>[0];

/** The plan drawn at 10 pixels to the metre: centre stage is at (60, 50) on screen. */
function plan(extra: Partial<Props> = {}) {
  const props = { width: 10, depth: 8, height: 5, fixtures: ROW, selectedIds: new Set<number>(), ...extra };
  const { container } = render(<StageView2D {...props} />);
  const svg = container.querySelector('svg')!;
  const [, , w, h] = svg.getAttribute('viewBox')!.split(' ').map(Number);
  svg.getBoundingClientRect = () => ({
    left: 0, top: 0, right: w * 10, bottom: h * 10, width: w * 10, height: h * 10, x: 0, y: 0, toJSON: () => ({}),
  });
  return svg;
}

const ROW = [spot(1, -1, 0), spot(2, 0, 0), spot(3, 1, 0)];

const grab = (name: string) => screen.getByText(name).parentElement!;
const pad = () => screen.queryByTestId('nudge-pad');
const padButton = (name: string) => within(pad()!).getByRole('button', { name }) as HTMLButtonElement;
const padHas = (name: string) => within(pad()!).queryByRole('button', { name }) !== null;
const press = (key: string, more: Record<string, unknown> = {}) => fireEvent.keyDown(document.body, { key, ...more });

const MIRROR = 'Mirror the selection left to right';
const EVEN = 'Space the selection evenly';
const SPACING = 'Spacing on the truss';
const METRES = 'Metres apart on the truss';

// ---------------------------------------------------------------------------
// The M key
// ---------------------------------------------------------------------------

describe('StageView2D: the M key', () => {
  const added: Element[] = [];
  afterEach(() => {
    cleanup();
    added.splice(0).forEach((element) => element.remove());
  });

  /** Something on the page outside the plan, with the focus on it. */
  function focused(html: string) {
    const holder = document.createElement('div');
    holder.innerHTML = html;
    document.body.appendChild(holder);
    added.push(holder);
    const element = holder.querySelector('#it') as HTMLElement;
    element.focus();
    return element;
  }

  it('asks for the selection to be mirrored, lower case or upper', () => {
    const onMirror = vi.fn();
    plan({ selectedIds: new Set([1, 3]), keyboard: true, onMirror });
    // Taken: the key does not go on to anything else on the page.
    expect(press('m')).toBe(false);
    expect(onMirror).toHaveBeenCalledTimes(1);
    expect(press('M', { shiftKey: true })).toBe(false);
    expect(onMirror).toHaveBeenCalledTimes(2);
  });

  it('only asks: it reports no click, no drag and no selection of its own', () => {
    const calls = {
      onFixtureClick: vi.fn(), onFixtureDragStart: vi.fn(), onFixtureDrag: vi.fn(), onFixturesDrag: vi.fn(),
      onFixtureDragEnd: vi.fn(), onSelectFixtures: vi.fn(), onFixtureSelectRow: vi.fn(),
    };
    plan({ selectedIds: new Set([1, 3]), keyboard: true, onMirror: vi.fn(), ...calls });
    press('m');
    for (const call of Object.values(calls)) expect(call).not.toHaveBeenCalled();
  });

  it('does nothing with nothing selected, and leaves the key alone', () => {
    const onMirror = vi.fn();
    plan({ keyboard: true, onMirror });
    expect(press('m')).toBe(true);
    cleanup();
    // A selection of something that is not in the rig is no selection.
    plan({ selectedIds: new Set([99]), keyboard: true, onMirror });
    expect(press('m')).toBe(true);
    expect(onMirror).not.toHaveBeenCalled();
  });

  it('is one mirror for one press: a key held down does not repeat', () => {
    const onMirror = vi.fn();
    plan({ selectedIds: new Set([1]), keyboard: true, onMirror });
    press('m');
    press('m', { repeat: true });
    press('m', { repeat: true });
    expect(onMirror).toHaveBeenCalledTimes(1);
  });

  it('is left to the browser with Ctrl, Cmd or Alt held', () => {
    const onMirror = vi.fn();
    plan({ selectedIds: new Set([1]), keyboard: true, onMirror });
    expect(press('m', { ctrlKey: true })).toBe(true);
    expect(press('m', { metaKey: true })).toBe(true);
    expect(press('m', { altKey: true })).toBe(true);
    expect(onMirror).not.toHaveBeenCalled();
  });

  it('is not the plan\'s where the keyboard is off, the plan is read-only, or no mirror is offered', () => {
    const onMirror = vi.fn();
    plan({ selectedIds: new Set([1]), onMirror });
    press('m');
    cleanup();
    plan({ selectedIds: new Set([1]), keyboard: true, readonly: true, onMirror });
    press('m');
    expect(onMirror).not.toHaveBeenCalled();
    cleanup();
    // No mirror offered: the key is left alone, as it always was.
    plan({ selectedIds: new Set([1]), keyboard: true });
    expect(press('m')).toBe(true);
  });

  it('is typed, not acted on, in a field, a drop-down or a dialog', () => {
    const onMirror = vi.fn();
    plan({ selectedIds: new Set([1]), keyboard: true, onMirror });
    for (const html of [
      '<input id="it" />',
      '<textarea id="it"></textarea>',
      '<select id="it"><option>Fill truss</option></select>',
      '<div id="it" contenteditable="true"></div>',
      '<div role="dialog"><button id="it">OK</button></div>',
    ]) {
      const element = focused(html);
      expect(fireEvent.keyDown(element, { key: 'm' })).toBe(true);
    }
    expect(onMirror).not.toHaveBeenCalled();
    // With the focus on a plain button it is the plan's again.
    fireEvent.keyDown(focused('<button id="it">Save</button>'), { key: 'm' });
    expect(onMirror).toHaveBeenCalledTimes(1);
  });

  it('does nothing while the pointer is holding a fixture or drawing a box', () => {
    const onMirror = vi.fn();
    const svg = plan({
      selectedIds: new Set([1, 2]), keyboard: true, onMirror,
      onFixtureClick: vi.fn(), onFixturesDrag: vi.fn(), onSelectFixtures: vi.fn(),
    });
    fireEvent.mouseDown(grab('Spot 2'), { clientX: 60, clientY: 50 });
    press('m');
    fireEvent.mouseUp(svg, { clientX: 60, clientY: 50 });
    expect(onMirror).not.toHaveBeenCalled();

    // A press on empty floor, 3 m downstage, that may yet be a box.
    fireEvent.mouseDown(svg, { clientX: 60, clientY: 80 });
    press('m');
    fireEvent.mouseUp(svg, { clientX: 60, clientY: 80 });
    expect(onMirror).not.toHaveBeenCalled();

    // Let go, the key is the plan's again.
    press('m');
    expect(onMirror).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// The nudge pad's Mirror and Even buttons
// ---------------------------------------------------------------------------

describe('StageView2D: Mirror and Even on the nudge pad', () => {
  afterEach(cleanup);

  it('offers each only where it is given', () => {
    plan({ selectedIds: new Set([2]), nudgePad: true });
    expect(padHas(MIRROR)).toBe(false);
    expect(padHas(EVEN)).toBe(false);
    cleanup();
    plan({ selectedIds: new Set([2]), nudgePad: true, onMirror: vi.fn() });
    expect(padHas(MIRROR)).toBe(true);
    expect(padHas(EVEN)).toBe(false);
    cleanup();
    plan({ selectedIds: new Set([2]), nudgePad: true, onSpaceEvenly: vi.fn() });
    expect(padHas(MIRROR)).toBe(false);
    expect(padHas(EVEN)).toBe(true);
  });

  it('names every button and makes each at least 44 pixels each way', () => {
    plan({
      selectedIds: new Set([1, 2, 3]), nudgePad: true, onFixtureSelectRow: vi.fn(), onLayRow: vi.fn(),
      onLayChoiceChange: vi.fn(), onMirror: vi.fn(), onSpaceEvenly: vi.fn(),
    });
    const buttons = within(pad()!).getAllByRole('button') as HTMLButtonElement[];
    expect(buttons.map((button) => button.getAttribute('aria-label'))).toEqual([
      'Nudge upstage', 'Nudge left', 'Nudge right', 'Nudge downstage', 'Ten grid steps for each tap',
      'Select the whole row', 'Lay the selection on the nearest truss', MIRROR, EVEN,
    ]);
    for (const button of buttons) {
      expect(parseFloat(button.style.minWidth)).toBeGreaterThanOrEqual(44);
      expect(parseFloat(button.style.minHeight)).toBeGreaterThanOrEqual(44);
    }
    expect(padButton(MIRROR).textContent).toBe('Mirror');
    expect(padButton(EVEN).textContent).toBe('Even');
  });

  it('asks for a mirror with one tap, for one fixture or several', () => {
    const onMirror = vi.fn();
    plan({ selectedIds: new Set([2]), nudgePad: true, onMirror });
    expect(padButton(MIRROR).disabled).toBe(false);
    fireEvent.click(padButton(MIRROR));
    expect(onMirror).toHaveBeenCalledTimes(1);
  });

  it('does with the Mirror button what the M key does', () => {
    const onMirror = vi.fn();
    plan({ selectedIds: new Set([1, 3]), nudgePad: true, keyboard: true, onMirror });
    fireEvent.click(padButton(MIRROR));
    press('m');
    expect(onMirror.mock.calls).toEqual([[], []]);
  });

  it('spaces evenly only for three or more', () => {
    const onSpaceEvenly = vi.fn();
    plan({ selectedIds: new Set([1, 2]), nudgePad: true, onSpaceEvenly });
    expect(padButton(EVEN).disabled).toBe(true);
    fireEvent.click(padButton(EVEN));
    expect(onSpaceEvenly).not.toHaveBeenCalled();
    cleanup();

    plan({ selectedIds: new Set([1, 2, 3]), nudgePad: true, onSpaceEvenly });
    expect(padButton(EVEN).disabled).toBe(false);
    fireEvent.click(padButton(EVEN));
    expect(onSpaceEvenly).toHaveBeenCalledTimes(1);
  });

  it('asks for nothing while the pointer is holding a fixture', () => {
    const onMirror = vi.fn();
    const onSpaceEvenly = vi.fn();
    const svg = plan({
      selectedIds: new Set([1, 2, 3]), nudgePad: true, onMirror, onSpaceEvenly,
      onFixtureClick: vi.fn(), onFixturesDrag: vi.fn(),
    });
    fireEvent.mouseDown(grab('Spot 2'), { clientX: 60, clientY: 50 });
    fireEvent.click(padButton(MIRROR));
    fireEvent.click(padButton(EVEN));
    expect(onMirror).not.toHaveBeenCalled();
    expect(onSpaceEvenly).not.toHaveBeenCalled();
    fireEvent.mouseUp(svg, { clientX: 60, clientY: 50 });
    fireEvent.click(padButton(MIRROR));
    fireEvent.click(padButton(EVEN));
    expect(onMirror).toHaveBeenCalledTimes(1);
    expect(onSpaceEvenly).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// The nudge pad's spacing choice for Lay on truss
// ---------------------------------------------------------------------------

describe('StageView2D: the spacing choice on the nudge pad', () => {
  afterEach(cleanup);

  const choice = () => within(pad()!).queryByLabelText(SPACING) as HTMLSelectElement | null;
  const metres = () => within(pad()!).queryByLabelText(METRES) as HTMLInputElement | null;

  it('is offered only with Lay on truss, and only where it can be changed', () => {
    plan({ selectedIds: new Set([1, 2]), nudgePad: true, onLayRow: vi.fn() });
    expect(choice()).toBeNull();
    cleanup();
    plan({ selectedIds: new Set([1, 2]), nudgePad: true, onLayChoiceChange: vi.fn() });
    expect(choice()).toBeNull();
    cleanup();
    plan({ selectedIds: new Set([1, 2]), nudgePad: true, onLayRow: vi.fn(), onLayChoiceChange: vi.fn() });
    expect(choice()).not.toBeNull();
  });

  it('fills the truss unless told otherwise, and offers the three ways', () => {
    plan({ selectedIds: new Set([1, 2]), nudgePad: true, onLayRow: vi.fn(), onLayChoiceChange: vi.fn() });
    expect(choice()!.value).toBe('fill');
    expect([...choice()!.options].map((option) => [option.value, option.textContent])).toEqual([
      ['fill', 'Fill truss'], ['keep', 'Keep spacing'], ['set', 'Set spacing'],
    ]);
    // A fingertip high, like the buttons.
    expect(parseFloat(choice()!.style.minHeight)).toBeGreaterThanOrEqual(44);
    // No metres to type until a spacing is to be set.
    expect(metres()).toBeNull();
  });

  it('reports a change of mode, keeping the metres that were typed', () => {
    const onLayChoiceChange = vi.fn();
    plan({
      selectedIds: new Set([1, 2]), nudgePad: true, onLayRow: vi.fn(), onLayChoiceChange,
      layChoice: { mode: 'fill', metres: '0.8' },
    });
    fireEvent.change(choice()!, { target: { value: 'keep' } });
    fireEvent.change(choice()!, { target: { value: 'set' } });
    expect(onLayChoiceChange.mock.calls).toEqual([
      [{ mode: 'keep', metres: '0.8' }], [{ mode: 'set', metres: '0.8' }],
    ]);
  });

  it('shows the mode it is given, and the metres to type when a spacing is set', () => {
    const onLayChoiceChange = vi.fn();
    plan({
      selectedIds: new Set([1, 2]), nudgePad: true, onLayRow: vi.fn(), onLayChoiceChange,
      layChoice: { mode: 'set', metres: '1.5' },
    });
    expect(choice()!.value).toBe('set');
    expect(metres()!.value).toBe('1.5');
    expect(parseFloat(metres()!.style.minHeight)).toBeGreaterThanOrEqual(44);
    fireEvent.change(metres()!, { target: { value: '0.75' } });
    expect(onLayChoiceChange.mock.calls).toEqual([[{ mode: 'set', metres: '0.75' }]]);
    cleanup();

    plan({
      selectedIds: new Set([1, 2]), nudgePad: true, onLayRow: vi.fn(), onLayChoiceChange,
      layChoice: { mode: 'keep', metres: '1.5' },
    });
    expect(choice()!.value).toBe('keep');
    expect(metres()).toBeNull();
  });

  it('keeps its keys: a letter typed in it is not the plan\'s', () => {
    const onMirror = vi.fn();
    const onFixtureSelectRow = vi.fn();
    plan({
      selectedIds: new Set([1, 2]), nudgePad: true, keyboard: true, onLayRow: vi.fn(), onLayChoiceChange: vi.fn(),
      layChoice: { mode: 'set', metres: '1' }, onMirror, onFixtureSelectRow,
    });
    fireEvent.keyDown(metres()!, { key: 'm' });
    fireEvent.keyDown(choice()!, { key: 'm' });
    fireEvent.keyDown(choice()!, { key: 'r' });
    expect(onMirror).not.toHaveBeenCalled();
    expect(onFixtureSelectRow).not.toHaveBeenCalled();
  });

  it('lays the row from the button whatever is chosen: the choice is the editor\'s to read', () => {
    const onLayRow = vi.fn();
    plan({
      selectedIds: new Set([1, 2]), nudgePad: true, onLayRow, onLayChoiceChange: vi.fn(),
      layChoice: { mode: 'keep', metres: '1' },
    });
    fireEvent.click(padButton('Lay the selection on the nearest truss'));
    expect(onLayRow).toHaveBeenCalledTimes(1);
  });
});
