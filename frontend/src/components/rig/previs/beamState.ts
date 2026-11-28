/**
 * What a fixture does with the DMX it is sent.
 *
 * One pure mapping: a fixture's profile plus the channel values in an output
 * frame give the state of its beam (level, colour, shutter, pan, tilt, zoom).
 * The 3D view draws that and nothing else, so what it shows is what the frame
 * says, blackout and grand master included.
 *
 * It is the reverse of `_render_fixture` in
 * backend/app/services/effects/fixture_groups.py, which writes the frame, and
 * follows the same rules:
 *
 * - a fixture with no dimmer channel carries its level in its colour values;
 * - cyan/magenta/yellow are subtractive flags (0 is open) only on a fixture
 *   with no red/green/blue emitters; beside RGB they are parked and ignored;
 * - a shutter channel at 255 is open, and a strobe channel at 0 is "no
 *   strobe", not "closed".
 *
 * Where the profile names its value ranges (an imported GDTF or OFL profile)
 * the shutter, strobe and colour wheel are read from those names. Where it
 * does not, the shutter falls back to the convention above and the colour
 * wheel is treated as open: a slot table made up here would show a colour the
 * fixture may not have.
 */

import { panTiltFromDmx } from './hangFlags';
import type { HangFlags, PanTiltPosition } from './hangFlags';

/** Reused by every read so the frame loop does not allocate. */
const scratchPosition: PanTiltPosition = { pan: 0.5, tilt: 0.5 };

/** A named span of one channel's values, as the fixture library stores it. */
export type ChannelValueRange = {
  name?: string | null;
  min_value: number;
  max_value: number;
};

/** The parts of a patched fixture the mapping reads. Structural, so tests need no full rig. */
export type BeamFixtureInput = {
  mode_id?: number | null;
  tags?: string[] | null;
  is_inverted?: boolean | null;
  /** Hang flags the engine applies on the way to DMX; see ./hangFlags.ts. */
  pan_invert?: boolean | null;
  tilt_invert?: boolean | null;
  pan_tilt_swap?: boolean | null;
  fixture?: {
    fixture_type?: string | null;
    beam_angle?: number | null;
    pan_range?: number | null;
    tilt_range?: number | null;
    modes?: Array<{
      id?: number;
      channels?: Array<{
        channel_number: number;
        channel_type?: string | null;
        name?: string | null;
        value_ranges?: ChannelValueRange[] | null;
      }>;
    }> | null;
  } | null;
};

export type BeamInvert = { pan: boolean; tilt: boolean };

/** Everything about a fixture that does not change from frame to frame. */
export type BeamProfile = {
  /** Channel type -> offset from the fixture's start address (0-based). */
  channels: Record<string, number>;
  /** Named value ranges, by channel type, where the profile has them. */
  ranges: Record<string, ChannelValueRange[]>;
  /** Full travel in degrees. 0 is a fixture that cannot move on that axis. */
  panRangeDeg: number;
  tiltRangeDeg: number;
  invert: BeamInvert;
  /**
   * The patch's hang flags, which the engine has already applied to the wire.
   * Undone when reading a frame so the beam is drawn where the real one goes.
   * Swap is only set when the fixture has both a pan and a tilt channel.
   */
  hang: HangFlags;
  /** Fixed beam angle from the profile, for a fixture with no zoom channel. */
  beamAngleDeg: number | null;
  /** Zoom used when the profile gives neither a zoom channel nor a beam angle. */
  fallbackZoom: number;
};

export type ShutterState = 'open' | 'closed' | 'strobe';

export type BeamState = {
  /** False when the frame is missing: nothing has been received for this fixture. */
  hasSignal: boolean;
  /** Light is leaving the fixture: level above zero and the shutter not closed. */
  lit: boolean;
  /** 0-1, what the beam is drawn at. 0 while the shutter is closed. */
  intensity: number;
  /** 0-1, the dimmer channel alone (1 when the fixture has none). */
  dimmer: number;
  /** 0-1 each, before intensity. */
  r: number;
  g: number;
  b: number;
  colorSource: 'rgb' | 'cmy' | 'white';
  /** The colour wheel slot in use, when the profile names one. */
  wheelSlot: string | null;
  /** Degrees from centre, invert applied. 0, 0 is straight down the fixture's own axis. */
  panDeg: number;
  tiltDeg: number;
  shutter: ShutterState;
  /** 0-1, how fast it flashes. 0 is a steady beam. */
  strobeRate: number;
  strobeSource: 'strobe' | 'shutter' | 'none';
  /** The raw value on the strobe or shutter channel, for the debug table. */
  strobeValue: number;
  /** 0 narrow to 1 wide. */
  zoom: number;
  zoomSource: 'zoom' | 'beam_angle' | 'fallback';
  zoomValue: number;
};

