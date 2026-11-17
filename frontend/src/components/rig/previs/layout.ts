/**
 * Where everything in the previs room goes.
 *
 * One pure function of the rig: the booth, the dance floor, the truss, how each
 * fixture is mounted and where the cameras stand all come from here, so they
 * cannot disagree with each other.
 *
 * Conventions (the rig's, not ours): the origin is the centre of the stage
 * floor, X runs across, Y is up, -Z is upstage where the DJ booth is, and +Z is
 * toward the audience and the dance floor.
 */
import { FIXTURE_SPECS } from './fixtureSpecs';
import type { FixtureModelKind } from './fixtureSpecs';

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

/** A fixture, reduced to what the layout needs. */
export type LayoutFixture = {
  id: number;
  x: number;
  y: number;
  z: number;
  kind: FixtureModelKind;
  /** Static fixtures can be stood lens-up; a moving head aims itself. */
  hasPanTilt: boolean;
};

/**
 * How a fixture is held up.
 *
 * - `truss`: clamped under a truss. `drop` is the pipe between its clamp and
 *   the chord, for a fixture hung lower than its neighbours on the same truss.
 * - `wall`: on an arm off a wall or the booth front. `dirX/dirZ` point at the
 *   surface and `reach` is the distance to it.
 * - `stand`: on the floor. `plinth` is the height of the block or pole under
 *   its feet, `lift` raises a fixture patched lower than its own feet, and
 *   `lensUp` turns a fixed-body fixture to face the ceiling.
 */
export type FixtureMount =
  | { type: 'truss'; drop: number }
  | { type: 'wall'; dirX: number; dirZ: number; reach: number }
  | { type: 'stand'; plinth: number; lift: number; lensUp: boolean };

export type TrussRow = {
  /** Centre line of the chord the fixtures hang from. */
  z: number;
  /** Height of the bottom chords. */
  chordY: number;
  xMin: number;
  xMax: number;
};

export type ClubLayout = {
  /** The rig's own stage box. */
  width: number;
  depth: number;
  height: number;
  /** Side walls at +/- wallX. */
  wallX: number;
  /** Upstage wall, behind the booth. */
  backZ: number;
  /** Rear-of-house wall, behind the dance floor. */
  houseZ: number;
  ceilingY: number;
  booth: {
    width: number;
    /** Front face of the booth, facing the dance floor. */
    fasciaZ: number;
    riserHeight: number;
    deskTopY: number;
    deskDepth: number;
    djZ: number;
  };
  speakers: {
    /** Stacks stand at +/- x. Absent when the room is too narrow for them. */
    x: number;
    z: number;
    width: number;
    depth: number;
    present: boolean;
  };
  danceFloor: { xMin: number; xMax: number; zMin: number; zMax: number };
  /** Where the dance-floor camera stands; the crowd leaves it some room. */
  floorCamera: { x: number; y: number; z: number; clearRadius: number };
};

export type Venue = {
  layout: ClubLayout;
  mounts: Map<number, FixtureMount>;
  trussRows: TrussRow[];
};

/** Fixtures below this stand on the floor rather than hang. */
export const FLOOR_MOUNT_BELOW = 0.6;
/** A fixture this close to a wall is bracketed to it. */
export const WALL_REACH = 0.25;
/** Depth of the box truss section, chord centre to chord centre. */
export const TRUSS_SECTION = 0.24;
export const TRUSS_CHORD_RADIUS = 0.025;

const TRUSS_ROW_Z_TOLERANCE = 0.5;
const TRUSS_ROW_Y_TOLERANCE = 0.45;
const TRUSS_OVERHANG = 0.5;
const RISER_HEIGHT = 0.3;
const DESK_HEIGHT = 0.95;
const DESK_DEPTH = 0.55;
const SPEAKER_WIDTH = 0.95;
const SPEAKER_DEPTH = 0.8;

