import { useState, useEffect, useLayoutEffect, useRef, useMemo, useCallback } from 'react';
import type { MutableRefObject } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Alert, Box, IconButton, Typography, Card, CardContent, ButtonGroup, Button, MenuItem, TextField, Tooltip,
} from '@mui/material';
import {
  ArrowBack as BackIcon,
} from '@mui/icons-material';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Grid, PerspectiveCamera } from '@react-three/drei';
import * as THREE from 'three';
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { demoApi, effectsApi, rigsApi } from '../../services/api';
import type { DemoPresetSummary } from '../../services/api';
import type { Rig, RoomShellBox } from '../../types';
import { useDMXStore } from '../../stores/dmxStore';
import { useHealthStore } from '../../stores/healthStore';
import { audioWebSocket } from '../../services/websocket';
import {
  createDemoRigFollower,
  fetchEngineRig,
  livePatchedRigId,
  onEngineOnAnotherRig,
  onLinkRestored,
  onPatchedRigActivated,
  settleRig,
} from '../../utils/demoRigSync';
import type { EngineRigApis } from '../../utils/demoRigSync';
import AudioDeviceChooser from '../common/AudioDeviceChooser';
import { ConsoleExportButton } from './ConsoleExportSection';
import { createBeatClock, ingestAnalysis } from './previs/beatClock';
import type { BeatClock } from './previs/beatClock';
import { isPositionUnconfirmed } from './previs/beamState';
import { ClubRoom } from './previs/ClubRoom';
import { BeatClockTicker, Crowd, PlacedCrowd } from './previs/Crowd';
import { DJBooth } from './previs/DJBooth';
import { FixtureRig } from './previs/FixtureRig';
import { describeFixture } from './previs/fixtureRuntime';
import type { BeamDebugSnapshot } from './previs/fixtureRuntime';
import { GuessMarkers } from './previs/GuessMarkers';
import type { GuessPoint } from './previs/GuessMarkers';
import { createOutputFeed, ingestOutput, summariseFeed } from './previs/outputFeed';
import type { FeedSummary, OutputFeed } from './previs/outputFeed';
import { roomOutline, scanHangers, scanRisers, scannedRoom, usableDisc, usableDome } from './previs/roomShell';
import type { OutlinePoint } from './previs/roomShell';
import { boxHeading } from './previs/raisedArea';
import { boxFloor, placeScanBooth, placeScanCrowd } from './previs/scanFloor';
import { boothCameraPreset, boothFloorStand } from './previs/boothCamera';
import { isDjBooth } from './previs/boothPick';
import type { FloorCamera } from './previs/scanFloor';
import { RoomShellView } from './previs/RoomShellView';
import { beamRoom, buildVenue, cameraPreset, roomSpan } from './previs/layout';
import type { CameraMode } from './previs/layout';
import { RigTruss } from './previs/Truss';
import { FixtureDragLayer } from './previs/FixtureDragLayer';
import type { DragHandle } from './previs/FixtureDragLayer';
import {
  nudgePosition, positionLimits, positionText, snapLines, withFixturePosition, withSavedFixture,
} from './previs/fixtureDrag';
import type { Point3 } from './previs/fixtureDrag';
import RoomScanUndoButton from './RoomScanUndoButton';
import { undoCount, undoResultText } from '../../utils/roomScan';
import { StagePlotFloor } from './previs/StagePlotFloor';
import type { StagePlotFloorProps } from './previs/StagePlotFloor';
import StagePlot3dToggle from './previs/StagePlot3dToggle';
import useStagePlot3d from './previs/useStagePlot3d';
import { FocusTargetMarkers } from './previs/FocusTargetMarkers';
import FocusTargets3dToggle from './previs/FocusTargets3dToggle';
import useFocusTargets3d from './previs/useFocusTargets3d';
import type { FocusMarker } from '../../utils/focusPresets';
import { createLightingWriter, createTrailingThrottle } from './previs/storeThrottle';
import {
  PREVIZ_SHADOWS_KEY, PREVIZ_STATS_KEY, defaultShowLabels, previzDpr, readViewToggle, writeViewToggle,
} from './previs/viewSettings';
import { StatsOverlay, StatsSampler } from './previs/PrevizStats';
import { createLookUniforms } from './previs/lookUniforms';
import {
  HAZE_DRIFT_COUNT, fogDensity, readLookSettings, staticHazeStrength, writeLookSettings,
} from './previs/lookSettings';
import type { LookSettings } from './previs/lookSettings';
import { HazeDrift } from './previs/HazeDrift';
import type { HazeBounds } from './previs/hazePuffs';
import LookControls from './previs/LookControls';
import type { PrevizStatsSample } from './previs/PrevizStats';

type QualityMode = 'performance' | 'balanced' | 'ultra';

// ============================================================================
// CONSTANTS
// ============================================================================

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