const clamp01 = (value: number) => (value < 0 ? 0 : value > 1 ? 1 : value);

/** Fixture types drawn narrow when nothing says how wide they are. */
const SPOT_TYPES = new Set(['spot']);

/** Additive emitters and the colour each adds at full. */
const EMITTERS: Array<[string, number, number, number]> = [
  ['red', 1, 0, 0],
  ['green', 0, 1, 0],
  ['blue', 0, 0, 1],
  ['white', 1, 1, 1],
  ['amber', 1, 0.75, 0],
  ['lime', 0.7, 1, 0],
  ['uv', 0.35, 0, 1],
  ['indigo', 0.3, 0, 1],
];

/** A shutter with no named ranges: the engine writes 255 for open and 0 only at blackout. */
export const SHUTTER_CLOSED_BELOW = 8;
export const SHUTTER_OPEN_FROM = 248;
/** A strobe channel with no named ranges: at or below this it is not strobing. */
export const STROBE_OFF_BELOW = 9;

/** One spelling per channel type, whatever the profile calls it. */
export function canonicalChannel(raw: string): string {
  const key = raw.trim().toLowerCase().replace(/[\s-]+/g, '_');
  if (key === 'pan' || key === 'pan_coarse' || key === 'pan_16bit' || key === 'pan_course') return 'pan';
  if (key === 'pan_fine' || key === 'pan_fine_16bit' || key === 'fine_pan') return 'pan_fine';
  if (key === 'tilt' || key === 'tilt_coarse' || key === 'tilt_16bit' || key === 'tilt_course') return 'tilt';
  if (key === 'tilt_fine' || key === 'tilt_fine_16bit' || key === 'fine_tilt') return 'tilt_fine';
  if (key === 'dimmer' || key === 'intensity' || key === 'master_dimmer') return 'dimmer';
  if (key === 'shutter_strobe') return 'strobe';
  if (key === 'colour_wheel') return 'color_wheel';
  return key;
}

function activeMode(fixture: BeamFixtureInput) {
  const modes = fixture.fixture?.modes;
  if (!modes?.length) return undefined;
  return fixture.mode_id ? modes.find((mode) => mode.id === fixture.mode_id) : modes[0];
}

/** Channel type -> offset from the start address, from the fixture's active mode. */
export function buildChannelMap(fixture: BeamFixtureInput): Record<string, number> {
  const map: Record<string, number> = {};
  const mode = activeMode(fixture);
  if (!mode?.channels) return map;
  for (const channel of mode.channels) {
    const offset = channel.channel_number - 1;
    const primary = canonicalChannel(String(channel.channel_type || ''));
    if (primary && !(primary in map)) map[primary] = offset;
    const byName = canonicalChannel(String(channel.name || ''));
    if (byName && !(byName in map)) map[byName] = offset;
  }
  return map;
}

/**
 * Which way round a fixture answers pan and tilt.
 *
 * The engine does not correct for these, so this describes the fixture, not
 * the frame: a head set to invert in its own menu, say, moves the opposite way
 * for the same values. (The patch's hang flags are different: the engine
 * applies those on the way to DMX, and `profile.hang` undoes them when a frame
 * is read; see ./hangFlags.ts.) The tags `pan_invert` and
 * `tilt_invert` each flip one axis. The rig's older single `is_inverted` flag
 * does not say which axis it means; it is read here as pan.
 */
export function resolveInvert(fixture: Pick<BeamFixtureInput, 'tags' | 'is_inverted'>): BeamInvert {
  const tags = fixture.tags ?? [];
  return {
    pan: tags.includes('pan_invert') !== Boolean(fixture.is_inverted),
    tilt: tags.includes('tilt_invert'),
  };
}

