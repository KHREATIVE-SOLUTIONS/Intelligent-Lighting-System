/**
 * The club itself: floor, dance floor, walls and ceiling.
 *
 * The room is a closed box, which would hide the rig from every camera outside
 * it. So each wall and the ceiling is drawn only while the camera is on its
 * inner side: from inside you are in a room, from outside you look straight in.
 */
import { memo, useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { box, cylZ, merge, paint, place } from './geometryKit';
import type { ClubLayout } from './layout';
import { glossMaterial, glowMaterial, mattMaterial } from './materials';

const FLOOR = '#3c3d45';
const WALL_A = '#50525d';
const WALL_B = '#454751';
const WALL_SEAM = '#26272d';
const SKIRTING = '#24252b';
const PILASTER = '#5c5f6b';
const CEILING = '#2a2b31';
const BEAM = '#3a3c44';
const DUCT = '#666a75';
const TILE_A = '#5a5c68';
const TILE_B = '#474953';
const GROUT = '#17171b';
const TRIM = '#7b808b';
const EDGE_GLOW = '#2a3aa8';
const BAR_GLOW = '#a35a1c';

/** A flat quad in the XZ plane facing up. */
function slab(width: number, depth: number): THREE.BufferGeometry {
  return new THREE.PlaneGeometry(width, depth).rotateX(-Math.PI / 2);
}

/** A quad in the XY plane facing +Z. */
function panel(width: number, height: number): THREE.BufferGeometry {
  return new THREE.PlaneGeometry(width, height);
}

/**
 * One wall, modelled standing on y = 0 in the XY plane and facing +Z, centred
 * on x = 0. Panels in two close shades with a pilaster on every other seam,
 * so a plain dark surface still shows its depth and its scale.
 */
export function buildWall(length: number, height: number): THREE.BufferGeometry {
  const parts: THREE.BufferGeometry[] = [
    paint(place(panel(length, height), [0, height / 2, 0]), WALL_SEAM),
    paint(place(box(length, 0.28, 0.04), [0, 0.14, 0.02]), SKIRTING),
  ];
  const count = Math.max(2, Math.round(length / 1.5));
  const each = length / count;
  for (let i = 0; i < count; i += 1) {
    const x = -length / 2 + each * (i + 0.5);
    parts.push(paint(place(panel(each - 0.03, height - 0.3), [x, 0.29 + (height - 0.3) / 2, 0.012]), i % 2 ? WALL_A : WALL_B));
    if (i > 0 && i % 2 === 0) {
      parts.push(paint(place(box(0.12, height, 0.07), [x - each / 2, height / 2, 0.035]), PILASTER));
    }
  }
  return merge(parts);
}

function buildFloor(layout: ClubLayout): THREE.BufferGeometry {
  const length = layout.houseZ - layout.backZ;
  return merge([
    paint(place(slab(layout.wallX * 2, length), [0, 0, (layout.backZ + layout.houseZ) / 2]), FLOOR),
  ]);
}

function buildDanceFloor(layout: ClubLayout): { tiles: THREE.BufferGeometry; glow: THREE.BufferGeometry } {
  const { xMin, xMax, zMin, zMax } = layout.danceFloor;
  const width = xMax - xMin;
  const depth = zMax - zMin;
  const cx = (xMin + xMax) / 2;
  const cz = (zMin + zMax) / 2;

  const tiles: THREE.BufferGeometry[] = [paint(place(slab(width, depth), [cx, 0.004, cz]), GROUT)];
  const nx = Math.max(2, Math.round(width / 0.6));
  const nz = Math.max(2, Math.round(depth / 0.6));
  const tw = width / nx;
  const td = depth / nz;
  for (let i = 0; i < nx; i += 1) {
    for (let j = 0; j < nz; j += 1) {
      tiles.push(paint(
        place(slab(tw - 0.012, td - 0.012), [xMin + tw * (i + 0.5), 0.008, zMin + td * (j + 0.5)]),
        (i + j) % 2 ? TILE_A : TILE_B,
      ));
    }
  }
  // Metal trim round the edge.
  tiles.push(
    paint(place(box(width + 0.1, 0.014, 0.05), [cx, 0.007, zMin - 0.025]), TRIM),
    paint(place(box(width + 0.1, 0.014, 0.05), [cx, 0.007, zMax + 0.025]), TRIM),
    paint(place(box(0.05, 0.014, depth), [xMin - 0.025, 0.007, cz]), TRIM),
    paint(place(box(0.05, 0.014, depth), [xMax + 0.025, 0.007, cz]), TRIM),
  );

  // A thin lit strip just inside the trim.
  const glow = merge([
    paint(place(slab(width - 0.06, 0.022), [cx, 0.016, zMin + 0.03]), EDGE_GLOW),
    paint(place(slab(width - 0.06, 0.022), [cx, 0.016, zMax - 0.03]), EDGE_GLOW),
    paint(place(slab(0.022, depth - 0.06), [xMin + 0.03, 0.016, cz]), EDGE_GLOW),
    paint(place(slab(0.022, depth - 0.06), [xMax - 0.03, 0.016, cz]), EDGE_GLOW),
  ]);

  return { tiles: merge(tiles), glow };
}

/** Ceiling, modelled hanging from y = 0. */
function buildCeiling(layout: ClubLayout): THREE.BufferGeometry {
  const length = layout.houseZ - layout.backZ;
  const cz = (layout.backZ + layout.houseZ) / 2;
  const parts: THREE.BufferGeometry[] = [
    paint(place(slab(layout.wallX * 2, length).rotateX(Math.PI), [0, 0, cz]), CEILING),
  ];
  const beams = Math.max(2, Math.round(length / 2.4));
  for (let i = 0; i <= beams; i += 1) {
    const z = layout.backZ + (length * i) / beams;
    parts.push(paint(place(box(layout.wallX * 2, 0.2, 0.16), [0, -0.1, z]), BEAM));
  }
  // An air duct down one side.
  parts.push(paint(place(cylZ(0.15, length * 0.86, 14), [-layout.wallX * 0.66, -0.18, cz]), DUCT));
  return merge(parts);
}

/** Bar counter and door on the rear-of-house wall, modelled like a wall. */
function buildHouseDressing(length: number): { solid: THREE.BufferGeometry; glow: THREE.BufferGeometry } {
  const barWidth = Math.min(4.5, length * 0.42);
  const barX = -length / 2 + barWidth / 2 + 0.5;
  const doorX = length / 2 - 1.3;
  const solid = merge([
    // Counter, with shelves behind it.
    paint(place(box(barWidth, 1.08, 0.55), [barX, 0.54, 0.9]), '#1a1b20'),
    paint(place(box(barWidth + 0.06, 0.05, 0.65), [barX, 1.1, 0.9]), '#33363d'),
    paint(place(box(barWidth, 0.04, 0.22), [barX, 1.5, 0.13]), '#2a2c33'),
    paint(place(box(barWidth, 0.04, 0.22), [barX, 1.95, 0.13]), '#2a2c33'),
    // Door.
    paint(place(box(1.1, 2.15, 0.05), [doorX, 1.075, 0.03]), '#2b2d35'),
    paint(place(box(0.94, 2.0, 0.02), [doorX, 1.02, 0.06]), '#191a1f'),
  ]);
  const glow = merge([
    paint(place(panel(barWidth - 0.1, 0.03), [barX, 1.54, 0.03]), BAR_GLOW),
    paint(place(panel(barWidth - 0.1, 0.03), [barX, 1.99, 0.03]), BAR_GLOW),
    paint(place(panel(barWidth, 0.025), [barX, 0.1, 1.18]), BAR_GLOW),
  ]);
  return { solid, glow };
}

/** "EXIT" drawn onto a canvas: no font file and nothing fetched. */
function makeExitTexture(): THREE.CanvasTexture | null {
  if (typeof document === 'undefined') return null;
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 96;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  ctx.fillStyle = '#0b3d1f';
  ctx.fillRect(0, 0, 256, 96);
  ctx.fillStyle = '#7dffa8';
  ctx.font = 'bold 64px Arial, Helvetica, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('EXIT', 128, 52);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

export const ClubRoom = memo(function ClubRoom({
  layout,
  ceiling = true,
  danceFloor = true,
  dressing = true,
  shell = true,
  boothLight = null,
}: {
  layout: ClubLayout;
  /**
   * Where the work light over the booth hangs, for a room whose booth is not
   * the one the view makes up (a scanned room). Left out, it is over that one.
   */
  boothLight?: [number, number, number] | null;
  /**
   * The room's own box: its floor, four walls and flat ceiling. Off for a
   * scanned room that is not a box, whose floor, walls and ceiling follow its
   * outline and are drawn from the room shell. The house lights stay.
   */
  shell?: boolean;
  /**
   * The bar counter, door and exit sign the view makes up for the rear wall.
   * Off for a scanned room: its walls are real, and the scan found no bar there.
   */
  dressing?: boolean;
  /** Off when the rig's own room shell supplies the ceiling (a dome). */
  ceiling?: boolean;
  /** Off when the rig's own room shell supplies the dance floor. */
  danceFloor?: boolean;
}) {
  const backRef = useRef<THREE.Group>(null);
  const leftRef = useRef<THREE.Group>(null);
  const rightRef = useRef<THREE.Group>(null);
  const houseRef = useRef<THREE.Group>(null);
  const ceilingRef = useRef<THREE.Group>(null);

  const built = useMemo(() => {
    const sideLength = layout.houseZ - layout.backZ;
    const crossLength = layout.wallX * 2;
    return {
      floor: buildFloor(layout),
      dance: buildDanceFloor(layout),
      crossWall: buildWall(crossLength, layout.ceilingY),
      sideWall: buildWall(sideLength, layout.ceilingY),
      ceiling: buildCeiling(layout),
      house: buildHouseDressing(crossLength),
      crossLength,
    };
  }, [layout]);

  const exitTexture = useMemo(() => makeExitTexture(), []);

  useEffect(() => () => {
    built.floor.dispose();
    built.dance.tiles.dispose();
    built.dance.glow.dispose();
    built.crossWall.dispose();
    built.sideWall.dispose();
    built.ceiling.dispose();
    built.house.solid.dispose();
    built.house.glow.dispose();
  }, [built]);
  useEffect(() => () => exitTexture?.dispose(), [exitTexture]);

  // Show each surface only from its inner side.
  useFrame(({ camera }) => {
    const p = camera.position;
    if (backRef.current) backRef.current.visible = p.z > layout.backZ;
    if (houseRef.current) houseRef.current.visible = p.z < layout.houseZ;
    if (leftRef.current) leftRef.current.visible = p.x > -layout.wallX;
    if (rightRef.current) rightRef.current.visible = p.x < layout.wallX;
    if (ceilingRef.current) ceilingRef.current.visible = p.y < layout.ceilingY;
  });

  const midZ = (layout.backZ + layout.houseZ) / 2;
  const doorX = built.crossLength / 2 - 1.3;
  // The bar is modelled on the house wall, which is turned to face the room,
  // so its X runs the other way in the room.
  const barLightX = built.crossLength / 2 - Math.min(4.5, built.crossLength * 0.42) / 2 - 0.5;

  return (
    <group>
      {/* House lights: a work light over the booth and the glow off the bar.
          Two fixed lights, so the room has some shape when the rig is dark.
          They are always on, which keeps the light count steady. */}
      <pointLight
        position={boothLight ?? [0, layout.booth.deskTopY + 1.5, layout.booth.fasciaZ + 0.55]}
        color="#b6c6ff"
        intensity={3.4}
        distance={9}
        decay={2}
      />
      <pointLight
        position={[barLightX, 2.2, layout.houseZ - 1.5]}
        color="#ffae6e"
        intensity={3.2}
        distance={10}
        decay={2}
      />

      {shell && <mesh geometry={built.floor} material={mattMaterial} receiveShadow dispose={null} />}
      {danceFloor && (
        <>
          <mesh geometry={built.dance.tiles} material={glossMaterial} receiveShadow dispose={null} />
          <mesh geometry={built.dance.glow} material={glowMaterial} dispose={null} />
        </>
      )}

      {shell && (
        <>
          <group ref={backRef} position={[0, 0, layout.backZ]}>
            <mesh geometry={built.crossWall} material={mattMaterial} receiveShadow dispose={null} />
          </group>
          <group ref={houseRef} position={[0, 0, layout.houseZ]} rotation={[0, Math.PI, 0]}>
            <mesh geometry={built.crossWall} material={mattMaterial} receiveShadow dispose={null} />
            {dressing && <mesh geometry={built.house.solid} material={mattMaterial} receiveShadow dispose={null} />}
            {dressing && <mesh geometry={built.house.glow} material={glowMaterial} dispose={null} />}
            {dressing && exitTexture && (
              <mesh position={[doorX, 2.42, 0.05]}>
                <planeGeometry args={[0.56, 0.21]} />
                <meshBasicMaterial map={exitTexture} toneMapped={false} />
              </mesh>
            )}
          </group>
          <group ref={leftRef} position={[-layout.wallX, 0, midZ]} rotation={[0, Math.PI / 2, 0]}>
            <mesh geometry={built.sideWall} material={mattMaterial} receiveShadow dispose={null} />
          </group>
          <group ref={rightRef} position={[layout.wallX, 0, midZ]} rotation={[0, -Math.PI / 2, 0]}>
            <mesh geometry={built.sideWall} material={mattMaterial} receiveShadow dispose={null} />
          </group>
        </>
      )}

      {shell && ceiling && (
        <group ref={ceilingRef} position={[0, layout.ceilingY, 0]}>
          <mesh geometry={built.ceiling} material={mattMaterial} dispose={null} />
        </group>
      )}
    </group>
  );
});
