import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import {
  advanceBeatClock,
  createBeatClock,
  ingestAnalysis,
  phaseDelta,
  sectionEnergy,
} from '../components/rig/previs/beatClock';
import { beamRise, beamThrow } from '../components/rig/previs/beamThrow';
import { crowdCapacity, placeCrowd } from '../components/rig/previs/crowdLayout';
import { getFixtureGeometry } from '../components/rig/previs/fixtureGeometry';
import { FIXTURE_SPECS, resolveModelKind } from '../components/rig/previs/fixtureSpecs';
import type { FixtureModelKind } from '../components/rig/previs/fixtureSpecs';
import { buildVenue, cameraPreset, roomSpan } from '../components/rig/previs/layout';
import {
  POOL_LIGHT_AT_FULL,
  POOL_LIGHT_DECAY,
  poolLightIntensity,
  poolLightRange,
} from '../components/rig/previs/poolLight';
import type { LayoutFixture } from '../components/rig/previs/layout';

// The club_night demo rig, as backend/app/services/demo/venue_presets.py lays
// it out: 12 x 10 m floor, 4.5 m trim, DJ booth upstage (-Z).
function clubNight(): { stage: { width: number; depth: number; height: number }; fixtures: LayoutFixture[] } {
  const fixtures: LayoutFixture[] = [];
  let id = 1;
  const spread = (count: number, from: number, to: number) =>
    Array.from({ length: count }, (_, i) => (count === 1 ? 0 : from + ((to - from) * i) / (count - 1)));
  const add = (kind: FixtureModelKind, hasPanTilt: boolean, xs: number[], y: number, z: number) => {
    for (const x of xs) fixtures.push({ id: id++, x, y, z, kind, hasPanTilt });
  };
  add('moving_head', true, spread(6, -5, 5), 4.2, -3.5); // back truss, ids 1-6
  add('moving_head', true, spread(6, -5, 5), 4.3, 0); // mid truss, 7-12
  add('wash', true, spread(4, -4.5, 4.5), 4.2, 3.5); // front truss, 13-16
  add('led_bar', false, spread(4, -2.25, 2.25), 1.0, -3.8); // booth front, 17-20
  add('led_bar', false, spread(4, -4.5, 4.5), 3.0, -4.8); // back wall, 21-24
  add('strobe', false, [-5.7, 5.7], 4.2, 0); // ends of the mid truss, 25-26
  add('strobe', false, [-2, 2], 3.6, -4.8); // back wall, 27-28
  for (const x of [-5.8, 5.8]) add('led_par', false, [x, x, x], 0.3, 0); // floor pars, 29-34
  fixtures.filter((f) => f.kind === 'led_par').forEach((f, i) => { f.z = [-2, 1, 4][i % 3]; });
  return { stage: { width: 12, depth: 10, height: 4.5 }, fixtures };
}

describe('moving head model', () => {
  it('keeps the yoke arms on the tilt axis for any pan and tilt', () => {
    // The head is one group with rotation order YXZ; the yoke is a separate
    // group beside it that is given the pan alone. The arms hold the tilt
    // axle, so the yoke's X axis has to be the axis the head tilts about.
    for (const panDeg of [-200, -90, -30, 0, 45, 135, 250]) {
      for (const tiltDeg of [-120, -45, 0, 30, 110]) {
        const head = new THREE.Object3D();
        head.rotation.order = 'YXZ';
        head.rotation.y = THREE.MathUtils.degToRad(panDeg);
        head.rotation.x = THREE.MathUtils.degToRad(tiltDeg);
        head.updateMatrixWorld(true);

        const yoke = new THREE.Object3D();
        yoke.rotation.y = head.rotation.y;
        yoke.updateMatrixWorld(true);

        const headAxle = new THREE.Vector3(1, 0, 0).transformDirection(head.matrixWorld);
        const yokeAxle = new THREE.Vector3(1, 0, 0).transformDirection(yoke.matrixWorld);
        expect(headAxle.distanceTo(yokeAxle)).toBeLessThan(1e-6);

        // And the beam is the one pan-then-tilt gives: straight down at 0, 0.
        const beam = new THREE.Vector3(0, -1, 0).transformDirection(head.matrixWorld);
        const expected = new THREE.Vector3(0, -1, 0)
          .applyAxisAngle(new THREE.Vector3(1, 0, 0), head.rotation.x)
          .applyAxisAngle(new THREE.Vector3(0, 1, 0), head.rotation.y);
        expect(beam.distanceTo(expected)).toBeLessThan(1e-6);
      }
    }
  });

  it('gives each moving type a head that clears its own yoke', () => {
    for (const kind of ['moving_head', 'beam', 'spot', 'wash'] as const) {
      const dims = FIXTURE_SPECS[kind].mover!;
      // The back of the barrel swings past the crossbar as the head tilts.
      expect(Math.hypot(dims.barrelRear, dims.barrelRadius)).toBeLessThan(dims.armDrop);
      // The barrel fits between the arms.
      expect(dims.barrelRadius).toBeLessThan(dims.armX - dims.armThick / 2);
    }
  });

  it('makes the beam narrower than the spot, and the spot barrel the longest', () => {
    const { beam, spot, moving_head: head, wash } = FIXTURE_SPECS;
    expect(beam.mover!.barrelRadius).toBeLessThan(head.mover!.barrelRadius);
    expect(beam.mover!.lensRadius).toBeLessThan(head.mover!.lensRadius);
    const length = (kind: typeof beam) => kind.mover!.barrelRear + kind.mover!.barrelFront;
    expect(length(spot)).toBeGreaterThan(length(head));
    expect(length(wash)).toBeLessThan(length(head));
    expect(wash.mover!.barrelRadius).toBeGreaterThan(head.mover!.barrelRadius);
  });
});