// Subscribes to the zones itself, so a change re-renders these few discs and
// not the scene they sit in. The store is written only when the zones change.
function KeyZoneHighlights({
  width,
  depth,
}: {
  width: number;
  depth: number;
}) {
  const keyZones = useDMXStore((state) => state.proLighting.keyLightingZones) as Array<{
    zone: string; active: boolean; intensity: number; color: { r: number; g: number; b: number };
  }>;
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

function HazeParticles({
  count,
  spread,
  strength,
}: {
  count: number;
  spread: [number, number, number];
  /** 1 as they always were; scaled with the Haze slider. */
  strength: number;
}) {
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
        opacity={Math.min(1, 0.06 * strength)}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        sizeAttenuation
      />
    </points>
  );
}

const ATMOSPHERE_LAYERS = [0.22, 0.45, 0.66, 0.84];

/**
 * Four faint haze sheets at rising heights, merged into one draw. They are
 * added to what is behind them, so each sheet's colour times its opacity is
 * baked into its vertex colours and the merged sheet is drawn at full opacity:
 * the same light added as four meshes with their own opacity gave.
 */
function buildAtmosphere(width: number, depth: number, height: number): THREE.BufferGeometry {
  const sheets = ATMOSPHERE_LAYERS.map((t) => {
    const sheet = new THREE.PlaneGeometry(width * 1.15, depth * 1.15)
      .rotateX(-Math.PI / 2)
      .translate(0, Math.max(0.7, t * height), 0);
    const opacity = 0.012 + t * 0.012;
    const r = (0.28 + t * 0.22) * opacity;
    const g = (0.36 + t * 0.18) * opacity;
    const b = (0.52 + t * 0.12) * opacity;
    const count = sheet.getAttribute('position').count;
    const colors = new Float32Array(count * 3);
    for (let i = 0; i < count; i += 1) {
      colors[i * 3] = r;
      colors[i * 3 + 1] = g;
      colors[i * 3 + 2] = b;
    }
    sheet.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    return sheet;
  });
  const merged = mergeGeometries(sheets, false);
  sheets.forEach((sheet) => sheet.dispose());
  return merged ?? new THREE.BufferGeometry();
}

const atmosphereMaterial = new THREE.MeshBasicMaterial({
  vertexColors: true,
  transparent: true,
  blending: THREE.AdditiveBlending,
  depthWrite: false,
});

