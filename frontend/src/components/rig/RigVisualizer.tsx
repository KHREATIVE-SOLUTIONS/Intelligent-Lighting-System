import { useState, useEffect, useRef, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Box, IconButton, Typography, Card, CardContent } from '@mui/material';
import { ArrowBack as BackIcon } from '@mui/icons-material';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Grid, PerspectiveCamera } from '@react-three/drei';
import * as THREE from 'three';
import { rigsApi } from '../../services/api';
import type { Rig, RigFixture } from '../../types';
import { useDMXStore } from '../../stores/dmxStore';

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
    float alpha = falloff * beamIntensity * 0.2;
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

  for (const ch of mode.channels) {
    map[ch.channel_type] = ch.channel_number - 1;
  }
  return map;
}

// ============================================================================
// VOLUMETRIC BEAM COMPONENT
// ============================================================================

function BeamCone({
  color,
  intensity,
  beamAngle,
  beamLength,
}: {
  color: THREE.Color;
  intensity: number;
  beamAngle: number;
  beamLength: number;
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

  if (intensity < 0.05) return null;

  return (
    <mesh position={[0, -beamLength / 2, 0]}>
      <coneGeometry args={[topRadius, beamLength, 16, 1, true]} />
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
  fixtureIndex,
}: {
  fixture: RigFixture;
  dmxData: number[];
  fixtureIndex: number;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const headRef = useRef<THREE.Group>(null);
  const lensRef = useRef<THREE.Mesh>(null);
  const spotRef = useRef<THREE.SpotLight>(null);

  const channelMapRef = useRef(buildChannelMap(fixture));

  // Smoothed values to avoid jitter
  const smoothed = useRef({ intensity: 0, r: 1, g: 1, b: 1, pan: 0, tilt: 0 });

  const beamAngle = fixture.fixture?.beam_angle || 25;
  const fixtureType = fixture.fixture?.fixture_type || 'other';
  const isMovingHead = fixtureType === 'moving_head' || fixtureType === 'spot' || fixtureType === 'beam';

  // Beam length scales with fixture height (fixtures on truss beam to floor)
  const beamLength = fixture.position_y > 0 ? fixture.position_y : 3;

  const [beamColor] = useState(() => new THREE.Color(1, 1, 1));
  const [beamIntensity, setBeamIntensity] = useState(0);

  useFrame((_, delta) => {
    const baseAddr = fixture.dmx_address - 1;
    const chMap = channelMapRef.current;
    const lerp = Math.min(1, delta * 15); // Smooth factor

    // Read DMX values
    const rawDimmer = chMap.dimmer !== undefined
      ? (dmxData[baseAddr + chMap.dimmer] || 0) / 255
      : 1;
    const rawR = chMap.red !== undefined
      ? (dmxData[baseAddr + chMap.red] || 0) / 255
      : 1;
    const rawG = chMap.green !== undefined
      ? (dmxData[baseAddr + chMap.green] || 0) / 255
      : 1;
    const rawB = chMap.blue !== undefined
      ? (dmxData[baseAddr + chMap.blue] || 0) / 255
      : 1;
    const rawPan = chMap.pan !== undefined
      ? dmxData[baseAddr + chMap.pan] || 128
      : 128;
    const rawTilt = chMap.tilt !== undefined
      ? dmxData[baseAddr + chMap.tilt] || 128
      : 128;
    const strobe = chMap.strobe !== undefined
      ? (dmxData[baseAddr + chMap.strobe] || 0) / 255
      : 0;
    const zoom = chMap.zoom !== undefined
      ? (dmxData[baseAddr + chMap.zoom] || 128) / 255
      : 0.5;

    // Smooth interpolation
    const s = smoothed.current;
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

    // Update beam color
    beamColor.setRGB(s.r, s.g, s.b);
    setBeamIntensity(effectiveIntensity);

    // Update lens glow emissive
    if (lensRef.current) {
      const lensMat = lensRef.current.material as THREE.MeshStandardMaterial;
      lensMat.emissive.setRGB(s.r, s.g, s.b);
      lensMat.emissiveIntensity = effectiveIntensity * 3;
      lensMat.color.setRGB(s.r * 0.5, s.g * 0.5, s.b * 0.5);
    }

    // Update spotlight for floor projection
    if (spotRef.current) {
      spotRef.current.color.setRGB(s.r, s.g, s.b);
      spotRef.current.intensity = effectiveIntensity * 8;
      spotRef.current.angle = 0.15 + zoom * 0.4; // Narrower to wider with zoom
    }

    // Pan/tilt for moving heads
    if (headRef.current && isMovingHead) {
      const panRange = fixture.fixture?.pan_range || 540;
      const tiltRange = fixture.fixture?.tilt_range || 270;
      const targetPan = (rawPan / 255) * (panRange * Math.PI / 180) - (panRange * Math.PI / 360);
      const targetTilt = (rawTilt / 255) * (tiltRange * Math.PI / 180) - (tiltRange * Math.PI / 360);

      s.pan += (targetPan - s.pan) * lerp;
      s.tilt += (targetTilt - s.tilt) * lerp;

      headRef.current.rotation.y = s.pan;
      headRef.current.rotation.x = s.tilt;
    }
  });

  // Fixture body geometry based on type
  const bodyGeometry = useMemo(() => {
    switch (fixtureType) {
      case 'moving_head':
      case 'spot':
      case 'beam':
        return <boxGeometry args={[0.25, 0.35, 0.3]} />;
      case 'led_par':
      case 'wash':
        return <cylinderGeometry args={[0.15, 0.18, 0.2, 8]} />;
      case 'led_bar':
        return <boxGeometry args={[0.8, 0.1, 0.15]} />;
      case 'strobe':
        return <boxGeometry args={[0.3, 0.1, 0.15]} />;
      default:
        return <boxGeometry args={[0.2, 0.2, 0.2]} />;
    }
  }, [fixtureType]);

  // SpotLight target position
  const targetPos = useMemo(
    () => new THREE.Vector3(fixture.position_x, 0, fixture.position_z),
    [fixture.position_x, fixture.position_z]
  );

  return (
    <group ref={groupRef} position={[fixture.position_x, fixture.position_y, fixture.position_z]}>
      {/* Head group (rotates for moving heads) */}
      <group ref={headRef}>
        {/* Fixture body */}
        <mesh castShadow>
          {bodyGeometry}
          <meshStandardMaterial color="#2a2a2a" metalness={0.9} roughness={0.15} />
        </mesh>

        {/* Lens */}
        <mesh ref={lensRef} position={[0, -0.18, 0]}>
          <cylinderGeometry args={[0.08, 0.1, 0.04, 16]} />
          <meshStandardMaterial
            color="#111"
            emissive={beamColor}
            emissiveIntensity={beamIntensity * 3}
            toneMapped={false}
          />
        </mesh>

        {/* Volumetric beam cone */}
        <BeamCone
          color={beamColor}
          intensity={beamIntensity}
          beamAngle={beamAngle}
          beamLength={beamLength}
        />

        {/* SpotLight for floor color projection (only first 16 fixtures for performance) */}
        {fixtureIndex < 16 && beamIntensity > 0.1 && (
          <>
            <spotLight
              ref={spotRef}
              position={[0, -0.2, 0]}
              angle={0.3}
              penumbra={0.6}
              intensity={beamIntensity * 8}
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

      {/* Yoke (static, visible for moving heads) */}
      {isMovingHead && (
        <mesh position={[0, 0.2, 0]}>
          <boxGeometry args={[0.05, 0.15, 0.3]} />
          <meshStandardMaterial color="#333" metalness={0.8} roughness={0.2} />
        </mesh>
      )}
    </group>
  );
}

// ============================================================================
// STAGE FLOOR WITH KEY LIGHTING ZONES
// ============================================================================

function Stage({
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

      {/* Key lighting zone highlights on stage floor */}
      {keyZones
        .filter((z) => z.active && ZONE_POSITIONS[z.zone])
        .map((zone) => {
          const pos = ZONE_POSITIONS[zone.zone];
          const worldX = pos.x * width;
          const worldZ = pos.z * depth;
          const zoneColor = new THREE.Color(
            zone.color.r / 255,
            zone.color.g / 255,
            zone.color.b / 255
          );
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
                emissiveIntensity={zone.intensity * 0.5}
                transparent
                opacity={zone.intensity * 0.3}
              />
            </mesh>
          );
        })}
    </group>
  );
}

// ============================================================================
// TRUSS COMPONENT (CYLINDRICAL TRUSS ELEMENTS)
// ============================================================================

function Truss({ width, height, depth }: { width: number; height: number; depth: number }) {
  // Truss chord parameters
  const chordRadius = 0.025;
  const segments = 8;

  return (
    <group position={[0, height, 0]}>
      {/* Front truss - main chord */}
      <mesh position={[0, 0, -depth / 2 + 0.5]}>
        <cylinderGeometry args={[chordRadius, chordRadius, width, segments]} />
        <meshStandardMaterial color="#666" metalness={0.9} roughness={0.15} />
      </mesh>
      {/* Front truss - bottom chord */}
      <mesh position={[0, -0.12, -depth / 2 + 0.5]}>
        <cylinderGeometry args={[chordRadius, chordRadius, width, segments]} />
        <meshStandardMaterial color="#666" metalness={0.9} roughness={0.15} />
      </mesh>
      {/* Rotate cylinders to be horizontal */}
      <group rotation={[0, 0, Math.PI / 2]}>
        {/* (Note: cylinder default axis is Y, rotated to X for horizontal) */}
      </group>

      {/* Back truss */}
      <mesh position={[0, 0, depth / 2 - 0.5]}>
        <cylinderGeometry args={[chordRadius, chordRadius, width, segments]} />
        <meshStandardMaterial color="#666" metalness={0.9} roughness={0.15} />
      </mesh>
      <mesh position={[0, -0.12, depth / 2 - 0.5]}>
        <cylinderGeometry args={[chordRadius, chordRadius, width, segments]} />
        <meshStandardMaterial color="#666" metalness={0.9} roughness={0.15} />
      </mesh>

      {/* Side trusses */}
      <mesh position={[-width / 2 + 0.5, 0, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[chordRadius, chordRadius, depth, segments]} />
        <meshStandardMaterial color="#666" metalness={0.9} roughness={0.15} />
      </mesh>
      <mesh position={[width / 2 - 0.5, 0, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[chordRadius, chordRadius, depth, segments]} />
        <meshStandardMaterial color="#666" metalness={0.9} roughness={0.15} />
      </mesh>

      {/* Vertical support legs (4 corners) */}
      {[
        [-width / 2 + 0.5, -depth / 2 + 0.5],
        [width / 2 - 0.5, -depth / 2 + 0.5],
        [-width / 2 + 0.5, depth / 2 - 0.5],
        [width / 2 - 0.5, depth / 2 - 0.5],
      ].map(([x, z], i) => (
        <mesh key={i} position={[x, -height / 2, z]}>
          <cylinderGeometry args={[0.04, 0.04, height, 6]} />
          <meshStandardMaterial color="#555" metalness={0.8} roughness={0.2} />
        </mesh>
      ))}

      {/* Cross braces on front truss (diagonal elements) */}
      {Array.from({ length: Math.floor(width / 1.5) }, (_, i) => {
        const x = -width / 2 + 1 + i * 1.5;
        return (
          <group key={`brace-${i}`} position={[x, -0.06, -depth / 2 + 0.5]}>
            <mesh rotation={[0, 0, Math.PI / 4]}>
              <cylinderGeometry args={[0.01, 0.01, 0.2, 4]} />
              <meshStandardMaterial color="#555" metalness={0.8} roughness={0.3} />
            </mesh>
          </group>
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

// ============================================================================
// MAIN SCENE COMPONENT
// ============================================================================

function Scene({ rig }: { rig: Rig }) {
  const dmxData = useDMXStore((state) => {
    const universeData = state.universes.get(0);
    return universeData || new Array(512).fill(0);
  });
  const keyLightingZones = useDMXStore((state) => state.proLighting.keyLightingZones);

  return (
    <>
      <PerspectiveCamera makeDefault position={[0, 8, 15]} fov={50} />
      <OrbitControls
        enablePan
        enableZoom
        enableRotate
        target={[0, rig.stage_height / 2, 0]}
        maxPolarAngle={Math.PI / 2}
      />

      {/* Minimal ambient - let beams and spots be the light sources */}
      <ambientLight intensity={0.03} />

      {/* Stage environment */}
      <Stage
        width={rig.stage_width}
        depth={rig.stage_depth}
        keyZones={keyLightingZones}
      />
      <Truss
        width={rig.stage_width - 1}
        height={rig.stage_height - 1}
        depth={rig.stage_depth - 1}
      />

      {/* Haze particles for atmospheric effect */}
      <HazeParticles
        count={200}
        spread={[rig.stage_width, rig.stage_height, rig.stage_depth]}
      />

      {/* Fixtures */}
      {rig.fixtures?.map((fixture, index) => (
        <Fixture3D
          key={fixture.id}
          fixture={fixture}
          dmxData={dmxData}
          fixtureIndex={index}
        />
      ))}

      {/* Exponential fog for haze effect */}
      <fogExp2 attach="fog" args={['#000000', 0.025]} />
    </>
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
  const proLighting = useDMXStore((state) => state.proLighting);

  useEffect(() => {
    if (id) {
      fetchRig(Number(id));
    }
  }, [id]);

  const fetchRig = async (rigId: number) => {
    setLoading(true);
    try {
      const data = await rigsApi.get(rigId);
      setRig(data);
    } catch (error) {
      console.error('Failed to fetch rig:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <Typography>Loading...</Typography>;
  }

  if (!rig) {
    return <Typography>Rig not found</Typography>;
  }

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2, gap: 2 }}>
        <IconButton onClick={() => navigate(`/rigs/${rig.id}`)}>
          <BackIcon />
        </IconButton>
        <Typography variant="h5">{rig.name} - 3D View</Typography>
        {proLighting.genre && (
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
              {proLighting.genre}
            </Typography>
            <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
              {proLighting.section}
            </Typography>
            <Box
              sx={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                bgcolor: proLighting.sectionIntensity > 0.7
                  ? 'error.main'
                  : proLighting.sectionIntensity > 0.4
                    ? 'warning.main'
                    : 'success.main',
              }}
            />
          </Box>
        )}
      </Box>

      {/* 3D Canvas */}
      <Box sx={{ flexGrow: 1, bgcolor: '#000', borderRadius: 2, overflow: 'hidden' }}>
        <Canvas
          shadows
          gl={{
            antialias: true,
            toneMapping: THREE.ACESFilmicToneMapping,
            toneMappingExposure: 1.2,
          }}
          dpr={[1, 1.5]}
        >
          <Scene rig={rig} />
        </Canvas>
      </Box>

      {/* Info Panel */}
      <Card sx={{ mt: 2 }}>
        <CardContent sx={{ py: 1 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="body2">
              Stage: {rig.stage_width}m x {rig.stage_depth}m x {rig.stage_height}m |
              Fixtures: {rig.fixtures?.length || 0} |
              Use mouse to rotate, scroll to zoom, right-click to pan
            </Typography>
            <Box sx={{ display: 'flex', gap: 2 }}>
              {proLighting.activeEffects.strobeMode !== 'off' && (
                <Typography variant="body2" color="warning.main">
                  Strobe: {proLighting.activeEffects.strobeMode}
                </Typography>
              )}
              {proLighting.activeEffects.movementType !== 'none' && (
                <Typography variant="body2" color="info.main">
                  Movement: {proLighting.activeEffects.movementType.replace(/_/g, ' ')}
                </Typography>
              )}
              {proLighting.activeEffects.chaseType !== 'off' && (
                <Typography variant="body2" color="success.main">
                  Chase: {proLighting.activeEffects.chaseType.replace(/_/g, ' ')}
                </Typography>
              )}
            </Box>
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