describe('fixture models', () => {
  const kinds: FixtureModelKind[] = ['moving_head', 'beam', 'spot', 'wash', 'led_par', 'led_bar', 'strobe', 'other'];

  it('builds every type, with a yoke only on the ones that pan and tilt', () => {
    for (const kind of kinds) {
      const geometry = getFixtureGeometry(kind);
      for (const part of [geometry.shell, geometry.emitter, geometry.supportHang, geometry.supportStand]) {
        expect(part.getAttribute('position').count).toBeGreaterThan(0);
        // Every part carries vertex colours: one material draws the lot.
        expect(part.getAttribute('color')).toBeTruthy();
      }
      const mover = FIXTURE_SPECS[kind].mover !== null;
      expect(geometry.yokeHang !== null).toBe(mover);
      expect(geometry.yokeStand !== null).toBe(mover);
    }
  });

  it('sizes each type like the real thing', () => {
    const size = (kind: FixtureModelKind) => {
      const box = getFixtureGeometry(kind).shell.boundingBox!;
      return box.getSize(new THREE.Vector3());
    };
    // A one-metre batten, a strobe panel wider than it is deep, a par can.
    expect(size('led_bar').x).toBeGreaterThan(0.95);
    expect(size('led_bar').x).toBeLessThan(1.1);
    expect(size('strobe').x).toBeGreaterThan(size('strobe').y * 3);
    expect(size('led_par').x).toBeGreaterThan(0.18);
    expect(size('led_par').x).toBeLessThan(0.3);
    // Clamp to lens, a moving head is around 0.7 m.
    const head = FIXTURE_SPECS.moving_head;
    expect(head.hangHeight + head.lensOffset).toBeGreaterThan(0.6);
    expect(head.hangHeight + head.lensOffset).toBeLessThan(0.85);
  });

  it('shares one geometry between fixtures of a type', () => {
    expect(getFixtureGeometry('beam')).toBe(getFixtureGeometry('beam'));
  });

  it('picks a model from the fixture type, and a yoke for anything that pans', () => {
    expect(resolveModelKind('moving_head', true)).toBe('moving_head');
    expect(resolveModelKind('beam', true)).toBe('beam');
    expect(resolveModelKind('spot', true)).toBe('spot');
    expect(resolveModelKind('wash', true)).toBe('wash');
    expect(resolveModelKind('led_par', false)).toBe('led_par');
    expect(resolveModelKind('led_bar', false)).toBe('led_bar');
    expect(resolveModelKind('strobe', false)).toBe('strobe');
    expect(resolveModelKind('other', false)).toBe('other');
    expect(resolveModelKind('laser', false)).toBe('other');
    expect(resolveModelKind(undefined, false)).toBe('other');
    // An unknown type with pan and tilt channels still gets a moving head.
    expect(resolveModelKind('effect', true)).toBe('moving_head');
  });
});

