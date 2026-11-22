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
import type { BeamRoom } from './beamThrow';
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
 * - `ceiling`: fixed to the ceiling itself, above the trim height the truss
 *   hangs at. `drop` is the pipe from its clamp up to the ceiling. No truss is
 *   drawn for it.
 * - `wall`: on an arm off a wall or the booth front. `dirX/dirZ` point at the
 *   surface and `reach` is the distance to it.
 * - `stand`: on the floor. `plinth` is the height of the block or pole under
 *   its feet, `lift` raises a fixture patched lower than its own feet, and
 *   `lensUp` turns a fixed-body fixture to face the ceiling.
 */
export type FixtureMount =
  | { type: 'truss'; drop: number }
  | { type: 'ceiling'; drop: number }
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
/**
 * A fixed-body fixture patched this far above the trim height is part of the
 * ceiling, not of the rig hung under it: cove lighting in a dome, say. Each
 * would otherwise get a truss of its own across the room.
 */
export const CEILING_MOUNT_ABOVE = 0.25;
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

/**
 * The room's own box, where it is known: wall to wall and floor to ceiling,
 * centred on the origin. A room scan gives one (`room_shell.room`).
 */
export type KnownRoom = { width: number; depth: number; height: number };

/** True for a room whose three sizes are real numbers a room could have. */
export function usableRoom(room: Partial<KnownRoom> | null | undefined): room is KnownRoom {
  return Boolean(room)
    && [room!.width, room!.depth, room!.height].every((v) => typeof v === 'number' && Number.isFinite(v))
    && room!.width! >= 1 && room!.depth! >= 1 && room!.height! >= 1.5;
}

/**
 * A truss the room itself has, which the view draws from the room and not
 * from the fixtures under it: a line at an angle on the plan, or a ring. A
 * room scan finds these (`room_shell.truss_lines`, `room_shell.truss_rings`).
 * `height` is its underside, where a fixture hangs from.
 */
export type Hanger =
  | { kind: 'line'; x1: number; z1: number; x2: number; z2: number; height: number }
  | { kind: 'ring'; centerX: number; centerZ: number; radius: number; height: number };

/** How far off a hanger's line on the plan, and off its height, a fixture still hangs from it. */
export const HANGER_REACH = 0.3;
export const HANGER_HEIGHT_WINDOW = 0.6;

/** How far a point on the plan is from a hanger's line or circle. */
export function hangerDistance(hanger: Hanger, x: number, z: number): number {
  if (hanger.kind === 'ring') {
    return Math.abs(Math.hypot(x - hanger.centerX, z - hanger.centerZ) - hanger.radius);
  }
  const dx = hanger.x2 - hanger.x1;
  const dz = hanger.z2 - hanger.z1;
  const lengthSq = dx * dx + dz * dz;
  const along = lengthSq > 0
    ? Math.max(0, Math.min(1, ((x - hanger.x1) * dx + (z - hanger.z1) * dz) / lengthSq))
    : 0;
  return Math.hypot(x - (hanger.x1 + along * dx), z - (hanger.z1 + along * dz));
}

/** Whether a fixture hangs from one of the room's own trusses. */
export function hangsFrom(hangers: Hanger[], fixture: { x: number; y: number; z: number }): boolean {
  return hangers.some((hanger) =>
    Math.abs(fixture.y - hanger.height) <= HANGER_HEIGHT_WINDOW
    && hangerDistance(hanger, fixture.x, fixture.z) <= HANGER_REACH);
}

/**
 * `room`, when given, is the room as measured: the walls and the ceiling go
 * where it says instead of being worked out from the stage box. The stage box
 * itself is left as it is, because the mounts and the cameras read it. As with
 * the stage box, a wall still moves out for a fixture patched beyond it, so a
 * fixture is never drawn outside the room.
 *
 * `hangers` are trusses the room has that do not run across it. A fixture
 * hanging from one is clamped to it and gets no truss of the view's own: the
 * view's truss only ever runs across the room, and would otherwise hang a
 * short stub of it over every fixture round a ring.
 */
