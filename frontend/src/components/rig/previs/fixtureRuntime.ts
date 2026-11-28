/**
 * One fixture's life in the 3D view, as a plain object the frame loop steps.
 *
 * This used to be a React component per fixture (`Fixture3D`), each with its
 * own frame callback and its own tree of meshes. It is now state objects
 * stepped by one frame callback, with every fixture drawn through a handful of
 * instanced meshes (FixtureRig.tsx, docs/PREVIZ_PERFORMANCE.md). The maths is
 * the component's, unchanged: the reading of the output frame through the
 * profile (readBeamState), the smoothing, the strobe, the fixed-step pan and
 * tilt inertia, where the beam lands and how it is shaped.
 *
 * Nothing here allocates per frame and nothing goes through React.
 */
import * as THREE from 'three';
import type { RigFixture } from '../../../types';
import { beamMouth } from './beamShape';
import type { BeamMouth } from './beamShape';
import { buildBeamProfile, buildChannelMap, createBeamState, readBeamState } from './beamState';
import type { BeamProfile, BeamState } from './beamState';
import { beamDirection, beamLanding, hangBeam } from './beamThrow';
import type { BeamRoom, BeamSurface, BeamVector } from './beamThrow';
import { FIXTURE_SPECS, resolveModelKind } from './fixtureSpecs';
import type { FixtureModelKind } from './fixtureSpecs';
import type { FixtureMount } from './layout';
import { poolConeDeg, poolRadius } from './poolLight';

export type BeamDebugSnapshot = {
  fixtureId: number;
  fixtureLabel: string;
  targetPanDeg: number;
  targetTiltDeg: number;
  currentPanDeg: number;
  currentTiltDeg: number;
  panVelocityDegPerSec: number;
  tiltVelocityDegPerSec: number;
  signalConfidence: number;
  hold: boolean;
  strobeLogical: number;
  strobeChannelValue: number;
  strobeChannelIndex?: number;
  strobeSource: 'strobe' | 'shutter' | 'none';
  shutter: 'open' | 'closed' | 'strobe';
  zoomLogical: number;
  zoomChannelValue: number;
  zoomChannelIndex?: number;
  zoomSource: 'zoom' | 'beam_angle' | 'fallback';
  finalIntensity: number;
  finalSpotAngleDeg: number;
  capabilityWarnings: string[];
  motionSource: string;
};

type MotionInertiaProfile = {
  panMaxVelDegPerSec: number;
  tiltMaxVelDegPerSec: number;
  panMaxAccelDegPerSec2: number;
  tiltMaxAccelDegPerSec2: number;
  damping: number;
};

// Fixture types that pan and tilt whether or not the profile lists the channels.
const MOVING_HEAD_TYPES = new Set(['moving_head', 'mover', 'spot', 'beam', 'wash', 'profile', 'hybrid']);

export const FIXTURE_MOTION_PROFILES: Record<string, MotionInertiaProfile> = {
  moving_head: { panMaxVelDegPerSec: 220, tiltMaxVelDegPerSec: 180, panMaxAccelDegPerSec2: 540, tiltMaxAccelDegPerSec2: 420, damping: 0.88 },
  mover: { panMaxVelDegPerSec: 220, tiltMaxVelDegPerSec: 180, panMaxAccelDegPerSec2: 540, tiltMaxAccelDegPerSec2: 420, damping: 0.88 },
  beam: { panMaxVelDegPerSec: 260, tiltMaxVelDegPerSec: 220, panMaxAccelDegPerSec2: 720, tiltMaxAccelDegPerSec2: 560, damping: 0.86 },
  spot: { panMaxVelDegPerSec: 180, tiltMaxVelDegPerSec: 150, panMaxAccelDegPerSec2: 420, tiltMaxAccelDegPerSec2: 340, damping: 0.90 },
  wash: { panMaxVelDegPerSec: 170, tiltMaxVelDegPerSec: 150, panMaxAccelDegPerSec2: 360, tiltMaxAccelDegPerSec2: 300, damping: 0.91 },
  profile: { panMaxVelDegPerSec: 175, tiltMaxVelDegPerSec: 150, panMaxAccelDegPerSec2: 380, tiltMaxAccelDegPerSec2: 320, damping: 0.90 },
  hybrid: { panMaxVelDegPerSec: 220, tiltMaxVelDegPerSec: 180, panMaxAccelDegPerSec2: 520, tiltMaxAccelDegPerSec2: 420, damping: 0.88 },
  default: { panMaxVelDegPerSec: 130, tiltMaxVelDegPerSec: 110, panMaxAccelDegPerSec2: 260, tiltMaxAccelDegPerSec2: 220, damping: 0.92 },
};

