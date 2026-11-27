/**
 * The calibrated stage plot, lying on the floor of the 3D view
 * (docs/STAGE_PLOT.md, "In the 3D view"). Placed by the same image-to-plan
 * matrix the 2D plan draws it with (utils/stagePlot3d.ts).
 *
 * The image is the object URL useStagePlot made from the authenticated fetch;
 * that hook revokes it. The texture loaded from it is this component's, and is
 * disposed when the image changes or the plot goes.
 *
 * Unlit, so the room's lights do not darken it; it writes no depth, so the
 * beams and the floor rings over it still draw; and it is never hit by a ray,
 * so a fixture drag and a click through it behave as if it were not there.
 */
import { memo, useEffect, useState } from 'react';
import * as THREE from 'three';
import type { Matrix } from '../../../utils/stagePlot';
import { STAGE_PLOT_LIFT, stagePlotPlane } from '../../../utils/stagePlot3d';

export interface StagePlotFloorProps {
  /** An object URL of the image. */
  href: string;
  widthPx: number;
  heightPx: number;
  matrix: Matrix;
  opacity: number;
}

const FLAT: [number, number, number] = [-Math.PI / 2, 0, 0];

/** Takes no hits: a ray goes through the plot to whatever is under it. */
const noRaycast = () => undefined;

export const StagePlotFloor = memo(function StagePlotFloor({ href, widthPx, heightPx, matrix, opacity }: StagePlotFloorProps) {
  const [texture, setTexture] = useState<THREE.Texture | null>(null);

  useEffect(() => {
    let live = true;
    // Not drei's useTexture: that caches by URL and would keep a texture of a revoked URL alive.
    const next = new THREE.TextureLoader().load(
      href,
      (loaded) => { if (live) setTexture(loaded); },
      undefined,
      () => { if (live) setTexture(null); },
    );
    next.colorSpace = THREE.SRGBColorSpace;
    return () => {
      live = false;
      next.dispose();
      setTexture(null);
    };
  }, [href]);

  const plane = stagePlotPlane(matrix, widthPx, heightPx);
  if (!plane || !texture) return null;
  return (
    <group name="stage-plot-floor" position={[plane.centerX, STAGE_PLOT_LIFT, plane.centerZ]} rotation={[0, plane.yaw, 0]}>
      <mesh name="stage-plot-floor-plane" rotation={FLAT} raycast={noRaycast} renderOrder={1}>
        <planeGeometry args={[plane.width, plane.depth]} />
        <meshBasicMaterial
          map={texture}
          transparent
          opacity={opacity}
          depthWrite={false}
          toneMapped={false}
          side={THREE.DoubleSide}
          polygonOffset
          polygonOffsetFactor={-1}
          polygonOffsetUnits={-1}
        />
      </mesh>
    </group>
  );
});