describe('venue layout on the club_night rig', () => {
  const { stage, fixtures } = clubNight();
  const venue = buildVenue(stage, fixtures);
  const mountOf = (id: number) => venue.mounts.get(id)!;

  it('puts the walls on the stage box and the ceiling above the truss', () => {
    const { layout } = venue;
    expect(layout.wallX).toBe(6);
    expect(layout.backZ).toBe(-5);
    expect(layout.houseZ).toBeGreaterThan(5);
    for (const row of venue.trussRows) expect(layout.ceilingY).toBeGreaterThan(row.chordY + 0.3);
  });

  it('runs truss only over the fixtures that hang', () => {
    // Back, mid and front. The old network grouped by depth alone and gave the
    // floor pars a truss across the dance floor.
    expect(venue.trussRows).toHaveLength(3);
    for (const row of venue.trussRows) expect(row.chordY).toBeGreaterThan(4.2);
    expect(venue.trussRows.map((row) => row.z)).toEqual([-3.5, 0, 3.5]);
  });

  it('hangs the strobes off the ends of the mid truss on a drop pipe', () => {
    const mid = venue.trussRows[1];
    expect(mid.xMin).toBeLessThan(-5.7);
    expect(mid.xMax).toBeGreaterThan(5.7);
    for (const id of [25, 26]) {
      const mount = mountOf(id);
      expect(mount.type).toBe('truss');
      // A strobe is shorter than a moving head, so it needs a pipe to reach.
      if (mount.type === 'truss') expect(mount.drop).toBeGreaterThan(0.1);
    }
    const mover = mountOf(8);
    if (mover.type === 'truss') expect(mover.drop).toBe(0);
  });

  it('brackets wall fixtures to the wall and booth bars to the booth front', () => {
    for (const id of [21, 22, 23, 24, 27, 28]) {
      const mount = mountOf(id);
      expect(mount.type).toBe('wall');
      if (mount.type === 'wall') {
        expect([mount.dirX, mount.dirZ]).toEqual([0, -1]);
        expect(mount.reach).toBeCloseTo(0.2, 5);
      }
    }
    for (const id of [17, 18, 19, 20]) {
      const mount = mountOf(id);
      expect(mount.type).toBe('wall');
      // The booth front, not the back wall a metre behind it.
      if (mount.type === 'wall') expect(mount.reach).toBeCloseTo(0.1, 5);
    }
  });

  it('stands the floor pars on the floor, lens up', () => {
    for (const id of [29, 30, 31, 32, 33, 34]) {
      expect(mountOf(id)).toEqual({ type: 'stand', plinth: 0, lift: 0, lensUp: true });
    }
  });

  it('never turns a moving head lens-up: it aims itself', () => {
    const floorMover = buildVenue(stage, [{ id: 1, x: 0, y: 0.2, z: 0, kind: 'moving_head', hasPanTilt: true }]);
    const mount = floorMover.mounts.get(1)!;
    expect(mount.type).toBe('stand');
    if (mount.type === 'stand') {
      expect(mount.lensUp).toBe(false);
      // Patched lower than its own base: raised to stand on the floor.
      expect(mount.lift).toBeGreaterThan(0);
    }
  });

  it('fits the booth, the DJ and the dance floor inside the room', () => {
    const { layout } = venue;
    const { booth, danceFloor } = layout;
    // The booth bars sit at y = 1.0, z = -3.8 on a booth front that covers them.
    expect(booth.fasciaZ).toBeCloseTo(-3.9, 5);
    expect(booth.deskTopY).toBeGreaterThan(1.0);
    expect(booth.width / 2).toBeGreaterThan(2.75);
    expect(booth.djZ).toBeGreaterThan(layout.backZ);
    expect(booth.djZ).toBeLessThan(booth.fasciaZ - booth.deskDepth);
    expect(danceFloor.zMin).toBeGreaterThan(booth.fasciaZ);
    expect(danceFloor.xMax).toBeLessThan(layout.wallX);
    // Clear of the pars standing along the side walls.
    expect(danceFloor.xMax).toBeLessThan(5.8 - 0.5);
    expect(layout.speakers.present).toBe(true);
    expect(layout.speakers.x - layout.speakers.width / 2).toBeGreaterThan(booth.width / 2);
  });

  it('still lays out a small rig and an empty one', () => {
    const small = buildVenue({ width: 4, depth: 3, height: 2.5 }, []);
    expect(small.trussRows).toHaveLength(0);
    expect(small.layout.booth.width).toBeLessThan(4);
    expect(small.layout.danceFloor.zMax).toBeGreaterThan(small.layout.danceFloor.zMin);
    expect(small.layout.ceilingY).toBeGreaterThan(2.5);
    // A fixture with a position that is not a number is left out, not fatal.
    const broken = buildVenue(stage, [{ id: 9, x: Number.NaN, y: 4, z: 0, kind: 'spot', hasPanTilt: true }]);
    expect(broken.mounts.has(9)).toBe(false);
  });

  it('widens the room for a fixture patched outside the stage box', () => {
    const wide = buildVenue(stage, [{ id: 1, x: 7.5, y: 4, z: 0, kind: 'spot', hasPanTilt: true }]);
    expect(wide.layout.wallX).toBeGreaterThan(7.5);
  });
});