/** Below this a beam is not drawn at all. */
export const BEAM_VISIBLE_FROM = 0.015;

const FIXED_CONTROL_DT = 1 / 60;
const MAX_STABLE_DELTA = 1 / 20;
const DELTA_SPIKE_FACTOR = 2.2;

// What kind of fixture this is. Worked out in one place because three things
// have to agree on it: the control loop, the model that is drawn, and the venue
// layout that decides how the fixture is mounted.
export function describeFixture(fixture: RigFixture, channelMap: Record<string, number> = buildChannelMap(fixture)) {
  const fixtureType: string = fixture.fixture?.fixture_type || 'other';
  const hasPanTiltChannels = channelMap.pan !== undefined && channelMap.tilt !== undefined;
  const isMovingHead = hasPanTiltChannels || MOVING_HEAD_TYPES.has(fixtureType);
  return {
    fixtureType,
    hasPanTiltChannels,
    isMovingHead,
    modelKind: resolveModelKind(fixtureType, isMovingHead),
  };
}

/**
 * Everything about one fixture: what does not change between frames (worked
 * out from the rig row and its mount) and what does (the smoothing, the head's
 * motion, where the beam lands), and this frame's results for the draw.
 */
export type FixtureRuntime = {
  id: number;
  fixture: RigFixture;
  mount: FixtureMount;
  // --- Fixed for a given rig row and mount -------------------------------
  profile: BeamProfile;
  universe: number;
  fixtureType: string;
  isMovingHead: boolean;
  isBeamLike: boolean;
  isSpotLike: boolean;
  modelKind: FixtureModelKind;
  motionProfile: MotionInertiaProfile;
  /** A fixed-body fixture standing on the floor, turned over to face the ceiling. */
  lensUp: boolean;
  standLift: number;
  /** Height of the point the light comes from. */
  sourceY: number;
  hangRx: number;
  hangRz: number;
  bodyYawRad: number;
  /** How far down the beam from the fixture's own position its light sits. */
  lightDepth: number;
  mouth: BeamMouth;
  // --- Carried from frame to frame ---------------------------------------
  beam: BeamState;
  smoothed: { intensity: number; r: number; g: number; b: number };
  controlAccumulator: number;
  stableDeltaEstimate: number;
  orientation: {
    previousPanRad: number;
    previousTiltRad: number;
    previousTargetPanRad: number;
    previousTargetTiltRad: number;
    currentPanRad: number;
    currentTiltRad: number;
    targetPanRad: number;
    targetTiltRad: number;
    panVelocityRadPerSec: number;
    tiltVelocityRadPerSec: number;
    holdDurationSec: number;
  };
  // --- This frame ---------------------------------------------------------
  /** The head's pan and tilt as drawn: interpolated between control steps. 0 for a fixed body. */
  panRad: number;
  tiltRad: number;
  /** Level with the strobe applied: what the beam, the lens and the pool show. */
  effectiveIntensity: number;
  /** The beam's colour, dark palettes lifted a little so they still read in haze. */
  beamColor: THREE.Color;
  coneRad: number;
  finalSpotAngleDeg: number;
  /** Which way the beam points in the room, where it lands, and on what. */
  pointing: BeamVector;
  surface: BeamSurface;
  reach: number;
  /** Half-width of the beam where it lands: its pool's radius. */
  endRadius: number;
  /** The gobo's turn this frame, radians 0 to 2 pi: held where the channel puts it, or run on at its speed. */
  goboAngle: number;
  // Debug numbers, kept so the table can be filled without redoing the step.
  motion: {
    targetPanDeg: number;
    targetTiltDeg: number;
    currentPanDeg: number;
    currentTiltDeg: number;
    panVelocityDegPerSec: number;
    tiltVelocityDegPerSec: number;
    signalConfidence: number;
    hold: boolean;
    strobe: number;
    zoom: number;
  };
  // --- Where the parts are drawn this frame ------------------------------
  /** Position and yaw only: the support, which stays upright. */
  supportMatrix: THREE.Matrix4;
  /** Support plus how the fixture is hung (rotation_x, rotation_z). */
  hangMatrix: THREE.Matrix4;
  /** Hang plus pan: the yoke arms. */
  yokeMatrix: THREE.Matrix4;
  /** Hang plus pan and tilt, then turned lens-up if it stands that way: housing and lens. */
  headMatrix: THREE.Matrix4;
  /** The head moved down to the mouth of the beam. */
  beamMatrix: THREE.Matrix4;
};

