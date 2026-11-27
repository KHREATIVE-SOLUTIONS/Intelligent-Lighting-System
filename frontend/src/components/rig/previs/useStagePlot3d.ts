/**
 * The stage plot for the 3D view (docs/STAGE_PLOT.md, "In the 3D view"): what
 * the rig's Stage plot control stored, read with the same hook the 2D plan
 * uses (useStagePlot: the authenticated fetch, the object URL, and its
 * revoking), and whether the operator wants it on the 3D floor.
 *
 * Only a calibrated plot is drawn in 3D: one that is not has no size in
 * metres. The choice is the operator's per rig, kept in localStorage; until
 * they make one it is on.
 */
import { useCallback, useEffect, useState } from 'react';
import useStagePlot from '../useStagePlot';
import { DEFAULT_OPACITY } from '../../../utils/stagePlot';
import { readStagePlot3dChoice, writeStagePlot3dChoice } from '../../../utils/stagePlot3d';
import type { StagePlotFloorProps } from './StagePlotFloor';

/** none: no plot. uncalibrated: a plot only the 2D plan can draw. calibrated: one the 3D view can. */
export type StagePlot3dStatus = 'none' | 'uncalibrated' | 'calibrated';

export interface StagePlot3dState {
  status: StagePlot3dStatus;
  /** Whether a calibrated plot is drawn (the choice, or on when none was made). */
  on: boolean;
  setOn: (on: boolean) => void;
  /** What StagePlotFloor draws, or null when nothing is. */
  floor: StagePlotFloorProps | null;
}

export default function useStagePlot3d(rigId: number | null | undefined, stageWidth: number, stageDepth: number): StagePlot3dState {
  const plot = useStagePlot(rigId, stageWidth, stageDepth);
  const [choice, setChoice] = useState<boolean | null>(() => (rigId == null ? null : readStagePlot3dChoice(rigId)));

  useEffect(() => {
    setChoice(rigId == null ? null : readStagePlot3dChoice(rigId));
  }, [rigId]);

  const setOn = useCallback((on: boolean) => {
    setChoice(on);
    if (rigId != null) writeStagePlot3dChoice(rigId, on);
  }, [rigId]);

  const { info, underlay } = plot;
  const transform = info?.present ? info.transform : null;
  const status: StagePlot3dStatus = !plot.present ? 'none' : transform ? 'calibrated' : 'uncalibrated';
  const on = choice ?? true;

  const floor: StagePlotFloorProps | null = status === 'calibrated' && on && underlay && transform
    ? {
      href: underlay.href,
      widthPx: underlay.widthPx,
      heightPx: underlay.heightPx,
      matrix: transform.matrix,
      opacity: info?.calibration?.opacity ?? DEFAULT_OPACITY,
    }
    : null;

  return { status, on, setOn, floor };
}
