import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Box, IconButton, Typography, Card, CardContent } from '@mui/material';
import { ArrowBack as BackIcon } from '@mui/icons-material';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, Grid, PerspectiveCamera } from '@react-three/drei';
import * as THREE from 'three';
import { rigsApi } from '../../services/api';
import type { Rig, RigFixture } from '../../types';
import { useDMXStore } from '../../stores/dmxStore';

// Fixture 3D component
function Fixture3D({
  fixture,
  dmxData,
}: {
  fixture: RigFixture;
  dmxData: number[];
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const lightRef = useRef<THREE.SpotLight>(null);
  const [intensity, setIntensity] = useState(0);
  const [color, setColor] = useState(new THREE.Color(1, 1, 1));

  useFrame(() => {
    // Get DMX values for this fixture using correct channel mapping
    // Mover/Wash channel layout: Pan(0), PanFine(1), Tilt(2), TiltFine(3), Speed(4),
    //                           Dimmer(5), Shutter(6), R(7), G(8), B(9), W(10)
    const baseAddr = fixture.dmx_address - 1;

    // Check if this is a mover/wash (16ch) or LED bar (12ch)
    const isMover = fixture.dmx_address < 213;

    let dimmer, red, green, blue, pan, tilt;

    if (isMover) {
      // Mover/Wash fixture channel mapping
      pan = dmxData[baseAddr] || 128;       // Channel 0: Pan
      tilt = dmxData[baseAddr + 2] || 128;  // Channel 2: Tilt
      dimmer = (dmxData[baseAddr + 5] || 0) / 255;  // Channel 5: Dimmer
      red = (dmxData[baseAddr + 7] || 0) / 255;     // Channel 7: Red
      green = (dmxData[baseAddr + 8] || 0) / 255;   // Channel 8: Green
      blue = (dmxData[baseAddr + 9] || 0) / 255;    // Channel 9: Blue
    } else {
      // LED Bar channel mapping: Dimmer(0), Strobe(1), R(2), G(3), B(4)
      dimmer = (dmxData[baseAddr] || 0) / 255;
      red = (dmxData[baseAddr + 2] || 0) / 255;
      green = (dmxData[baseAddr + 3] || 0) / 255;
      blue = (dmxData[baseAddr + 4] || 0) / 255;
      pan = 128;
      tilt = 128;
    }

    setIntensity(dimmer);
    setColor(new THREE.Color(red, green, blue));

    // Apply rotation for moving heads
    if (meshRef.current && isMover) {
      // Convert pan from 0-255 to radians (-π to π)
      const panRad = (pan / 255) * Math.PI * 2 - Math.PI;
      // Convert tilt from 0-255 to radians (-π/2 to π/2)
      const tiltRad = (tilt / 255) * Math.PI - Math.PI / 2;
      meshRef.current.rotation.y = panRad;
      meshRef.current.rotation.x = tiltRad;
    }
  });

  return (
    <group position={[fixture.position_x, fixture.position_y, fixture.position_z]}>
      {/* Fixture body */}
      <mesh ref={meshRef}>
        <boxGeometry args={[0.3, 0.3, 0.4]} />
        <meshStandardMaterial color="#333" metalness={0.8} roughness={0.2} />
      </mesh>

      {/* Lens glow */}
      <mesh position={[0, -0.15, 0]}>
        <cylinderGeometry args={[0.1, 0.12, 0.05, 16]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={intensity * 2}
        />
      </mesh>

      {/* Spotlight beam (visible cone) */}
      {intensity > 0.1 && (
        <spotLight
          ref={lightRef}
          position={[0, -0.2, 0]}
          angle={0.3}
          penumbra={0.5}
          intensity={intensity * 10}
          color={color}
          castShadow
          target-position={[fixture.position_x, 0, fixture.position_z]}
        />
      )}

      {/* Label */}
      <Html position={[0, 0.3, 0]}>
        <div
          style={{
            background: 'rgba(0,0,0,0.7)',
            color: 'white',
            padding: '2px 6px',
            borderRadius: '4px',
            fontSize: '10px',
            whiteSpace: 'nowrap',
          }}
        >
          {fixture.name || `#${fixture.dmx_address}`}
        </div>
      </Html>
    </group>
  );
}

// Simple HTML component for labels in 3D
function Html({ children, position }: { children: React.ReactNode; position: [number, number, number] }) {
  const { camera, size } = useThree();
  const ref = useRef<HTMLDivElement>(null);

  useFrame(() => {
    if (ref.current) {
      const vec = new THREE.Vector3(...position);
      vec.project(camera);
      const x = (vec.x * 0.5 + 0.5) * size.width;
      const y = (-vec.y * 0.5 + 0.5) * size.height;
      ref.current.style.transform = `translate(-50%, -50%) translate(${x}px, ${y}px)`;
    }
  });

  return (
    <div
      ref={ref}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        pointerEvents: 'none',
      }}
    >
      {children}
    </div>
  );
}

