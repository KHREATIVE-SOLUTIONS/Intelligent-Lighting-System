import { useState, useEffect, useLayoutEffect, useRef, useMemo } from 'react';
import type { MutableRefObject } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box, IconButton, Typography, Card, CardContent, ButtonGroup, Button, MenuItem, TextField, Tooltip,
} from '@mui/material';
import {
  ArrowBack as BackIcon,
} from '@mui/icons-material';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Grid, PerspectiveCamera, Html } from '@react-three/drei';
import * as THREE from 'three';
import { demoApi, rigsApi } from '../../services/api';
import type { DemoPresetSummary } from '../../services/api';
import type { Rig, RigFixture } from '../../types';
import { useDMXStore } from '../../stores/dmxStore';
import { useHealthStore } from '../../stores/healthStore';
import { audioWebSocket } from '../../services/websocket';
import { createDemoRigFollower, onEngineOnAnotherRig, onLinkRestored, settleRig } from '../../utils/demoRigSync';
import AudioDeviceChooser from '../common/AudioDeviceChooser';
import { createBeatClock, ingestAnalysis } from './previs/beatClock';
import type { BeatClock } from './previs/beatClock';
import { ClubRoom } from './previs/ClubRoom';
import { BeatClockTicker, Crowd } from './previs/Crowd';
import { DJBooth } from './previs/DJBooth';
import { FixtureHead, FixtureSupport, FixtureYoke } from './previs/FixtureBody';
import { FIXTURE_SPECS, resolveModelKind } from './previs/fixtureSpecs';
import { buildVenue, cameraPreset } from './previs/layout';
import type { CameraMode, FixtureMount } from './previs/layout';
import { RigTruss } from './previs/Truss';

type BeamDebugSnapshot = {
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
  strobeSource: 'strobe' | 'shutter' | 'fallback';
  zoomLogical: number;
  zoomChannelValue: number;
  zoomChannelIndex?: number;
  zoomSource: 'zoom' | 'beam_angle' | 'fallback';
  finalIntensity: number;
  finalSpotAngleDeg: number;
  capabilityWarnings: string[];
  motionSource: string;
  sourceStaleMs?: number;
};

type LiveFixtureState = {
  id: string;
  dmx_address?: number;
  universe?: number;
  pan?: number;
  tilt?: number;
  dimmer?: number;
  r?: number;
  g?: number;
  b?: number;
  _updatedAt?: number;
};

const BLANK_UNIVERSE: number[] = new Array(512).fill(0);

type QualityMode = 'performance' | 'balanced' | 'ultra';

// A fixture not in the venue layout (a position that is not a number) still
// has to draw: treat it as hung, with no pipe.
const DEFAULT_MOUNT: FixtureMount = { type: 'truss', drop: 0 };

// ============================================================================
// CONSTANTS
// ============================================================================

// Beam cone material - shared across all fixtures for performance
const BEAM_VERTEX_SHADER = `
  varying float vIntensity;
  void main() {
    vIntensity = position.y;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const BEAM_FRAGMENT_SHADER = `
  uniform vec3 beamColor;
  uniform float beamIntensity;
  varying float vIntensity;
  void main() {
    float falloff = smoothstep(0.0, 1.0, 1.0 - vIntensity);
    float alpha = falloff * beamIntensity * 0.42;
    gl_FragColor = vec4(beamColor, alpha);
  }