/** Fill in, or refill, what is fixed about a fixture from its rig row and mount. */
function applyFixedParts(rt: FixtureRuntime, fixture: RigFixture, mount: FixtureMount): void {
  rt.fixture = fixture;
  rt.mount = mount;
  rt.profile = buildBeamProfile(fixture);
  rt.universe = Number(fixture.universe) || 0;
  const described = describeFixture(fixture, rt.profile.channels);
  rt.fixtureType = described.fixtureType;
  rt.isMovingHead = described.isMovingHead;
  rt.modelKind = described.modelKind;
  rt.isBeamLike = rt.fixtureType === 'beam' || rt.fixtureType === 'moving_head' || rt.fixtureType === 'mover';
  rt.isSpotLike = rt.fixtureType === 'spot';
  rt.motionProfile = FIXTURE_MOTION_PROFILES[rt.fixtureType] || FIXTURE_MOTION_PROFILES.default;

  // How the rig says the fixture is hung, beyond its yaw: rotation_x and
  // rotation_z, for one on its side or leaning. Applied to the yoke, the head
  // and the beam together, inside the yaw.
  rt.hangRx = THREE.MathUtils.degToRad(Number(fixture.rotation_x) || 0);
  rt.hangRz = THREE.MathUtils.degToRad(Number(fixture.rotation_z) || 0);
  const leaning = rt.hangRx !== 0 || rt.hangRz !== 0;
  // A fixed-body fixture standing on the floor faces the ceiling: the model,
  // its beam and its light are turned over together. That is a guess from
  // where it stands, so a rotation the rig gives outright wins.
  rt.lensUp = mount.type === 'stand' && Boolean(mount.lensUp) && !leaning;
  // A fixture patched lower than its own feet is raised to stand on the floor.
  rt.standLift = mount.type === 'stand' ? mount.lift : 0;
  rt.sourceY = fixture.position_y + rt.standLift;
  // The yaw the rig says this fixture is hung at. 0 aims down local +Z
  // (downstage, toward the audience), +90 deg aims toward +X.
  rt.bodyYawRad = THREE.MathUtils.degToRad(Number(fixture.rotation_y) || 0);
  rt.lightDepth = FIXTURE_SPECS[rt.modelKind].lensOffset + 0.02;
  rt.mouth = beamMouth(rt.modelKind);

  // Position and yaw, then the hang.
  scratchPosition.set(fixture.position_x, rt.sourceY, fixture.position_z);
  scratchEuler.set(0, rt.bodyYawRad, 0, 'XYZ');
  scratchQuaternion.setFromEuler(scratchEuler);
  rt.supportMatrix.compose(scratchPosition, scratchQuaternion, UNIT);
  scratchEuler.set(rt.hangRx, 0, rt.hangRz, 'XYZ');
  scratchMatrix.makeRotationFromEuler(scratchEuler);
  rt.hangMatrix.multiplyMatrices(rt.supportMatrix, scratchMatrix);
}

/**
 * The runtime for `fixture`, reusing `previous` (the same fixture id in the
 * rig drawn before) so a head keeps its place and a beam its level when the
 * rig is replaced by an edit: a drag, a nudge, an activation.
 */
