import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { buildVenue, usableRoom } from '../components/rig/previs/layout';
import {
  buildOverheadLines,
  buildRisers,
  lineAlreadyDrawn,
  scanRisers,
  scannedRoom,
  usableLine,
} from '../components/rig/previs/roomShell';
import {
  DEFAULT_SCAN_OPTIONS,
  ROOM_SCAN_ACCEPT,
  ROOM_SCAN_MAX_BYTES,
  fileProblem,
  fixtureMoveText,
  foundLines,
  moveText,
  roomScanErrorText,
  roomScanParams,
  roomScanPath,
  roomShellPath,
  roomSizeText,
  NO_TURN_TEXT,
  turnSummaryText,
  turnText,
  turnedCount,
} from '../utils/roomScan';
import type { RoomScanMove, RoomScanPreview } from '../utils/roomScan';
import type { RoomShell, RoomShellLine } from '../types';

// The room backend/tests/unit/room_scan_meshes.py builds, as the scan reader
// writes it (backend/app/services/room_scan/extract.py): 12 m by 9 m by 5 m, a
// stage against the upstage wall, a riser, and one truss across the room.
const TRUSS: RoomShellLine = {
  name: 'Overhead line 1', x1: -4, z1: 0.5, x2: 4, z2: 0.5, height: 4, top: 4.3,
  length: 8, across: 0.3, axis: 'x', suggested: true,
};
const SCANNED: RoomShell = {
  basis: 'Suggested from a room scan (club.obj). Nothing here has been checked against the room.',
  source: 'scan',
  suggested: true,
  room: { width: 12, depth: 9, height: 5, suggested: true },
  risers: [
    { center_x: -1.5, center_z: -3.25, width: 6, depth: 2.5, height: 0.9, base_height: 0, name: 'Stage', kind: 'stage', suggested: true },
    { center_x: 4.5, center_z: 2.75, width: 2, depth: 1.5, height: 0.3, base_height: 0, name: 'Riser', kind: 'riser', suggested: true },
  ],
  truss_lines: [TRUSS],
  hanging_bands: [{ height: 4, top: 4.3, lines: 1, suggested: true }],
};

const STAGE_BOX = { width: 12, depth: 10, height: 8 };

function bounds(geometry: THREE.BufferGeometry): THREE.Box3 {
  geometry.computeBoundingBox();
  return geometry.boundingBox as THREE.Box3;
}

function preview(overrides: Partial<RoomScanPreview> = {}): RoomScanPreview {
  return {
    rig_id: 7,
    rig_name: 'Club',
    file: 'club.obj',
    format: 'obj',
    room_shell: SCANNED,
    replaces_existing_shell: false,
    summary: {
      width: 12, depth: 9, height: 5, raised_areas: 2, overhead_lines: 1,
      hanging_heights: [4], units: 'cm', up_axis: 'z',
    },
    assumptions: ['Units read as cm.'],
    warnings: [],
    fixtures: { total: 11, unconfirmed: 8, would_move: 7, moves: [] },
    operator_guide: 'docs/ROOM_SCAN.md',
    applied: null,
    ...overrides,
  };
}