describe('camera presets', () => {
  const { layout } = buildVenue({ width: 12, depth: 10, height: 4.5 }, clubNight().fixtures);

  it('leaves the four existing cameras where they were', () => {
    expect(cameraPreset('iso', layout).position).toEqual([0, 4.5 * 0.8, 10 * 1.15]);
    expect(cameraPreset('iso', layout).target).toEqual([0, 4.5 * 0.45, 0]);
    expect(cameraPreset('top', layout).position).toEqual([0, 4.5 + 7, 0.01]);
    expect(cameraPreset('front', layout).position).toEqual([0, 4.5 * 0.55, 10 * 1.65]);
    expect(cameraPreset('audience', layout).position).toEqual([0, 2.5, 10 * 1.95]);
    expect(cameraPreset('audience', layout).target).toEqual([0, 2.8, 0]);
    for (const mode of ['iso', 'top', 'front', 'audience'] as const) {
      expect(cameraPreset(mode, layout).fov).toBe(50);
    }
  });

  it('looks out from behind the DJ toward the dance floor', () => {
    const dj = cameraPreset('dj', layout);
    expect(dj.position[2]).toBeLessThan(layout.booth.djZ);
    expect(dj.position[1]).toBeGreaterThan(layout.booth.deskTopY);
    expect(dj.target[2]).toBeGreaterThan(layout.danceFloor.zMin);
  });

  it('stands on the dance floor looking at the booth', () => {
    const floor = cameraPreset('floor', layout);
    const { danceFloor, booth } = layout;
    expect(floor.position[2]).toBeGreaterThan(danceFloor.zMin);
    expect(floor.position[2]).toBeLessThan(danceFloor.zMax);
    expect(floor.position[0]).toBeGreaterThan(danceFloor.xMin);
    expect(floor.position[0]).toBeLessThan(danceFloor.xMax);
    expect(floor.target[2]).toBeCloseTo(booth.fasciaZ, 5);
    // Above head height, so the view clears the people in front.
    expect(floor.position[1]).toBeGreaterThan(1.95);
  });
});

describe('crowd', () => {
  const { layout } = buildVenue({ width: 12, depth: 10, height: 4.5 }, clubNight().fixtures);
  const { danceFloor, floorCamera } = layout;

  it('is the same crowd every time', () => {
    expect(placeCrowd(layout, 180)).toEqual(placeCrowd(layout, 180));
  });

  it('grows with the quality mode', () => {
    const [perf, balanced, ultra] = [80, 180, 320].map((count) => placeCrowd(layout, count).length);
    expect(perf).toBe(80);
    expect(balanced).toBeGreaterThan(perf * 1.8);
    expect(ultra).toBeGreaterThan(balanced * 1.25);
    expect(ultra).toBeLessThanOrEqual(crowdCapacity(layout));
  });

  it('stays on the dance floor, clear of the floor camera and of each other', () => {
    const people = placeCrowd(layout, 320);
    for (const person of people) {
      expect(person.x).toBeGreaterThan(danceFloor.xMin);
      expect(person.x).toBeLessThan(danceFloor.xMax);
      expect(person.z).toBeGreaterThan(danceFloor.zMin);
      expect(person.z).toBeLessThan(danceFloor.zMax);
      expect(Math.hypot(person.x - floorCamera.x, person.z - floorCamera.z)).toBeGreaterThanOrEqual(floorCamera.clearRadius);
    }
    let nearest = Infinity;
    for (let i = 0; i < people.length; i += 1) {
      for (let j = i + 1; j < people.length; j += 1) {
        nearest = Math.min(nearest, Math.hypot(people[i].x - people[j].x, people[i].z - people[j].z));
      }
    }
    expect(nearest).toBeGreaterThanOrEqual(0.4);
  });

  it('is denser near the booth and faces it', () => {
    const people = placeCrowd(layout, 180);
    const mid = (danceFloor.zMin + danceFloor.zMax) / 2;
    const front = people.filter((person) => person.z < mid).length;
    expect(front).toBeGreaterThan((people.length - front) * 1.5);
    for (const person of people) {
      // Yaw 0 faces +Z. Everyone looks toward the DJ, give or take: someone at
      // the front corner is turned well in, someone at the back faces upstage.
      const toDjX = -person.x;
      const toDjZ = layout.booth.djZ - person.z;
      const reach = Math.hypot(toDjX, toDjZ);
      const facing = (Math.sin(person.yaw) * toDjX + Math.cos(person.yaw) * toDjZ) / reach;
      expect(facing).toBeGreaterThan(0.8);
    }
  });

  it('asks for nobody on a floor with no room', () => {
    expect(placeCrowd(layout, 0)).toEqual([]);
  });
});

