/**
 * The generic fixture models, built from primitives.
 *
 * Each type is built once and shared by every fixture of that type. A model is
 * up to four geometries, split by what moves:
 *
 * - `support`: the part bolted to the venue. A base and clamps for a moving
 *   head, a bracket for a fixed body. Built once for hanging and once for
 *   standing on the floor.
 * - `yoke`: the U-shaped arms of a moving head, which turn with pan.
 * - `shell` and `emitter`: the head, which turns with pan and tilt. The
 *   emitter is the lit part (lens or LED cells) and gets its own material so
 *   it can glow with the fixture's colour.
 *
 * All of them are modelled around the origin, which is where the light comes
 * from, with the beam leaving along -Y.
 */
import * as THREE from 'three';
import {
  box, cylX, cylY, discDown, domeDown, hexCells, merge, paint, place, strut, tubeY,
} from './geometryKit';
import {
  CLAMP_HEIGHT, FIXTURE_SPECS, FOOT_HEIGHT, YOKE_TOP_ALLOWANCE,
} from './fixtureSpecs';
import type { FixtureModelKind, MoverDims } from './fixtureSpecs';

// Real housings are black. These are lifted to dark grey so the bodies still
// read when the rig is dark, which is the state the view opens in.
const HOUSING = '#585c66';
const HOUSING_HI = '#6e727d';
const DARK = '#2b2c32';
const METAL = '#b6bbc3';
const BRIGHT_METAL = '#c9ced6';
const SCREEN = '#22406e';

export type FixtureGeometry = {
  shell: THREE.BufferGeometry;
  emitter: THREE.BufferGeometry;
  /** Null for the fixed-body types. */
  yokeHang: THREE.BufferGeometry | null;
  yokeStand: THREE.BufferGeometry | null;
  supportHang: THREE.BufferGeometry;
  supportStand: THREE.BufferGeometry;
  /** Where along X the clamps sit, for wall arms and drop pipes. */
  clampXs: number[];
};

/** A half-coupler gripping a truss chord that runs along X, on a short riser. */
function clampParts(x: number, topY: number): THREE.BufferGeometry[] {
  const riser = CLAMP_HEIGHT - 0.03;
  return [
    paint(place(box(0.032, riser, 0.032), [x, topY + riser / 2, 0]), METAL),
    paint(place(new THREE.TorusGeometry(0.034, 0.011, 6, 14).rotateY(Math.PI / 2), [x, topY + CLAMP_HEIGHT, 0]), METAL),
  ];
}

// ---------------------------------------------------------------------------
// Moving heads: beam, spot, wash and the general-purpose head
// ---------------------------------------------------------------------------