describe('a scanned room in the 3D view', () => {
  it('takes its walls and ceiling from the scan, not from the stage box', () => {
    const invented = buildVenue(STAGE_BOX, []).layout;
    expect(invented.wallX).toBeCloseTo(6, 6);
    expect(invented.backZ).toBeCloseTo(-5, 6);
    expect(invented.houseZ).toBeCloseTo(8.5, 6);
    expect(invented.ceilingY).toBeCloseTo(8.9, 6);

    const { layout } = buildVenue(STAGE_BOX, [], scannedRoom(SCANNED));
    expect(layout.wallX).toBeCloseTo(6, 6);
    expect(layout.backZ).toBeCloseTo(-4.5, 6);
    expect(layout.houseZ).toBeCloseTo(4.5, 6);
    expect(layout.ceilingY).toBeCloseTo(5, 6);
    // The stage box the mounts and the cameras read is the rig's own, untouched.
    expect([layout.width, layout.depth, layout.height]).toEqual([12, 10, 8]);
  });

  it('still moves a wall or the ceiling out for a fixture patched beyond it', () => {
    const room = scannedRoom(SCANNED);
    const wide = buildVenue(STAGE_BOX, [{ id: 1, x: 7.5, y: 4, z: 0, kind: 'spot', hasPanTilt: true }], room);
    expect(wide.layout.wallX).toBeCloseTo(7.65, 6);
    const deep = buildVenue(STAGE_BOX, [{ id: 1, x: 0, y: 4, z: 6, kind: 'spot', hasPanTilt: true }], room);
    expect(deep.layout.houseZ).toBeCloseTo(6.15, 6);
    const high = buildVenue(STAGE_BOX, [{ id: 1, x: 0, y: 5.2, z: 0, kind: 'moving_head', hasPanTilt: true }], room);
    expect(high.layout.ceilingY).toBeGreaterThan(5.4);
  });

  it('hangs a fixture under a low truss even when the rig was drawn for a high one', () => {
    // 3.5 m up: under half of the 8 m trim the template was drawn to, well up a 5 m room.
    const fixture = { id: 1, x: 0, y: 3.5, z: 0, kind: 'moving_head' as const, hasPanTilt: true };
    expect(buildVenue(STAGE_BOX, [fixture]).mounts.get(1)?.type).toBe('stand');
    const scanned = buildVenue(STAGE_BOX, [fixture], scannedRoom(SCANNED));
    expect(scanned.mounts.get(1)?.type).toBe('truss');
    expect(scanned.trussRows).toHaveLength(1);
  });

  it('only treats a shell as a scanned room when it is one and its sizes are real', () => {
    expect(scannedRoom(SCANNED)).toEqual({ width: 12, depth: 9, height: 5 });
    expect(scannedRoom(null)).toBeNull();
    // A demo preset's shell: no source, no room box.
    expect(scannedRoom({ dj_booth: { center_x: 0, center_z: -12, width: 6, depth: 1, height: 1 } })).toBeNull();
    expect(scannedRoom({ ...SCANNED, source: 'preset' })).toBeNull();
    expect(scannedRoom({ ...SCANNED, room: { width: 12, depth: 9, height: 0 } })).toBeNull();
    expect(scannedRoom({ ...SCANNED, room: { width: Number.NaN, depth: 9, height: 5 } })).toBeNull();
    expect(usableRoom({ width: 12, depth: 9 })).toBe(false);
    // An unusable room is the same as none: the room is worked out from the stage box.
    expect(buildVenue(STAGE_BOX, [], { width: Number.NaN, depth: 9, height: 5 }).layout.houseZ).toBeCloseTo(8.5, 6);
  });

  it('draws the stage and the riser where the scan found them', () => {
    const risers = scanRisers(SCANNED);
    expect(risers.map((r) => r.kind)).toEqual(['stage', 'riser']);
    const box = bounds(buildRisers(risers) as THREE.BufferGeometry);
    expect(box.min.y).toBeCloseTo(0, 4);
    expect(box.max.y).toBeCloseTo(0.93, 4);
    expect(box.min.x).toBeCloseTo(-4.52, 4);
    expect(box.max.x).toBeCloseTo(5.52, 4);
    expect(box.min.z).toBeCloseTo(-4.52, 4);

    const broken = { ...SCANNED, risers: [{ ...SCANNED.risers![0], height: 0 }] };
    expect(scanRisers(broken)).toEqual([]);
    expect(scanRisers(null)).toEqual([]);
  });

  it('draws an overhead line as a bar at its own height, whichever way it runs', () => {
    const across = bounds(buildOverheadLines([TRUSS]) as THREE.BufferGeometry);
    expect(across.min.x).toBeCloseTo(-4, 4);
    expect(across.max.x).toBeCloseTo(4, 4);
    expect(across.min.y).toBeCloseTo(4, 4);
    expect(across.max.y).toBeCloseTo(4.3, 4);
    expect(across.min.z).toBeCloseTo(0.35, 4);
    expect(across.max.z).toBeCloseTo(0.65, 4);

    // No top and no width given: 0.3 m of each.
    const along = bounds(buildOverheadLines([{ x1: 2, z1: -3, x2: 2, z2: 3, height: 3.5 }]) as THREE.BufferGeometry);
    expect(along.min.x).toBeCloseTo(1.85, 4);
    expect(along.max.x).toBeCloseTo(2.15, 4);
    expect(along.min.z).toBeCloseTo(-3, 4);
    expect(along.max.z).toBeCloseTo(3, 4);
    expect(along.max.y).toBeCloseTo(3.8, 4);

    expect(buildOverheadLines([])).toBeNull();
    expect(usableLine(TRUSS)).toBe(true);
    expect(usableLine({ ...TRUSS, x2: -4 })).toBe(false);
    expect(usableLine({ ...TRUSS, height: Number.NaN })).toBe(false);
    expect(usableLine(undefined)).toBe(false);
  });

  it('does not draw a second truss where the rig already hangs one under the line', () => {
    // Fixtures moved under the line hang at its underside; their truss chord is a little above.
    const hung = { z: 0.5, chordY: 4.45, xMin: -3.5, xMax: 3.5 };
    expect(lineAlreadyDrawn(TRUSS, [hung])).toBe(true);
    expect(lineAlreadyDrawn(TRUSS, [])).toBe(false);
    expect(lineAlreadyDrawn(TRUSS, [{ ...hung, z: 3 }])).toBe(false);
    expect(lineAlreadyDrawn(TRUSS, [{ ...hung, chordY: 7 }])).toBe(false);
    expect(lineAlreadyDrawn(TRUSS, [{ ...hung, xMin: 5, xMax: 6 }])).toBe(false);
    // The view's truss runs across the room; a line running the other way is never it.
    expect(lineAlreadyDrawn({ x1: 0.5, z1: -3, x2: 0.5, z2: 3, height: 4 }, [hung])).toBe(false);
  });
});