function AtmosphereLayers({
  width,
  depth,
  height,
  strength,
}: {
  width: number;
  depth: number;
  height: number;
  /** 1 as they always were; scaled with the Haze slider (the material's colour multiplies the baked sheets). */
  strength: number;
}) {
  const geometry = useMemo(() => buildAtmosphere(width, depth, height), [width, depth, height]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  useLayoutEffect(() => {
    atmosphereMaterial.color.setScalar(strength);
  }, [strength]);
  return <mesh geometry={geometry} material={atmosphereMaterial} dispose={null} />;
}

// ============================================================================
// MAIN SCENE COMPONENT
// ============================================================================

/** One empty list for "no focus targets", so the scene's default does not change on every render. */
const NO_FOCUS_TARGETS: FocusMarker[] = [];

function Scene({
  rig,
  debugBuffer,
  cameraMode,
  qualityMode,
  showVenue,
  showLabels,
  shadows,
  beatClock,
  feed,
  debug,
  move,
  stagePlot = null,
  focusTargets = NO_FOCUS_TARGETS,
  lookSettings,
}: {
  rig: Rig;
  /** Haze, soft beams, gobos and the drifting haze (lookSettings.ts). Bloom and exposure are the canvas's. */
  lookSettings: LookSettings;
  /** Shadows on: the brightest few beams get a real, shadow-casting spot light. */
  shadows: boolean;
  /** The calibrated stage plot to lay on the floor, or null. */
  stagePlot?: StagePlotFloorProps | null;
  /** The focus presets' target points to mark (docs/FOCUS_PRESETS.md); empty with the toggle off. */
  focusTargets?: FocusMarker[];
  debugBuffer: MutableRefObject<Record<number, BeamDebugSnapshot>>;
  cameraMode: CameraMode;
  qualityMode: QualityMode;
  showVenue: boolean;
  showLabels: boolean;
  beatClock: MutableRefObject<BeatClock>;
  /** The frames the engine outputs. The fixtures read it; nothing writes DMX. */
  feed: MutableRefObject<OutputFeed>;
  /** Whether the beam debug table is open. */
  debug: boolean;
  /** Move fixtures mode: which fixture is selected and what a drag does. Null with the mode off. */
  move: {
    selectedId: number | null;
    snap: boolean;
    onSelect: (id: number) => void;
    onMove: (id: number, to: Point3) => void;
  } | null;
}) {

  // Crowd size rides on the same switch as haze and spot lights; the floor's
  // own capacity caps it for a small room.
  const quality = useMemo(() => {
    if (qualityMode === 'performance') return { hazeCount: 120, beamSegments: 10, crowdCount: 80 };
    if (qualityMode === 'ultra') return { hazeCount: 360, beamSegments: 24, crowdCount: 320 };
    return { hazeCount: 220, beamSegments: 16, crowdCount: 180 };
  }, [qualityMode]);
  const rigFixtures = useMemo(() => rig.fixtures ?? [], [rig.fixtures]);

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
          // A wall the scan measured does not move out for a position nobody has confirmed.
          guess: isPositionUnconfirmed(fixture),
        };
      }),
      // A scanned room has walls and a ceiling of its own.
      scannedRoom(rig.room_shell),
      // And may have truss the view's own cannot stand in for: at an angle, or a ring.
      scanHangers(rig.room_shell),
      // And may not be a box: then its walls are the outline of its floor.
      roomOutline(rig.room_shell),
    ),
    [rig]
  );

  // The room the rig describes, where it describes one. It takes the place of
  // the flat ceiling and the square dance floor the view would otherwise build.
  const shell = rig.room_shell ?? null;
  const shellDome = usableDome(shell?.dome);
  const shellDisc = usableDisc(shell?.dance_floor);
  // A room read from a scan is drawn as the scan found it. The booth against
  // the upstage wall, the speaker stacks and the square dance floor are the
  // view's own invention for a room it knows nothing about, and would stand
  // through the stage and risers the scan did find, so they are left out of
  // that room. Its booth and its crowd are fitted to it instead (below).
  const scanned = scannedRoom(shell) !== null;
  // One that is not a box has its floor, walls and ceiling drawn along its
  // outline (RoomShellView), in place of the club room's box. The outline is
  // the venue's: the one the mounts, the beams and the cameras go by too.
  const outlined = venue.outline !== null;

  // The booth and the crowd of a scanned room (scanFloor.ts): the booth on
  // the raised area that is one, the crowd on the floor left open round the
  // stage, the risers and the booth. Both are worked out from the floor and
  // the raised areas alone, written out as text first: an edit to the room
  // changes the text and places them again, and a fixture moved, which makes
  // a new rig and a new venue but the same text, leaves everybody standing.
  const scanFloorKey = useMemo(() => {
    if (!scanned) return null;
    const { layout } = venue;
    const stand = cameraPreset('floor', layout, venue.outline).position;
    return JSON.stringify({
      outline: venue.outline ?? boxFloor(-layout.wallX, layout.wallX, layout.backZ, layout.houseZ),
      risers: scanRisers(shell).map((riser) => ({
        kind: riser.kind,
        center_x: riser.center_x,
        center_z: riser.center_z,
        width: riser.width,
        depth: riser.depth,
        height: riser.height,
        base_height: riser.base_height ?? 0,
        // One at a heading stands turned (slice 21); one that is not says nothing, as before.
        ...(boxHeading(riser) !== 0 ? { heading_deg: boxHeading(riser) } : {}),
        // The one somebody marked as the DJ's booth (slice 28) says so; no other does, so a room
        // nobody marked one in is the same text, and the same booth and crowd, as before.
        ...(isDjBooth(riser) ? { is_dj_booth: true } : {}),
      })),
      camera: { x: stand[0], z: stand[2], clearRadius: layout.floorCamera.clearRadius },
    });
  }, [scanned, shell, venue]);
  const scanFloor = useMemo(() => {
    if (!scanFloorKey) return null;
    const floor = JSON.parse(scanFloorKey) as { outline: OutlinePoint[]; risers: RoomShellBox[]; camera: FloorCamera };
    const booth = placeScanBooth(floor.outline, floor.risers);
    // The Floor camera stands in front of the booth that is drawn (boothCamera.ts), and the crowd
    // leaves it room there. With no booth, or nowhere in front of it, it stands where it did.
    const stand = booth ? boothFloorStand(booth, floor.outline, floor.risers) : null;
    return { ...floor, camera: stand ? { ...floor.camera, ...stand } : floor.camera, booth };
  }, [scanFloorKey]);
  const scanBooth = scanFloor?.booth ?? null;
  const scanPeople = useMemo(
    () => (scanFloor
      ? placeScanCrowd(scanFloor.outline, scanFloor.risers, scanFloor.booth, quality.crowdCount, scanFloor.camera)
      : []),
    [scanFloor, quality.crowdCount],
  );
  // The work light that is over the booth goes with it.
  const scanBoothLight = useMemo<[number, number, number] | null>(
    () => (scanBooth
      ? [scanBooth.x + scanBooth.faceX * 0.55, scanBooth.deskTopY + 1.5, scanBooth.z + scanBooth.faceZ * 0.55]
      : null),
    [scanBooth],
  );

  // Fixtures whose position nobody has confirmed: drawn where the guess puts
  // them, and marked so that is plain.
  const guesses = useMemo<GuessPoint[]>(
    () => (rig.fixtures || []).filter(isPositionUnconfirmed).map((fixture) => {
      const mount = venue.mounts.get(fixture.id);
      return {
        x: fixture.position_x,
        y: fixture.position_y + (mount?.type === 'stand' ? mount.lift : 0),
        z: fixture.position_z,
      };
    }),
    [rig, venue]
  );

  // Move fixtures mode: something to grab on every fixture, drawn where the
  // fixture is drawn (one on a stand is lifted, like its guess marker).
  const moving = move !== null;
  const handles = useMemo<DragHandle[]>(
    () => (moving ? (rig.fixtures || []).map((fixture) => {
      const mount = venue.mounts.get(fixture.id);
      return {
        id: fixture.id,
        x: fixture.position_x,
        y: fixture.position_y,
        z: fixture.position_z,
        lift: mount?.type === 'stand' ? mount.lift : 0,
        unconfirmed: isPositionUnconfirmed(fixture),
      };
    }) : []),
    [rig, venue, moving]
  );
  const dragLimits = useMemo(() => positionLimits(rig), [rig]);
  const dragSnapLines = useMemo(() => snapLines(rig.room_shell), [rig.room_shell]);

  // In a room that is not a box the cameras stand, and look, inside its outline. In a scanned room
  // the DJ and Floor cameras go by the booth that is drawn there (marked, the room's own or a
  // guess), at its heading; every other camera, and every camera of a room with no scan or no
  // booth, is the preset as it always was.
  const camera = useMemo(() => {
    const preset = cameraPreset(cameraMode, venue.layout, venue.outline);
    return scanFloor
      ? boothCameraPreset(cameraMode, preset, scanFloor.booth, scanFloor.outline, scanFloor.risers)
      : preset;
  }, [cameraMode, venue, scanFloor]);
  const longestThrow = useMemo(() => roomSpan(venue.layout), [venue.layout]);
  // With the venue hidden no walls are drawn, so none stops a beam. In a room
  // that is not a box a beam ends on the outline's walls, not on the box.
  const room = useMemo(() => beamRoom(venue.layout, showVenue, venue.outlineWalls), [venue, showVenue]);

  // Empty the beam debug buffer when the rig changes. It is keyed by fixture
  // id and nothing ever removed an entry, so after the Demo rig chooser went
  // from a 52-fixture rig to a 34-fixture one the table still listed 52.
  // A layout effect in the scene itself, not in the page: by the time it runs
  // the old rig's fixtures that have no counterpart in the new one have
  // unmounted in this same commit, so none of them can write a row back
  // afterwards. A fixture whose id is in both rigs is the same component
  // reused, and the next row it writes is the new rig's.
  useLayoutEffect(() => {
    debugBuffer.current = {};
  }, [rig, debugBuffer]);

  // The look controls as uniforms the beam, pool and haze materials share
  // (lookUniforms.ts): made once, written here, read on the next frame.
  const look = useMemo(() => createLookUniforms(), []);
  useLayoutEffect(() => {
    look.haze.value = lookSettings.haze;
    look.softBeams.value = lookSettings.softBeams ? 1 : 0;
    look.gobos.value = lookSettings.gobos ? 1 : 0;
  }, [look, lookSettings.haze, lookSettings.softBeams, lookSettings.gobos]);

  // What the drifting haze fills: the club room, or above the bare stage.
  const hazeBounds = useMemo<HazeBounds>(() => {
    const { layout } = venue;
    return showVenue
      ? { xMin: -layout.wallX, xMax: layout.wallX, zMin: layout.backZ, zMax: layout.houseZ, floorY: 0, ceilingY: layout.ceilingY }
      : {
          xMin: -rig.stage_width / 2,
          xMax: rig.stage_width / 2,
          zMin: -rig.stage_depth / 2,
          zMax: rig.stage_depth / 2,
          floorY: 0,
          ceilingY: Math.max(3, rig.stage_height),
        };
  }, [venue, showVenue, rig.stage_width, rig.stage_depth, rig.stage_height]);
  const staticHaze = staticHazeStrength(lookSettings.haze);

  return (
    <>
      <PerspectiveCamera key={`cam-${cameraMode}`} makeDefault position={camera.position} fov={camera.fov} />
      {/* makeDefault: a fixture drag switches the camera off through the
          scene's default controls, and without it there are none to find. */}
      <OrbitControls
        makeDefault
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
          <ClubRoom
            layout={venue.layout}
            ceiling={!shellDome}
            danceFloor={!shellDisc && !scanned}
            dressing={!scanned}
            shell={!outlined}
            boothLight={scanBoothLight}
          />
          {shell && (
            <RoomShellView shell={shell} layout={venue.layout} trussRows={venue.trussRows} outline={venue.outline} />
          )}
          {!scanned && <DJBooth layout={venue.layout} clock={beatClock} />}
          {!scanned && <Crowd layout={venue.layout} count={quality.crowdCount} clock={beatClock} />}
          {/* A scanned room: the booth on the raised area marked as the DJ's, or
              where the room has one (or, with the amber mark of a guess, on its
              first stage), and the crowd on its open floor. */}
          {scanned && scanBooth && <DJBooth layout={venue.layout} clock={beatClock} placed={scanBooth} />}
          {scanned && <PlacedCrowd people={scanPeople} clock={beatClock} />}
        </>
      ) : (
        <Stage width={rig.stage_width} depth={rig.stage_depth} />
      )}
      {/* The calibrated stage plot, flat on the floor; never hit, so dragging goes through it. */}
      {stagePlot && <StagePlotFloor {...stagePlot} />}
      <KeyZoneHighlights
        width={rig.stage_width}
        depth={rig.stage_depth}
      />
      {/* Truss is part of the rig, so it stays when the venue is hidden; only
          the hoists up to the ceiling go, because the ceiling has. */}
      <RigTruss rows={venue.trussRows} hangTo={showVenue ? venue.layout.ceilingY : undefined} />

      {/* The static haze: faint sheets and specks, as strong as the Haze slider
          says (as they always were at its default, gone in clean air). */}
      {staticHaze > 0 && (
        <AtmosphereLayers
          width={rig.stage_width}
          depth={rig.stage_depth}
          height={rig.stage_height}
          strength={staticHaze}
        />
      )}
      {/* Keyed on the count: three cannot resize a buffer attribute in place, so
          switching quality with the same geometry threw on every frame and froze
          the view until the original quality was selected again. */}
      {staticHaze > 0 && (
        <HazeParticles
          key={`haze-${quality.hazeCount}`}
          count={quality.hazeCount}
          spread={[rig.stage_width, rig.stage_height, rig.stage_depth]}
          strength={staticHaze}
        />
      )}
      {/* The drifting haze: a few big soft puffs, lit by the rig (HazeDrift.tsx). */}
      {lookSettings.hazeDrift && lookSettings.haze > 0 && (
        <HazeDrift look={look} count={HAZE_DRIFT_COUNT[qualityMode]} bounds={hazeBounds} />
      )}

      {/* Fixtures */}
      {/* Every fixture: bodies, beams and floor pools as instanced draws,
          moved by one frame callback (FixtureRig.tsx). With Shadows on, the
          brightest few beams get a real shadow-casting light. */}
      <FixtureRig
        fixtures={rigFixtures}
        mounts={venue.mounts}
        feed={feed}
        room={room}
        longestThrow={longestThrow}
        beamSegments={quality.beamSegments}
        shadows={shadows}
        showLabels={showLabels}
        debug={debug}
        debugBuffer={debugBuffer}
        look={look}
      />

      {/* Positions that are a guess, marked as one */}
      <GuessMarkers points={guesses} />

      {/* Where the focus presets aim; never hit, so dragging goes through them. */}
      {focusTargets.length > 0 && <FocusTargetMarkers markers={focusTargets} />}

      {/* Move fixtures mode: pick one up and put it down somewhere else */}
      {move && (
        <FixtureDragLayer
          handles={handles}
          selectedId={move.selectedId}
          limits={dragLimits}
          snapLines={move.snap && dragSnapLines.length > 0 ? dragSnapLines : null}
          onSelect={move.onSelect}
          onMove={move.onMove}
        />
      )}

      {/* Exponential fog for haze effect: a trace in clean air, thicker with the Haze slider. */}
      <fogExp2 attach="fog" args={['#05070a', 0.006]} density={fogDensity(lookSettings.haze)} />
      {/* Black behind everything, drawn or post-processed: bloom must not see a transparent canvas. */}
      <color attach="background" args={['#000000']} />
    </>
  );
}