function buildMover(d: MoverDims): FixtureGeometry {
  const R = d.barrelRadius;
  const bezelLen = 0.03;
  const bezelOuter = Math.max(d.lensRadius + 0.024, d.nose > 0 ? 0 : R + 0.006);
  const rearEnd = d.barrelRear;
  const rearCap = 0.035;
  const bezelTop = -(d.barrelFront - bezelLen);
  const noseTop = bezelTop + d.nose;
  const barrelLen = rearEnd - rearCap - noseTop;

  // --- Head ---------------------------------------------------------------
  const shell: THREE.BufferGeometry[] = [
    paint(place(cylY(R * 0.94, R, barrelLen, 28), [0, noseTop + barrelLen / 2, 0]), HOUSING),
    paint(place(cylY(R * 0.6, R * 0.94, rearCap, 28), [0, rearEnd - rearCap / 2, 0]), HOUSING_HI),
    paint(place(tubeY(bezelOuter, d.lensRadius, bezelLen, 28), [0, bezelTop - bezelLen / 2, 0]), DARK),
    // Backing behind the lens, so the gaps between LED cells are not see-through.
    paint(place(discDown(d.lensRadius + 0.002, 28), [0, bezelTop + 0.001, 0]), DARK),
    // Tilt axle and the squared mid-section the yoke arms bolt to.
    paint(cylX(d.armWidth * 0.3, d.armX * 2 - 0.004, 14), DARK),
    paint(box((d.armX - d.armThick / 2) * 2 - 0.008, Math.min(0.16, (d.barrelRear + d.barrelFront) * 0.42), R * 1.72), HOUSING_HI),
  ];
  if (d.nose > 0) {
    shell.push(paint(place(cylY(R, bezelOuter, d.nose, 28), [0, bezelTop + d.nose / 2, 0]), HOUSING));
  }
  // Cooling fins round the back of the barrel.
  for (let i = 0; i < 3; i += 1) {
    shell.push(paint(place(cylY(R * 1.035, R * 1.035, 0.007, 28), [0, rearEnd - rearCap - 0.022 - i * 0.022, 0]), DARK));
  }

  // The lens sits back inside the bezel, like the real thing.
  const lensPlane = bezelTop - 0.006;
  const emitter: THREE.BufferGeometry[] = [];
  if (d.cellFace) {
    const pitch = d.lensRadius * 0.41;
    for (const [cx, cz] of hexCells(pitch, 2)) {
      emitter.push(place(domeDown(pitch * 0.43, 0.008, 10), [cx, lensPlane, cz]));
    }
  } else {
    emitter.push(place(domeDown(d.lensRadius * 0.97, 0.017, 24), [0, lensPlane, 0]));
  }

  // --- Yoke and base, hanging (dir +1) or standing (dir -1) ----------------
  const yokeTop = d.armDrop + YOKE_TOP_ALLOWANCE;
  const buildYoke = (dir: 1 | -1) => {
    const parts: THREE.BufferGeometry[] = [];
    for (const side of [-1, 1]) {
      parts.push(
        paint(place(box(d.armThick, d.armDrop, d.armWidth), [side * d.armX, (dir * d.armDrop) / 2, 0]), HOUSING),
        paint(place(cylX(d.armWidth / 2, d.armThick, 18), [side * d.armX, 0, 0]), HOUSING),
        paint(place(cylX(d.armWidth * 0.32, d.armThick + 0.014, 14), [side * d.armX, 0, 0]), HOUSING_HI),
      );
    }
    parts.push(
      paint(place(box(d.armX * 2 + d.armThick, 0.05, d.armWidth), [0, dir * (d.armDrop + 0.025), 0]), HOUSING),
      paint(place(cylY(0.075, 0.075, 0.03, 20), [0, dir * (d.armDrop + 0.065), 0]), DARK),
    );
    return merge(parts);
  };

  const clampXs = [-d.baseWidth * 0.27, d.baseWidth * 0.27];
  const buildBase = (dir: 1 | -1) => {
    const centreY = dir * (yokeTop + d.baseHeight / 2);
    const outerY = dir * (yokeTop + d.baseHeight);
    const parts: THREE.BufferGeometry[] = [];
    if (d.roundBase) {
      parts.push(paint(place(cylY(d.baseWidth / 2, d.baseWidth / 2, d.baseHeight, 32), [0, centreY, 0]), HOUSING));
      parts.push(paint(place(cylY(d.baseWidth / 2 + 0.006, d.baseWidth / 2 + 0.006, 0.014, 32), [0, centreY, 0]), DARK));
    } else {
      parts.push(paint(place(box(d.baseWidth, d.baseHeight, d.baseDepth), [0, centreY, 0]), HOUSING));
      // Carry handles down each end.
      for (const side of [-1, 1]) {
        parts.push(paint(place(box(0.014, d.baseHeight * 0.34, d.baseDepth * 0.62), [side * (d.baseWidth / 2 + 0.007), centreY, 0]), DARK));
      }
    }
    // Menu display on the front.
    const frontZ = (d.roundBase ? d.baseWidth : d.baseDepth) / 2 + 0.002;
    parts.push(paint(place(box(d.baseWidth * 0.3, d.baseHeight * 0.42, 0.006), [0, centreY, frontZ]), SCREEN));

    if (dir === 1) {
      for (const x of clampXs) {
        parts.push(paint(place(box(0.07, 0.012, 0.12), [x, outerY + 0.006, 0]), METAL));
        parts.push(...clampParts(x, outerY));
      }
    } else {
      const fx = d.baseWidth / 2 - 0.04;
      const fz = (d.roundBase ? d.baseWidth : d.baseDepth) / 2 - 0.04;
      const spread = d.roundBase ? 0.7 : 1;
      for (const sx of [-1, 1]) {
        for (const sz of [-1, 1]) {
          parts.push(paint(place(cylY(0.02, 0.02, FOOT_HEIGHT, 10), [sx * fx * spread, outerY - FOOT_HEIGHT / 2, sz * fz * spread]), DARK));
        }
      }
    }
    return merge(parts);
  };

  return {
    shell: merge(shell),
    emitter: merge(emitter),
    yokeHang: buildYoke(1),
    yokeStand: buildYoke(-1),
    supportHang: buildBase(1),
    supportStand: buildBase(-1),
    clampXs,
  };
}

// ---------------------------------------------------------------------------
// Fixed bodies
// ---------------------------------------------------------------------------

/** A U-bracket from the tilt knobs on each side up to one clamp. */
function hangBracket(halfWidth: number, height: number, stripDepth: number): THREE.BufferGeometry[] {
  return [
    paint(place(box(0.005, height, stripDepth), [-halfWidth, height / 2, 0]), METAL),
    paint(place(box(0.005, height, stripDepth), [halfWidth, height / 2, 0]), METAL),
    paint(place(box(halfWidth * 2 + 0.005, 0.005, stripDepth), [0, height, 0]), METAL),
    ...clampParts(0, height),
  ];
}