describe('room scan requests', () => {
  it('posts to the rig and sends only the guesses the operator overrode', () => {
    expect(roomScanPath(12)).toBe('/rigs/12/room-scan');
    expect(roomShellPath(12)).toBe('/rigs/12/room-shell');
    expect(roomScanParams(DEFAULT_SCAN_OPTIONS)).toEqual({});
    expect(roomScanParams({ units: 'cm', upAxis: 'z', rotate: 90 })).toEqual({ units: 'cm', up_axis: 'z', rotate: 90 });
  });

  it('a preview never asks to apply, and apply says whether fixtures move', () => {
    expect('apply' in roomScanParams({ units: 'm', upAxis: 'auto', rotate: 0 })).toBe(false);
    expect(roomScanParams(DEFAULT_SCAN_OPTIONS, { moveFixtures: true })).toEqual({ apply: true, move_fixtures: true });
    expect(roomScanParams(DEFAULT_SCAN_OPTIONS, { moveFixtures: false })).toEqual({ apply: true, move_fixtures: false });
  });

  it('stops a file the server would refuse for its size before it is sent', () => {
    expect(fileProblem({ name: 'club.obj', size: 1024 })).toBeNull();
    expect(fileProblem({ name: 'club.obj', size: ROOM_SCAN_MAX_BYTES })).toBeNull();
    expect(fileProblem({ name: 'club.obj', size: ROOM_SCAN_MAX_BYTES + 1 })).toContain('200 MB');
    expect(fileProblem({ name: 'club.obj', size: 0 })).toContain('empty');
  });

  it('lets the file picker choose a glTF, which is what most scanning apps export', () => {
    const endings = ROOM_SCAN_ACCEPT.split(',');
    expect(endings).toEqual(expect.arrayContaining(['.glb', '.gltf', '.obj', '.ply', '.usdz', '.usda', '.json']));
    expect(endings.every((ending) => /^\.[a-z]+$/.test(ending))).toBe(true);
    expect(fileProblem({ name: 'club.glb', size: 1024 })).toBeNull();
  });
});