// What the picture is drawn from, in a line: on the wire, preview only,
// blackout, or nothing arriving. Polls the feed twice a second and re-renders
// only when the line changes.
function FeedReadout({ feed, guessCount }: { feed: MutableRefObject<OutputFeed>; guessCount: number }) {
  const [summary, setSummary] = useState<FeedSummary>(() => summariseFeed(feed.current, performance.now()));
  useEffect(() => {
    const timer = window.setInterval(() => {
      const next = summariseFeed(feed.current, performance.now());
      setSummary((shown) => (shown.kind === next.kind && shown.label === next.label ? shown : next));
    }, 500);
    return () => window.clearInterval(timer);
  }, [feed]);
  const color = summary.kind === 'live'
    ? 'success.main'
    : summary.kind === 'stale' || summary.kind === 'blackout'
      ? 'error.main'
      : summary.kind === 'none' ? 'text.secondary' : 'warning.main';
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
      <Tooltip describeChild title={`${summary.detail} This view only reads the output; it never sends DMX.`}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }} data-testid="previs-feed-status">
          <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: color }} />
          <Typography variant="body2">{summary.label}</Typography>
        </Box>
      </Tooltip>
      {guessCount > 0 && (
        <Tooltip describeChild title="Marked in amber. These were laid out on a template and nobody has confirmed where they really are, so their beams may be drawn in the wrong place.">
          <Typography variant="body2" sx={{ color: '#ffb74d' }}>
            {guessCount} position{guessCount === 1 ? '' : 's'} unconfirmed
          </Typography>
        </Tooltip>
      )}
    </Box>
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
                {' '}| shutter {row.shutter} | src {row.motionSource}
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