/** The same bracket turned over to stand on the floor. */
function standBracket(halfWidth: number, height: number, stripDepth: number, plateDepth: number): THREE.BufferGeometry[] {
  return [
    paint(place(box(0.005, height, stripDepth), [-halfWidth, -height / 2, 0]), METAL),
    paint(place(box(0.005, height, stripDepth), [halfWidth, -height / 2, 0]), METAL),
    paint(place(box(halfWidth * 2 + 0.03, 0.006, plateDepth), [0, -height + 0.003, 0]), METAL),
  ];
}

function buildPar(): FixtureGeometry {
  const spec = FIXTURE_SPECS.led_par;
  const shell = merge([
    paint(place(cylY(0.098, 0.105, 0.15, 26), [0, -0.01, 0]), HOUSING),
    paint(place(cylY(0.06, 0.098, 0.03, 26), [0, 0.08, 0]), HOUSING_HI),
    paint(place(cylY(0.109, 0.109, 0.006, 26), [0, 0.045, 0]), DARK),
    paint(place(cylY(0.109, 0.109, 0.006, 26), [0, 0.025, 0]), DARK),
    paint(place(cylY(0.109, 0.109, 0.006, 26), [0, 0.005, 0]), DARK),
    paint(place(tubeY(0.113, 0.094, 0.018, 26), [0, -0.094, 0]), DARK),
    paint(place(discDown(0.095, 26), [0, -0.086, 0]), DARK),
    paint(place(cylX(0.02, 0.014, 12), [-0.121, 0, 0]), METAL),
    paint(place(cylX(0.02, 0.014, 12), [0.121, 0, 0]), METAL),
  ]);
  const emitter = merge(hexCells(0.06, 1).map(([cx, cz]) => place(domeDown(0.027, 0.009, 12), [cx, -0.087, cz])));

  // On the floor the double bracket opens into an A-frame.
  const foot = -spec.standHeight + 0.008;
  const stand: THREE.BufferGeometry[] = [];
  for (const sx of [-1, 1]) {
    for (const sz of [-1, 1]) {
      stand.push(paint(strut([sx * 0.118, 0, 0], [sx * 0.118, foot, sz * 0.13], 0.007), METAL));
    }
  }
  for (const sz of [-1, 1]) {
    stand.push(paint(strut([-0.13, foot, sz * 0.13], [0.13, foot, sz * 0.13], 0.008), METAL));
  }

  return {
    shell,
    emitter,
    yokeHang: null,
    yokeStand: null,
    supportHang: merge(hangBracket(0.118, spec.hangHeight - CLAMP_HEIGHT, 0.032)),
    supportStand: merge(stand),
    clampXs: [0],
  };
}

function buildBar(): FixtureGeometry {
  const spec = FIXTURE_SPECS.led_bar;
  const shellParts: THREE.BufferGeometry[] = [
    paint(box(1.0, 0.07, 0.085), HOUSING),
    paint(place(box(0.012, 0.078, 0.093), [-0.506, 0, 0]), METAL),
    paint(place(box(0.012, 0.078, 0.093), [0.506, 0, 0]), METAL),
    // Recessed lens strip the cells sit in.
    paint(place(box(0.97, 0.004, 0.066), [0, -0.036, 0]), DARK),
  ];
  for (const z of [-0.025, 0, 0.025]) {
    shellParts.push(paint(place(box(0.94, 0.008, 0.012), [0, 0.039, z]), DARK));
  }

  const cells: THREE.BufferGeometry[] = [];
  for (let i = 0; i < 12; i += 1) {
    cells.push(place(domeDown(0.027, 0.011, 12), [(i - 5.5) * 0.08, -0.038, 0]));
  }

  const clampXs = [-0.34, 0.34];
  const bracketTop = spec.hangHeight - CLAMP_HEIGHT;
  const hang: THREE.BufferGeometry[] = [];
  const stand: THREE.BufferGeometry[] = [];
  for (const x of clampXs) {
    hang.push(paint(place(box(0.03, bracketTop - 0.035, 0.006), [x, (bracketTop + 0.035) / 2, 0]), METAL));
    hang.push(paint(place(box(0.05, 0.006, 0.05), [x, bracketTop, 0]), METAL));
    hang.push(...clampParts(x, bracketTop));
    stand.push(paint(place(box(0.03, 0.03, 0.03), [x, -0.05, 0]), METAL));
    stand.push(paint(place(box(0.05, 0.012, 0.17), [x, -spec.standHeight + 0.006, 0]), METAL));
  }

  return {
    shell: merge(shellParts),
    emitter: merge(cells),
    yokeHang: null,
    yokeStand: null,
    supportHang: merge(hang),
    supportStand: merge(stand),
    clampXs,
  };
}

