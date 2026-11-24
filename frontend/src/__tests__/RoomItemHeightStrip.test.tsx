// The height strip beside the 2D plan (slice 22): the handles a raised area,
// a truss line and a ring have, a drag drawn as it goes with its live value,
// one call when it is let go, and the handle put back when the change is
// refused. The numbers are tested in roomItemHeight.test.ts. docs/ROOM_SCAN.md.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import RoomItemHeightStrip from '../components/rig/RoomItemHeightStrip';
import { heightGauge } from '../components/rig/roomItemHeight';
import { shellItems } from '../utils/roomShellEdit';
import type { RoomShell } from '../types';

/** A scanned room 6 m high: a stage, a balcony floating 2.7 m up, a truss at 4.2 m and a ring at 5 m. */
const SHELL = (trim = 4.2): RoomShell => ({
  source: 'scan',
  room: { width: 12, depth: 10, height: 6 },
  risers: [
    { center_x: 0, center_z: -3.5, width: 6, depth: 3, height: 0.6, name: 'Stage', kind: 'stage' },
    { center_x: 0, center_z: 4, width: 4, depth: 2, height: 0.3, base_height: 2.7, name: 'Balcony', kind: 'riser' },
  ],
  truss_lines: [{ name: 'Truss 1', x1: -4, z1: 1, x2: 4, z2: 1, height: trim, across: 0.3 }],
  truss_rings: [{ name: 'Ring 1', center_x: 0, center_z: 0, radius: 2, height: 5, across: 0.3 }],
}) as unknown as RoomShell;

const gaugeOf = (key: string, shell: RoomShell = SHELL()) => {
  const [kind, index] = key.split(':');
  return heightGauge(shellItems(shell).find((item) => item.kind === kind && item.index === Number(index)), shell);
};

// The strip is 320 units high with 272 of them from the floor to the top of its scale. With no
// layout a unit is a pixel, so in this 6 m room a metre is 272 / 6 pixels.
const PX_PER_M = 272 / 6;
const DOWN_Y = 200;

/**
 * A pointer event built by hand, with the pointer's own fields written onto
 * it, so it reads the same whether or not the test environment knows what a
 * PointerEvent is.
 */
function pointer(
  type: 'pointerdown' | 'pointermove' | 'pointerup' | 'pointercancel',
  target: Element | Window, clientY: number,
  more: { pointerType?: string; pointerId?: number; shiftKey?: boolean; clientX?: number; button?: number } = {},
) {
  const event = new MouseEvent(type, {
    bubbles: true, cancelable: true, clientX: more.clientX ?? 50, clientY, shiftKey: more.shiftKey ?? false,
    button: more.button ?? 0,
  });
  Object.defineProperty(event, 'pointerType', { value: more.pointerType ?? 'mouse' });
  Object.defineProperty(event, 'pointerId', { value: more.pointerId ?? 1 });
  return fireEvent(target as Element, event);
}

const handle = (grip: string) => screen.getByTestId(`item-height-handle-${grip}`);
const valueOf = (grip: string) => Number(handle(grip).getAttribute('data-value'));
const readout = () => screen.getByTestId('item-height-readout').textContent;
const flush = () => act(async () => {});

/** Presses a handle and carries it `metres` up (down for less than 0), without letting go. */
function lift(grip: string, metres: number, more: { shiftKey?: boolean; pointerType?: string } = {}) {
  pointer('pointerdown', handle(grip), DOWN_Y, more);
  pointer('pointermove', window, DOWN_Y - metres * PX_PER_M, more);
}
const letGo = (more: { pointerType?: string } = {}) => pointer('pointerup', window, 0, more);