describe('beat clock', () => {
  type Hit = { at: number };
  type Pattern = (beatIndex: number) => Hit[];

  // How the engine reports a beat, as measured on the wire: about 45 reports a
  // second, the phase counting up from the last hit the detector heard and
  // falling back at the next one.
  const everyBeat: Pattern = (beat) => [{ at: beat }];
  // What the detector actually does on a four-on-the-floor track: it also
  // fires on the off-beat hit.
  const beatAndOffBeat: Pattern = (beat) => [{ at: beat }, { at: beat + 0.5 }];
  // The same, with the off-beat hit landing late or early, as it does.
  const ragged: Pattern = (beat) => [{ at: beat }, { at: beat + 0.5 + ((beat * 37) % 7 - 3) * 0.03 }];

  function play(
    clock: ReturnType<typeof createBeatClock>,
    options: { bpm?: number; fromMs?: number; seconds: number; pattern?: Pattern; section?: string; offsetBeats?: number },
  ) {
    const bpm = options.bpm ?? 128;
    const pattern = options.pattern ?? everyBeat;
    const from = options.fromMs ?? 0;
    const to = from + options.seconds * 1000;
    const truth = (t: number) => (t * bpm) / 60000 + (options.offsetBeats ?? 0);
    let nextReport = from;
    let largestStep = 0;
    let wentBack = false;
    for (let t = from; t <= to; t += 16) {
      if (t >= nextReport) {
        const position = truth(t);
        const beat = Math.floor(position);
        const hits = [...pattern(beat - 1), ...pattern(beat)].filter((hit) => hit.at <= position);
        const last = hits[hits.length - 1];
        ingestAnalysis(clock, {
          beat: { bpm, phase: Math.min(1, position - last.at) },
          lighting: { section: options.section ?? 'verse' },
        }, t);
        nextReport += 22;
      }
      const before = clock.beat;
      advanceBeatClock(clock, 0.016, t);
      largestStep = Math.max(largestStep, clock.beat - before);
      if (clock.beat < before) wentBack = true;
    }
    const endMs = from + Math.floor((to - from) / 16) * 16;
    // How far the clock's beat is from the music's, in beats, -0.5 to 0.5.
    const offBy = phaseDelta(truth(endMs) % 1, clock.beat - Math.floor(clock.beat));
    return { offBy, largestStep, wentBack, endMs };
  }

  it('locks to a beat reported cleanly', () => {
    for (const bpm of [96, 128, 174]) {
      const clock = createBeatClock();
      const { offBy } = play(clock, { bpm, seconds: 6 });
      expect(clock.running).toBe(true);
      expect(clock.bpm).toBe(bpm);
      expect(Math.abs(offBy)).toBeLessThan(0.05);
    }
  });

  it('keeps to the tempo when the detector also fires on the off-beat', () => {
    // Following the reported phase directly doubled the tempo here.
    for (const pattern of [beatAndOffBeat, ragged]) {
      const clock = createBeatClock();
      play(clock, { seconds: 3, pattern });
      const start = clock.beat;
      const { offBy } = play(clock, { fromMs: 3000, seconds: 10, pattern });
      const expected = (10 * 128) / 60;
      expect(Math.abs(clock.beat - start - expected)).toBeLessThan(0.3);
      expect(Math.abs(offBy)).toBeLessThan(0.08);
    }
  });

  it('holds whichever half of the beat it found: it cannot tell beat from off-beat', () => {
    // A known limit, pinned here so a change to it is a decision. The reports
    // carry nothing that says which hits are the beat, so a clock that starts
    // half a beat out stays half a beat out, steadily.
    const clock = createBeatClock();
    const { offBy, wentBack } = play(clock, { seconds: 14, pattern: ragged, offsetBeats: 0.5 });
    expect(Math.abs(Math.abs(offBy) - 0.5)).toBeLessThan(0.08);
    expect(wentBack).toBe(false);
  });

  it('runs smoothly: never backwards, never a jump', () => {
    for (const pattern of [everyBeat, beatAndOffBeat, ragged]) {
      const clock = createBeatClock();
      const { largestStep, wentBack } = play(clock, { seconds: 12, pattern });
      expect(wentBack).toBe(false);
      // A frame at 128 bpm is 0.034 of a beat; the most the clock may be
      // pulled adds 0.01 to that.
      expect(largestStep).toBeLessThan(0.05);
    }
  });

  it('counts one hit once when two reports carry it', () => {
    // The engine sends each analysis twice, a few milliseconds apart.
    const clock = createBeatClock();
    for (let t = 0; t <= 6000; t += 8) {
      const position = (t * 128) / 60000;
      const phase = position % 1;
      if (t % 24 === 0) ingestAnalysis(clock, { beat: { bpm: 128, phase } }, t);
      // The second copy is the first one again, 16 ms late.
      if (t % 24 === 16) ingestAnalysis(clock, { beat: { bpm: 128, phase: (((t - 16) * 128) / 60000) % 1 } }, t);
      if (t % 16 === 0) advanceBeatClock(clock, 0.016, t);
    }
    const beats = (6000 * 128) / 60000;
    expect(clock.ticks).toBeGreaterThan(beats - 2);
    expect(clock.ticks).toBeLessThan(beats + 2);
  });

  it('stops when the reported phase stops moving, as it does with no music', () => {
    const clock = createBeatClock();
    play(clock, { seconds: 3 });
    expect(clock.running).toBe(true);
    const beatAtStop = clock.beat;
    for (let t = 3000; t <= 7000; t += 16) {
      if (t % 32 === 0) ingestAnalysis(clock, { beat: { bpm: 120, phase: 0 }, lighting: { section: 'breakdown' } }, t);
      advanceBeatClock(clock, 0.016, t);
    }
    expect(clock.running).toBe(false);
    expect(clock.energy).toBeLessThan(0.02);
    // It coasts for a moment, then holds: nobody dances to a beat that is gone.
    expect(clock.beat - beatAtStop).toBeLessThan(4);
    // And it has let go of the old track, to find the next one afresh.
    expect(clock.ticks).toBe(0);
  });

  it('never starts on a clock that has seen no reports', () => {
    const clock = createBeatClock();
    for (let t = 0; t < 2000; t += 16) advanceBeatClock(clock, 0.016, t);
    expect(clock.running).toBe(false);
    expect(clock.beat).toBe(0);
  });

  it('ignores a phase that is not a number between 0 and 1', () => {
    const clock = createBeatClock();
    // The demo simulation has a field called phase that holds a name.
    for (const bad of ['build', null, undefined, Number.NaN, 1.4, -0.2, {}]) {
      ingestAnalysis(clock, { beat: { bpm: 128, phase: bad } }, 100);
    }
    ingestAnalysis(clock, null, 100);
    ingestAnalysis(clock, 'nonsense', 100);
    advanceBeatClock(clock, 0.016, 116);
    expect(clock.running).toBe(false);
    expect(clock.reportedPhase).toBe(0);
    expect(clock.ticks).toBe(0);
  });

  it('ignores a tempo that cannot be one', () => {
    const clock = createBeatClock();
    for (const bpm of [0, Number.NaN, 900, -128]) ingestAnalysis(clock, { beat: { bpm, phase: 0.5 } }, 0);
    expect(clock.bpm).toBe(120);
  });

  it('is at its most energetic in a drop, whatever case the section arrives in', () => {
    expect(sectionEnergy('drop')).toBe(1);
    for (const other of ['verse', 'chorus', 'buildup', 'breakdown', 'intro', 'unknown']) {
      expect(sectionEnergy(other)).toBeLessThan(sectionEnergy('drop'));
    }
    const upper = createBeatClock();
    const lower = createBeatClock();
    play(upper, { seconds: 8, section: 'DROP' });
    play(lower, { seconds: 8, section: 'drop' });
    expect(upper.section).toBe('drop');
    expect(upper.energy).toBeCloseTo(lower.energy, 6);
    expect(upper.energy).toBeGreaterThan(0.95);

    const verse = createBeatClock();
    play(verse, { seconds: 8, section: 'verse' });
    expect(verse.energy).toBeLessThan(upper.energy - 0.3);
  });

  it('measures the short way round between two phases', () => {
    expect(phaseDelta(0.9, 0.1)).toBeCloseTo(0.2, 6);
    expect(phaseDelta(0.1, 0.9)).toBeCloseTo(-0.2, 6);
    expect(phaseDelta(0.25, 0.5)).toBeCloseTo(0.25, 6);
  });
});