`;

// 9-zone stage grid positions (normalized -0.33 to 0.33 for both axes)
const ZONE_POSITIONS: Record<string, { x: number; z: number }> = {
  USL: { x: -0.33, z: -0.33 },
  USC: { x: 0, z: -0.33 },
  USR: { x: 0.33, z: -0.33 },
  MSL: { x: -0.33, z: 0 },
  MSC: { x: 0, z: 0 },
  MSR: { x: 0.33, z: 0 },
  DSL: { x: -0.33, z: 0.33 },
  DSC: { x: 0, z: 0.33 },
  DSR: { x: 0.33, z: 0.33 },
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

const FIXTURE_MOTION_PROFILES: Record<string, MotionInertiaProfile> = {
  moving_head: { panMaxVelDegPerSec: 220, tiltMaxVelDegPerSec: 180, panMaxAccelDegPerSec2: 540, tiltMaxAccelDegPerSec2: 420, damping: 0.88 },
  mover: { panMaxVelDegPerSec: 220, tiltMaxVelDegPerSec: 180, panMaxAccelDegPerSec2: 540, tiltMaxAccelDegPerSec2: 420, damping: 0.88 },
  beam: { panMaxVelDegPerSec: 260, tiltMaxVelDegPerSec: 220, panMaxAccelDegPerSec2: 720, tiltMaxAccelDegPerSec2: 560, damping: 0.86 },
  spot: { panMaxVelDegPerSec: 180, tiltMaxVelDegPerSec: 150, panMaxAccelDegPerSec2: 420, tiltMaxAccelDegPerSec2: 340, damping: 0.90 },
  wash: { panMaxVelDegPerSec: 170, tiltMaxVelDegPerSec: 150, panMaxAccelDegPerSec2: 360, tiltMaxAccelDegPerSec2: 300, damping: 0.91 },
  profile: { panMaxVelDegPerSec: 175, tiltMaxVelDegPerSec: 150, panMaxAccelDegPerSec2: 380, tiltMaxAccelDegPerSec2: 320, damping: 0.90 },
  hybrid: { panMaxVelDegPerSec: 220, tiltMaxVelDegPerSec: 180, panMaxAccelDegPerSec2: 520, tiltMaxAccelDegPerSec2: 420, damping: 0.88 },
  default: { panMaxVelDegPerSec: 130, tiltMaxVelDegPerSec: 110, panMaxAccelDegPerSec2: 260, tiltMaxAccelDegPerSec2: 220, damping: 0.92 },
};

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

// Build a channel type -> DMX offset map from the fixture's active mode
function buildChannelMap(fixture: RigFixture): Record<string, number> {
  const map: Record<string, number> = {};
  if (!fixture.fixture?.modes?.length) return map;

  const mode = fixture.mode_id
    ? fixture.fixture.modes.find((m) => m.id === fixture.mode_id)
    : fixture.fixture.modes[0];

  if (!mode?.channels) return map;

  const canonicalMap = (raw: string): string => {
    const key = raw.toLowerCase().replace(/[\s-]+/g, '_');
    if (key === 'pan' || key === 'pan_coarse' || key === 'pan_16bit' || key === 'pan_course') return 'pan';
    if (key === 'pan_fine' || key === 'pan_fine_16bit' || key === 'fine_pan') return 'pan_fine';
    if (key === 'tilt' || key === 'tilt_coarse' || key === 'tilt_16bit' || key === 'tilt_course') return 'tilt';
    if (key === 'tilt_fine' || key === 'tilt_fine_16bit' || key === 'fine_tilt') return 'tilt_fine';
    if (key === 'dimmer' || key === 'intensity' || key === 'master_dimmer') return 'dimmer';
    if (key === 'strobe' || key === 'shutter' || key === 'shutter_strobe') return key.includes('strobe') ? 'strobe' : 'shutter';
    if (key === 'red' || key === 'green' || key === 'blue' || key === 'white' || key === 'zoom') return key;
    return key;
  };

  for (const ch of mode.channels) {
    const offset = ch.channel_number - 1;
    const primary = canonicalMap(String(ch.channel_type || ''));
    if (!(primary in map)) map[primary] = offset;
    const byName = canonicalMap(String(ch.name || ''));
    if (!(byName in map)) map[byName] = offset;
  }
  return map;
}

// What kind of fixture this is. Worked out in one place because three things
// have to agree on it: the control loop, the model that is drawn, and the venue
// layout that decides how the fixture is mounted.
function describeFixture(fixture: RigFixture, channelMap: Record<string, number> = buildChannelMap(fixture)) {
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

// Floor light from a fixture, for a beam level of 0 to 1. Below the threshold
// the spot light is off, as it was when it was unmounted instead.
const SPOT_LIGHT_THRESHOLD = 0.08;
function spotIntensityFor(level: number): number {
  return level > SPOT_LIGHT_THRESHOLD ? level * 8 : 0;
}

// ============================================================================
// VOLUMETRIC BEAM COMPONENT
// ============================================================================

function BeamCone({
  color,
  intensity,
  beamAngle,
  beamLength,
  segments,
}: {
  color: THREE.Color;
  intensity: number;
  beamAngle: number;
  beamLength: number;
  segments: number;
}) {
  const materialRef = useRef<THREE.ShaderMaterial>(null);

  const uniforms = useMemo(
    () => ({
      beamColor: { value: new THREE.Color(1, 1, 1) },
      beamIntensity: { value: 0 },
    }),
    []
  );

  useFrame(() => {
    if (materialRef.current) {
      materialRef.current.uniforms.beamColor.value.copy(color);
      materialRef.current.uniforms.beamIntensity.value = intensity;
    }
  });

  const topRadius = Math.tan((beamAngle * Math.PI) / 360) * beamLength;

  if (intensity < 0.015) return null;

  return (
    <mesh position={[0, -beamLength / 2, 0]}>
      <coneGeometry args={[topRadius, beamLength, segments, 1, true]} />
      <shaderMaterial
        ref={materialRef}
        vertexShader={BEAM_VERTEX_SHADER}
        fragmentShader={BEAM_FRAGMENT_SHADER}
        uniforms={uniforms}
        transparent
        side={THREE.DoubleSide}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </mesh>
  );
}

// ============================================================================
// FIXTURE 3D COMPONENT
// ============================================================================

function Fixture3D({
  fixture,
  dmxData,
  liveBinding,
  fixtureIndex,
  spotCap,
  beamSegments,
  mount,
  showLabel,
  onDebugUpdate,
}: {
  fixture: RigFixture;
  dmxData: number[];
  liveBinding?: { state?: LiveFixtureState; source: string; staleMs?: number };
  fixtureIndex: number;
  spotCap: number;
  beamSegments: number;
  mount: FixtureMount;
  showLabel: boolean;
  onDebugUpdate?: (snapshot: BeamDebugSnapshot) => void;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const headRef = useRef<THREE.Group>(null);
  const yokeRef = useRef<THREE.Group>(null);
  const lensRef = useRef<THREE.Mesh>(null);
  const spotRef = useRef<THREE.SpotLight>(null);

  // Memoised: this component re-renders every frame, and walking the channel
  // list each time was most of what that cost.
  const channelMap = useMemo(() => buildChannelMap(fixture), [fixture]);
  const channelMapRef = useRef(channelMap);
  channelMapRef.current = channelMap;
  const fallbackWarningRef = useRef<Set<string>>(new Set());

  // Smoothed values to avoid jitter
  const smoothed = useRef({ intensity: 0, r: 1, g: 1, b: 1 });

  const FIXED_CONTROL_DT = 1 / 60;
  const MAX_STABLE_DELTA = 1 / 20;
  const DELTA_SPIKE_FACTOR = 2.2;
  const controlAccumulator = useRef(0);
  const stableDeltaEstimate = useRef(FIXED_CONTROL_DT);

  const orientationState = useRef({
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
  });

  const { fixtureType, hasPanTiltChannels, isMovingHead, modelKind } = useMemo(
    () => describeFixture(fixture, channelMap),
    [fixture, channelMap]
  );
  const isBeamLike = fixtureType === 'beam' || fixtureType === 'moving_head' || fixtureType === 'mover';
  const isSpotLike = fixtureType === 'spot';
  const defaultBeamAngleDeg = isSpotLike ? 18.0 : 5.0;
  const modelSpec = FIXTURE_SPECS[modelKind];
  const motionProfile = FIXTURE_MOTION_PROFILES[fixtureType] || FIXTURE_MOTION_PROFILES.default;

  // A fixed-body fixture standing on the floor is drawn lens-up. Its beam and
  // spot light are not turned with it: they still point down, as before.
  const lensUp = mount.type === 'stand' && mount.lensUp;
  // A fixture patched lower than its own feet is raised to stand on the floor.
  const standLift = mount.type === 'stand' ? mount.lift : 0;

  // Beam length scales with fixture height (fixtures on truss beam to floor)
  const beamLength = fixture.position_y > 0 ? fixture.position_y : 3;

  const [beamColor] = useState(() => new THREE.Color(1, 1, 1));
  const [beamIntensity, setBeamIntensity] = useState(0);

  const emitFallbackWarning = (key: string, message: string) => {
    if (fallbackWarningRef.current.has(key)) return;
    fallbackWarningRef.current.add(key);
    // Explicit signal that we are using fallback behavior instead of silently no-oping.
    console.warn(message);
  };

  useFrame((_, rawDelta) => {
    const liveState = liveBinding?.state;
    const baseAddr = fixture.dmx_address - 1;
    const chMap = channelMapRef.current;
    const delta = Math.min(rawDelta, MAX_STABLE_DELTA);

    // Smooth and clamp noisy frame spikes before they enter the control loop.
    stableDeltaEstimate.current = THREE.MathUtils.lerp(stableDeltaEstimate.current, delta, 0.15);
    const spikeLimit = Math.max(FIXED_CONTROL_DT * 1.5, stableDeltaEstimate.current * DELTA_SPIKE_FACTOR);
    const stableDelta = Math.min(delta, spikeLimit);

    // Read DMX values
    const rawDimmer = liveState?.dimmer ?? (
      chMap.dimmer !== undefined
        ? (dmxData[baseAddr + chMap.dimmer] || 0) / 255
        : 1
    );
    const rawR = liveState?.r ?? (
      chMap.red !== undefined
        ? (dmxData[baseAddr + chMap.red] || 0) / 255
        : 1
    );
    const rawG = liveState?.g ?? (
      chMap.green !== undefined
        ? (dmxData[baseAddr + chMap.green] || 0) / 255
        : 1
    );
    const rawB = liveState?.b ?? (
      chMap.blue !== undefined
        ? (dmxData[baseAddr + chMap.blue] || 0) / 255
        : 1
    );
    const coarsePan = chMap.pan !== undefined ? dmxData[baseAddr + chMap.pan] || 128 : 128;
    const finePan = chMap.pan_fine !== undefined ? dmxData[baseAddr + chMap.pan_fine] || 0 : 0;
    const coarseTilt = chMap.tilt !== undefined ? dmxData[baseAddr + chMap.tilt] || 128 : 128;
    const fineTilt = chMap.tilt_fine !== undefined ? dmxData[baseAddr + chMap.tilt_fine] || 0 : 0;
    let strobe = 0;
    let strobeSource: BeamDebugSnapshot['strobeSource'] = 'fallback';
    let strobeChannelValue = 0;
    let strobeChannelIndex: number | undefined;
    if (chMap.strobe !== undefined) {
      strobeChannelValue = dmxData[baseAddr + chMap.strobe] || 0;
      // Many fixtures use low/high values as open/no-strobe and middle bands for strobe rates.
      // Treat extremes as non-strobe so we do not simulate constant flicker from open shutter values.
      if (strobeChannelValue <= 8 || strobeChannelValue >= 240) {
        strobe = 0;
      } else {
        strobe = THREE.MathUtils.clamp((strobeChannelValue - 16) / 208, 0, 1);
      }
      strobeSource = 'strobe';
      strobeChannelIndex = chMap.strobe + 1;
    } else if (chMap.shutter !== undefined) {
      strobeChannelValue = dmxData[baseAddr + chMap.shutter] || 0;
      // Typical shutter map:
      // 0-31 closed, 32-63 open, 64-223 strobe (slow->fast), 224-255 open.
      if (strobeChannelValue >= 64 && strobeChannelValue <= 223) {
        strobe = THREE.MathUtils.clamp((strobeChannelValue - 64) / (223 - 64), 0, 1);
      } else {
        strobe = 0;
      }
      strobeSource = 'shutter';
      strobeChannelIndex = chMap.shutter + 1;
      emitFallbackWarning(
        `strobe-${fixture.id}`,
        `[RigVisualizer] ${fixture.name || `Fixture ${fixture.id}`} has no strobe channel; deriving strobe from shutter range 64-223.`
      );
    } else {
      strobeSource = 'fallback';
      emitFallbackWarning(
        `strobe-${fixture.id}`,
        `[RigVisualizer] ${fixture.name || `Fixture ${fixture.id}`} has neither strobe nor shutter channel; forcing strobe to 0.`
      );
    }

    let zoom = isSpotLike ? 0.45 : 0.12;
    let zoomSource: BeamDebugSnapshot['zoomSource'] = 'fallback';
    let zoomChannelValue = 128;
    let zoomChannelIndex: number | undefined;
    if (chMap.zoom !== undefined) {
      zoomChannelValue = dmxData[baseAddr + chMap.zoom] || 0;
      zoom = zoomChannelValue / 255;
      zoomSource = 'zoom';
      zoomChannelIndex = chMap.zoom + 1;
    } else if (typeof fixture.fixture?.beam_angle === 'number') {
      const normalizedBeamAngle = THREE.MathUtils.clamp((fixture.fixture.beam_angle - 5) / 40, 0, 1);
      zoom = normalizedBeamAngle;
      zoomChannelValue = Math.round(normalizedBeamAngle * 255);
      zoomSource = 'beam_angle';
      emitFallbackWarning(
        `zoom-${fixture.id}`,
        `[RigVisualizer] ${fixture.name || `Fixture ${fixture.id}`} has no zoom channel; deriving beam width from fixture beam_angle (${fixture.fixture.beam_angle}°).`
      );
    } else {
      zoomSource = 'fallback';
      emitFallbackWarning(
        `zoom-${fixture.id}`,
        `[RigVisualizer] ${fixture.name || `Fixture ${fixture.id}`} has no zoom or beam_angle definition; defaulting to narrow beam zoom.`
      );
    }

    const hasLivePan = Number.isFinite(Number(liveState?.pan));
    const hasLiveTilt = Number.isFinite(Number(liveState?.tilt));
    const panNormalizedFromState = hasLivePan
      ? THREE.MathUtils.clamp((Number(liveState?.pan) + 270) / 540, 0, 1)
      : undefined;
    const tiltNormalizedFromState = hasLiveTilt
      ? THREE.MathUtils.clamp((Number(liveState?.tilt) + 135) / 270, 0, 1)
      : undefined;
    const panNormalized = panNormalizedFromState ?? (
      chMap.pan_fine !== undefined
        ? ((coarsePan << 8) | finePan) / 65535
        : coarsePan / 255
    );
    const tiltNormalized = tiltNormalizedFromState ?? (
      chMap.tilt_fine !== undefined
        ? ((coarseTilt << 8) | fineTilt) / 65535
        : coarseTilt / 255
    );

    // Smooth interpolation
    const s = smoothed.current;
    const lerp = Math.min(1, stableDelta * 15);
    s.intensity += (rawDimmer - s.intensity) * lerp;
    s.r += (rawR - s.r) * lerp;
    s.g += (rawG - s.g) * lerp;
    s.b += (rawB - s.b) * lerp;

    // Apply strobe effect (rapid intensity modulation)
    let effectiveIntensity = s.intensity;
    if (strobe > 0.1) {
      const strobeFreq = 2 + strobe * 20; // 2-22 Hz
      const strobePhase = (performance.now() / 1000 * strobeFreq) % 1;
      effectiveIntensity = strobePhase < 0.5 ? s.intensity : 0;
    }

    // Volumetric intensity follows backend dimmer directly — no artificial floors.
    // Beams form from true darkness when audio activates.
    const volumetricIntensity = effectiveIntensity;

    // Update beam color
    const luminance = 0.2126 * s.r + 0.7152 * s.g + 0.0722 * s.b;
    if (isBeamLike && luminance < 0.09) {
      // Keep dark palettes moody but still visible in haze previs.
      const lift = (0.09 - luminance) / 0.09;
      beamColor.setRGB(
        THREE.MathUtils.clamp(s.r + 0.25 * lift, 0, 1),
        THREE.MathUtils.clamp(s.g + 0.30 * lift, 0, 1),
        THREE.MathUtils.clamp(s.b + 0.40 * lift, 0, 1)
      );
    } else {
      beamColor.setRGB(s.r, s.g, s.b);
    }
    setBeamIntensity(volumetricIntensity);

    // Update lens glow emissive
    if (lensRef.current) {
      const lensMat = lensRef.current.material as THREE.MeshStandardMaterial;
      lensMat.emissive.setRGB(s.r, s.g, s.b);
      lensMat.emissiveIntensity = volumetricIntensity * 3;
      // Dark glass when the fixture is off, taking its colour as it comes up.
      const lensTint = 0.5 * Math.min(1, s.intensity * 4);
      lensMat.color.setRGB(0.045 + s.r * lensTint, 0.05 + s.g * lensTint, 0.06 + s.b * lensTint);
    }

    // Update spotlight for floor projection
    const finalSpotAngleDeg = isSpotLike
      ? (10.0 + zoom * 40.0)
      : (2.5 + zoom * 9.0);
    const finalBeamAngleDeg = isSpotLike
      ? THREE.MathUtils.clamp(finalSpotAngleDeg, 10.0, 50.0)
      : THREE.MathUtils.clamp(finalSpotAngleDeg, 2.5, 11.5);
    if (spotRef.current) {
      spotRef.current.color.setRGB(s.r, s.g, s.b);
      spotRef.current.intensity = spotIntensityFor(effectiveIntensity);
      spotRef.current.angle = THREE.MathUtils.degToRad(finalSpotAngleDeg); // Narrower to wider with zoom
    }

    let targetPanDeg = 0;
    let targetTiltDeg = 0;
    let currentPanDeg = 0;
    let currentTiltDeg = 0;
    let panVelocityDegPerSec = 0;
    let tiltVelocityDegPerSec = 0;
    let signalConfidence = 1;
    let hold = false;

    // Pan/tilt for moving heads
    if (isMovingHead) {
      const panRange = fixture.fixture?.pan_range || (hasPanTiltChannels ? 540 : 0);
      const tiltRange = fixture.fixture?.tilt_range || (hasPanTiltChannels ? 270 : 0);
      const panRangeRad = THREE.MathUtils.degToRad(panRange);
      const tiltRangeRad = THREE.MathUtils.degToRad(tiltRange);
      const targetPan = panNormalized * panRangeRad - (panRangeRad / 2);
      const targetTilt = tiltNormalized * tiltRangeRad - (tiltRangeRad / 2);

      controlAccumulator.current += stableDelta;
      let stepCount = 0;
      const o = orientationState.current;
      while (controlAccumulator.current >= FIXED_CONTROL_DT && stepCount < 5) {
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

        controlAccumulator.current -= FIXED_CONTROL_DT;
        stepCount += 1;
      }

      if (stepCount === 5 && controlAccumulator.current >= FIXED_CONTROL_DT) {
        // Prevent spiral-of-death if rendering starves for too long.
        controlAccumulator.current = 0;
      }

      if (headRef.current) {
        const alpha = Math.min(1, controlAccumulator.current / FIXED_CONTROL_DT);
        // A moving head pans its yoke about the vertical and tilts the head
        // inside the yoke, so tilt has to be applied first and pan second:
        // 'YXZ'. With three's default 'XYZ' the pan turned the head about its
        // own beam, and no amount of pan moved a beam in this view.
        headRef.current.rotation.order = 'YXZ';
        headRef.current.rotation.y = THREE.MathUtils.lerp(o.previousPanRad, o.currentPanRad, alpha);
        headRef.current.rotation.x = THREE.MathUtils.lerp(o.previousTiltRad, o.currentTiltRad, alpha);
        // The yoke arms take the same pan and nothing else. They are a separate
        // group beside the head, so the beam's direction is still set by the
        // two lines above and by nothing in the model.
        if (yokeRef.current) yokeRef.current.rotation.y = headRef.current.rotation.y;
      }

      const panErrorNorm = Math.min(1, Math.abs(o.targetPanRad - o.currentPanRad) / Math.max(0.0001, panRangeRad));
      const tiltErrorNorm = Math.min(1, Math.abs(o.targetTiltRad - o.currentTiltRad) / Math.max(0.0001, tiltRangeRad));
      const spikePenalty = Math.min(0.5, Math.max(0, (rawDelta - stableDelta) * 5));
      const confidence = Math.max(0, 1 - ((panErrorNorm + tiltErrorNorm) * 0.5 + spikePenalty));

      targetPanDeg = THREE.MathUtils.radToDeg(o.targetPanRad);
      targetTiltDeg = THREE.MathUtils.radToDeg(o.targetTiltRad);
      currentPanDeg = THREE.MathUtils.radToDeg(o.currentPanRad);
      currentTiltDeg = THREE.MathUtils.radToDeg(o.currentTiltRad);
      panVelocityDegPerSec = THREE.MathUtils.radToDeg(o.panVelocityRadPerSec);
      tiltVelocityDegPerSec = THREE.MathUtils.radToDeg(o.tiltVelocityRadPerSec);
      signalConfidence = confidence;
      hold = o.holdDurationSec > 0.35;
    }

    onDebugUpdate?.({
      fixtureId: fixture.id,
      fixtureLabel: fixture.name || fixture.fixture?.model || `Fixture ${fixture.id}`,
      targetPanDeg,
      targetTiltDeg,
      currentPanDeg,
      currentTiltDeg,
      panVelocityDegPerSec,
      tiltVelocityDegPerSec,
      signalConfidence,
      hold,
      strobeLogical: strobe,
      strobeChannelValue,
      strobeChannelIndex,
      strobeSource,
      zoomLogical: zoom,
      zoomChannelValue,
      zoomChannelIndex,
      zoomSource,
      finalIntensity: effectiveIntensity,
      finalSpotAngleDeg,
      capabilityWarnings: [
        strobeSource === 'fallback' ? 'missing strobe/shutter capability' : '',
        zoomSource === 'fallback' ? 'missing zoom/beam_angle capability' : '',
      ].filter(Boolean),
      motionSource: liveBinding?.source || 'dmx',
      sourceStaleMs: liveBinding?.staleMs,
    });
  });

  // The yaw the rig says this fixture is hung at. Object3D.rotation.y takes the
  // wizard's convention directly: 0 aims down local +Z (downstage, toward the
  // audience), +90 deg aims toward +X. Ignoring it rendered every fixture facing
  // the same way, so "each fixture points at the performance area" had no
  // observable effect in the previs.
  const bodyYawRad = useMemo(
    () => THREE.MathUtils.degToRad(fixture.rotation_y || 0),
    [fixture.rotation_y]
  );

  // SpotLight target. World space - light.target is not a child of the light -
  // so it is the one thing in here the body yaw must not be applied to twice.
  const targetPos = useMemo(
    () => new THREE.Vector3(fixture.position_x, 0, fixture.position_z),
    [fixture.position_x, fixture.position_z]
  );

  return (
    <group
      ref={groupRef}
      position={[fixture.position_x, fixture.position_y + standLift, fixture.position_z]}
      rotation={[0, bodyYawRad, 0]}
    >
      {/* What holds it up: base or bracket, and the reach to truss, wall or floor */}
      <FixtureSupport kind={modelKind} mount={mount} bodyYaw={bodyYawRad} />

      {/* Yoke arms: turn with pan, beside the head rather than around it */}
      {isMovingHead && (
        <FixtureYoke ref={yokeRef} kind={modelKind} standing={mount.type === 'stand'} />
      )}

      {/* Head group (rotates for moving heads). It sits on the fixture's own
          position, so the beam starts where the rig says the fixture is. */}
      <group ref={headRef}>
        {/* Housing and the lit lens; the lens material is driven in useFrame */}
        <FixtureHead kind={modelKind} lensRef={lensRef} lensUp={lensUp} />

        {/* Volumetric beam cone */}
        <BeamCone
          color={beamColor}
          intensity={beamIntensity}
          beamAngle={defaultBeamAngleDeg}
          beamLength={beamLength}
          segments={beamSegments}
        />

        {/* SpotLight for floor color projection (cap count for performance).
            It stays mounted and is switched with its intensity. Mounting it
            only while the fixture was lit changed the number of lights in the
            scene every time a fixture faded or strobed, and three.js builds a
            new shader for every lit material at each new count: 168 shaders
            in 100 seconds of music, each a freeze of a second or more the
            first time a machine meets it. */}
        {fixtureIndex < spotCap && (
          <>
            <spotLight
              ref={spotRef}
              position={[0, -modelSpec.lensOffset - 0.02, 0]}
              angle={0.3}
              penumbra={0.6}
              intensity={spotIntensityFor(beamIntensity)}
              color={beamColor}
              castShadow={fixtureIndex < 4}
              shadow-mapSize-width={256}
              shadow-mapSize-height={256}
              distance={beamLength * 1.5}
              decay={1.5}
              target-position={targetPos}
            />
          </>
        )}
      </group>

      {/* Fixture ID label for quick patch/debug identification */}
      {showLabel && (
        <Html
          position={[0, 0.55, 0]}
          center
          occlude={false}
          distanceFactor={12}
          style={{ pointerEvents: 'none' }}
        >
          <div
            style={{
              padding: '2px 6px',
              borderRadius: 4,
              background: 'rgba(0,0,0,0.65)',
              color: '#f0f4ff',
              fontSize: '10px',
              fontFamily: 'Consolas, monospace',
              lineHeight: 1.1,
              whiteSpace: 'nowrap',
              border: '1px solid rgba(255,255,255,0.2)',
            }}
          >
            {fixture.id}
          </div>
        </Html>
      )}
    </group>
  );
}

// ============================================================================
// BARE STAGE FLOOR (shown when the venue is hidden)
// ============================================================================

function Stage({ width, depth }: { width: number; depth: number }) {
  return (
    <group>
      {/* Stage floor with slight reflectivity */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow>
        <planeGeometry args={[width, depth]} />
        <meshStandardMaterial
          color="#1a1a1a"
          metalness={0.1}
          roughness={0.8}
        />
      </mesh>

      {/* Stage grid */}
      <Grid
        args={[width, depth]}
        cellSize={1}
        cellThickness={0.5}
        cellColor="#333"
        sectionSize={5}
        sectionThickness={1}
        sectionColor="#444"
        fadeDistance={50}
        fadeStrength={1}
        position={[0, 0.01, 0]}
      />

      {/* Audience area (dark region beyond downstage) */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, depth / 2 + 2]}>
        <planeGeometry args={[width + 4, 4]} />
        <meshStandardMaterial color="#0a0a0a" />
      </mesh>

      {/* DJ booth platform at front-center */}
      <mesh position={[0, 0.1, -depth / 2 + 1]} receiveShadow>
        <boxGeometry args={[2, 0.2, 1.5]} />
        <meshStandardMaterial color="#222" metalness={0.3} roughness={0.7} />
      </mesh>
    </group>
  );
}

// ============================================================================
// KEY LIGHTING ZONES (drawn on the floor, with or without the venue)
// ============================================================================

function KeyZoneHighlights({
  width,
  depth,
  keyZones,
}: {
  width: number;
  depth: number;
  keyZones: Array<{ zone: string; active: boolean; intensity: number; color: { r: number; g: number; b: number } }>;
}) {
  return (
    <group>
      {keyZones
        .filter((z: any) => z && z.active && z.zone && ZONE_POSITIONS[z.zone])
        .map((zone) => {
          const pos = ZONE_POSITIONS[zone.zone];
          const worldX = pos.x * width;
          const worldZ = pos.z * depth;
          const colorSafe = zone.color ?? { r: 160, g: 180, b: 255 };
          const zoneColor = new THREE.Color(
            Number(colorSafe.r ?? 160) / 255,
            Number(colorSafe.g ?? 180) / 255,
            Number(colorSafe.b ?? 255) / 255
          );
          const zoneIntensity = Number.isFinite(Number(zone.intensity)) ? Number(zone.intensity) : 0.35;
          return (
            <mesh
              key={zone.zone}
              rotation={[-Math.PI / 2, 0, 0]}
              position={[worldX, 0.02, worldZ]}
            >
              <circleGeometry args={[width / 6, 32]} />
              <meshStandardMaterial
                color={zoneColor}
                emissive={zoneColor}
                emissiveIntensity={zoneIntensity * 0.5}
                transparent
                opacity={zoneIntensity * 0.3}
              />
            </mesh>
          );
        })}
    </group>
  );
}

// ============================================================================
// HAZE PARTICLES (SUBTLE ATMOSPHERIC EFFECT)
// ============================================================================

function HazeParticles({ count, spread }: { count: number; spread: [number, number, number] }) {
  const particlesRef = useRef<THREE.Points>(null);

  const [positions, sizes] = useMemo(() => {
    const pos = new Float32Array(count * 3);
    const sz = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * spread[0];
      pos[i * 3 + 1] = Math.random() * spread[1];
      pos[i * 3 + 2] = (Math.random() - 0.5) * spread[2];
      sz[i] = 0.05 + Math.random() * 0.15;
    }
    return [pos, sz];
  }, [count, spread[0], spread[1], spread[2]]);

  useFrame((_, delta) => {
    if (particlesRef.current) {
      // Slow upward drift
      const posArray = particlesRef.current.geometry.attributes.position.array as Float32Array;
      for (let i = 0; i < count; i++) {
        posArray[i * 3 + 1] += delta * 0.05 * (0.5 + Math.random() * 0.5);
        if (posArray[i * 3 + 1] > spread[1]) {
          posArray[i * 3 + 1] = 0;
        }
      }
      particlesRef.current.geometry.attributes.position.needsUpdate = true;
    }
  });

  return (
    <points ref={particlesRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={count}
          array={positions}
          itemSize={3}
        />
        <bufferAttribute
          attach="attributes-size"
          count={count}
          array={sizes}
          itemSize={1}
        />
      </bufferGeometry>
      <pointsMaterial
        color="#888"
        size={0.08}
        transparent
        opacity={0.06}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        sizeAttenuation
      />
    </points>
  );
}

function AtmosphereLayers({ width, depth, height }: { width: number; depth: number; height: number }) {
  const layers = [0.22, 0.45, 0.66, 0.84];
  return (
    <group>
      {layers.map((t, i) => (
        <mesh
          key={`atm-${i}`}
          rotation={[-Math.PI / 2, 0, 0]}
          position={[0, Math.max(0.7, t * height), 0]}
        >
          <planeGeometry args={[width * 1.15, depth * 1.15]} />
          <meshBasicMaterial
            color={new THREE.Color(0.28 + t * 0.22, 0.36 + t * 0.18, 0.52 + t * 0.12)}
            transparent
            opacity={0.012 + t * 0.012}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      ))}
    </group>
  );
}

// ============================================================================
// MAIN SCENE COMPONENT
// ============================================================================

function Scene({
  rig,
  debugBuffer,
  cameraMode,
  qualityMode,
  showVenue,
  showLabels,
  beatClock,
}: {
  rig: Rig;
  debugBuffer: MutableRefObject<Record<number, BeamDebugSnapshot>>;
  cameraMode: CameraMode;
  qualityMode: QualityMode;
  showVenue: boolean;
  showLabels: boolean;
  beatClock: MutableRefObject<BeatClock>;
}) {
  const universes = useDMXStore((state) => state.universes);
  const keyLightingZones = useDMXStore((state) => state.proLighting.keyLightingZones);
  const fixtureStates = useDMXStore((state) => state.fixtureStates);
  const liveBindings = useMemo(() => {
    const now = Date.now();
    // A DMX address only identifies a fixture within its own universe: a rig with
    // fixtures at address 1 in universes 0 and 1 has two fixtures sharing an address.
    const patchKey = (universe: unknown, address: unknown) =>
      `${Number(universe) || 0}:${Number(address)}`;
    const byAddress = new Map<string, LiveFixtureState>();
    const byId = new Map<string, LiveFixtureState>();
    const allStates: LiveFixtureState[] = [];

    fixtureStates.forEach((value) => {
      const state = value as LiveFixtureState;
      allStates.push(state);
      byId.set(String(state.id), state);
      const addr = Number(state?.dmx_address);
      if (Number.isFinite(addr) && addr > 0) byAddress.set(patchKey(state?.universe, addr), state);
    });

    const rigSorted = [...(rig.fixtures || [])].sort((a, b) => a.dmx_address - b.dmx_address);
    const stateSorted = [...allStates]
      .filter((s) => Number.isFinite(Number(s.dmx_address)))
      .sort((a, b) => Number(a.dmx_address) - Number(b.dmx_address));
    const ordinalFallback = new Map<number, LiveFixtureState>();
    const n = Math.min(rigSorted.length, stateSorted.length);
    for (let i = 0; i < n; i += 1) {
      ordinalFallback.set(rigSorted[i].id, stateSorted[i]);
    }

    const bindings = new Map<number, { state?: LiveFixtureState; source: string; staleMs?: number }>();
    for (const fx of rig.fixtures || []) {
      let state: LiveFixtureState | undefined;
      let source = 'dmx';

      if (byAddress.has(patchKey(fx.universe, fx.dmx_address))) {
        state = byAddress.get(patchKey(fx.universe, fx.dmx_address));
        source = 'state:dmx_address';
      } else if (byId.has(String(fx.id))) {
        state = byId.get(String(fx.id));
        source = 'state:fixture_id';
      } else if (fx.name && byId.has(String(fx.name))) {
        state = byId.get(String(fx.name));
        source = 'state:name';
      } else if (ordinalFallback.has(fx.id)) {
        state = ordinalFallback.get(fx.id);
        source = 'state:ordinal_fallback';
      }

      const staleMs = state?._updatedAt ? Math.max(0, now - Number(state._updatedAt)) : undefined;
      bindings.set(fx.id, { state, source, staleMs });
    }

    return bindings;
  }, [fixtureStates, rig]);

  // Crowd size rides on the same switch as haze and spot lights; the floor's
  // own capacity caps it for a small room.
  const quality = useMemo(() => {
    if (qualityMode === 'performance') return { hazeCount: 120, beamSegments: 10, spotCap: 12, crowdCount: 80 };
    if (qualityMode === 'ultra') return { hazeCount: 360, beamSegments: 24, spotCap: 40, crowdCount: 320 };
    return { hazeCount: 220, beamSegments: 16, spotCap: 24, crowdCount: 180 };
  }, [qualityMode]);

  // The room, the truss and how each fixture is mounted all come from one
  // layout, so they agree with each other and with the cameras.
  const venue = useMemo(
    () => buildVenue(
      { width: rig.stage_width, depth: rig.stage_depth, height: rig.stage_height },
      (rig.fixtures || []).map((fixture) => {
        const described = describeFixture(fixture);
        return {
          id: fixture.id,
          x: fixture.position_x,
          y: fixture.position_y,
          z: fixture.position_z,
          kind: described.modelKind,
          hasPanTilt: described.isMovingHead,
        };
      }),
    ),
    [rig]
  );

  const camera = useMemo(() => cameraPreset(cameraMode, venue.layout), [cameraMode, venue.layout]);

  // Empty the beam debug buffer when the rig changes. It is keyed by fixture
  // id and nothing ever removed an entry, so after the Demo rig chooser went
  // from a 52-fixture rig to a 34-fixture one the table still listed 52.
  // A layout effect in the scene itself, not in the page: by the time it runs
  // the old rig's fixtures have unmounted in this same commit, so none of them
  // can write a row back afterwards.
  useLayoutEffect(() => {
    debugBuffer.current = {};
  }, [rig, debugBuffer]);

  return (
    <>
      <PerspectiveCamera key={`cam-${cameraMode}`} makeDefault position={camera.position} fov={camera.fov} />
      <OrbitControls
        enablePan
        enableZoom
        enableRotate
        target={camera.target}
        maxPolarAngle={camera.maxPolar}
      />

      {/* Keep a visible baseline so scene never appears as a blank black page. */}
      <ambientLight intensity={0.24} />
      <hemisphereLight args={['#6f8cff', '#1b1b1b', 0.28]} />
      <directionalLight position={[6, 10, 4]} intensity={0.35} color="#9db4ff" />

      {/* The venue: club room, DJ booth and crowd. Hidden, the rig stands on
          the bare stage floor it always had. */}
      <BeatClockTicker clock={beatClock} />
      {showVenue ? (
        <>
          <ClubRoom layout={venue.layout} />
          <DJBooth layout={venue.layout} clock={beatClock} />
          <Crowd layout={venue.layout} count={quality.crowdCount} clock={beatClock} />
        </>
      ) : (
        <Stage width={rig.stage_width} depth={rig.stage_depth} />
      )}
      <KeyZoneHighlights
        width={rig.stage_width}
        depth={rig.stage_depth}
        keyZones={keyLightingZones}
      />
      {/* Truss is part of the rig, so it stays when the venue is hidden; only
          the hoists up to the ceiling go, because the ceiling has. */}
      <RigTruss rows={venue.trussRows} hangTo={showVenue ? venue.layout.ceilingY : undefined} />

      {/* Haze particles for atmospheric effect */}
      <AtmosphereLayers width={rig.stage_width} depth={rig.stage_depth} height={rig.stage_height} />
      {/* Keyed on the count: three cannot resize a buffer attribute in place, so
          switching quality with the same geometry threw on every frame and froze
          the view until the original quality was selected again. */}
      <HazeParticles
        key={`haze-${quality.hazeCount}`}
        count={quality.hazeCount}
        spread={[rig.stage_width, rig.stage_height, rig.stage_depth]}
      />

      {/* Fixtures */}
      {rig.fixtures?.map((fixture, index) => (
        <Fixture3D
          key={fixture.id}
          fixture={fixture}
          dmxData={universes.get(Number(fixture.universe) || 0) || BLANK_UNIVERSE}
          liveBinding={liveBindings.get(fixture.id)}
          fixtureIndex={index}
          spotCap={quality.spotCap}
          beamSegments={quality.beamSegments}
          mount={venue.mounts.get(fixture.id) ?? DEFAULT_MOUNT}
          showLabel={showLabels}
          onDebugUpdate={(snapshot) => {
            debugBuffer.current[snapshot.fixtureId] = snapshot;
          }}
        />
      ))}

      {/* Exponential fog for haze effect */}
      <fogExp2 attach="fog" args={['#05070a', 0.006]} />
    </>
  );
}

function fmt(value: unknown, digits = 1): string {
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n.toFixed(digits) : '0.0';
}

// ============================================================================
// LIVE READOUTS
//
// Each reads only the store fields it shows. The page around them does not
// subscribe to the store at all, so a message re-renders these few lines of
// text and nothing else.
// ============================================================================

function SectionReadout() {
  const genre = useDMXStore((state) => state.proLighting.genre);
  const section = useDMXStore((state) => state.proLighting.section);
  const dotColor = useDMXStore((state) => (
    state.proLighting.sectionIntensity > 0.7
      ? 'error.main'
      : state.proLighting.sectionIntensity > 0.4
        ? 'warning.main'
        : 'success.main'
  ));
  if (!genre) return null;
  return (
    <Box
      sx={{
        ml: 'auto',
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        px: 2,
        py: 0.5,
        bgcolor: 'grey.800',
        borderRadius: 2,
      }}
    >
      <Typography variant="body2" color="text.secondary">
        {genre}
      </Typography>
      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
        {section}
      </Typography>
      <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: dotColor }} />
    </Box>
  );
}

function EffectsReadout() {
  const strobeMode = useDMXStore((state) => state.proLighting.activeEffects.strobeMode);
  const movementType = useDMXStore((state) => state.proLighting.activeEffects.movementType);
  const chaseType = useDMXStore((state) => state.proLighting.activeEffects.chaseType);
  return (
    <Box sx={{ display: 'flex', gap: 2 }}>
      {strobeMode !== 'off' && (
        <Typography variant="body2" color="warning.main">
          Strobe: {strobeMode}
        </Typography>
      )}
      {movementType !== 'none' && (
        <Typography variant="body2" color="info.main">
          Movement: {movementType.replace(/_/g, ' ')}
        </Typography>
      )}
      {chaseType !== 'off' && (
        <Typography variant="body2" color="success.main">
          Chase: {chaseType.replace(/_/g, ' ')}
        </Typography>
      )}
    </Box>
  );
}

// Holds its own rows and timer, so the eight refreshes a second redraw this
// table and not the page it sits in.
function BeamDebugOverlay({ buffer }: { buffer: MutableRefObject<Record<number, BeamDebugSnapshot>> }) {
  const [rows, setRows] = useState<BeamDebugSnapshot[]>([]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setRows(Object.values(buffer.current).sort((a, b) => a.fixtureId - b.fixtureId));
    }, 120);

    return () => window.clearInterval(timer);
  }, [buffer]);

  return (
    <Card sx={{ mt: 2, maxHeight: 220, overflow: 'auto' }}>
      <CardContent sx={{ py: 1.25 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Beam Debug Overlay (movement + logical strobe/zoom mapping)
        </Typography>
        {rows.length === 0 ? (
          <Typography variant="caption" color="text.secondary">
            Waiting for moving-head fixture updates...
          </Typography>
        ) : (
          <Box sx={{ display: 'grid', gap: 0.3, fontFamily: 'monospace' }}>
            {rows.map((row) => (
              <Typography key={row.fixtureId} variant="caption" component="div">
                {String(row.fixtureLabel ?? `Fixture ${row.fixtureId}`).padEnd(18, ' ')} | tgt P/T {fmt(row.targetPanDeg)}°/{fmt(row.targetTiltDeg)}°
                {' '}| cur P/T {fmt(row.currentPanDeg)}°/{fmt(row.currentTiltDeg)}°
                {' '}| vel P/T {fmt(row.panVelocityDegPerSec)}/{fmt(row.tiltVelocityDegPerSec)} °/s
                {' '}| conf {fmt((row.signalConfidence ?? 0) * 100, 0)}%
                {' '}| strobe {fmt(row.strobeLogical, 2)} ({row.strobeSource} {row.strobeChannelIndex ? `ch${row.strobeChannelIndex}=${row.strobeChannelValue}` : 'no-channel'})
                {' '}| zoom {fmt(row.zoomLogical, 2)} ({row.zoomSource} {row.zoomChannelIndex ? `ch${row.zoomChannelIndex}=${row.zoomChannelValue}` : `dmx=${row.zoomChannelValue}`})
                {' '}| out I {fmt(row.finalIntensity, 2)} angle {fmt(row.finalSpotAngleDeg)}°
                {' '}| src {row.motionSource}{row.sourceStaleMs !== undefined ? ` (${Math.round(row.sourceStaleMs)}ms)` : ''}
                {' '}| {row.hold ? 'HOLD' : 'TRACK'}
                {row.capabilityWarnings.length > 0 ? ` | WARN: ${row.capabilityWarnings.join(', ')}` : ''}
              </Typography>
            ))}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}

// ============================================================================
// MAIN EXPORT COMPONENT
// ============================================================================

export default function RigVisualizer() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [rig, setRig] = useState<Rig | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const beamDebugBuffer = useRef<Record<number, BeamDebugSnapshot>>({});
  const [cameraMode, setCameraMode] = useState<CameraMode>('iso');
  const [qualityMode, setQualityMode] = useState<QualityMode>('balanced');
  // The room, DJ and crowd. Off leaves the bare rig for inspection.
  const [showVenue, setShowVenue] = useState(true);
  // Fixture ID labels. Until the operator chooses, they follow the venue: off
  // in the club view, on for the bare rig, where they are what you came for.
  const [labelChoice, setLabelChoice] = useState<boolean | null>(null);
  const showLabels = labelChoice ?? !showVenue;
  // Beat and section for the crowd. A ref, so a message re-renders nothing.
  const beatClock = useRef<BeatClock>(createBeatClock());
  const isDemo = !id; // No rig ID = demo mode
  const [demoPresets, setDemoPresets] = useState<DemoPresetSummary[]>([]);
  const [demoPresetError, setDemoPresetError] = useState<string | null>(null);

  // Connect to WebSocket for real-time DMX data
  useEffect(() => {
    // The store's actions, read once. Calling useDMXStore() here to get them
    // subscribed this whole page to every store change, so each of the 45
    // messages a second re-rendered the header, the dropdowns and the debug
    // table, and the 3D view was left a few frames a second.
    const {
      setUniverse,
      setFixtureStates,
      setEffectsInfo,
      setGenre,
      setSection,
      setActiveEffects,
      setKeyLightingZones,
      setEmotionVector,
      setBeatPhrase,
    } = useDMXStore.getState();

    const handleAnalysis = (data: any) => {
      const msg = data as any;
      ingestAnalysis(beatClock.current, msg, performance.now());
      if (msg.lighting) {
        const l = msg.lighting;
        if (l.dmx_frames) {
          Object.entries(l.dmx_frames).forEach(([universe, frame]) => {
            setUniverse(Number(universe) || 0, frame as number[]);
          });
        } else if (l.dmx_frame) {
          setUniverse(Number(l.dmx_universe) || 0, l.dmx_frame);
        }
        if (l.fixtures) setFixtureStates(l.fixtures);
        if (l.state) setEffectsInfo(l.state, l.movement || 'none', l.dimmer || 'none');
        if (l.genre) setGenre(l.genre);
        if (l.section) setSection(l.section, l.section_intensity ?? 0);
        if (l.pro_effects) setActiveEffects(l.pro_effects);
        if (l.key_zones) setKeyLightingZones(l.key_zones);
        if (l.emotion_vector) setEmotionVector(l.emotion_vector);
        if (l.beat_phrase !== undefined) setBeatPhrase(l.beat_phrase, l.beats_per_phrase ?? 4);
      }
    };

    audioWebSocket.on('analysis', handleAnalysis);
    audioWebSocket.connect().catch((err: any) => {
      console.warn('WebSocket connect failed, will retry:', err);
    });

    return () => {
      audioWebSocket.off('analysis', handleAnalysis);
    };
  }, []);

  useEffect(() => {
    if (id) {
      fetchRig(Number(id));
    } else {
      fetchDemoRig();
    }
  }, [id]);

  const fetchRig = async (rigId: number) => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await rigsApi.get(rigId);
      setRig(data);
    } catch (error) {
      console.error('Failed to fetch rig:', error);
      setLoadError('Failed to load rig data.');
    } finally {
      setLoading(false);
    }
  };

  const fetchDemoRig = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      // Through the shared axios instance, which is what attaches the operator
      // token; a bare fetch() here 401s on a box that has a password set.
      // No preset is named: the backend answers with the demo rig its engine
      // is running, so this view draws the rig whose state it receives.
      setRig(await demoApi.getRig());
    } catch (error) {
      console.error('Failed to fetch demo rig:', error);
      setLoadError(`Failed to load demo rig: ${(error as any)?.message || 'unknown error'}`);
    } finally {
      setLoading(false);
    }
    demoApi.listPresets().then(setDemoPresets).catch(() => setDemoPresets([]));
  };

  // The demo rig drawn here follows the engine: this view is sent state for
  // whatever rig the engine runs, and that rig can change without this view
  // asking. A restarted backend boots on its default demo rig, whatever was
  // picked before; another tab or a script can put a different one on. So
  // when the link comes back after dropping, and whenever the status poll
  // names a demo rig other than the one drawn, the view asks which rig is
  // running and draws that. It never puts its old pick back on the engine;
  // changing what the engine drives is the operator's call.
  // `loading` stays out of it: that flag swaps the whole page for a line of
  // text, which would throw the canvas away on every blip in the link.
  // This one component serves the patched-rig route as well, so an answer
  // still on its way when the operator opens a patched rig is not drawn.
  const showingDemo = useRef(isDemo);
  showingDemo.current = isDemo;
  // Refs, not state: the listeners below outlive any one render.
  const drawnVenue = useRef<string | null>(null);
  drawnVenue.current = rig?.venue ?? null;
  const demoRigFollower = useMemo(
    () =>
      createDemoRigFollower<Rig>({
        source: demoApi,
        draw: (next) => {
          if (!showingDemo.current) return;
          setRig((drawn) => settleRig(drawn, next));
          setLoadError(null);
        },
      }),
    []
  );

  useEffect(() => {
    if (!isDemo) return;
    const stopLink = onLinkRestored(audioWebSocket, () => {
      void demoRigFollower.follow();
      // A page opened while the box was down has no list for the chooser.
      demoApi.listPresets().then(setDemoPresets).catch(() => {});
    });
    // Read straight from the store, not through a hook: it changes with every
    // analysis message and this page must not re-render for that.
    const stopPoll = onEngineOnAnotherRig(
      useHealthStore,
      () => drawnVenue.current,
      () => void demoRigFollower.follow()
    );
    return () => {
      stopLink();
      stopPoll();
    };
  }, [isDemo, demoRigFollower]);

  // Put a different demo rig on the engine, then draw it.
  const changeDemoPreset = async (name: string) => {
    setDemoPresetError(null);
    try {
      await demoRigFollower.pick(name);
    } catch (error) {
      const detail = (error as any)?.response?.data?.detail;
      setDemoPresetError(typeof detail === 'string' ? detail : 'Could not switch the demo rig.');
    }
  };

  if (loading) {
    return <Typography>Loading visualizer...</Typography>;
  }

  if (!rig) {
    return (
      <Box sx={{ p: 2 }}>
        <Typography color="error.main">
          {loadError || 'Rig not found'}
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1, gap: 2, flexWrap: 'wrap' }}>
        <IconButton onClick={() => navigate(isDemo ? '/' : `/rigs/${rig.id}`)}>
          <BackIcon />
        </IconButton>
        <Typography variant="h5">{rig.name}</Typography>
        {isDemo && demoPresets.length > 0 && (
          <TextField
            select
            size="small"
            label="Demo rig"
            value={demoPresets.some((d) => d.name === rig.venue) ? rig.venue : ''}
            onChange={(event) => changeDemoPreset(event.target.value)}
            sx={{ minWidth: 190 }}
          >
            {demoPresets.map((preset) => (
              <MenuItem key={preset.name} value={preset.name}>
                {preset.display_name} ({preset.total_fixtures})
              </MenuItem>
            ))}
          </TextField>
        )}
        {demoPresetError && (
          <Typography variant="body2" color="error.main">{demoPresetError}</Typography>
        )}
        <ButtonGroup size="small" variant="outlined" sx={{ ml: 1 }}>
          <Button variant={cameraMode === 'iso' ? 'contained' : 'outlined'} onClick={() => setCameraMode('iso')}>Iso</Button>
          <Button variant={cameraMode === 'top' ? 'contained' : 'outlined'} onClick={() => setCameraMode('top')}>Top</Button>
          <Button variant={cameraMode === 'front' ? 'contained' : 'outlined'} onClick={() => setCameraMode('front')}>Front</Button>
          <Button variant={cameraMode === 'audience' ? 'contained' : 'outlined'} onClick={() => setCameraMode('audience')}>Audience</Button>
          <Button variant={cameraMode === 'dj' ? 'contained' : 'outlined'} onClick={() => setCameraMode('dj')}>DJ</Button>
          <Button variant={cameraMode === 'floor' ? 'contained' : 'outlined'} onClick={() => setCameraMode('floor')}>Floor</Button>
        </ButtonGroup>
        <ButtonGroup size="small" variant="outlined">
          <Button variant={qualityMode === 'performance' ? 'contained' : 'outlined'} onClick={() => setQualityMode('performance')}>Perf</Button>
          <Button variant={qualityMode === 'balanced' ? 'contained' : 'outlined'} onClick={() => setQualityMode('balanced')}>Balanced</Button>
          <Button variant={qualityMode === 'ultra' ? 'contained' : 'outlined'} onClick={() => setQualityMode('ultra')}>Ultra</Button>
        </ButtonGroup>
        <ButtonGroup size="small" variant="outlined">
          <Tooltip describeChild title="Show the club room, DJ and crowd. Off leaves the bare rig.">
            <Button
              variant={showVenue ? 'contained' : 'outlined'}
              aria-pressed={showVenue}
              onClick={() => setShowVenue((on) => !on)}
            >
              Venue
            </Button>
          </Tooltip>
          <Tooltip describeChild title="Show each fixture's ID">
            <Button
              variant={showLabels ? 'contained' : 'outlined'}
              aria-pressed={showLabels}
              onClick={() => setLabelChoice(!showLabels)}
            >
              IDs
            </Button>
          </Tooltip>
        </ButtonGroup>
      </Box>

      {/* Audio Device Chooser */}
      <Box sx={{ mb: 1, display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
        <AudioDeviceChooser />
        <SectionReadout />
      </Box>

      {/* 3D Canvas */}
      <Box sx={{ flexGrow: 1, bgcolor: '#000', borderRadius: 2, overflow: 'hidden' }}>
        <Canvas
          shadows
          gl={{
            antialias: true,
            toneMapping: THREE.ACESFilmicToneMapping,
            toneMappingExposure: qualityMode === 'ultra' ? 1.32 : 1.2,
          }}
          dpr={qualityMode === 'ultra' ? [1.2, 2] : qualityMode === 'performance' ? [1, 1.2] : [1, 1.5]}
        >
          <Scene
            rig={rig}
            debugBuffer={beamDebugBuffer}
            cameraMode={cameraMode}
            qualityMode={qualityMode}
            showVenue={showVenue}
            showLabels={showLabels}
            beatClock={beatClock}
          />
        </Canvas>
      </Box>

      {/* Beam debug overlay to separate control jitter from render jitter */}
      <BeamDebugOverlay buffer={beamDebugBuffer} />

      {/* Info Panel */}
      <Card sx={{ mt: 2 }}>
        <CardContent sx={{ py: 1 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2">
              Stage: {rig.stage_width}m x {rig.stage_depth}m x {rig.stage_height}m |
              Fixtures: {rig.fixtures?.length || 0} |
              Use mouse to rotate, scroll to zoom, right-click to pan
            </Typography>
            <EffectsReadout />
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