// How the live view finds the rig the engine is running.
const engineRigApis: EngineRigApis<Rig> = {
  getStatus: effectsApi.getStatus,
  getPatchedRig: rigsApi.get,
  getDemoRig: demoApi.getRig,
};

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
  // in the club view, on for the bare rig, where they are what you came for;
  // but off on a big rig, where a hundred HTML labels cost more than the rig.
  const [labelChoice, setLabelChoice] = useState<boolean | null>(null);
  const showLabels = labelChoice ?? defaultShowLabels(showVenue, rig?.fixtures?.length ?? 0);
  // Shadows from the brightest beams. Off until the operator turns them on;
  // the choice is kept for this machine.
  const [shadows, setShadowsState] = useState<boolean>(() => readViewToggle(PREVIZ_SHADOWS_KEY) ?? false);
  const setShadows = useCallback((on: boolean) => {
    setShadowsState(on);
    writeViewToggle(PREVIZ_SHADOWS_KEY, on);
  }, []);
  // The frame-rate overlay. The numbers are published on window.__previzStats either way.
  const [showStats, setShowStatsState] = useState<boolean>(() => readViewToggle(PREVIZ_STATS_KEY) ?? false);
  const setShowStats = useCallback((on: boolean) => {
    setShowStatsState(on);
    writeViewToggle(PREVIZ_STATS_KEY, on);
  }, []);
  const statsSink = useRef<((sample: PrevizStatsSample) => void) | null>(null);
  // Haze, bloom, exposure, soft beams, gobos (lookSettings.ts), kept for this machine.
  const [lookSettings, setLookSettings] = useState<LookSettings>(() => readLookSettings());
  const changeLook = useCallback((next: Partial<LookSettings>) => {
    setLookSettings((current) => {
      const updated = { ...current, ...next };
      writeLookSettings(updated);
      return updated;
    });
  }, []);
  // Beat and section for the crowd. A ref, so a message re-renders nothing.
  const beatClock = useRef<BeatClock>(createBeatClock());
  // The frames the engine outputs, as they arrive. A ref for the same reason;
  // the fixtures read it in the frame loop. Read-only: nothing here sends DMX.
  const outputFeed = useRef<OutputFeed>(createOutputFeed());
  // The beam debug table. Off, no fixture writes a row for it.
  const [showDebug, setShowDebug] = useState(false);
  const isDemo = !id; // No rig ID = demo mode
  // The rig's stage plot, on the floor once it is calibrated (docs/STAGE_PLOT.md). The demo rig has none to ask for.
  const stagePlot = useStagePlot3d(isDemo ? null : Number(id), rig?.stage_width ?? 10, rig?.stage_depth ?? 8);
  // The focus presets' targets, marked when the operator asks (docs/FOCUS_PRESETS.md). The demo rig has no room to aim in.
  const focusTargets = useFocusTargets3d(isDemo ? null : Number(id));
  const [demoPresets, setDemoPresets] = useState<DemoPresetSummary[]>([]);
  const [demoPresetError, setDemoPresetError] = useState<string | null>(null);

  // Connect to WebSocket for real-time DMX data
  useEffect(() => {
    // The store's actions, read once. Calling useDMXStore() here to get them
    // subscribed this whole page to every store change, so each of the 45
    // messages a second re-rendered the header, the dropdowns and the debug
    // table, and the 3D view was left a few frames a second.
    // The store is written at most ten times a second, and only with values
    // that changed (storeThrottle.ts). The 3D view does not wait on it: the
    // beat clock and the output feed below are refs fed on every message.
    const writer = createLightingWriter(useDMXStore.getState());
    const throttle = createTrailingThrottle(() => { writer.flush(); });

    const handleAnalysis = (data: any) => {
      const msg = data as any;
      ingestAnalysis(beatClock.current, msg, performance.now());
      if (msg.lighting) {
        const l = msg.lighting;
        ingestOutput(outputFeed.current, l, performance.now());
        writer.ingest(l);
        throttle.request();
      }
    };

    audioWebSocket.on('analysis', handleAnalysis);
    audioWebSocket.connect().catch((err: any) => {
      console.warn('WebSocket connect failed, will retry:', err);
    });

    return () => {
      audioWebSocket.off('analysis', handleAnalysis);
      throttle.cancel();
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
      // This view is sent state for the rig the engine runs, so that is the
      // rig it draws: the patched rig once one has been activated, and the
      // engine's demo rig until then.
      setRig(await fetchEngineRig(engineRigApis));
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
        source: {
          // Asked which rig the engine runs, the answer may be a patched rig.
          getRig: (preset) => (preset ? demoApi.getRig(preset) : fetchEngineRig(engineRigApis)),
          applyPreset: demoApi.applyPreset,
        },
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

  // Activate puts a rig on the running engine with no restart, from the rig
  // pages or another tab. The status poll's next reading carries a new rig
  // version, and the view draws again: on the live view, whichever rig the
  // engine now runs; on a patched rig's own page, that rig as it was just
  // applied, so an edit shows without a reload. Quietly, like the demo
  // follower: the canvas stays up and an unchanged rig is not rebuilt.
  const shownRigId = useRef<number | null>(null);
  shownRigId.current = id ? Number(id) : null;
  useEffect(() => {
    return onPatchedRigActivated(useHealthStore, (report) => {
      const pageRigId = shownRigId.current;
      if (pageRigId === null) {
        void demoRigFollower.follow();
        return;
      }
      if (livePatchedRigId(report) !== pageRigId) return;
      rigsApi
        .get(pageRigId)
        .then((next) => {
          if (shownRigId.current === pageRigId) setRig((drawn) => settleRig(drawn, next));
        })
        .catch(() => {
          // Keep what is drawn; the next activation asks again.
        });
    });
  }, [demoRigFollower]);

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

  // --- Move fixtures mode (a rig stored in the database only) ---------------
  // Drag a fixture in the view, or nudge the selected one with the keys; each
  // move is saved through the position route, which confirms the position, so
  // the fixture stops being drawn as a guess. Stored positions only: no DMX.
  const [moveMode, setMoveMode] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [snapOn, setSnapOn] = useState(true);
  const [moveNotice, setMoveNotice] = useState<{ severity: 'success' | 'error' | 'info'; text: string } | null>(null);
  const rigRef = useRef<Rig | null>(null);
  rigRef.current = rig;
  // The newest save of each fixture. An older answer that lands late is dropped.
  const saveSeq = useRef<Record<number, number>>({});
  const saveChain = useRef<Record<number, Promise<unknown>>>({});

  useEffect(() => {
    setMoveMode(false);
    setSelectedId(null);
    setMoveNotice(null);
  }, [id]);

  // Read the rig again without the loading flag, which would swap the page
  // for a line of text and throw the canvas away.
  const refreshRig = useCallback(async () => {
    if (!id) return;
    try {
      const data = await rigsApi.get(Number(id));
      if (rigRef.current && rigRef.current.id !== data.id) return;
      setRig(data);
    } catch {
      setMoveNotice({ severity: 'error', text: 'The rig could not be read again. Reload the page to see it as stored.' });
    }
  }, [id]);

  const moveFixture = useCallback(async (fixtureId: number, to: Point3) => {
    const current = rigRef.current;
    const fixture = current?.fixtures?.find((item) => item.id === fixtureId);
    if (!id || !current || !fixture) return;
    const rigId = current.id;
    const label = fixture.name || `Fixture ${fixtureId}`;
    const before: Point3 = { x: fixture.position_x, y: fixture.position_y, z: fixture.position_z };
    const seq = (saveSeq.current[fixtureId] ?? 0) + 1;
    saveSeq.current[fixtureId] = seq;
    const newest = () => saveSeq.current[fixtureId] === seq && rigRef.current?.id === rigId;
    // Drawn where it was put straight away; the server's answer follows.
    setRig((drawn) => (drawn ? withFixturePosition(drawn, fixtureId, to) : drawn));
    try {
      // One fixture's saves go to the server one after another, in the order
      // they were made: a held nudge key must not leave an earlier position
      // stored after a later one.
      const earlier = saveChain.current[fixtureId] ?? Promise.resolve();
      const request = earlier.catch(() => undefined).then(() => rigsApi.setFixturePosition(rigId, fixtureId, to));
      saveChain.current[fixtureId] = request;
      const saved = await request;
      if (!newest()) return;
      setRig((drawn) => (drawn ? withSavedFixture(drawn, saved) : drawn));
      setMoveNotice({
        severity: 'success',
        text: `${label} moved to ${positionText({
          x: saved.position_x, y: saved.position_y, z: saved.position_z,
        })}. Its position is confirmed.`,
      });
    } catch (error) {
      if (!newest()) return;
      setRig((drawn) => (drawn ? withFixturePosition(drawn, fixtureId, before) : drawn));
      const detail = (error as any)?.response?.data?.detail;
      setMoveNotice({
        severity: 'error',
        text: typeof detail === 'string' && detail.trim()
          ? detail
          : `${label} could not be saved and was put back where it was.`,
      });
    }
  }, [id]);

  // Arrow keys move the selected fixture on the plan, Page Up and Page Down
  // change its height; Shift takes a metre at a time.
  useEffect(() => {
    if (!moveMode || selectedId === null) return undefined;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      // Keys meant for a field, a dropdown, a menu or a dialog are theirs:
      // arrowing through the audio device list must not move a fixture.
      if (target?.closest?.(
        'input,textarea,select,[contenteditable="true"],[role="combobox"],[role="listbox"],[role="menu"],[role="dialog"]',
      )) return;
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const current = rigRef.current;
      const fixture = current?.fixtures?.find((item) => item.id === selectedId);
      if (!current || !fixture) return;
      const next = nudgePosition(
        { x: fixture.position_x, y: fixture.position_y, z: fixture.position_z },
        event.key,
        event.shiftKey,
        positionLimits(current),
      );
      if (!next) return;
      event.preventDefault();
      void moveFixture(selectedId, next);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [moveMode, selectedId, moveFixture]);

  const sceneMove = useMemo(
    () => (moveMode && !isDemo
      ? {
          selectedId,
          snap: snapOn,
          onSelect: setSelectedId,
          onMove: (fixtureId: number, to: Point3) => { void moveFixture(fixtureId, to); },
        }
      : null),
    [moveMode, isDemo, selectedId, snapOn, moveFixture]
  );
  const canSnap = useMemo(() => snapLines(rig?.room_shell).length > 0, [rig?.room_shell]);

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
        {/* Hidden once a patched rig is drawn: a demo rig cannot go over it. */}
        {isDemo && rig.id === 0 && demoPresets.length > 0 && (
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
          <Tooltip describeChild title="Cast shadows from the brightest few beams. Costs frame time; off by default.">
            <Button
              variant={shadows ? 'contained' : 'outlined'}
              aria-pressed={shadows}
              onClick={() => setShadows(!shadows)}
            >
              Shadows
            </Button>
          </Tooltip>
          <Tooltip describeChild title="Show frame rate, frame time, draw calls and triangles (also on window.__previzStats)">
            <Button
              variant={showStats ? 'contained' : 'outlined'}
              aria-pressed={showStats}
              onClick={() => setShowStats(!showStats)}
            >
              Stats
            </Button>
          </Tooltip>
          <Tooltip describeChild title="Show the beam debug table: what each fixture is sent and how it is drawn">
            <Button
              variant={showDebug ? 'contained' : 'outlined'}
              aria-pressed={showDebug}
              onClick={() => setShowDebug((on) => !on)}
            >
              Debug
            </Button>
          </Tooltip>
        </ButtonGroup>
        <LookControls settings={lookSettings} onChange={changeLook} />
        <StagePlot3dToggle status={stagePlot.status} on={stagePlot.on} onChange={stagePlot.setOn} />
        <FocusTargets3dToggle available={focusTargets.available} on={focusTargets.on} onChange={focusTargets.setOn} />
        {/* The rig on screen, written out for a desk or a visualiser. */}
        {isDemo ? (
          rig.venue && demoPresets.some((d) => d.name === rig.venue) && (
            <ConsoleExportButton target={{ preset: rig.venue }} />
          )
        ) : (
          <ConsoleExportButton target={{ rigId: rig.id }} />
        )}
        {!isDemo && (
          <ButtonGroup size="small" variant="outlined">
            <Tooltip
              describeChild
              title="Drag a fixture to where it really is. Shift-drag changes its height. Saving confirms the position."
            >
              <Button
                variant={moveMode ? 'contained' : 'outlined'}
                aria-pressed={moveMode}
                onClick={() => setMoveMode((on) => !on)}
              >
                Move fixtures
              </Button>
            </Tooltip>
            {moveMode && canSnap && (
              <Tooltip
                describeChild
                title="Snap a dragged fixture to the nearest scanned truss line or stage edge. Hold Alt to let go of it for one drag."
              >
                <Button
                  variant={snapOn ? 'contained' : 'outlined'}
                  aria-pressed={snapOn}
                  onClick={() => setSnapOn((on) => !on)}
                >
                  Snap
                </Button>
              </Tooltip>
            )}
          </ButtonGroup>
        )}
        {!isDemo && (
          <RoomScanUndoButton
            rigId={rig.id}
            moves={undoCount(rig)}
            size="small"
            onDone={(result) => {
              setMoveNotice({ severity: result.skipped > 0 ? 'info' : 'success', text: undoResultText(result) });
              void refreshRig();
            }}
          />
        )}
      </Box>

      {moveNotice && (
        <Alert severity={moveNotice.severity} onClose={() => setMoveNotice(null)} sx={{ mb: 1, py: 0 }}>
          {moveNotice.text}
        </Alert>
      )}

      {/* Audio Device Chooser */}
      <Box sx={{ mb: 1, display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
        <AudioDeviceChooser />
        <FeedReadout
          feed={outputFeed}
          guessCount={(rig.fixtures || []).filter(isPositionUnconfirmed).length}
        />
        <SectionReadout />
      </Box>

      {/* 3D Canvas */}
      <Box sx={{ flexGrow: 1, bgcolor: '#000', borderRadius: 2, overflow: 'hidden', position: 'relative' }}>
        {showStats && <StatsOverlay sink={statsSink} />}
        <Canvas
          shadows={shadows}
          gl={{
            antialias: true,
            // Ask for the discrete GPU on a laptop or desktop that also has an
            // integrated one; the browser may still decide otherwise.
            powerPreference: 'high-performance',
            toneMapping: THREE.ACESFilmicToneMapping,
            toneMappingExposure: qualityMode === 'ultra' ? 1.32 : 1.2,
          }}
          dpr={previzDpr(qualityMode, typeof window === 'undefined' ? 1 : window.devicePixelRatio)}
        >
          <Scene
            rig={rig}
            debugBuffer={beamDebugBuffer}
            cameraMode={cameraMode}
            qualityMode={qualityMode}
            showVenue={showVenue}
            showLabels={showLabels}
            shadows={shadows}
            beatClock={beatClock}
            feed={outputFeed}
            debug={showDebug}
            move={sceneMove}
            stagePlot={stagePlot.floor}
            focusTargets={focusTargets.markers}
            lookSettings={lookSettings}
          />
          <StatsSampler sink={statsSink} />
        </Canvas>
      </Box>

      {/* Beam debug overlay to separate control jitter from render jitter */}
      {showDebug && <BeamDebugOverlay buffer={beamDebugBuffer} />}

      {/* Info Panel */}
      <Card sx={{ mt: 2 }}>
        <CardContent sx={{ py: 1 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2">
              Stage: {rig.stage_width}m x {rig.stage_depth}m x {rig.stage_height}m |
              Fixtures: {rig.fixtures?.length || 0} |
              {moveMode
                ? 'Drag a fixture to move it along the floor plan, Shift-drag for height, Alt to skip the snap, Esc to cancel. '
                  + 'Arrow keys and Page Up/Down nudge the selected fixture (Shift: 1 m).'
                : 'Use mouse to rotate, scroll to zoom, right-click to pan'}
            </Typography>
            <EffectsReadout />
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
