import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import FixtureProperties from '../components/rig/FixtureProperties';
import { panTiltFromDmx } from '../components/rig/previs/hangFlags';
import type { RigFixture } from '../types';

function patch(overrides: Partial<RigFixture> = {}): RigFixture {
  return {
    id: 7,
    rig_id: 1,
    fixture_id: 3,
    name: 'Head R1',
    universe: 0,
    dmx_address: 21,
    position_x: 3,
    position_y: 5,
    position_z: 0,
    rotation_x: 0,
    rotation_y: 0,
    rotation_z: 0,
    tags: [],
    is_active: true,
    is_inverted: false,
    is_address_locked: false,
    ...overrides,
  };
}

// label, what switching it on sends, what switching it off sends
const TOGGLES: Array<[string, Partial<RigFixture>, Partial<RigFixture>]> = [
  ['Invert pan', { pan_invert: true }, { pan_invert: false }],
  ['Invert tilt', { tilt_invert: true }, { tilt_invert: false }],
  ['Swap pan/tilt', { pan_tilt_swap: true }, { pan_tilt_swap: false }],
];

describe('FixtureProperties hang toggles', () => {
  afterEach(cleanup);

  it('shows all three off for a patch saved before the flags existed', () => {
    render(<FixtureProperties fixture={patch()} onChange={vi.fn()} />);

    for (const [label] of TOGGLES) {
      expect((screen.getByLabelText(label) as HTMLInputElement).checked).toBe(false);
    }
  });

  it.each(TOGGLES)('%s sends only its own flag', (label, on) => {
    const onChange = vi.fn();
    render(<FixtureProperties fixture={patch()} onChange={onChange} />);

    fireEvent.click(screen.getByLabelText(label));

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(on);
  });

  it.each(TOGGLES)('%s can be turned back off', (label, on, off) => {
    const onChange = vi.fn();
    render(<FixtureProperties fixture={patch(on)} onChange={onChange} />);

    const toggle = screen.getByLabelText(label) as HTMLInputElement;
    expect(toggle.checked).toBe(true);
    fireEvent.click(toggle);

    expect(onChange).toHaveBeenCalledWith(off);
  });

  it('shows each flag on its own switch', () => {
    render(<FixtureProperties fixture={patch({ tilt_invert: true })} onChange={vi.fn()} />);

    expect((screen.getByLabelText('Invert pan') as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText('Invert tilt') as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText('Swap pan/tilt') as HTMLInputElement).checked).toBe(false);
  });
});

describe('panTiltFromDmx', () => {
  const out = { pan: 0, tilt: 0 };
  // pan 100 of 540 is 44904 = (175, 104); tilt -40 of 270 is 23059 = (90, 19).
  const PAN = 44904 / 65535;
  const TILT = 23059 / 65535;

  it('reads the channels plainly when no flag is set', () => {
    panTiltFromDmx({ coarse: 175, fine: 104 }, { coarse: 90, fine: 19 }, {}, out);
    expect(out.pan).toBeCloseTo(PAN, 9);
    expect(out.tilt).toBeCloseTo(TILT, 9);

    panTiltFromDmx({ coarse: 55 }, { coarse: 200 }, {}, out);
    expect(out.pan).toBeCloseTo(55 / 255, 9);
    expect(out.tilt).toBeCloseTo(200 / 255, 9);
  });

  it('undoes an invert, fine byte included', () => {
    // What the engine sends for the same look with pan inverted: 65535 - 44904.
    panTiltFromDmx({ coarse: 80, fine: 151 }, { coarse: 90, fine: 19 }, { panInvert: true }, out);
    expect(out.pan).toBeCloseTo(PAN, 9);
    expect(out.tilt).toBeCloseTo(TILT, 9);

    panTiltFromDmx({ coarse: 175, fine: 104 }, { coarse: 165, fine: 236 }, { tiltInvert: true }, out);
    expect(out.pan).toBeCloseTo(PAN, 9);
    expect(out.tilt).toBeCloseTo(TILT, 9);

    panTiltFromDmx({ coarse: 200 }, { coarse: 200 }, { panInvert: true }, out);
    expect(out.pan).toBeCloseTo(55 / 255, 9);
  });

  it('undoes a swap, and an invert on top of one', () => {
    // Swapped: tilt's value rides the pan channels and pan's the tilt channels.
    panTiltFromDmx({ coarse: 90, fine: 19 }, { coarse: 175, fine: 104 }, { swap: true }, out);
    expect(out.pan).toBeCloseTo(PAN, 9);
    expect(out.tilt).toBeCloseTo(TILT, 9);

    panTiltFromDmx(
      { coarse: 90, fine: 19 },
      { coarse: 80, fine: 151 },
      { swap: true, panInvert: true },
      out
    );
    expect(out.pan).toBeCloseTo(PAN, 9);
    expect(out.tilt).toBeCloseTo(TILT, 9);
  });

  it('draws a mixed-hang pair as mirror images', () => {
    // A mirrored look sends an inverted right-hand head the same bytes as the
    // left; drawn raw they would sweep together instead of mirroring.
    const left = panTiltFromDmx({ coarse: 175, fine: 104 }, { coarse: 90, fine: 19 }, {}, { pan: 0, tilt: 0 });
    const right = panTiltFromDmx(
      { coarse: 175, fine: 104 },
      { coarse: 90, fine: 19 },
      { panInvert: true },
      { pan: 0, tilt: 0 }
    );

    expect(right.pan - 0.5).toBeCloseTo(-(left.pan - 0.5), 9);
    expect(right.tilt).toBeCloseTo(left.tilt, 9);
  });
});
