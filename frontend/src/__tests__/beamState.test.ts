import { describe, expect, it } from 'vitest';
import {
  buildBeamProfile,
  buildChannelMap,
  isPositionUnconfirmed,
  readBeamState,
  resolveInvert,
  wheelColor,
} from '../components/rig/previs/beamState';
import type { BeamFixtureInput, ChannelValueRange } from '../components/rig/previs/beamState';

type ChannelSpec = string | { type: string; ranges: ChannelValueRange[] };

/** A patched fixture whose channels run in the order given, from channel 1. */
function fixtureOf(
  channels: ChannelSpec[],
  extra: Partial<NonNullable<BeamFixtureInput['fixture']>> = {},
  patch: Pick<BeamFixtureInput, 'tags' | 'is_inverted'> = {},
): BeamFixtureInput {
  return {
    ...patch,
    fixture: {
      fixture_type: 'moving_head',
      pan_range: 540,
      tilt_range: 270,
      ...extra,
      modes: [{
        id: 1,
        channels: channels.map((spec, index) => ({
          channel_number: index + 1,
          channel_type: typeof spec === 'string' ? spec : spec.type,
          name: typeof spec === 'string' ? spec : spec.type,
          value_ranges: typeof spec === 'string' ? null : spec.ranges,
        })),
      }],
    },
  };
}

/** A universe with these values written from a 1-based start address. */
function frameAt(start: number, values: number[]): number[] {
  const frame = new Array(512).fill(0);
  values.forEach((value, index) => { frame[start - 1 + index] = value; });
  return frame;
}

// The demo rigs' moving head, as backend/app/services/demo/venue_presets.py
// lays its 16 channels out.
const MOVER = [
  'pan', 'pan_fine', 'tilt', 'tilt_fine', 'speed', 'dimmer', 'shutter',
  'red', 'green', 'blue', 'white', 'color_wheel', 'gobo', 'gobo_rotation', 'prism', 'focus',
];

/** The bytes the engine writes for an angle on a 16-bit axis: _render_fixture's own sum. */
function axisBytes(deg: number, rangeDeg: number): [number, number] {
  const word = Math.round(Math.max(0, Math.min(1, (deg + rangeDeg / 2) / rangeDeg)) * 65535);
  return [(word >> 8) & 0xff, word & 0xff];
}

function moverFrame(start: number, set: Partial<Record<string, number>>): number[] {
  return frameAt(start, MOVER.map((name) => set[name] ?? 0));
}