export function buildVenue(
  stage: { width: number; depth: number; height: number },
  fixtures: LayoutFixture[],
  room?: KnownRoom | null,
  hangers: Hanger[] = [],
): Venue {
  const width = Math.max(2, Number(stage.width) || 10);
  const depth = Math.max(2, Number(stage.depth) || 8);
  const height = Math.max(2, Number(stage.height) || 4);
  const known = usableRoom(room) ? room : null;

  const usable = fixtures.filter(
    (f) => Number.isFinite(f.x) && Number.isFinite(f.y) && Number.isFinite(f.z),
  );

  // Walls go exactly on the stage box: rigs put fixtures a few centimetres off
  // them. They only move out for a fixture patched outside the box.
  const reachX = usable.reduce((m, f) => Math.max(m, Math.abs(f.x)), 0);
  const minZ = usable.reduce((m, f) => Math.min(m, f.z), 0);
  const maxZ = usable.reduce((m, f) => Math.max(m, f.z), 0);
  const wallX = Math.max((known ? known.width : width) / 2, reachX + 0.15);
  const backZ = Math.min(-(known ? known.depth : depth) / 2, minZ - 0.15);
  // With no room known, the house is made up: the stage box, then some floor
  // for the audience. A known room ends at its own rear wall.
  const stageFrontZ = known
    ? Math.max(known.depth / 2, maxZ + 0.15) - 0.3
    : Math.max(depth / 2, maxZ + 0.3);
  const houseZ = known ? stageFrontZ + 0.3 : stageFrontZ + clamp(depth * 0.35, 2.5, 6);

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
  // What "high enough to hang" is measured against: the trim height the rig
  // was laid out to, or the real ceiling once the room is known. A rig drawn
  // on an 8 m template and then fitted under a 3.5 m truss still hangs.
  const trim = known ? Math.min(height, known.height) : height;
  const trussMembers: Array<{ fixture: LayoutFixture; clampY: number }> = [];
  const ceilingMembers: Array<{ fixture: LayoutFixture; clampY: number }> = [];

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

    if (hangers.length > 0 && hangsFrom(hangers, fixture)) {
      // On the room's own truss, which is drawn from the room.
      mounts.set(fixture.id, { type: 'truss', drop: 0 });
      continue;
    }

    if (!fixture.hasPanTilt && fixture.y > trim + CEILING_MOUNT_ABOVE) {
      // Its pipe is measured once the ceiling height is known, below.
      ceilingMembers.push({ fixture, clampY: fixture.y + spec.hangHeight });
      continue;
    }

    if (fixture.y < trim * 0.45) {
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
  // sits above it with room for the truss. A known room has its own ceiling,
  // which only goes up for a fixture or a truss patched above it.
  const ceilingY = known
    ? Math.max(known.height, trussTop + 0.05, highest + 0.3)
    : Math.max(height + 0.9, trussTop + 0.45, highest + 0.6);

  for (const member of ceilingMembers) {
    mounts.set(member.fixture.id, { type: 'ceiling', drop: Math.max(0, ceilingY - member.clampY) });
  }

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

/**
 * The longest straight line that fits in the room, corner to corner. No beam
 * travels further than this before it meets a wall, the floor or the ceiling.
 */
export function roomSpan(layout: ClubLayout): number {
  return Math.hypot(layout.wallX * 2, layout.houseZ - layout.backZ, layout.ceilingY);
}

/**
 * What a beam can land on in this room. With the venue hidden there are no
 * walls to stop it, so only the floor and the ceiling height count.
 */
export function beamRoom(layout: ClubLayout, withWalls: boolean): BeamRoom {
  return {
    ceilingY: layout.ceilingY,
    walls: withWalls
      ? { xMin: -layout.wallX, xMax: layout.wallX, zMin: layout.backZ, zMax: layout.houseZ }
      : null,
  };
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
