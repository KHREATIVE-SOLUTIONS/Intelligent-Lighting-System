/**
 * Draws the room a rig describes in its `room_shell`: dome, round dance
 * floor, balcony, risers and LED walls, and for a scanned room its raised
 * areas, the trusses, bars and rings found overhead, and, where the room is
 * not a box, the floor, walls and ceiling along its outline.
 *
 * It stands inside the club room the view already builds (floor and walls),
 * and takes the place of that room's flat ceiling and square dance floor. As
 * with the walls, the dome is drawn only while the camera is under it, so a
 * camera outside the room looks straight in.
 */
import { memo, useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import type { RoomShell } from '../../../types';
import type { ClubLayout, TrussRow } from './layout';
import { glossMaterial, glowMaterial, mattMaterial } from './materials';
import { buildWall } from './ClubRoom';
import {
  boothAlreadyDrawn,
  buildBalcony,
  buildDanceDisc,
  buildDome,
  buildDomeSurround,
  buildLedWalls,
  buildOutlineCeilingDressing,
  buildOutlineFlat,
  buildOverheadLines,
  buildRisers,
  buildTrussRings,
  lineAlreadyDrawn,
  onRoomSide,
  outlineWalls,
  scanRings,
  scanRisers,
  underDome,
  usableBalcony,
  usableBox,
  usableDisc,
  usableDome,
  usableLine,
} from './roomShell';
import type { OutlinePoint } from './roomShell';

/** One array for "no truss", so a caller that passes none does not rebuild the room each render. */
const NO_ROWS: TrussRow[] = [];

/** The club room's own floor and ceiling colours (ClubRoom.tsx), so an outlined room matches a box one. */
const OUTLINE_FLOOR = '#3c3d45';
const OUTLINE_CEILING = '#2a2b31';

/**
 * A scanned room that is not a box: a floor and a ceiling cut to its outline
 * and one wall along each segment of it. It takes the place of the club room's
 * box (`ClubRoom` with `shell` off). As there, each wall is drawn only while
 * the camera is on the room's side of it, so a camera outside looks in.
 */
const OutlineRoom = memo(function OutlineRoom({
  outline,
  height,
  ceiling,
}: {
  outline: OutlinePoint[];
  height: number;
  /** Off when the shell supplies the ceiling itself (a dome). */
  ceiling: boolean;
}) {
  const wallRefs = useRef<Array<THREE.Group | null>>([]);
  const ceilingRef = useRef<THREE.Group>(null);

  const built = useMemo(() => {
    const walls = outlineWalls(outline);
    return {
      walls,
      panels: walls.map((wall) => buildWall(wall.length, height)),
      floor: buildOutlineFlat(outline, 0, OUTLINE_FLOOR),
      ceiling: buildOutlineFlat(outline, height, OUTLINE_CEILING),
      // The beams and the duct the box room's ceiling has, kept inside the outline.
      dressing: buildOutlineCeilingDressing(outline, height),
    };
  }, [outline, height]);

  useEffect(() => () => {
    built.panels.forEach((panel) => panel.dispose());
    built.floor.dispose();
    built.ceiling.dispose();
    built.dressing?.dispose();
  }, [built]);

  useFrame(({ camera }) => {
    const p = camera.position;
    built.walls.forEach((wall, index) => {
      const group = wallRefs.current[index];
      if (group) group.visible = onRoomSide(wall, p.x, p.z);
    });
    if (ceilingRef.current) ceilingRef.current.visible = p.y < height;
  });

  return (
    <group>
      <mesh geometry={built.floor} material={mattMaterial} receiveShadow dispose={null} />
      {built.walls.map((wall, index) => (
        <group
          key={`${index}-${wall.x1}-${wall.z1}-${wall.x2}-${wall.z2}`}
          ref={(node) => { wallRefs.current[index] = node; }}
          position={[wall.midX, 0, wall.midZ]}
          rotation={[0, wall.yaw, 0]}
        >
          <mesh geometry={built.panels[index]} material={mattMaterial} receiveShadow dispose={null} />
        </group>
      ))}
      {ceiling && (
        <group ref={ceilingRef}>
          <mesh geometry={built.ceiling} material={mattMaterial} dispose={null} />
          {built.dressing && <mesh geometry={built.dressing} material={mattMaterial} dispose={null} />}
        </group>
      )}
    </group>
  );
});

export const RoomShellView = memo(function RoomShellView({
  shell,
  layout,
  trussRows = NO_ROWS,
  outline = null,
}: {
  /**
   * The floor outline of a scanned room that is not a box, as the venue has
   * it (`Venue.outline`): the same one the beams, the mounts and the cameras
   * go by, with a wall moved out for a fixture beyond it. Null for a box.
   */
  outline?: OutlinePoint[] | null;
  shell: RoomShell;
  layout: ClubLayout;
  /** The truss the view hangs over the rig's own fixtures: a scanned line under one of these is not drawn twice. */
  trussRows?: TrussRow[];
}) {
  const domeRef = useRef<THREE.Group>(null);
  const dome = usableDome(shell.dome) ? shell.dome : null;

  const built = useMemo(() => {
    // A scanned room's raised areas (stage, risers, booth) are all drawn as
    // the scan found them. The desk, decks and DJ of that room's booth stand
    // on one of these boxes (DJBooth with `placed`), which stays drawn here.
    const risers = [shell.rear_stage].filter(usableBox).concat(scanRisers(shell));
    const overhead = (shell.truss_lines ?? [])
      .filter(usableLine)
      .filter((line) => !lineAlreadyDrawn(line, trussRows));
    // The detailed booth the view builds stands in for the shell's, when they
    // are the same booth; a shell that puts it elsewhere gets its box drawn.
    if (
      usableBox(shell.dj_booth)
      && !boothAlreadyDrawn(shell.dj_booth, { width: layout.booth.width, fasciaZ: layout.booth.fasciaZ, backZ: layout.backZ })
    ) {
      risers.push(shell.dj_booth);
    }
    return {
      dome: dome ? buildDome(dome) : null,
      surround: dome
        ? buildDomeSurround(dome, { xMin: -layout.wallX, xMax: layout.wallX, zMin: layout.backZ, zMax: layout.houseZ })
        : null,
      disc: usableDisc(shell.dance_floor) ? buildDanceDisc(shell.dance_floor) : null,
      balcony: usableBalcony(shell.balcony) ? buildBalcony(shell.balcony) : null,
      risers: buildRisers(risers),
      overhead: buildOverheadLines(overhead),
      rings: shell.source === 'scan' ? buildTrussRings(scanRings(shell)) : null,
      walls: buildLedWalls((shell.led_walls ?? []).filter(usableBox)),
    };
  }, [shell, dome, layout, trussRows]);

  useEffect(() => () => {
    built.overhead?.dispose();
    built.rings?.dispose();
    built.dome?.dispose();
    built.surround?.dispose();
    built.disc?.dispose();
    built.balcony?.dispose();
    built.risers?.dispose();
    built.walls?.frames.dispose();
    built.walls?.panels.dispose();
  }, [built]);

  useFrame(({ camera }) => {
    if (!domeRef.current || !dome) return;
    const p = camera.position;
    const indoors = p.x > -layout.wallX && p.x < layout.wallX && p.z > layout.backZ && p.z < layout.houseZ;
    // Past the dome's edge but still in the room, the flat surround is overhead.
    domeRef.current.visible = indoors && (underDome(dome, p.x, p.y, p.z) || p.y < dome.rim_height);
  });

  return (
    <group>
      <group ref={domeRef}>
        {built.dome && <mesh geometry={built.dome} material={mattMaterial} dispose={null} />}
        {built.surround && <mesh geometry={built.surround} material={mattMaterial} dispose={null} />}
      </group>
      {built.disc && <mesh geometry={built.disc} material={glossMaterial} receiveShadow dispose={null} />}
      {built.balcony && <mesh geometry={built.balcony} material={mattMaterial} receiveShadow dispose={null} />}
      {built.risers && <mesh geometry={built.risers} material={mattMaterial} receiveShadow dispose={null} />}
      {built.overhead && <mesh geometry={built.overhead} material={mattMaterial} dispose={null} />}
      {built.rings && <mesh geometry={built.rings} material={mattMaterial} dispose={null} />}
      {outline && <OutlineRoom outline={outline} height={layout.ceilingY} ceiling={!dome} />}
      {built.walls && (
        <>
          <mesh geometry={built.walls.frames} material={mattMaterial} dispose={null} />
          <mesh geometry={built.walls.panels} material={glowMaterial} dispose={null} />
        </>
      )}
    </group>
  );
});