export function syncFixtureRuntime(
  previous: FixtureRuntime | undefined,
  fixture: RigFixture,
  mount: FixtureMount,
): FixtureRuntime {
  if (previous) {
    if (previous.fixture !== fixture || previous.mount !== mount) applyFixedParts(previous, fixture, mount);
    return previous;
  }
  const rt = {
    id: fixture.id,
    beam: createBeamState(),
    smoothed: { intensity: 0, r: 1, g: 1, b: 1 },
    controlAccumulator: 0,
    stableDeltaEstimate: FIXED_CONTROL_DT,
    orientation: {
      previousPanRad: 0,
      previousTiltRad: 0,
      previousTargetPanRad: 0,
      previousTargetTiltRad: 0,
      currentPanRad: 0,
      currentTiltRad: 0,
      targetPanRad: 0,
      targetTiltRad: 0,
      panVelocityRadPerSec: 0,
      tiltVelocityRadPerSec: 0,
      holdDurationSec: 0,
    },
    panRad: 0,
    tiltRad: 0,
    effectiveIntensity: 0,
    beamColor: new THREE.Color(1, 1, 1),
    coneRad: 0,
    finalSpotAngleDeg: 0,
    pointing: { x: 0, y: -1, z: 0 },
    surface: { x: 0, y: 0, z: 0, d: 0 },
    reach: 1,
    endRadius: 0,
    goboAngle: 0,
    motion: {
      targetPanDeg: 0,
      targetTiltDeg: 0,
      currentPanDeg: 0,
      currentTiltDeg: 0,
      panVelocityDegPerSec: 0,
      tiltVelocityDegPerSec: 0,
      signalConfidence: 1,
      hold: false,
      strobe: 0,
      zoom: 0,
    },
    supportMatrix: new THREE.Matrix4(),
    hangMatrix: new THREE.Matrix4(),
    yokeMatrix: new THREE.Matrix4(),
    headMatrix: new THREE.Matrix4(),
    beamMatrix: new THREE.Matrix4(),
  } as unknown as FixtureRuntime;
  applyFixedParts(rt, fixture, mount);
  return rt;
}

const UNIT = new THREE.Vector3(1, 1, 1);
const scratchPosition = new THREE.Vector3();
const scratchQuaternion = new THREE.Quaternion();
const scratchEuler = new THREE.Euler();
const scratchMatrix = new THREE.Matrix4();
const headEuler = new THREE.Euler(0, 0, 0, 'YXZ');
// Half a turn about X: a fixed body standing lens-up.
const FACING_UP = new THREE.Matrix4().makeRotationX(Math.PI);

/**
 * Step one fixture by one frame: read what it is sent, smooth it, move its
 * head, find where its beam lands, and place its parts. `frame` is its
 * universe's output frame (or nothing), `rawDelta` the frame time in seconds,
 * `nowMs` the clock the strobe runs on.
 */