/** A position that was generated, not measured or tapped: see docs/FLASH_AND_TAP.md. */
export const POSITION_UNCONFIRMED_TAG = 'position_unconfirmed';

export function isPositionUnconfirmed(fixture: { tags?: string[] | null }): boolean {
  return (fixture.tags ?? []).includes(POSITION_UNCONFIRMED_TAG);
}

export function buildBeamProfile(
  fixture: BeamFixtureInput,
  invert: BeamInvert = resolveInvert(fixture),
): BeamProfile {
  const channels = buildChannelMap(fixture);
  const ranges: Record<string, ChannelValueRange[]> = {};
  for (const channel of activeMode(fixture)?.channels ?? []) {
    if (!channel.value_ranges?.length) continue;
    const type = canonicalChannel(String(channel.channel_type || channel.name || ''));
    if (type && !(type in ranges)) ranges[type] = channel.value_ranges;
  }

  const type = String(fixture.fixture?.fixture_type || 'other');
  const hasPanTilt = channels.pan !== undefined && channels.tilt !== undefined;
  const beamAngle = fixture.fixture?.beam_angle;
  return {
    channels,
    ranges,
    // A profile that lists the channels but no travel gets the usual 540 x 270.
    panRangeDeg: Number(fixture.fixture?.pan_range) || (hasPanTilt ? 540 : 0),
    tiltRangeDeg: Number(fixture.fixture?.tilt_range) || (hasPanTilt ? 270 : 0),
    invert,
    hang: {
      panInvert: Boolean(fixture.pan_invert),
      tiltInvert: Boolean(fixture.tilt_invert),
      swap: Boolean(fixture.pan_tilt_swap) && hasPanTilt,
    },
    beamAngleDeg: typeof beamAngle === 'number' && Number.isFinite(beamAngle) ? beamAngle : null,
    fallbackZoom: SPOT_TYPES.has(type) ? 0.45 : 0.12,
  };
}

export function createBeamState(): BeamState {
  return {
    hasSignal: false,
    lit: false,
    intensity: 0,
    dimmer: 0,
    r: 1,
    g: 1,
    b: 1,
    colorSource: 'white',
    wheelSlot: null,
    panDeg: 0,
    tiltDeg: 0,
    shutter: 'open',
    strobeRate: 0,
    strobeSource: 'none',
    strobeValue: 0,
    zoom: 0,
    zoomSource: 'fallback',
    zoomValue: 0,
  };
}

function rangeAt(ranges: ChannelValueRange[] | undefined, value: number): ChannelValueRange | null {
  if (!ranges) return null;
  for (const range of ranges) {
    if (value >= range.min_value && value <= range.max_value) return range;
  }
  return null;
}

/** How far through its range a value is, 0-1. */
function along(range: ChannelValueRange, value: number): number {
  const span = range.max_value - range.min_value;
  return span > 0 ? clamp01((value - range.min_value) / span) : 1;
}

type Flash = { state: ShutterState; rate: number };
const flash: Flash = { state: 'open', rate: 0 };

/** What a named range on a shutter or strobe channel does. Null when the name says nothing. */
function flashFromName(range: ChannelValueRange, value: number): Flash | null {
  const name = String(range.name ?? '').toLowerCase();
  if (!name) return null;
  const strobeOff = /no\s*strob|strob\w*\s*(off|stop)|no\s*func/.test(name);
  if (!strobeOff && /strob|puls|random|flash|lightning/.test(name)) {
    flash.state = 'strobe';
    // "Strobe slow to fast" and unlabelled ones rise with the value; the few
    // profiles that run fast to slow say so.
    const up = along(range, value);
    flash.rate = Math.max(0.05, /fast\s*(to|-|>|…|\.\.)+\s*slow/.test(name) ? 1 - up : up);
    return flash;
  }
  if (/clos|black\s*out|dark/.test(name)) {
    flash.state = 'closed';
    flash.rate = 0;
    return flash;
  }
  if (strobeOff || /open|unused|nothing|\bon\b/.test(name)) {
    flash.state = 'open';
    flash.rate = 0;
    return flash;
  }
  return null;
}