describe('room scan wording', () => {
  it('says how big the room is and what was found in it', () => {
    expect(roomSizeText(preview())).toBe('12.0 m wide, 9.0 m deep, 5.0 m high');
    expect(foundLines(preview())).toEqual([
      'Stage: 6.0 m by 2.5 m, 0.90 m high',
      'Riser: 2.0 m by 1.5 m, 0.30 m high',
      'Overhead line 1: 8.0 m long, underside 4.00 m up, running across the room',
    ]);
    const bare = preview({ room_shell: { ...SCANNED, risers: [], truss_lines: [] } });
    expect(foundLines(bare)).toHaveLength(1);
    expect(foundLines(bare)[0]).toContain('only the floor, walls and ceiling');
  });

  it('says which fixtures would move and that the rest stay put', () => {
    expect(fixtureMoveText(preview())).toBe(
      '7 unconfirmed fixtures of 11 would be moved to agree with the scan; the other 4 stay exactly where they are.',
    );
    expect(fixtureMoveText(preview({ fixtures: { total: 1, unconfirmed: 1, would_move: 1, moves: [] } }))).toBe(
      '1 unconfirmed fixture of 1 would be moved to agree with the scan.',
    );
    expect(fixtureMoveText(preview({ fixtures: { total: 0, unconfirmed: 0, would_move: 0, moves: [] } })))
      .toContain('no fixtures');
    expect(fixtureMoveText(preview({ fixtures: { total: 4, unconfirmed: 0, would_move: 0, moves: [] } })))
      .toContain('None would be moved');
    expect(fixtureMoveText(preview({ fixtures: { total: 4, unconfirmed: 2, would_move: 0, moves: [] } })))
      .toContain('None of the 2 unconfirmed fixtures would be moved');
  });

  describe('the turn of a move', () => {
    const move = (id: number, turn?: unknown): RoomScanMove => ({
      rig_fixture_id: id, name: `Par ${id}`, group: 'Floor Pars',
      from: { x: 0, y: 0, z: 0 }, to: { x: 1, y: 0.9, z: -3 }, reason: 'Moved onto Stage.',
      ...(turn === undefined ? {} : { turn_deg: turn as number }),
    });

    it('writes a turn in degrees, to a tenth, with its sign', () => {
      expect(turnText(move(1, 30))).toBe('30 deg');
      expect(turnText(move(1, -12.5))).toBe('-12.5 deg');
      expect(turnText(move(1, 44.96))).toBe('45 deg');
      expect(turnText(move(1, 7.25))).toBe('7.3 deg');
    });

    it('writes a dash where the fixture is not turned: 0, no key, or not a number', () => {
      expect(NO_TURN_TEXT).toBe('-');
      expect(turnText(move(1, 0))).toBe('-');
      expect(turnText(move(1))).toBe('-');
      expect('turn_deg' in move(1)).toBe(false);
      expect(turnText(move(1, -0))).toBe('-');
      expect(turnText(move(1, null))).toBe('-');
      expect(turnText(move(1, '30'))).toBe('-');
      expect(turnText(move(1, Number.NaN))).toBe('-');
      expect(turnText(move(1, Number.POSITIVE_INFINITY))).toBe('-');
      // Too small to show as a tenth, either way round: no "0 deg" and no "-0 deg".
      expect(turnText(move(1, 0.04))).toBe('-');
      expect(turnText(move(1, -0.04))).toBe('-');
    });

    it('counts the moves that turn, which are the ones whose cell is not a dash', () => {
      expect(turnedCount([move(1, 30), move(2, 0), move(3), move(4, -30), move(5, 0.01)])).toBe(2);
      expect(turnedCount([move(1), move(2, 0)])).toBe(0);
      expect(turnedCount([])).toBe(0);
      expect(turnedCount(null)).toBe(0);
      expect(turnedCount(undefined)).toBe(0);
    });

    it('says how many will be turned, and nothing when none are', () => {
      expect(turnSummaryText([move(1), move(2, 0)])).toBe('');
      expect(turnSummaryText([])).toBe('');
      expect(turnSummaryText(undefined)).toBe('');
      expect(turnSummaryText([move(1, 30), move(2, 30), move(3)]))
        .toBe('2 of them will also be turned with the stage, which stands at a heading.');
      expect(turnSummaryText([move(1, 30), move(2), move(3)]))
        .toBe('1 of them will also be turned with the stage, which stands at a heading.');
      expect(turnSummaryText([move(1, 30), move(2, 30), move(3, 30)]))
        .toBe('All 3 will also be turned with the stage, which stands at a heading.');
      expect(turnSummaryText([move(1, 30), move(2, 30)]))
        .toBe('Both will also be turned with the stage, which stands at a heading.');
      expect(turnSummaryText([move(1, 30)]))
        .toBe('It will also be turned with the stage, which stands at a heading.');
    });

    it('says it in the past once the scan is applied', () => {
      expect(turnSummaryText([move(1, 30), move(2, 30), move(3)], true))
        .toBe('2 of them were also turned with the stage, which stands at a heading.');
      expect(turnSummaryText([move(1, 30), move(2), move(3)], true))
        .toBe('1 of them was also turned with the stage, which stands at a heading.');
      expect(turnSummaryText([move(1, 30), move(2, 30), move(3, 30)], true))
        .toBe('All 3 were also turned with the stage, which stands at a heading.');
      expect(turnSummaryText([move(1, 30)], true))
        .toBe('It was also turned with the stage, which stands at a heading.');
      expect(turnSummaryText([move(1), move(2)], true)).toBe('');
    });

    it('leaves the sentence about the moves as it was', () => {
      const moves = [move(1, 30), move(2, 30)];
      expect(fixtureMoveText(preview({ fixtures: { total: 11, unconfirmed: 8, would_move: 7, moves } }))).toBe(
        '7 unconfirmed fixtures of 11 would be moved to agree with the scan; the other 4 stay exactly where they are.',
      );
    });
  });

  it('writes a move as where from and where to', () => {
    expect(moveText({
      rig_fixture_id: 3, name: 'Spot 1', group: 'Truss Spots',
      from: { x: -3, y: 6, z: -1.5 }, to: { x: -3, y: 4, z: 0.5 }, reason: 'Moved under Overhead line 1 at 4.00 m.',
    })).toBe('(-3.00, 6.00, -1.50) to (-3.00, 4.00, 0.50)');
  });

  it('offers every ending the server reads, glTF and binary USD among them, and a zip of a scan last', () => {
    expect(ROOM_SCAN_ACCEPT.split(',')).toEqual([
      '.obj', '.ply', '.glb', '.gltf', '.usdz', '.usdc', '.usda', '.json', '.zip',
    ]);
    expect(fileProblem({ name: 'polycam-export.zip', size: 1024 })).toBeNull();
  });

  it('uses the server\'s own words for a refusal, and has some when it gave none', () => {
    const usdz = 'This binary USD (USDC) file cannot be read: it is cut short. Export OBJ from Polycam or Scaniverse instead.';
    expect(roomScanErrorText(400, usdz)).toBe(usdz);
    expect(roomScanErrorText(422, [{ msg: "String should match pattern '^(auto|m|cm|mm)$'" }])).toContain('pattern');
    expect(roomScanErrorText(413, undefined)).toContain('too large');
    expect(roomScanErrorText(409, '')).toContain('locate walkthrough');
    expect(roomScanErrorText(404, undefined)).toContain('no longer exists');
    expect(roomScanErrorText(undefined, undefined)).toContain('could not be reached');
    expect(roomScanErrorText(500, { unexpected: true })).toContain('Nothing was changed');
  });
});