export function stepFixture(
  rt: FixtureRuntime,
  frame: ArrayLike<number> | null | undefined,
  rawDelta: number,
  nowMs: number,
  room: BeamRoom,
  longestThrow: number,
): void {
  const { beam, profile, motionProfile, fixture } = rt;
  const delta = Math.min(rawDelta, MAX_STABLE_DELTA);

  // Smooth and clamp noisy frame spikes before they enter the control loop.
  rt.stableDeltaEstimate = THREE.MathUtils.lerp(rt.stableDeltaEstimate, delta, 0.15);
  const spikeLimit = Math.max(FIXED_CONTROL_DT * 1.5, rt.stableDeltaEstimate * DELTA_SPIKE_FACTOR);
  const stableDelta = Math.min(delta, spikeLimit);

  // What this fixture is being sent: its own channels out of the frame the
  // engine outputs for its universe, read through its profile. With no frame
  // yet the fixture is dark and its head at centre.
  readBeamState(profile, frame, fixture.dmx_address, beam);
  // A closed shutter, a zero dimmer and a colour mixed to black are all dark.
  const rawDimmer = beam.lit ? beam.intensity : 0;
  const strobe = beam.shutter === 'strobe' ? beam.strobeRate : 0;
  const zoom = beam.zoom;

  // Smooth interpolation
  const s = rt.smoothed;
  const lerp = Math.min(1, stableDelta * 15);
  s.intensity += (rawDimmer - s.intensity) * lerp;
  s.r += (beam.r - s.r) * lerp;
  s.g += (beam.g - s.g) * lerp;
  s.b += (beam.b - s.b) * lerp;

  // Apply strobe effect (rapid intensity modulation)
  let effectiveIntensity = s.intensity;
  if (strobe > 0) {
    const strobeFreq = 2 + strobe * 20; // 2-22 Hz
    const strobePhase = (nowMs / 1000 * strobeFreq) % 1;
    effectiveIntensity = strobePhase < 0.5 ? s.intensity : 0;
  }
  rt.effectiveIntensity = effectiveIntensity;

  // Beam colour
  const luminance = 0.2126 * s.r + 0.7152 * s.g + 0.0722 * s.b;
  if (rt.isBeamLike && luminance < 0.09) {
    // Keep dark palettes moody but still visible in haze previs.
    const lift = (0.09 - luminance) / 0.09;
    rt.beamColor.setRGB(
      THREE.MathUtils.clamp(s.r + 0.25 * lift, 0, 1),
      THREE.MathUtils.clamp(s.g + 0.30 * lift, 0, 1),
      THREE.MathUtils.clamp(s.b + 0.40 * lift, 0, 1)
    );
  } else {
    rt.beamColor.setRGB(s.r, s.g, s.b);
  }

  // The gobo's turn. An angle the channel gives is taken as it is (it wraps, so
  // it is never smoothed: a lerp would spin it back the long way at 255 -> 0);
  // a speed is run on from where it was.
  if (beam.goboIndexed) {
    rt.goboAngle = beam.goboAngle;
  } else if (beam.goboSpin !== 0) {
    const turned = (rt.goboAngle + beam.goboSpin * delta) % (Math.PI * 2);
    rt.goboAngle = turned < 0 ? turned + Math.PI * 2 : turned;
  }

  // How wide the light is. The pool and the drawn beam both come from this.
  rt.finalSpotAngleDeg = poolConeDeg(rt.isSpotLike, zoom);
  rt.coneRad = THREE.MathUtils.degToRad(rt.finalSpotAngleDeg);

  const m = rt.motion;
  m.targetPanDeg = 0;
  m.targetTiltDeg = 0;
  m.currentPanDeg = 0;
  m.currentTiltDeg = 0;
  m.panVelocityDegPerSec = 0;
  m.tiltVelocityDegPerSec = 0;
  m.signalConfidence = 1;
  m.hold = false;
  m.strobe = strobe;
  m.zoom = zoom;

  if (rt.isMovingHead) {
    const panRangeRad = THREE.MathUtils.degToRad(profile.panRangeDeg);
    const tiltRangeRad = THREE.MathUtils.degToRad(profile.tiltRangeDeg);
    // Degrees from centre, the fixture's pan and tilt invert already applied.
    const targetPan = THREE.MathUtils.degToRad(beam.panDeg);
    const targetTilt = THREE.MathUtils.degToRad(beam.tiltDeg);

    rt.controlAccumulator += stableDelta;
    let stepCount = 0;
    const o = rt.orientation;
    while (rt.controlAccumulator >= FIXED_CONTROL_DT && stepCount < 5) {
      o.previousPanRad = o.currentPanRad;
      o.previousTiltRad = o.currentTiltRad;
      o.previousTargetPanRad = o.targetPanRad;
      o.previousTargetTiltRad = o.targetTiltRad;
      o.targetPanRad = targetPan;
      o.targetTiltRad = targetTilt;

      // Fixture-specific inertia profile: velocity/accel clamps + damping.
      const panErrorRad = o.targetPanRad - o.currentPanRad;
      const tiltErrorRad = o.targetTiltRad - o.currentTiltRad;

      const panDesiredVel = THREE.MathUtils.clamp(
        panErrorRad / FIXED_CONTROL_DT,
        -THREE.MathUtils.degToRad(motionProfile.panMaxVelDegPerSec),
        THREE.MathUtils.degToRad(motionProfile.panMaxVelDegPerSec)
      );
      const tiltDesiredVel = THREE.MathUtils.clamp(
        tiltErrorRad / FIXED_CONTROL_DT,
        -THREE.MathUtils.degToRad(motionProfile.tiltMaxVelDegPerSec),
        THREE.MathUtils.degToRad(motionProfile.tiltMaxVelDegPerSec)
      );

      const panVelDelta = panDesiredVel - o.panVelocityRadPerSec;
      const tiltVelDelta = tiltDesiredVel - o.tiltVelocityRadPerSec;
      const panMaxDelta = THREE.MathUtils.degToRad(motionProfile.panMaxAccelDegPerSec2) * FIXED_CONTROL_DT;
      const tiltMaxDelta = THREE.MathUtils.degToRad(motionProfile.tiltMaxAccelDegPerSec2) * FIXED_CONTROL_DT;

      o.panVelocityRadPerSec += THREE.MathUtils.clamp(panVelDelta, -panMaxDelta, panMaxDelta);
      o.tiltVelocityRadPerSec += THREE.MathUtils.clamp(tiltVelDelta, -tiltMaxDelta, tiltMaxDelta);
      o.panVelocityRadPerSec *= motionProfile.damping;
      o.tiltVelocityRadPerSec *= motionProfile.damping;

      o.currentPanRad += o.panVelocityRadPerSec * FIXED_CONTROL_DT;
      o.currentTiltRad += o.tiltVelocityRadPerSec * FIXED_CONTROL_DT;

      o.currentPanRad = THREE.MathUtils.clamp(o.currentPanRad, -panRangeRad / 2, panRangeRad / 2);
      o.currentTiltRad = THREE.MathUtils.clamp(o.currentTiltRad, -tiltRangeRad / 2, tiltRangeRad / 2);

      const panErr = Math.abs(o.targetPanRad - o.currentPanRad);
      const tiltErr = Math.abs(o.targetTiltRad - o.currentTiltRad);
      const targetPanDelta = Math.abs(o.targetPanRad - o.previousTargetPanRad);
      const targetTiltDelta = Math.abs(o.targetTiltRad - o.previousTargetTiltRad);
      const targetStable = targetPanDelta < THREE.MathUtils.degToRad(0.08) && targetTiltDelta < THREE.MathUtils.degToRad(0.08);
      const canShowHold = effectiveIntensity > 0.08;
      if (
        canShowHold &&
        targetStable &&
        panErr < THREE.MathUtils.degToRad(0.15) &&
        tiltErr < THREE.MathUtils.degToRad(0.15)
      ) {
        o.holdDurationSec += FIXED_CONTROL_DT;
      } else {
        o.holdDurationSec = 0;
      }

      rt.controlAccumulator -= FIXED_CONTROL_DT;
      stepCount += 1;
    }

    if (stepCount === 5 && rt.controlAccumulator >= FIXED_CONTROL_DT) {
      // Prevent spiral-of-death if rendering starves for too long.
      rt.controlAccumulator = 0;
    }

    const alpha = Math.min(1, rt.controlAccumulator / FIXED_CONTROL_DT);
    // A moving head pans its yoke about the vertical and tilts the head inside
    // the yoke, so tilt is applied first and pan second ('YXZ' below).
    rt.panRad = THREE.MathUtils.lerp(o.previousPanRad, o.currentPanRad, alpha);
    rt.tiltRad = THREE.MathUtils.lerp(o.previousTiltRad, o.currentTiltRad, alpha);

    const panErrorNorm = Math.min(1, Math.abs(o.targetPanRad - o.currentPanRad) / Math.max(0.0001, panRangeRad));
    const tiltErrorNorm = Math.min(1, Math.abs(o.targetTiltRad - o.currentTiltRad) / Math.max(0.0001, tiltRangeRad));
    const spikePenalty = Math.min(0.5, Math.max(0, (rawDelta - stableDelta) * 5));
    const confidence = Math.max(0, 1 - ((panErrorNorm + tiltErrorNorm) * 0.5 + spikePenalty));

    m.targetPanDeg = THREE.MathUtils.radToDeg(o.targetPanRad);
    m.targetTiltDeg = THREE.MathUtils.radToDeg(o.targetTiltRad);
    m.currentPanDeg = THREE.MathUtils.radToDeg(o.currentPanRad);
    m.currentTiltDeg = THREE.MathUtils.radToDeg(o.currentTiltRad);
    m.panVelocityDegPerSec = THREE.MathUtils.radToDeg(o.panVelocityRadPerSec);
    m.tiltVelocityDegPerSec = THREE.MathUtils.radToDeg(o.tiltVelocityRadPerSec);
    m.signalConfidence = confidence;
    m.hold = o.holdDurationSec > 0.35;
  } else {
    // Nothing turns the head of a fixture that cannot pan or tilt. A fixture
    // id reused by a different fixture in a new rig must not keep the old
    // one's pan and tilt.
    rt.panRad = 0;
    rt.tiltRad = 0;
  }

  // Where the beam lands: the first of the floor, the ceiling and the walls
  // along it. In the fixture's own frame first (this frame's pan and tilt, the
  // ones it is drawn with), then turned by how it is hung.
  const pointing = hangBeam(
    beamDirection(rt.tiltRad, rt.panRad, rt.lensUp, rt.pointing),
    rt.hangRx,
    rt.hangRz,
    rt.bodyYawRad
  );
  rt.reach = beamLanding(
    fixture.position_x,
    rt.sourceY,
    fixture.position_z,
    pointing,
    room,
    longestThrow,
    rt.surface
  );
  // It ends as wide as its pool, measured from where the light sits (the lens).
  rt.endRadius = poolRadius(rt.reach - rt.lightDepth, rt.coneRad);

  placeParts(rt);
}

