import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { beamDirection, hangBeam } from '../components/rig/previs/beamThrow';
import type { BeamVector } from '../components/rig/previs/beamThrow';
import {
  FEED_STALE_AFTER_MS,
  clearOutputFeed,
  createOutputFeed,
  ingestOutput,
  summariseFeed,
} from '../components/rig/previs/outputFeed';
import {
  boothAlreadyDrawn,
  buildBalcony,
  buildDanceDisc,
  buildDome,
  buildDomeSurround,
  buildLedWalls,
  buildRisers,
  domeHeightAt,
  ringPoint,
  underDome,
  usableBalcony,
  usableBox,
  usableDome,
} from '../components/rig/previs/roomShell';
import { buildVenue } from '../components/rig/previs/layout';
import type { RoomShell } from '../types';

// The LIV approximate demo rig's room, as _liv_room_shell() in
// backend/app/services/demo/venue_presets.py returns it.
const LIV: Required<Pick<RoomShell, 'dome' | 'dance_floor' | 'balcony' | 'dj_booth' | 'rear_stage' | 'led_walls'>> = {
  dome: { diameter_ft: 88, radius: 13.4, center_x: 0, center_z: 0, rim_height: 7.2, apex_height: 9.1 },
  dance_floor: { center_x: 0, center_z: 0, radius: 7.5 },
  balcony: {
    center_x: 0, center_z: 0, inner_radius: 10, outer_radius: 13.4,
    soffit_height: 4.0, deck_height: 4.4, start_deg: 90, end_deg: 270,
  },
  dj_booth: { center_x: 0, center_z: -12.85, width: 6.5, depth: 1.3, height: 1.25, name: 'DJ booth' },
  rear_stage: { center_x: 0, center_z: 12.5, width: 7, depth: 1.8, height: 0.6, name: 'Rear stage riser' },
  led_walls: [
    { center_x: 0, center_z: -13.4, width: 6, depth: 0.1, height: 2.4, base_height: 3.2 },
    { center_x: -5, center_z: -13.4, width: 2, depth: 0.1, height: 2.4, base_height: 3.2 },
    { center_x: 5, center_z: -13.4, width: 2, depth: 0.1, height: 2.4, base_height: 3.2 },
  ],
};

function bounds(geometry: THREE.BufferGeometry): THREE.Box3 {
  geometry.computeBoundingBox();
  return geometry.boundingBox as THREE.Box3;
}