// The groups a fixture is drawn with, nested as Fixture3D nests them: the body
// at the fixture's position, turned by the yaw it is hung at; inside it the
// head, turned tilt first and pan second; and inside that the group that faces
// the fixture down or, with half a turn about X, up. The housing, the beam and
// the spot light all sit in that last group, and the beam runs down its -Y.
function drawnBeam({ y, yawDeg = 0, panDeg = 0, tiltDeg = 0, lensUp = false }: {
  y: number; yawDeg?: number; panDeg?: number; tiltDeg?: number; lensUp?: boolean;
}) {
  const body = new THREE.Group();
  body.position.set(1.5, y, -2);
  body.rotation.y = THREE.MathUtils.degToRad(yawDeg);
  const head = new THREE.Group();
  head.rotation.order = 'YXZ';
  head.rotation.y = THREE.MathUtils.degToRad(panDeg);
  head.rotation.x = THREE.MathUtils.degToRad(tiltDeg);
  body.add(head);
  const facing = new THREE.Group();
  facing.rotation.x = lensUp ? Math.PI : 0;
  head.add(facing);
  body.updateMatrixWorld(true);
  const direction = new THREE.Vector3(0, -1, 0).transformDirection(facing.matrixWorld);
  return { direction, tiltRad: head.rotation.x, facing };
}

