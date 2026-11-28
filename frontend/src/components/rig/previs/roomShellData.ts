/**
 * The checks on a rig's `room_shell` that have no three.js in them: which
 * boxes, lines and rings a shell holds can be drawn. The 2D room plan and the
 * room shell editor read these, and they load before the 3D view does, so
 * they live apart from the geometry in roomShell.ts (which re-exports them).
 * Keeping three.js out of this file keeps it out of the first page load
 * (docs/BUNDLE_SIZE.md).
 */
import type { RoomShell, RoomShellBox, RoomShellLine, RoomShellRing } from '../../../types';

export const finite = (...values: unknown[]) => values.every((value) => typeof value === 'number' && Number.isFinite(value));

export function usableBox(shape: RoomShellBox | null | undefined): shape is RoomShellBox {
  return Boolean(shape) && finite(shape!.center_x, shape!.center_z, shape!.width, shape!.depth, shape!.height)
    && shape!.width > 0 && shape!.depth > 0 && shape!.height > 0;
}

/** The raised areas a scan found that can be drawn: stage, risers, booth. */
export function scanRisers(shell: RoomShell | null | undefined): RoomShellBox[] {
  return (shell?.risers ?? []).filter(usableBox);
}

export function usableLine(line: RoomShellLine | null | undefined): line is RoomShellLine {
  return Boolean(line) && finite(line!.x1, line!.z1, line!.x2, line!.z2, line!.height)
    && line!.height > 0
    && Math.hypot(line!.x2 - line!.x1, line!.z2 - line!.z1) > 0.2;
}

export function usableRing(ring: RoomShellRing | null | undefined): ring is RoomShellRing {
  return Boolean(ring) && finite(ring!.center_x, ring!.center_z, ring!.radius, ring!.height)
    && ring!.radius > 0.2 && ring!.height > 0;
}

/** The rings of truss a scan found that can be drawn. */
export function scanRings(shell: RoomShell | null | undefined): RoomShellRing[] {
  return (shell?.truss_rings ?? []).filter(usableRing);
}