describe('room shell', () => {
  it('counts angles clockwise from upstage, as the rig does', () => {
    const at = (deg: number) => ringPoint(0, 0, 10, deg).map((v) => Math.round(v * 1000) / 1000 + 0);
    expect(at(0)).toEqual([0, -10]);
    expect(at(90)).toEqual([10, 0]);
    expect(at(180)).toEqual([0, 10]);
    expect(at(270)).toEqual([-10, 0]);
  });

  it('builds the dome from its rim to its apex over its own circle', () => {
    const dome = LIV.dome!;
    expect(domeHeightAt(dome, 0)).toBeCloseTo(9.1, 6);
    expect(domeHeightAt(dome, 13.4)).toBeCloseTo(7.2, 6);
    const box = bounds(buildDome(dome));
    expect(box.max.y).toBeCloseTo(9.1, 2);
    expect(box.min.y).toBeGreaterThan(7.0);
    expect(box.max.x).toBeCloseTo(13.4, 1);
    expect(box.min.z).toBeCloseTo(-13.4, 1);
  });

  it('knows a camera on the dance floor is under the dome and one above the room is not', () => {
    const dome = LIV.dome!;
    expect(underDome(dome, 0, 2.3, 4)).toBe(true);
    expect(underDome(dome, 0, 16, 0)).toBe(false);
    expect(underDome(dome, 0, 2.3, 30)).toBe(false);
  });

  it('fills the corners between a round dome and square walls, at rim height', () => {
    const surround = buildDomeSurround(LIV.dome!, { xMin: -13.5, xMax: 13.5, zMin: -13.5, zMax: 19.5 });
    expect(surround).not.toBeNull();
    const box = bounds(surround as THREE.BufferGeometry);
    expect(box.min.y).toBeCloseTo(7.2, 6);
    expect(box.max.y).toBeCloseTo(7.2, 6);
    expect(box.max.z).toBeCloseTo(19.5, 6);
    // No vertex of it is inside the dome's circle.
    const position = (surround as THREE.BufferGeometry).getAttribute('position');
    for (let i = 0; i < position.count; i += 1) {
      expect(Math.hypot(position.getX(i), position.getZ(i))).toBeGreaterThan(13.4 - 1e-3);
    }
    expect(buildDomeSurround(LIV.dome!, { xMin: -5, xMax: 5, zMin: -5, zMax: 5 })).toBeNull();
  });

  it('puts the balcony round the rear half of the room, between its soffit and its rail', () => {
    const box = bounds(buildBalcony(LIV.balcony!));
    // 90 to 270 degrees clockwise from upstage is the +Z half.
    expect(box.min.z).toBeGreaterThan(-1e-6);
    expect(box.max.z).toBeCloseTo(13.4, 2);
    expect(box.min.x).toBeCloseTo(-13.4, 2);
    expect(box.max.x).toBeCloseTo(13.4, 2);
    expect(box.min.y).toBeCloseTo(4.0, 6);
    expect(box.max.y).toBeGreaterThan(4.4);
    expect(box.max.y).toBeLessThan(6);
  });

  it('lays the dance floor flat on the floor', () => {
    const box = bounds(buildDanceDisc(LIV.dance_floor!));
    expect(box.max.x).toBeCloseTo(7.56, 2);
    expect(box.max.y).toBeLessThan(0.03);
  });

  it('stands risers on the floor and hangs LED walls at their own height', () => {
    const riser = bounds(buildRisers([LIV.rear_stage!]) as THREE.BufferGeometry);
    expect(riser.min.y).toBeCloseTo(0, 6);
    expect(riser.max.y).toBeCloseTo(0.63, 6);
    expect(riser.min.z).toBeCloseTo(12.5 - 0.92, 6);

    const walls = buildLedWalls(LIV.led_walls!);
    const panels = bounds(walls!.panels);
    expect(panels.min.y).toBeCloseTo(3.2, 6);
    expect(panels.max.y).toBeCloseTo(5.6, 6);
    expect(panels.min.x).toBeCloseTo(-6, 6);
    expect(panels.max.x).toBeCloseTo(6, 6);
    expect(buildRisers([])).toBeNull();
    expect(buildLedWalls([])).toBeNull();
  });

  it('leaves the shell\'s booth to the booth the view already builds in a 27 m room', () => {
    // LIV's stage box: the booth the layout builds is the booth the shell describes.
    const { layout } = buildVenue({ width: 27, depth: 27, height: 6.5 }, []);
    const drawn = { width: layout.booth.width, fasciaZ: layout.booth.fasciaZ, backZ: layout.backZ };
    expect(boothAlreadyDrawn(LIV.dj_booth!, drawn)).toBe(true);
    expect(boothAlreadyDrawn({ ...LIV.dj_booth!, center_z: 0 }, drawn)).toBe(false);
    expect(boothAlreadyDrawn({ ...LIV.dj_booth!, center_x: 4 }, drawn)).toBe(false);
  });

  it('refuses shapes with missing or impossible numbers', () => {
    expect(usableDome(null)).toBe(false);
    expect(usableDome({ ...LIV.dome!, apex_height: 7.2 })).toBe(false);
    expect(usableDome({ ...LIV.dome!, radius: Number.NaN })).toBe(false);
    expect(usableBalcony({ ...LIV.balcony!, outer_radius: 9 })).toBe(false);
    expect(usableBox({ ...LIV.rear_stage!, height: 0 })).toBe(false);
    expect(usableBox(undefined)).toBe(false);
    expect(usableDome(LIV.dome)).toBe(true);
    expect(usableBalcony(LIV.balcony)).toBe(true);
  });
});

describe('hang orientation', () => {
  const rad = THREE.MathUtils.degToRad;

  /** The beam's direction as three.js draws it, from the same nest of groups the view uses. */
  function drawn(tilt: number, pan: number, rx: number, ry: number, rz: number): THREE.Vector3 {
    const body = new THREE.Group();
    body.rotation.set(0, ry, 0);
    const hang = new THREE.Group();
    hang.rotation.set(rx, 0, rz);
    const head = new THREE.Group();
    head.rotation.order = 'YXZ';
    head.rotation.set(tilt, pan, 0);
    body.add(hang);
    hang.add(head);
    body.updateMatrixWorld(true);
    return new THREE.Vector3(0, -1, 0).transformDirection(head.matrixWorld);
  }

  it('is beamDirection with the yaw added when the fixture hangs straight', () => {
    const cases: Array<[number, number, number]> = [[20, 35, 0], [-40, 110, 90], [65, -200, -45]];
    for (const [tilt, pan, yaw] of cases) {
      const plain = beamDirection(rad(tilt), rad(pan + yaw), false, { x: 0, y: 0, z: 0 });
      const hung = hangBeam(beamDirection(rad(tilt), rad(pan), false, { x: 0, y: 0, z: 0 }), 0, 0, rad(yaw));
      expect(hung.x).toBeCloseTo(plain.x, 9);
      expect(hung.y).toBeCloseTo(plain.y, 9);
      expect(hung.z).toBeCloseTo(plain.z, 9);
    }
  });

  it('agrees with the scene for any rotation the rig gives', () => {
    const cases: Array<[number, number, number, number, number]> = [
      [0, 0, 90, 0, 0],
      [0, 0, 0, 0, 90],
      [30, 40, 90, 20, 0],
      [-25, 130, 15, -70, 35],
      [50, -60, 180, 45, 0],
    ];
    for (const [tilt, pan, rx, ry, rz] of cases) {
      const want = drawn(rad(tilt), rad(pan), rad(rx), rad(ry), rad(rz));
      const got: BeamVector = hangBeam(
        beamDirection(rad(tilt), rad(pan), false, { x: 0, y: 0, z: 0 }),
        rad(rx), rad(rz), rad(ry),
      );
      expect(got.x).toBeCloseTo(want.x, 6);
      expect(got.y).toBeCloseTo(want.y, 6);
      expect(got.z).toBeCloseTo(want.z, 6);
    }
  });

  it('points a fixture turned over about X straight up', () => {
    const up = hangBeam(beamDirection(0, 0, false, { x: 0, y: 0, z: 0 }), Math.PI, 0, 0);
    expect(up.y).toBeCloseTo(1, 9);
  });
});