function buildStrobe(): FixtureGeometry {
  const spec = FIXTURE_SPECS.strobe;
  const shellParts: THREE.BufferGeometry[] = [
    // Body behind the tray, then the four walls of the frame round it.
    paint(place(box(0.44, 0.075, 0.25), [0, 0.015, 0]), HOUSING),
    paint(place(box(0.44, 0.03, 0.02), [0, -0.0375, -0.115]), HOUSING),
    paint(place(box(0.44, 0.03, 0.02), [0, -0.0375, 0.115]), HOUSING),
    paint(place(box(0.02, 0.03, 0.21), [-0.21, -0.0375, 0]), HOUSING),
    paint(place(box(0.02, 0.03, 0.21), [0.21, -0.0375, 0]), HOUSING),
    // Reflector tray: a bright floor with two angled sides.
    paint(place(box(0.4, 0.003, 0.21), [0, -0.024, 0]), BRIGHT_METAL),
    paint(place(box(0.4, 0.003, 0.05), [0, -0.036, -0.086], [-0.62, 0, 0]), BRIGHT_METAL),
    paint(place(box(0.4, 0.003, 0.05), [0, -0.036, 0.086], [0.62, 0, 0]), BRIGHT_METAL),
    paint(place(cylX(0.022, 0.012, 12), [-0.228, 0, 0]), METAL),
    paint(place(cylX(0.022, 0.012, 12), [0.228, 0, 0]), METAL),
  ];
  for (let i = 0; i < 6; i += 1) {
    shellParts.push(paint(place(box(0.36, 0.012, 0.006), [0, 0.058, -0.075 + i * 0.03]), DARK));
  }

  const emitter = merge([
    place(box(0.34, 0.004, 0.052), [0, -0.03, -0.03]),
    place(box(0.34, 0.004, 0.052), [0, -0.03, 0.03]),
  ]);

  return {
    shell: merge(shellParts),
    emitter,
    yokeHang: null,
    yokeStand: null,
    supportHang: merge(hangBracket(0.2325, spec.hangHeight - CLAMP_HEIGHT, 0.035)),
    supportStand: merge(standBracket(0.2325, spec.standHeight, 0.035, 0.13)),
    clampXs: [0],
  };
}

function buildFlood(): FixtureGeometry {
  const spec = FIXTURE_SPECS.other;
  const shellParts: THREE.BufferGeometry[] = [
    paint(place(box(0.22, 0.1, 0.2), [0, 0.015, 0]), HOUSING),
    paint(place(box(0.22, 0.03, 0.016), [0, -0.05, -0.092]), HOUSING_HI),
    paint(place(box(0.22, 0.03, 0.016), [0, -0.05, 0.092]), HOUSING_HI),
    paint(place(box(0.016, 0.03, 0.168), [-0.102, -0.05, 0]), HOUSING_HI),
    paint(place(box(0.016, 0.03, 0.168), [0.102, -0.05, 0]), HOUSING_HI),
    paint(place(cylX(0.018, 0.012, 12), [-0.116, 0, 0]), METAL),
    paint(place(cylX(0.018, 0.012, 12), [0.116, 0, 0]), METAL),
  ];
  for (let i = 0; i < 4; i += 1) {
    shellParts.push(paint(place(box(0.18, 0.012, 0.006), [0, 0.07, -0.045 + i * 0.03]), DARK));
  }

  return {
    shell: merge(shellParts),
    emitter: merge([place(box(0.18, 0.004, 0.16), [0, -0.04, 0])]),
    yokeHang: null,
    yokeStand: null,
    supportHang: merge(hangBracket(0.1205, spec.hangHeight - CLAMP_HEIGHT, 0.03)),
    supportStand: merge(standBracket(0.1205, spec.standHeight, 0.03, 0.12)),
    clampXs: [0],
  };
}

const cache = new Map<FixtureModelKind, FixtureGeometry>();

/** The shared geometry for a fixture type, built on first use. */
export function getFixtureGeometry(kind: FixtureModelKind): FixtureGeometry {
  const cached = cache.get(kind);
  if (cached) return cached;

  const spec = FIXTURE_SPECS[kind];
  let built: FixtureGeometry;
  if (spec.mover) built = buildMover(spec.mover);
  else if (kind === 'led_par') built = buildPar();
  else if (kind === 'led_bar') built = buildBar();
  else if (kind === 'strobe') built = buildStrobe();
  else built = buildFlood();

  cache.set(kind, built);
  return built;
}