describe('RoomItemHeightStrip', () => {
  afterEach(cleanup);

  it('says what it is for when nothing is selected, and has no handle', () => {
    render(<RoomItemHeightStrip gauge={null} />);
    expect(screen.getByTestId('item-height-strip')).toBeTruthy();
    expect(screen.getByTestId('item-height-empty').textContent).toContain('Select a raised area, a truss line or a ring');
    expect(screen.queryByTestId('item-height-svg')).toBeNull();
    expect(screen.queryByTestId('item-height-handle-trim')).toBeNull();
  });

  it('gives a truss line one trim handle where it hangs, under the ceiling', () => {
    render(<RoomItemHeightStrip gauge={gaugeOf('truss_lines:0')} />);
    expect(screen.getByTestId('item-height-title').textContent).toBe('Height: Truss 1');
    expect(valueOf('trim')).toBe(4.2);
    expect(handle('trim').textContent).toContain('Trim');
    expect(handle('trim').textContent).toContain('4.20');
    expect(screen.queryByTestId('item-height-handle-top')).toBeNull();
    expect(screen.queryByTestId('item-height-handle-base')).toBeNull();
    expect(screen.getByTestId('item-height-ceiling').textContent).toBe('ceiling 6.00 m');
    // 4.2 m of 6, up from the floor at 296: 296 - 0.7 * 272.
    expect(handle('trim').getAttribute('transform')).toBe(`translate(60, ${296 - (4.2 / 6) * 272})`);
  });

  it('gives a ring the same', () => {
    render(<RoomItemHeightStrip gauge={gaugeOf('truss_rings:0')} />);
    expect(valueOf('trim')).toBe(5);
  });

  it('gives a raised area a top and a base, side by side', () => {
    render(<RoomItemHeightStrip gauge={gaugeOf('risers:1')} />);
    expect(valueOf('top')).toBe(3);
    expect(valueOf('base')).toBe(2.7);
    expect(screen.queryByTestId('item-height-handle-trim')).toBeNull();
    // Not one over the other, however thin the deck is.
    expect(handle('top').getAttribute('transform')).toMatch(/^translate\(90, /);
    expect(handle('base').getAttribute('transform')).toMatch(/^translate\(30, /);
  });

  it('draws a drag as it goes with the live value, and reports it once when it is let go', async () => {
    const onChange = vi.fn();
    render(<RoomItemHeightStrip gauge={gaugeOf('truss_lines:0')} onChange={onChange} />);

    lift('trim', 0.31);
    expect(valueOf('trim')).toBe(4.5);
    expect(readout()).toBe('trim 4.50 m');
    pointer('pointermove', window, DOWN_Y - 0.62 * PX_PER_M);
    expect(valueOf('trim')).toBe(4.8);
    expect(readout()).toBe('trim 4.80 m');
    // Nothing is sent while it is held.
    expect(onChange).not.toHaveBeenCalled();

    letGo();
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('truss_lines', 0, { height: 4.8 });
    await flush();
    // The answer is in and the room given is drawn: this one still has it at 4.2.
    expect(valueOf('trim')).toBe(4.2);
    expect(readout()).toBe('Drag a handle up or down');
  });

  it('goes down as well as up, and no lower than a truss can hang', () => {
    const onChange = vi.fn();
    render(<RoomItemHeightStrip gauge={gaugeOf('truss_lines:0')} onChange={onChange} />);
    lift('trim', -1);
    expect(valueOf('trim')).toBe(3.2);
    pointer('pointermove', window, DOWN_Y + 9 * PX_PER_M);
    expect(valueOf('trim')).toBe(0.5);
    letGo();
    expect(onChange).toHaveBeenCalledWith('truss_lines', 0, { height: 0.5 });
  });

  it('snaps to 0.25 m with Shift held', () => {
    const onChange = vi.fn();
    render(<RoomItemHeightStrip gauge={gaugeOf('truss_lines:0')} onChange={onChange} />);
    lift('trim', 0.4, { shiftKey: true });
    expect(valueOf('trim')).toBe(4.5);
    // Without it the same place is 4.6.
    pointer('pointermove', window, DOWN_Y - 0.4 * PX_PER_M);
    expect(valueOf('trim')).toBe(4.6);
    pointer('pointermove', window, DOWN_Y - 0.4 * PX_PER_M, { shiftKey: true });
    letGo();
    expect(onChange).toHaveBeenCalledWith('truss_lines', 0, { height: 4.5 });
  });

  it('has a button for the coarse step, for a finger that has no Shift', () => {
    const onChange = vi.fn();
    render(<RoomItemHeightStrip gauge={gaugeOf('truss_lines:0')} onChange={onChange} />);
    const step = screen.getByTestId('item-height-step');
    expect(step.textContent).toBe('Step 0.05 m');
    fireEvent.click(step);
    expect(step.textContent).toBe('Step 0.25 m');
    expect(step.getAttribute('aria-pressed')).toBe('true');

    lift('trim', 0.4, { pointerType: 'touch' });
    expect(valueOf('trim')).toBe(4.5);
    letGo({ pointerType: 'touch' });
    expect(onChange).toHaveBeenCalledWith('truss_lines', 0, { height: 4.5 });
  });

  it('sends nothing for a press that stays within 5 pixels', () => {
    const onChange = vi.fn();
    render(<RoomItemHeightStrip gauge={gaugeOf('truss_lines:0')} onChange={onChange} />);
    pointer('pointerdown', handle('trim'), DOWN_Y);
    pointer('pointermove', window, DOWN_Y - 4);
    expect(valueOf('trim')).toBe(4.2);
    expect(readout()).toBe('Drag a handle up or down');
    letGo();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('sends nothing for a drag brought back to where it began', () => {
    const onChange = vi.fn();
    render(<RoomItemHeightStrip gauge={gaugeOf('truss_lines:0')} onChange={onChange} />);
    lift('trim', 0.5);
    expect(valueOf('trim')).toBe(4.7);
    pointer('pointermove', window, DOWN_Y - 0.01 * PX_PER_M);
    expect(valueOf('trim')).toBe(4.2);
    letGo();
    expect(onChange).not.toHaveBeenCalled();
    expect(readout()).toBe('Drag a handle up or down');
  });

  it('goes on with the drag when the pointer leaves the strip sideways', () => {
    const onChange = vi.fn();
    render(<RoomItemHeightStrip gauge={gaugeOf('truss_lines:0')} onChange={onChange} />);
    pointer('pointerdown', handle('trim'), DOWN_Y);
    pointer('pointermove', window, DOWN_Y - 0.5 * PX_PER_M, { clientX: 900 });
    expect(valueOf('trim')).toBe(4.7);
    pointer('pointerup', window, DOWN_Y - 0.5 * PX_PER_M, { clientX: 900 });
    expect(onChange).toHaveBeenCalledWith('truss_lines', 0, { height: 4.7 });
  });

  it('takes a finger as it takes a mouse, and prevents the press so the page does not pan', () => {
    const onChange = vi.fn();
    render(<RoomItemHeightStrip gauge={gaugeOf('truss_lines:0')} onChange={onChange} />);
    // False: the press was prevented.
    expect(pointer('pointerdown', handle('trim'), DOWN_Y, { pointerType: 'touch' })).toBe(false);
    // Another finger is not this one.
    pointer('pointermove', window, DOWN_Y - 2 * PX_PER_M, { pointerType: 'touch', pointerId: 2 });
    expect(valueOf('trim')).toBe(4.2);
    pointer('pointermove', window, DOWN_Y - 0.3 * PX_PER_M, { pointerType: 'touch' });
    expect(valueOf('trim')).toBe(4.5);
    letGo({ pointerType: 'touch' });
    expect(onChange).toHaveBeenCalledWith('truss_lines', 0, { height: 4.5 });
  });

  it('sends nothing when the browser takes the finger away', () => {
    const onChange = vi.fn();
    render(<RoomItemHeightStrip gauge={gaugeOf('truss_lines:0')} onChange={onChange} />);
    lift('trim', 0.5, { pointerType: 'touch' });
    pointer('pointercancel', window, 0, { pointerType: 'touch' });
    expect(onChange).not.toHaveBeenCalled();
    expect(valueOf('trim')).toBe(4.2);
    // And the press is over: a later move carries nothing.
    pointer('pointermove', window, DOWN_Y - 1 * PX_PER_M, { pointerType: 'touch' });
    expect(valueOf('trim')).toBe(4.2);
  });

  it('takes no press from a mouse button other than the first', () => {
    const onChange = vi.fn();
    render(<RoomItemHeightStrip gauge={gaugeOf('truss_lines:0')} onChange={onChange} />);
    pointer('pointerdown', handle('trim'), DOWN_Y, { button: 2 });
    pointer('pointermove', window, DOWN_Y - 1 * PX_PER_M);
    letGo();
    expect(valueOf('trim')).toBe(4.2);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('sets a raised area\'s deck from its top handle, and leaves its base where it is', () => {
    const onChange = vi.fn();
    render(<RoomItemHeightStrip gauge={gaugeOf('risers:0')} onChange={onChange} />);

    lift('top', 0.4);
    expect(valueOf('top')).toBe(1);
    // The base stays where it is.
    expect(valueOf('base')).toBe(0);
    expect(readout()).toBe('top 1.00 m');
    letGo();
    expect(onChange).toHaveBeenLastCalledWith('risers', 0, { height: 1 });
  });

  it('carries the whole of a raised area with its base handle, as thick as it was', async () => {
    const onChange = vi.fn();
    render(<RoomItemHeightStrip gauge={gaugeOf('risers:0')} onChange={onChange} />);
    lift('base', 2.7);
    expect(valueOf('base')).toBe(2.7);
    expect(valueOf('top')).toBe(3.3);
    expect(readout()).toBe('base 2.70 m');
    letGo();
    expect(onChange).toHaveBeenCalledWith('risers', 0, { base_height: 2.7 });
  });

  it('brings a floating platform down to the floor, and sends its deck above its base from its top', () => {
    const onChange = vi.fn();
    render(<RoomItemHeightStrip gauge={gaugeOf('risers:1')} onChange={onChange} />);
    lift('base', -5);
    expect(valueOf('base')).toBe(0);
    expect(valueOf('top')).toBe(0.3);
    expect(readout()).toBe('on the floor');
    letGo();
    expect(onChange).toHaveBeenLastCalledWith('risers', 1, { base_height: 0 });
  });

  it('keeps the handle where it was dropped until the answer, then draws the room it is given', async () => {
    let answer: () => void = () => {};
    const onChange = vi.fn(() => new Promise<void>((resolve) => { answer = resolve; }));
    const view = render(<RoomItemHeightStrip gauge={gaugeOf('truss_lines:0')} onChange={onChange} />);
    lift('trim', 0.3);
    letGo();
    await flush();
    // Not answered yet: still where it was dropped, and no second drag begins from the old room.
    expect(valueOf('trim')).toBe(4.5);
    lift('trim', 1);
    letGo();
    expect(onChange).toHaveBeenCalledTimes(1);

    // The server stored it: the room given has the truss at 4.5.
    view.rerender(<RoomItemHeightStrip gauge={gaugeOf('truss_lines:0', SHELL(4.5))} onChange={onChange} />);
    await act(async () => { answer(); });
    expect(valueOf('trim')).toBe(4.5);
    expect(readout()).toBe('Drag a handle up or down');
  });

  it('puts the handle back when the change is refused', async () => {
    let refuse: (reason: unknown) => void = () => {};
    const onChange = vi.fn(() => new Promise<void>((_resolve, reject) => { refuse = reject; }));
    render(<RoomItemHeightStrip gauge={gaugeOf('truss_lines:0')} onChange={onChange} />);
    lift('trim', 1.5);
    letGo();
    await flush();
    expect(valueOf('trim')).toBe(5.7);

    await act(async () => { refuse(new Error('422')); });
    // The room was not changed, so the same room is drawn: back at 4.2.
    expect(valueOf('trim')).toBe(4.2);
    expect(readout()).toBe('Drag a handle up or down');
    // And it can be dragged again.
    lift('trim', 0.3);
    expect(valueOf('trim')).toBe(4.5);
  });

  it('does not draw one item\'s drop on another', async () => {
    const onChange = vi.fn(() => new Promise<void>(() => {}));
    const view = render(<RoomItemHeightStrip gauge={gaugeOf('truss_lines:0')} onChange={onChange} />);
    lift('trim', 0.3);
    letGo();
    view.rerender(<RoomItemHeightStrip gauge={gaugeOf('truss_rings:0')} onChange={onChange} />);
    expect(valueOf('trim')).toBe(5);
  });
});
