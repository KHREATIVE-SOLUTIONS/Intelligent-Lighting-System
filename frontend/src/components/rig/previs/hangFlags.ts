/**
 * Where a beam points, read back off the DMX a fixture is being sent.
 *
 * A patch can say how its unit is hung: pan runs backwards, tilt runs
 * backwards, or the two axes are exchanged. The engine corrects for that at the
 * one place a position becomes DMX, so on the wire a flagged head's values are
 * reversed or carried on the other axis's channels, and the real head ends up
 * pointing where the look asked.
 *
 * The 3D view draws every head as if it were hung the ordinary way. Fed the
 * raw values it would draw a flagged head pointing the wrong way while the
 * real one points the right way. This undoes the engine's mapping, exactly,
 * so the drawn beam goes where the real beam goes.
 *
 * The engine's order (backend fixture_groups.route_pan_tilt) is: invert the
 * logical axis, then swap decides which channels carry it. So to read pan:
 * take the channels that carry it (tilt's, when swapped), then undo pan's
 * invert at those channels' resolution.
 */

/** One axis as it is on the wire. `fine` is absent on a coarse-only fixture. */
export interface AxisBytes {
  coarse: number;
  fine?: number;
}

export interface HangFlags {
  panInvert?: boolean;
  tiltInvert?: boolean;
  /** Only when the fixture has both a pan and a tilt channel to exchange. */
  swap?: boolean;
}

/** Pan and tilt as 0 to 1 across each axis's travel. */
export interface PanTiltPosition {
  pan: number;
  tilt: number;
}

function axisPosition(axis: AxisBytes, inverted: boolean): number {
  if (axis.fine !== undefined) {
    const raw = ((axis.coarse & 0xff) << 8) | (axis.fine & 0xff);
    return (inverted ? 65535 - raw : raw) / 65535;
  }
  const raw = axis.coarse & 0xff;
  return (inverted ? 255 - raw : raw) / 255;
}

/**
 * The position a look asked for, from the bytes on the fixture's pan and tilt
 * channels. With no flags set this is the plain reading of those channels.
 * Writes into `out` and returns it, so a render loop can reuse one object.
 */
export function panTiltFromDmx(
  pan: AxisBytes,
  tilt: AxisBytes,
  flags: HangFlags,
  out: PanTiltPosition
): PanTiltPosition {
  const swapped = Boolean(flags.swap);
  out.pan = axisPosition(swapped ? tilt : pan, Boolean(flags.panInvert));
  out.tilt = axisPosition(swapped ? pan : tilt, Boolean(flags.tiltInvert));
  return out;
}