/** Colours a wheel slot's name can stand for. Longest names first, so "light blue" is not "blue". */
const WHEEL_COLORS: Array<[string, number, number, number]> = [
  ['light blue', 0.45, 0.75, 1],
  ['dark blue', 0, 0.1, 0.8],
  ['light green', 0.5, 1, 0.5],
  ['dark green', 0, 0.55, 0.15],
  ['deep red', 0.8, 0, 0],
  ['congo', 0.25, 0, 0.9],
  ['lavender', 0.7, 0.55, 1],
  ['turquoise', 0, 0.9, 0.8],
  ['magenta', 1, 0, 1],
  ['orange', 1, 0.45, 0],
  ['yellow', 1, 0.95, 0],
  ['purple', 0.55, 0, 1],
  ['violet', 0.55, 0, 1],
  ['amber', 1, 0.7, 0],
  ['green', 0, 1, 0],
  ['cyan', 0, 1, 1],
  ['pink', 1, 0.4, 0.7],
  ['lime', 0.6, 1, 0],
  ['blue', 0, 0, 1],
  ['red', 1, 0, 0],
  ['cto', 1, 0.8, 0.55],
  ['ctb', 0.7, 0.85, 1],
  ['uv', 0.35, 0, 1],
];

/** The colour a wheel slot name stands for, or null for open, white or a name not known. */
export function wheelColor(name: string | null | undefined): [number, number, number] | null {
  const text = String(name ?? '').toLowerCase();
  if (!text || /open|white|no\s*func|rotat|spin|scroll|rainbow/.test(text)) return null;
  for (const [word, r, g, b] of WHEEL_COLORS) {
    if (text.includes(word)) return [r, g, b];
  }
  return null;
}

/**
 * Read one fixture's beam out of a frame.
 *
 * `frame` is a whole universe (512 values, the first channel at index 0) and
 * `start` is the fixture's DMX address, 1-based as it is patched. A missing
 * frame is "no signal": dark, with the head at centre.
 *
 * Writes into `out` and returns it, so the frame loop makes no garbage: this
 * runs for every fixture on every frame.
 */