// Stage floor component
function Stage({ width, depth }: { width: number; depth: number }) {
  return (
    <group>
      {/* Stage floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow>
        <planeGeometry args={[width, depth]} />
        <meshStandardMaterial color="#1a1a1a" />
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
    </group>
  );
}

// Truss component
function Truss({ width, height, depth }: { width: number; height: number; depth: number }) {
  return (
    <group position={[0, height, 0]}>
      {/* Front truss */}
      <mesh position={[0, 0, -depth / 2 + 0.5]}>
        <boxGeometry args={[width, 0.15, 0.15]} />
        <meshStandardMaterial color="#555" metalness={0.8} />
      </mesh>

      {/* Back truss */}
      <mesh position={[0, 0, depth / 2 - 0.5]}>
        <boxGeometry args={[width, 0.15, 0.15]} />
        <meshStandardMaterial color="#555" metalness={0.8} />
      </mesh>

      {/* Side trusses */}
      <mesh position={[-width / 2 + 0.5, 0, 0]}>
        <boxGeometry args={[0.15, 0.15, depth]} />
        <meshStandardMaterial color="#555" metalness={0.8} />
      </mesh>
      <mesh position={[width / 2 - 0.5, 0, 0]}>
        <boxGeometry args={[0.15, 0.15, depth]} />
        <meshStandardMaterial color="#555" metalness={0.8} />
      </mesh>
    </group>
  );
}

// Main scene component
function Scene({ rig }: { rig: Rig }) {
  const dmxData = useDMXStore((state) => {
    const universeData = state.universes.get(0);
    return universeData || new Array(512).fill(0);
  });

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

      <ambientLight intensity={0.1} />
      <pointLight position={[10, 10, 10]} intensity={0.5} />

      <Stage width={rig.stage_width} depth={rig.stage_depth} />
      <Truss
        width={rig.stage_width - 1}
        height={rig.stage_height - 1}
        depth={rig.stage_depth - 1}
      />

      {rig.fixtures?.map((fixture) => (
        <Fixture3D key={fixture.id} fixture={fixture} dmxData={dmxData} />
      ))}

      <fog attach="fog" args={['#000', 10, 50]} />
    </>
  );
}

export default function RigVisualizer() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [rig, setRig] = useState<Rig | null>(null);
  const [loading, setLoading] = useState(true);

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
      </Box>

      {/* 3D Canvas */}
      <Box sx={{ flexGrow: 1, bgcolor: '#000', borderRadius: 2, overflow: 'hidden' }}>
        <Canvas shadows>
          <Scene rig={rig} />
        </Canvas>
      </Box>

      {/* Info Panel */}
      <Card sx={{ mt: 2 }}>
        <CardContent sx={{ py: 1 }}>
          <Typography variant="body2">
            Stage: {rig.stage_width}m x {rig.stage_depth}m x {rig.stage_height}m |
            Fixtures: {rig.fixtures?.length || 0} |
            Use mouse to rotate, scroll to zoom, right-click to pan
          </Typography>
        </CardContent>
      </Card>
    </Box>
  );
}