describe('how far a beam travels', () => {
  const CEILING = 5.4;
  const FAR = 1000;

  it('is the distance to the floor along the beam, however the head is turned', () => {
    for (const yawDeg of [0, 90, 180, -45]) {
      for (const panDeg of [-200, -80, 0, 35, 170]) {
        for (const tiltDeg of [-68, -40, -10, 0, 25, 48, 60, 75]) {
          const y = 4.2;
          const { direction, tiltRad } = drawnBeam({ y, yawDeg, panDeg, tiltDeg });
          // Follow the drawn beam down to the floor plane.
          const alongBeam = y / -direction.y;
          expect(beamThrow(y, beamRise(tiltRad), CEILING, FAR)).toBeCloseTo(alongBeam, 6);
        }
      }
    }
  });

  it('is the height of the fixture for a beam pointing straight down, as it always was', () => {
    expect(beamThrow(4.2, beamRise(0), CEILING, FAR)).toBeCloseTo(4.2, 9);
    expect(beamThrow(9.2, beamRise(0), 11, FAR)).toBeCloseTo(9.2, 9);
  });

  it('grows as the head leans, so the light still reaches the floor', () => {
    const lean = (deg: number) => beamThrow(4.2, beamRise(THREE.MathUtils.degToRad(deg)), CEILING, FAR);
    expect(lean(40)).toBeGreaterThan(lean(0) * 1.3);
    // The old range was 1.5 times the height: gone by 48 degrees of lean.
    expect(lean(60)).toBeGreaterThan(4.2 * 1.5);
    expect(lean(-60)).toBeCloseTo(lean(60), 9);
  });

  it('goes to the ceiling for a beam pointing above level', () => {
    for (const tiltDeg of [100, 120, 135, -135, 180]) {
      const y = 4.2;
      const { direction, tiltRad } = drawnBeam({ y, panDeg: 30, tiltDeg });
      expect(direction.y).toBeGreaterThan(0);
      const alongBeam = (CEILING - y) / direction.y;
      expect(beamThrow(y, beamRise(tiltRad), CEILING, FAR)).toBeCloseTo(alongBeam, 6);
    }
  });

  it('stops at the longest line in the room for a beam that is level or nearly so', () => {
    for (const tiltDeg of [89.9, 90, 90.1, -90]) {
      expect(beamThrow(4.2, beamRise(THREE.MathUtils.degToRad(tiltDeg)), CEILING, 19)).toBe(19);
    }
    expect(beamThrow(4.2, 0, CEILING, 19)).toBe(19);
    expect(beamThrow(4.2, -0, CEILING, 19)).toBe(19);
  });

  it('is always a positive, finite distance: three.js reads a range of 0 as no limit', () => {
    const awkward: Array<[number, number, number, number]> = [
      [Number.NaN, -1, CEILING, 19], // a fixture with no position
      [4.2, Number.NaN, CEILING, 19], // a tilt that is not a number
      [0, -1, CEILING, 19], // on the floor, pointing down
      [-0.5, -1, CEILING, 19], // patched under the floor
      [6, 1, CEILING, 19], // above the ceiling, pointing up
      [4.2, -1, Number.NaN, 19],
      [4.2, 1, Number.NaN, 19],
      [4.2, -1, CEILING, Number.NaN],
      [4.2, -1, CEILING, 0],
      [4.2, -1, CEILING, -3],
      [4.2, 0, CEILING, Number.POSITIVE_INFINITY],
    ];
    for (const [sourceY, rise, ceilingY, longest] of awkward) {
      const reach = beamThrow(sourceY, rise, ceilingY, longest);
      expect(Number.isFinite(reach)).toBe(true);
      expect(reach).toBeGreaterThan(0);
    }
  });

  it('sends the light of a fixture standing lens-up to the ceiling', () => {
    const { layout, mounts } = buildVenue({ width: 12, depth: 10, height: 4.5 }, clubNight().fixtures);
    for (const id of [29, 30, 31, 32, 33, 34]) {
      const mount = mounts.get(id)!;
      expect(mount.type === 'stand' && mount.lensUp).toBe(true);
    }
    // The six floor pars stand at 0.3 m, turned to face whichever way.
    for (const yawDeg of [0, 90, -90, 180]) {
      const { direction, tiltRad } = drawnBeam({ y: 0.3, yawDeg, lensUp: true });
      expect(direction.distanceTo(new THREE.Vector3(0, 1, 0))).toBeLessThan(1e-9);
      const reach = beamThrow(0.3, beamRise(tiltRad, true), layout.ceilingY, roomSpan(layout));
      expect(reach).toBeCloseTo(layout.ceilingY - 0.3, 9);
      // The old beam was as long as the fixture is high: 0.3 m, into the floor.
      expect(reach).toBeGreaterThan(4);
    }
  });

  it('turns the lit face of the housing up with the beam, not on its own', () => {
    // The lit face of every model is on its -Y side, where the beam leaves.
    // The one group that faces a fixture up carries both, so after the turn
    // the lit face is on top and the beam goes the same way.
    const { direction, facing } = drawnBeam({ y: 0.3, lensUp: true });
    for (const kind of ['led_par', 'led_bar', 'strobe', 'other'] as const) {
      const emitter = getFixtureGeometry(kind).emitter;
      emitter.computeBoundingBox();
      const litFace = emitter.boundingBox!.getCenter(new THREE.Vector3());
      expect(litFace.y).toBeLessThan(0);
      const turned = litFace.clone().applyMatrix4(facing.matrixWorld).sub(new THREE.Vector3(1.5, 0.3, -2));
      expect(turned.y).toBeGreaterThan(0);
      expect(Math.sign(turned.y)).toBe(Math.sign(direction.y));
    }
  });

  it('leaves every other fixture pointing as its tilt says', () => {
    for (const tiltDeg of [-120, -40, 0, 30, 95]) {
      const tiltRad = THREE.MathUtils.degToRad(tiltDeg);
      expect(beamRise(tiltRad)).toBe(beamRise(tiltRad, false));
      expect(beamRise(tiltRad, true)).toBeCloseTo(-beamRise(tiltRad), 12);
    }
    expect(beamRise(0)).toBe(-1);
    expect(beamRise(0, true)).toBe(1);
  });

  it('takes the room corner to corner as the longest line in it', () => {
    const { layout } = buildVenue({ width: 12, depth: 10, height: 4.5 }, clubNight().fixtures);
    const corners: THREE.Vector3[] = [];
    for (const x of [-layout.wallX, layout.wallX]) {
      for (const y of [0, layout.ceilingY]) {
        for (const z of [layout.backZ, layout.houseZ]) corners.push(new THREE.Vector3(x, y, z));
      }
    }
    let longest = 0;
    for (const a of corners) for (const b of corners) longest = Math.max(longest, a.distanceTo(b));
    expect(roomSpan(layout)).toBeCloseTo(longest, 9);
    // Longer than the throw of the steepest lean the engine asks for (68 degrees).
    expect(roomSpan(layout)).toBeGreaterThan(4.3 / Math.cos(THREE.MathUtils.degToRad(68)));
  });
});