/** Where the yoke, the head and the beam are drawn, from this frame's pan and tilt. */
export function placeParts(rt: FixtureRuntime): void {
  // Yoke: the hang, then the pan.
  scratchMatrix.makeRotationY(rt.panRad);
  rt.yokeMatrix.multiplyMatrices(rt.hangMatrix, scratchMatrix);
  // Head: the hang, then pan and tilt ('YXZ': tilt inside the pan), then which
  // way it faces.
  headEuler.set(rt.tiltRad, rt.panRad, 0, 'YXZ');
  scratchMatrix.makeRotationFromEuler(headEuler);
  rt.headMatrix.multiplyMatrices(rt.hangMatrix, scratchMatrix);
  if (rt.lensUp) rt.headMatrix.multiply(FACING_UP);
  // Beam: from the lit face, down the head's -Y.
  scratchMatrix.makeTranslation(0, -rt.mouth.offset, 0);
  rt.beamMatrix.multiplyMatrices(rt.headMatrix, scratchMatrix);
}

/** The row this fixture gives the beam debug table for this frame. */
export function debugSnapshot(rt: FixtureRuntime): BeamDebugSnapshot {
  const { beam, fixture, profile, motion } = rt;
  const channelMap = profile.channels;
  const strobeChannel = beam.strobeSource === 'none' ? undefined : channelMap[beam.strobeSource];
  return {
    fixtureId: fixture.id,
    fixtureLabel: fixture.name || fixture.fixture?.model || `Fixture ${fixture.id}`,
    targetPanDeg: motion.targetPanDeg,
    targetTiltDeg: motion.targetTiltDeg,
    currentPanDeg: motion.currentPanDeg,
    currentTiltDeg: motion.currentTiltDeg,
    panVelocityDegPerSec: motion.panVelocityDegPerSec,
    tiltVelocityDegPerSec: motion.tiltVelocityDegPerSec,
    signalConfidence: motion.signalConfidence,
    hold: motion.hold,
    strobeLogical: motion.strobe,
    strobeChannelValue: beam.strobeValue,
    strobeChannelIndex: strobeChannel === undefined ? undefined : strobeChannel + 1,
    strobeSource: beam.strobeSource,
    shutter: beam.shutter,
    zoomLogical: motion.zoom,
    zoomChannelValue: beam.zoomValue,
    zoomChannelIndex: beam.zoomSource === 'zoom' ? channelMap.zoom + 1 : undefined,
    zoomSource: beam.zoomSource,
    finalIntensity: rt.effectiveIntensity,
    finalSpotAngleDeg: rt.finalSpotAngleDeg,
    capabilityWarnings: [
      beam.strobeSource === 'none' ? 'no strobe or shutter channel' : '',
      beam.zoomSource === 'fallback' ? 'no zoom channel or beam angle' : '',
      profile.invert.pan ? 'pan inverted' : '',
      profile.invert.tilt ? 'tilt inverted' : '',
    ].filter(Boolean),
    motionSource: beam.hasSignal ? 'output frame' : 'no frame',
  };
}