describe('output feed', () => {
  const frame = (value: number) => new Array(512).fill(value);

  it('takes a frame per universe and what stands between them and the wire', () => {
    const feed = createOutputFeed();
    const took = ingestOutput(feed, {
      dmx_frames: { '0': frame(1), '2': frame(3) },
      output: { master: 0.6, blackout: false, on_wire: false },
    }, 1000);
    expect(took).toBe(true);
    expect([...feed.frames.keys()].sort()).toEqual([0, 2]);
    expect(feed.frames.get(2)?.[0]).toBe(3);
    expect(feed.master).toBe(0.6);
    expect(feed.onWire).toBe(false);
    expect(feed.receivedAt).toBe(1000);
  });

  it('drops a universe the rig no longer occupies', () => {
    const feed = createOutputFeed();
    ingestOutput(feed, { dmx_frames: { '0': frame(1), '3': frame(9) } }, 1);
    ingestOutput(feed, { dmx_frames: { '0': frame(2) } }, 2);
    expect([...feed.frames.keys()]).toEqual([0]);
  });

  it('reads a single-universe message from an older backend', () => {
    const feed = createOutputFeed();
    expect(ingestOutput(feed, { dmx_frame: frame(7), dmx_universe: 4 }, 5)).toBe(true);
    expect(feed.frames.get(4)?.[0]).toBe(7);
    expect(feed.onWire).toBeNull();
    expect(feed.master).toBeNull();
  });

  it('changes nothing for a message with no frames', () => {
    const feed = createOutputFeed();
    ingestOutput(feed, { dmx_frames: { '0': frame(1) }, output: { master: 1, on_wire: true } }, 10);
    expect(ingestOutput(feed, { output: { blackout: true } }, 20)).toBe(false);
    expect(ingestOutput(feed, null, 20)).toBe(false);
    expect(ingestOutput(feed, { dmx_frames: {} }, 20)).toBe(false);
    expect(feed.blackout).toBe(false);
    expect(feed.receivedAt).toBe(10);
    expect(feed.frames.size).toBe(1);
  });

  it('says in one line what the picture is drawn from', () => {
    const feed = createOutputFeed();
    expect(summariseFeed(feed, 0).kind).toBe('none');

    ingestOutput(feed, { dmx_frames: { '0': frame(1) }, output: { master: 1, blackout: false, on_wire: true } }, 100);
    expect(summariseFeed(feed, 200)).toMatchObject({ kind: 'live', label: 'On the wire' });

    ingestOutput(feed, { dmx_frames: { '0': frame(1) }, output: { master: 0.5, blackout: false, on_wire: false } }, 300);
    expect(summariseFeed(feed, 400)).toMatchObject({ kind: 'held', label: 'Preview only, master 50%' });

    ingestOutput(feed, { dmx_frames: { '0': frame(0) }, output: { master: 1, blackout: true, on_wire: true } }, 500);
    expect(summariseFeed(feed, 600).kind).toBe('blackout');

    ingestOutput(feed, { dmx_frames: { '0': frame(1) } }, 700);
    expect(summariseFeed(feed, 800).kind).toBe('unknown');
    expect(summariseFeed(feed, 700 + FEED_STALE_AFTER_MS + 1).kind).toBe('stale');

    clearOutputFeed(feed);
    expect(summariseFeed(feed, 9000).kind).toBe('none');
    expect(feed.frames.size).toBe(0);
  });
});