export function readBeamState(
  profile: BeamProfile,
  frame: ArrayLike<number> | null | undefined,
  start: number,
  out: BeamState = createBeamState(),
): BeamState {
  const { channels, ranges } = profile;
  const base = start - 1;
  const has = (name: string) => channels[name] !== undefined;
  const value = (name: string): number => {
    const raw = frame ? Number(frame[base + channels[name]]) : 0;
    return Number.isFinite(raw) ? Math.max(0, Math.min(255, raw)) : 0;
  };

  out.hasSignal = Boolean(frame);
  out.wheelSlot = null;

  // --- Colour ---------------------------------------------------------------
  const additive = EMITTERS.some(([name]) => has(name));
  let colourCarriesLevel = false;
  if (additive) {
    let r = 0;
    let g = 0;
    let b = 0;
    for (const [name, er, eg, eb] of EMITTERS) {
      if (!has(name)) continue;
      const level = value(name) / 255;
      r += er * level;
      g += eg * level;
      b += eb * level;
    }
    out.r = clamp01(r);
    out.g = clamp01(g);
    out.b = clamp01(b);
    out.colorSource = 'rgb';
    colourCarriesLevel = true;
  } else if (has('cyan') || has('magenta') || has('yellow')) {
    // Subtractive flags over a white source: a flag the profile lacks is open.
    out.r = has('cyan') ? 1 - value('cyan') / 255 : 1;
    out.g = has('magenta') ? 1 - value('magenta') / 255 : 1;
    out.b = has('yellow') ? 1 - value('yellow') / 255 : 1;
    out.colorSource = 'cmy';
    colourCarriesLevel = true;
  } else {
    out.r = 1;
    out.g = 1;
    out.b = 1;
    out.colorSource = 'white';
  }

  // A colour wheel filters whatever is behind it, where the profile names its slots.
  if (has('color_wheel') && ranges.color_wheel) {
    const slot = rangeAt(ranges.color_wheel, value('color_wheel'));
    if (slot?.name) {
      out.wheelSlot = slot.name;
      const tint = wheelColor(slot.name);
      if (tint) {
        out.r *= tint[0];
        out.g *= tint[1];
        out.b *= tint[2];
      }
    }
  }

  // --- Shutter and strobe ---------------------------------------------------
  out.shutter = 'open';
  out.strobeRate = 0;
  out.strobeSource = 'none';
  out.strobeValue = 0;
  if (has('shutter')) {
    const v = value('shutter');
    out.strobeSource = 'shutter';
    out.strobeValue = v;
    const range = rangeAt(ranges.shutter, v);
    const named = range ? flashFromName(range, v) : null;
    if (named) {
      out.shutter = named.state;
      out.strobeRate = named.rate;
    } else if (v < SHUTTER_CLOSED_BELOW) {
      out.shutter = 'closed';
    } else if (v < SHUTTER_OPEN_FROM) {
      out.shutter = 'strobe';
      out.strobeRate = Math.max(0.05, (v - SHUTTER_CLOSED_BELOW) / (SHUTTER_OPEN_FROM - 1 - SHUTTER_CLOSED_BELOW));
    }
  }
  if (has('strobe') && out.shutter !== 'closed') {
    const v = value('strobe');
    const range = rangeAt(ranges.strobe, v);
    const named = range ? flashFromName(range, v) : null;
    if (named) {
      if (named.state !== 'open') {
        out.shutter = named.state;
        out.strobeRate = named.rate;
        out.strobeSource = 'strobe';
        out.strobeValue = v;
      }
    } else if (v >= STROBE_OFF_BELOW) {
      out.shutter = 'strobe';
      out.strobeRate = Math.max(0.05, v / 255);
      out.strobeSource = 'strobe';
      out.strobeValue = v;
    }
    if (out.strobeSource === 'none') {
      out.strobeSource = 'strobe';
      out.strobeValue = v;
    }
  }

  // --- Level ----------------------------------------------------------------
  if (has('dimmer')) {
    out.dimmer = value('dimmer') / 255;
  } else if (colourCarriesLevel) {
    out.dimmer = 1;
  } else {
    // Nothing but a shutter or strobe channel to say it is on: lit while that
    // is doing something, dark otherwise.
    out.dimmer = out.shutter === 'strobe' || (has('shutter') && out.shutter === 'open') ? 1 : 0;
  }
  if (!frame) out.dimmer = 0;
  out.intensity = out.shutter === 'closed' ? 0 : out.dimmer;
  out.lit = out.intensity > 0 && out.r + out.g + out.b > 0;

  // --- Pan and tilt ---------------------------------------------------------
  out.panDeg = 0;
  out.tiltDeg = 0;
  if (frame && (has('pan') || has('tilt'))) {
    // Undo the engine's hang mapping first (a plain read when no flag is set),
    // then the fixture's own invert, which describes the head, not the wire.
    const position = panTiltFromDmx(
      { coarse: value('pan'), fine: has('pan_fine') ? value('pan_fine') : undefined },
      { coarse: value('tilt'), fine: has('tilt_fine') ? value('tilt_fine') : undefined },
      profile.hang,
      scratchPosition
    );
    if (has('pan') && profile.panRangeDeg > 0) {
      const deg = (position.pan - 0.5) * profile.panRangeDeg;
      out.panDeg = profile.invert.pan ? -deg : deg;
    }
    if (has('tilt') && profile.tiltRangeDeg > 0) {
      const deg = (position.tilt - 0.5) * profile.tiltRangeDeg;
      out.tiltDeg = profile.invert.tilt ? -deg : deg;
    }
  }

  // --- Zoom -----------------------------------------------------------------
  if (has('zoom')) {
    out.zoomValue = value('zoom');
    out.zoom = out.zoomValue / 255;
    out.zoomSource = 'zoom';
  } else if (profile.beamAngleDeg !== null) {
    out.zoom = clamp01((profile.beamAngleDeg - 5) / 40);
    out.zoomValue = Math.round(out.zoom * 255);
    out.zoomSource = 'beam_angle';
  } else {
    out.zoom = profile.fallbackZoom;
    out.zoomValue = Math.round(out.zoom * 255);
    out.zoomSource = 'fallback';
  }

  return out;
}
