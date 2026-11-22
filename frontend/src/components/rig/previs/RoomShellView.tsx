/**
 * Draws the room a rig describes in its `room_shell`: dome, round dance
 * floor, balcony, risers and LED walls, and for a scanned room its raised
 * areas and the trusses or bars found overhead.
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
import {
  boothAlreadyDrawn,
  buildBalcony,
  buildDanceDisc,
  buildDome,
  buildDomeSurround,
  buildLedWalls,
  buildOverheadLines,
  buildRisers,
  lineAlreadyDrawn,
  scanRisers,
  underDome,
  usableBalcony,
  usableBox,
  usableDisc,
  usableDome,
  usableLine,
} from './roomShell';

/** One array for "no truss", so a caller that passes none does not rebuild the room each render. */
const NO_ROWS: TrussRow[] = [];

export const RoomShellView = memo(function RoomShellView({
  shell,
  layout,
  trussRows = NO_ROWS,
}: {
  shell: RoomShell;
  layout: ClubLayout;
  /** The truss the view hangs over the rig's own fixtures: a scanned line under one of these is not drawn twice. */
  trussRows?: TrussRow[];
}) {
  const domeRef = useRef<THREE.Group>(null);
  const dome = usableDome(shell.dome) ? shell.dome : null;

  const built = useMemo(() => {
    // A scanned room's raised areas (stage, risers, booth) are all drawn as
    // the scan found them; the view builds no booth of its own in that room.
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
      walls: buildLedWalls((shell.led_walls ?? []).filter(usableBox)),
    };
  }, [shell, dome, layout, trussRows]);

  useEffect(() => () => {
    built.overhead?.dispose();
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
      {built.walls && (
        <>
          <mesh geometry={built.walls.frames} material={mattMaterial} dispose={null} />
          <mesh geometry={built.walls.panels} material={glowMaterial} dispose={null} />
        </>
      )}
    </group>
  );
});