export function buildVenue(
  stage: { width: number; depth: number; height: number },
  fixtures: LayoutFixture[],
): Venue {
  const width = Math.max(2, Number(stage.width) || 10);
  const depth = Math.max(2, Number(stage.depth) || 8);
  const height = Math.max(2, Number(stage.height) || 4);

  const usable = fixtures.filter(
    (f) => Number.isFinite(f.x) && Number.isFinite(f.y) && Number.isFinite(f.z),
  );

  // Walls go exactly on the stage box: rigs put fixtures a few centimetres off
  // them. They only move out for a fixture patched outside the box.
  const reachX = usable.reduce((m, f) => Math.max(m, Math.abs(f.x)), 0);
  const minZ = usable.reduce((m, f) => Math.min(m, f.z), 0);
  const maxZ = usable.reduce((m, f) => Math.max(m, f.z), 0);
  const wallX = Math.max(width / 2, reachX + 0.15);
  const backZ = Math.min(-depth / 2, minZ - 0.15);
  const stageFrontZ = Math.max(depth / 2, maxZ + 0.3);
  const houseZ = stageFrontZ + clamp(depth * 0.35, 2.5, 6);

  // Booth: a low riser against the upstage wall with the desk at its front
  // edge, leaving the DJ the strip between desk and wall.
  const boothDepth = clamp(depth * 0.11, 0.95, 1.3);
  const fasciaZ = backZ + boothDepth;
  const boothWidth = clamp(width * 0.5, 2.2, Math.min(6.5, wallX * 2 - 0.6));
  const djZ = backZ + Math.max(0.2, (boothDepth - DESK_DEPTH) * 0.5);

  const speakerX = Math.min(boothWidth / 2 + 0.25 + SPEAKER_WIDTH / 2, wallX - SPEAKER_WIDTH / 2 - 0.1);
  const speakersPresent = speakerX - SPEAKER_WIDTH / 2 >= boothWidth / 2 + 0.05;

  const danceHalf = Math.max(0.8, wallX - 1.1);
  const danceZMin = fasciaZ + 0.9;
  const danceZMax = Math.max(danceZMin + 1.5, stageFrontZ - 0.3);

  // --- How each fixture is held up -----------------------------------------
  const mounts = new Map<number, FixtureMount>();
  const trussMembers: Array<{ fixture: LayoutFixture; clampY: number }> = [];

  for (const fixture of usable) {
    const spec = FIXTURE_SPECS[fixture.kind];

    if (fixture.y < FLOOR_MOUNT_BELOW) {
      const gap = fixture.y - spec.standHeight;
      mounts.set(fixture.id, {
        type: 'stand',
        plinth: Math.max(0, gap),
        lift: Math.max(0, -gap),
        lensUp: !fixture.hasPanTilt,
      });
      continue;
    }

    // Nearest vertical surface: a wall, or the booth front for a fixture
    // hung just in front of it below desk height.
    const surfaces: Array<{ reach: number; dirX: number; dirZ: number }> = [
      { reach: fixture.z - backZ, dirX: 0, dirZ: -1 },
      { reach: wallX - fixture.x, dirX: 1, dirZ: 0 },
      { reach: fixture.x + wallX, dirX: -1, dirZ: 0 },
    ];
    const inFrontOfBooth =
      Math.abs(fixture.x) <= boothWidth / 2 + 0.05 && fixture.y <= RISER_HEIGHT + DESK_HEIGHT;
    if (inFrontOfBooth) surfaces.push({ reach: fixture.z - fasciaZ, dirX: 0, dirZ: -1 });

    const nearest = surfaces
      .filter((s) => s.reach >= -0.05 && s.reach <= WALL_REACH)
      .sort((a, b) => a.reach - b.reach)[0];
    if (nearest) {
      mounts.set(fixture.id, {
        type: 'wall',
        dirX: nearest.dirX,
        dirZ: nearest.dirZ,
        reach: Math.max(0.02, nearest.reach),
      });
      continue;
    }

    if (fixture.y < height * 0.45) {
      // Too low for a truss and not on a wall: on a stand, aimed as patched.
      mounts.set(fixture.id, {
        type: 'stand',
        plinth: Math.max(0, fixture.y - spec.standHeight),
        lift: 0,
        lensUp: false,
      });
      continue;
    }

    trussMembers.push({ fixture, clampY: fixture.y + spec.hangHeight });
  }

  // --- Truss: one run per line of hung fixtures -----------------------------
  // Grouped by depth and by height, so a floor par or a booth bar never drags
  // a truss down to it.
  type RowBuild = TrussRow & { members: Array<{ fixture: LayoutFixture; clampY: number }> };
  const rows: RowBuild[] = [];
  const sorted = [...trussMembers].sort((a, b) => a.fixture.z - b.fixture.z || a.fixture.x - b.fixture.x);
  for (const member of sorted) {
    const row = rows.find(
      (r) =>
        Math.abs(member.fixture.z - r.z) <= TRUSS_ROW_Z_TOLERANCE &&
        Math.abs(member.clampY - r.chordY) <= TRUSS_ROW_Y_TOLERANCE,
    );
    if (row) {
      row.members.push(member);
      row.chordY = Math.max(row.chordY, member.clampY);
      row.xMin = Math.min(row.xMin, member.fixture.x);
      row.xMax = Math.max(row.xMax, member.fixture.x);
    } else {
      rows.push({
        z: member.fixture.z,
        chordY: member.clampY,
        xMin: member.fixture.x,
        xMax: member.fixture.x,
        members: [member],
      });
    }
  }

  const trussRows: TrussRow[] = rows.map((row) => {
    for (const member of row.members) {
      mounts.set(member.fixture.id, { type: 'truss', drop: Math.max(0, row.chordY - member.clampY) });
    }
    const xMin = Math.max(-wallX + 0.05, row.xMin - TRUSS_OVERHANG);
    const xMax = Math.min(wallX - 0.05, row.xMax + TRUSS_OVERHANG);
    return { z: row.z, chordY: row.chordY, xMin, xMax };
  });

  const trussTop = trussRows.reduce((m, r) => Math.max(m, r.chordY + TRUSS_SECTION + TRUSS_CHORD_RADIUS), 0);
  const highest = usable.reduce((m, f) => Math.max(m, f.y), 0);
  // `stage_height` is the trim height the fixtures hang at, so the ceiling
  // sits above it with room for the truss.
  const ceilingY = Math.max(height + 0.9, trussTop + 0.45, highest + 0.6);

  const layout: ClubLayout = {
    width,
    depth,
    height,
    wallX,
    backZ,
    houseZ,
    ceilingY,
    booth: {
      width: boothWidth,
      fasciaZ,
      riserHeight: RISER_HEIGHT,
      deskTopY: RISER_HEIGHT + DESK_HEIGHT,
      deskDepth: DESK_DEPTH,
      djZ,
    },
    speakers: {
      x: speakerX,
      z: backZ + 0.08 + SPEAKER_DEPTH / 2,
      width: SPEAKER_WIDTH,
      depth: SPEAKER_DEPTH,
      present: speakersPresent,
    },
    danceFloor: { xMin: -danceHalf, xMax: danceHalf, zMin: danceZMin, zMax: danceZMax },
    floorCamera: {
      x: 0,
      y: 2.3,
      z: danceZMax - 0.25,
      clearRadius: 1.1,
    },
  };

  return { layout, mounts, trussRows };
}