// How much of a light with a range is left at a distance, as three.js works it
// out (getDistanceAttenuation in lights_pars_begin.glsl.js, three 0.160, the
// branch used when legacy lights are off): a falloff with distance, times a
// fade that reaches nothing at the range.
function lightLeft(distance: number, range: number, decay: number): number {
  const falloff = 1 / Math.max(Math.pow(distance, decay), 0.01);
  if (!(range > 0)) return falloff;
  const fade = Math.min(1, Math.max(0, 1 - Math.pow(distance / range, 4)));
  return falloff * fade * fade;
}

describe('how bright a pool of light is', () => {
  // Where the beam lands, for a level and a throw.
  const atLanding = (level: number, throwDistance: number) =>
    poolLightIntensity(level) * lightLeft(throwDistance, poolLightRange(throwDistance), POOL_LIGHT_DECAY);

  it('is the same from a 13 m truss as from a stand a metre off the floor', () => {
    const fromClubTruss = atLanding(0.5, 4.2);
    expect(fromClubTruss).toBeGreaterThan(0);
    for (const throwDistance of [0.93, 2.8, 4.2, 6.5, 9.2, 13]) {
      expect(atLanding(0.5, throwDistance)).toBeCloseTo(fromClubTruss, 9);
    }
  });

  it('does not burn out something close to the fixture', () => {
    // With the falloff three.js applies by default, a head 0.5 m under a lamp
    // 9 m up took dozens of times the light the floor did.
    for (const throwDistance of [4.2, 9.2, 13]) {
      const range = poolLightRange(throwDistance);
      const near = lightLeft(0.5, range, POOL_LIGHT_DECAY);
      const landing = lightLeft(throwDistance, range, POOL_LIGHT_DECAY);
      expect(near / landing).toBeLessThan(1.6);
    }
  });

  it('follows the level from zero, with no step on the way up', () => {
    expect(poolLightIntensity(0)).toBe(0);
    expect(poolLightIntensity(0.2)).toBeCloseTo(0.2 * POOL_LIGHT_AT_FULL, 9);
    expect(poolLightIntensity(0.5)).toBeCloseTo(0.5 * POOL_LIGHT_AT_FULL, 9);
    // The light used to switch on at 8 % of full as the level passed 0.08.
    expect(poolLightIntensity(0.05)).toBeGreaterThan(0);
    let previous = 0;
    for (let i = 1; i <= 200; i += 1) {
      const now = poolLightIntensity(i / 200);
      expect(now).toBeGreaterThan(previous);
      expect(now - previous).toBeLessThan(POOL_LIGHT_AT_FULL * 0.006);
      previous = now;
    }
  });

  it('is full at a level of 1, no more above it, and nothing for a level that makes no sense', () => {
    expect(poolLightIntensity(1)).toBe(POOL_LIGHT_AT_FULL);
    expect(poolLightIntensity(1.7)).toBe(POOL_LIGHT_AT_FULL);
    for (const level of [-0.3, Number.NaN, Number.NEGATIVE_INFINITY]) expect(poolLightIntensity(level)).toBe(0);
  });

  it('ends the light a little way past where the beam lands, and not before', () => {
    for (const throwDistance of [0.93, 4.2, 9.2]) {
      const range = poolLightRange(throwDistance);
      expect(range).toBeGreaterThan(throwDistance);
      // More than half the light is still there at the landing point...
      expect(lightLeft(throwDistance, range, POOL_LIGHT_DECAY)).toBeGreaterThan(0.5);
      // ...and none at the range, which is under twice as far.
      expect(lightLeft(range, range, POOL_LIGHT_DECAY)).toBe(0);
      expect(range).toBeLessThan(throwDistance * 2);
    }
  });
});