describe('beam state from a DMX frame', () => {
  it('reads level, colour, pan and tilt at the fixture\'s own address', () => {
    const profile = buildBeamProfile(fixtureOf(MOVER));
    const [pan, panFine] = axisBytes(90, 540);
    const [tilt, tiltFine] = axisBytes(-45, 270);
    const state = readBeamState(profile, moverFrame(33, {
      pan, pan_fine: panFine, tilt, tilt_fine: tiltFine, dimmer: 255, shutter: 255, red: 255, green: 128,
    }), 33);

    expect(state.hasSignal).toBe(true);
    expect(state.lit).toBe(true);
    expect(state.intensity).toBe(1);
    expect(state.shutter).toBe('open');
    expect(state.r).toBe(1);
    expect(state.g).toBeCloseTo(128 / 255, 6);
    expect(state.b).toBe(0);
    expect(state.panDeg).toBeCloseTo(90, 1);
    expect(state.tiltDeg).toBeCloseTo(-45, 1);
  });

  it('writes 170/170 for +90 degrees of a 540 degree pan, as the engine does', () => {
    expect(axisBytes(90, 540)).toEqual([170, 170]);
    const profile = buildBeamProfile(fixtureOf(MOVER));
    const state = readBeamState(profile, moverFrame(1, { pan: 170, pan_fine: 170 }), 1);
    expect(state.panDeg).toBeCloseTo(90, 2);
  });

  it('turns the other way on an inverted axis, and only on that axis', () => {
    const [pan, panFine] = axisBytes(90, 540);
    const [tilt, tiltFine] = axisBytes(30, 270);
    const frame = moverFrame(1, { pan, pan_fine: panFine, tilt, tilt_fine: tiltFine });

    const panInverted = readBeamState(buildBeamProfile(fixtureOf(MOVER, {}, { tags: ['pan_invert'] })), frame, 1);
    expect(panInverted.panDeg).toBeCloseTo(-90, 1);
    expect(panInverted.tiltDeg).toBeCloseTo(30, 1);

    const tiltInverted = readBeamState(buildBeamProfile(fixtureOf(MOVER, {}, { tags: ['tilt_invert'] })), frame, 1);
    expect(tiltInverted.panDeg).toBeCloseTo(90, 1);
    expect(tiltInverted.tiltDeg).toBeCloseTo(-30, 1);

    const both = readBeamState(buildBeamProfile(fixtureOf(MOVER), { pan: true, tilt: true }), frame, 1);
    expect(both.panDeg).toBeCloseTo(-90, 1);
    expect(both.tiltDeg).toBeCloseTo(-30, 1);
  });

  it('reads the rig\'s single invert flag as pan, and two inverts of one axis as none', () => {
    expect(resolveInvert({ is_inverted: true })).toEqual({ pan: true, tilt: false });
    expect(resolveInvert({ tags: ['tilt_invert'] })).toEqual({ pan: false, tilt: true });
    expect(resolveInvert({ tags: ['pan_invert'], is_inverted: true })).toEqual({ pan: false, tilt: false });
    expect(resolveInvert({})).toEqual({ pan: false, tilt: false });
  });

  it('shows no beam while the shutter is closed, whatever the dimmer says', () => {
    const profile = buildBeamProfile(fixtureOf(MOVER));
    const state = readBeamState(profile, moverFrame(1, { dimmer: 255, shutter: 0, red: 255, green: 255, blue: 255 }), 1);
    expect(state.shutter).toBe('closed');
    expect(state.dimmer).toBe(1);
    expect(state.intensity).toBe(0);
    expect(state.lit).toBe(false);
  });

  it('takes 255 on an unlabelled shutter as open: it is what the engine writes', () => {
    const profile = buildBeamProfile(fixtureOf(MOVER));
    const state = readBeamState(profile, moverFrame(1, { dimmer: 200, shutter: 255, blue: 255 }), 1);
    expect(state.shutter).toBe('open');
    expect(state.strobeRate).toBe(0);
    expect(state.lit).toBe(true);
  });

  it('reads a mid shutter value as a strobe, faster as it rises', () => {
    const profile = buildBeamProfile(fixtureOf(MOVER));
    const slow = readBeamState(profile, moverFrame(1, { dimmer: 255, shutter: 40, red: 255 }), 1).strobeRate;
    const fast = readBeamState(profile, moverFrame(1, { dimmer: 255, shutter: 220, red: 255 }), 1).strobeRate;
    expect(slow).toBeGreaterThan(0);
    expect(fast).toBeGreaterThan(slow);
    expect(readBeamState(profile, moverFrame(1, { dimmer: 255, shutter: 40, red: 255 }), 1).shutter).toBe('strobe');
  });

  it('follows the profile\'s own shutter ranges when it names them', () => {
    const shutter = {
      type: 'shutter',
      ranges: [
        { name: 'Shutter closed', min_value: 0, max_value: 19 },
        { name: 'Shutter open', min_value: 20, max_value: 49 },
        { name: 'Strobe slow to fast', min_value: 50, max_value: 200 },
        { name: 'Shutter open', min_value: 201, max_value: 255 },
      ],
    };
    const profile = buildBeamProfile(fixtureOf(['dimmer', shutter]));
    const at = (value: number) => readBeamState(profile, frameAt(1, [255, value]), 1);
    expect(at(10).shutter).toBe('closed');
    expect(at(10).lit).toBe(false);
    // 30 would be a strobe by the unlabelled rule; this profile says open.
    expect(at(30).shutter).toBe('open');
    expect(at(30).lit).toBe(true);
    expect(at(125).shutter).toBe('strobe');
    expect(at(125).strobeRate).toBeCloseTo(0.5, 2);
    expect(at(255).shutter).toBe('open');
  });

  it('does not call 0 on a strobe channel closed', () => {
    const profile = buildBeamProfile(fixtureOf(['dimmer', 'strobe', 'red', 'green', 'blue']));
    const steady = readBeamState(profile, frameAt(1, [255, 0, 255, 0, 0]), 1);
    expect(steady.shutter).toBe('open');
    expect(steady.lit).toBe(true);
    const flashing = readBeamState(profile, frameAt(1, [255, 128, 255, 0, 0]), 1);
    expect(flashing.shutter).toBe('strobe');
    expect(flashing.strobeRate).toBeCloseTo(128 / 255, 3);
  });

  it('is dark on a frame at grand master zero, with the head left where it was', () => {
    const profile = buildBeamProfile(fixtureOf(MOVER));
    const [pan, panFine] = axisBytes(120, 540);
    // What _render_fixture writes at master 0: dimmer 0, colour and position kept.
    const state = readBeamState(profile, moverFrame(1, {
      pan, pan_fine: panFine, dimmer: 0, shutter: 255, red: 255, green: 40,
    }), 1);
    expect(state.lit).toBe(false);
    expect(state.intensity).toBe(0);
    expect(state.panDeg).toBeCloseTo(120, 1);
  });

  it('is dark on a blacked-out frame of zeros', () => {
    const profile = buildBeamProfile(fixtureOf(MOVER));
    expect(readBeamState(profile, new Array(512).fill(0), 1).lit).toBe(false);
  });

  it('carries the level in the colour on a fixture with no dimmer channel', () => {
    const profile = buildBeamProfile(fixtureOf(['red', 'green', 'blue'], { fixture_type: 'led_par', pan_range: 0, tilt_range: 0 }));
    const half = readBeamState(profile, frameAt(10, [128, 0, 0]), 10);
    expect(half.intensity).toBe(1);
    expect(half.r).toBeCloseTo(128 / 255, 6);
    expect(half.lit).toBe(true);
    expect(readBeamState(profile, frameAt(10, [0, 0, 0]), 10).lit).toBe(false);
  });

  it('lights a white-only fixture and adds white and amber to a mix', () => {
    const whiteOnly = buildBeamProfile(fixtureOf(['dimmer', 'white']));
    const white = readBeamState(whiteOnly, frameAt(1, [255, 255]), 1);
    expect([white.r, white.g, white.b]).toEqual([1, 1, 1]);
    expect(white.lit).toBe(true);

    const rgbwa = buildBeamProfile(fixtureOf(['dimmer', 'red', 'green', 'blue', 'white', 'amber']));
    const amber = readBeamState(rgbwa, frameAt(1, [255, 0, 0, 0, 0, 255]), 1);
    expect(amber.r).toBe(1);
    expect(amber.g).toBeCloseTo(0.75, 6);
    expect(amber.b).toBe(0);
  });

  it('mixes cyan, magenta and yellow subtractively: 0 is open', () => {
    const profile = buildBeamProfile(fixtureOf(['dimmer', 'cyan', 'magenta', 'yellow']));
    const open = readBeamState(profile, frameAt(1, [255, 0, 0, 0]), 1);
    expect([open.r, open.g, open.b]).toEqual([1, 1, 1]);
    expect(open.colorSource).toBe('cmy');
    const red = readBeamState(profile, frameAt(1, [255, 0, 255, 255]), 1);
    expect([red.r, red.g, red.b]).toEqual([1, 0, 0]);
  });

  it('ignores parked cyan, magenta and yellow beside red, green and blue emitters', () => {
    const profile = buildBeamProfile(fixtureOf(['dimmer', 'red', 'green', 'blue', 'cyan', 'magenta', 'yellow']));
    const state = readBeamState(profile, frameAt(1, [255, 0, 255, 0, 255, 255, 255]), 1);
    expect([state.r, state.g, state.b]).toEqual([0, 1, 0]);
    expect(state.colorSource).toBe('rgb');
  });

  it('filters through a colour wheel slot the profile names, and leaves an unnamed wheel open', () => {
    const wheel = {
      type: 'color_wheel',
      ranges: [
        { name: 'Open', min_value: 0, max_value: 9 },
        { name: 'Red', min_value: 10, max_value: 19 },
        { name: 'Light Blue', min_value: 20, max_value: 29 },
      ],
    };
    const named = buildBeamProfile(fixtureOf(['dimmer', wheel]));
    const open = readBeamState(named, frameAt(1, [255, 5]), 1);
    expect([open.r, open.g, open.b]).toEqual([1, 1, 1]);
    const red = readBeamState(named, frameAt(1, [255, 15]), 1);
    expect([red.r, red.g, red.b]).toEqual([1, 0, 0]);
    expect(red.wheelSlot).toBe('Red');
    expect(wheelColor('Light Blue')).toEqual([0.45, 0.75, 1]);

    const unnamed = buildBeamProfile(fixtureOf(['dimmer', 'color_wheel']));
    const guess = readBeamState(unnamed, frameAt(1, [255, 120]), 1);
    expect([guess.r, guess.g, guess.b]).toEqual([1, 1, 1]);
    expect(guess.wheelSlot).toBeNull();
  });

  it('takes zoom from its channel, else from the profile\'s beam angle', () => {
    const zoomed = buildBeamProfile(fixtureOf(['dimmer', 'zoom'], { beam_angle: 25 }));
    const state = readBeamState(zoomed, frameAt(1, [255, 51]), 1);
    expect(state.zoomSource).toBe('zoom');
    expect(state.zoom).toBeCloseTo(0.2, 6);

    const fixed = readBeamState(buildBeamProfile(fixtureOf(['dimmer'], { beam_angle: 25 })), frameAt(1, [255]), 1);
    expect(fixed.zoomSource).toBe('beam_angle');
    expect(fixed.zoom).toBeCloseTo(0.5, 6);

    const unknown = readBeamState(buildBeamProfile(fixtureOf(['dimmer'], { beam_angle: null })), frameAt(1, [255]), 1);
    expect(unknown.zoomSource).toBe('fallback');
  });

  it('reads DMX 0 on pan as the end stop, not as centre', () => {
    const profile = buildBeamProfile(fixtureOf(['pan', 'tilt', 'dimmer']));
    const state = readBeamState(profile, frameAt(1, [0, 255, 255]), 1);
    expect(state.panDeg).toBeCloseTo(-270, 6);
    expect(state.tiltDeg).toBeCloseTo(135, 6);
  });

  it('does not move a fixture whose profile gives it no travel', () => {
    const profile = buildBeamProfile(fixtureOf(['dimmer', 'red'], { fixture_type: 'led_par', pan_range: 0, tilt_range: 0 }));
    const state = readBeamState(profile, frameAt(1, [255, 255]), 1);
    expect(state.panDeg).toBe(0);
    expect(state.tiltDeg).toBe(0);
  });

  it('is dark and centred when no frame has arrived', () => {
    const profile = buildBeamProfile(fixtureOf(MOVER));
    const state = readBeamState(profile, null, 1);
    expect(state.hasSignal).toBe(false);
    expect(state.lit).toBe(false);
    expect(state.panDeg).toBe(0);
    expect(state.tiltDeg).toBe(0);
  });

  it('reads the mode the fixture is patched in', () => {
    const fixture: BeamFixtureInput = {
      mode_id: 2,
      fixture: {
        modes: [
          { id: 1, channels: [{ channel_number: 1, channel_type: 'dimmer' }] },
          { id: 2, channels: [{ channel_number: 1, channel_type: 'red' }, { channel_number: 2, channel_type: 'Pan Fine' }] },
        ],
      },
    };
    expect(buildChannelMap(fixture)).toEqual({ red: 0, pan_fine: 1 });
  });

  it('writes into the state it is given and makes no new one', () => {
    const profile = buildBeamProfile(fixtureOf(MOVER));
    const first = readBeamState(profile, moverFrame(1, { dimmer: 255, shutter: 255, red: 255 }), 1);
    const second = readBeamState(profile, moverFrame(1, {}), 1, first);
    expect(second).toBe(first);
    expect(second.lit).toBe(false);
  });
});

describe('guessed positions', () => {
  it('knows a fixture by its position_unconfirmed tag', () => {
    expect(isPositionUnconfirmed({ tags: ['position_source:template', 'position_unconfirmed'] })).toBe(true);
    expect(isPositionUnconfirmed({ tags: ['position_source:tap'] })).toBe(false);
    expect(isPositionUnconfirmed({ tags: null })).toBe(false);
    expect(isPositionUnconfirmed({})).toBe(false);
  });
});