// ---------------------------------------------------------------------------
// Cameras
// ---------------------------------------------------------------------------

export type CameraMode = 'iso' | 'top' | 'front' | 'audience' | 'dj' | 'floor';

export type CameraPreset = {
  position: [number, number, number];
  target: [number, number, number];
  maxPolar: number;
  fov: number;
};

export function cameraPreset(mode: CameraMode, layout: ClubLayout): CameraPreset {
  const { depth, height } = layout;
  const baseTarget: [number, number, number] = [0, height * 0.45, 0];

  if (mode === 'top') {
    return { position: [0, height + 7, 0.01], target: [0, 0, 0], maxPolar: Math.PI, fov: 50 };
  }
  if (mode === 'front') {
    return { position: [0, height * 0.55, depth * 1.65], target: baseTarget, maxPolar: Math.PI / 1.95, fov: 50 };
  }
  if (mode === 'audience') {
    return { position: [0, 2.5, depth * 1.95], target: [0, 2.8, 0], maxPolar: Math.PI / 2.05, fov: 50 };
  }
  if (mode === 'dj') {
    // Over the DJ's shoulder, looking out across the decks at the crowd. The
    // booth is against the upstage wall, so the camera stands just behind
    // that wall, which is not drawn from its outer side.
    const { booth, danceFloor } = layout;
    return {
      position: [0.95, booth.riserHeight + 2.3, layout.backZ - 1.0],
      target: [-0.1, 1.2, danceFloor.zMin + (danceFloor.zMax - danceFloor.zMin) * 0.35],
      maxPolar: Math.PI * 0.72,
      fov: 58,
    };
  }
  if (mode === 'floor') {
    // Held up over the heads on the dance floor, looking at the booth.
    const { floorCamera, booth } = layout;
    return {
      position: [floorCamera.x, floorCamera.y, floorCamera.z],
      target: [0, booth.deskTopY + 1.55, booth.fasciaZ],
      maxPolar: Math.PI * 0.72,
      fov: 66,
    };
  }
  return { position: [0, height * 0.8, depth * 1.15], target: baseTarget, maxPolar: Math.PI / 2, fov: 50 };
}
