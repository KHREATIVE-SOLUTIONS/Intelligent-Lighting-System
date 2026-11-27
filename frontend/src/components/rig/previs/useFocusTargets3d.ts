/**
 * The focus targets for the 3D view (docs/FOCUS_PRESETS.md, "In the app"): the
 * table read with the same hook the Focus presets panel uses, so a target
 * added or removed there appears on, or goes from, the view without a reload;
 * and whether the operator wants them shown, per rig in localStorage
 * (`focusTargets3d:{rigId}`). Until they choose, they are off, and nothing is
 * read.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import useFocusPresets from '../useFocusPresets';
import { focusMarkers, readFocusTargets3dChoice, writeFocusTargets3dChoice } from '../../../utils/focusPresets';
import type { FocusMarker } from '../../../utils/focusPresets';

export interface FocusTargets3dState {
  /** False for a demo rig: it has no stored room to aim in. */
  available: boolean;
  on: boolean;
  setOn: (on: boolean) => void;
  /** What FocusTargetMarkers draws; empty while off. */
  markers: FocusMarker[];
}

export default function useFocusTargets3d(rigId: number | null | undefined): FocusTargets3dState {
  const [choice, setChoice] = useState<boolean | null>(() => (rigId == null ? null : readFocusTargets3dChoice(rigId)));

  useEffect(() => {
    setChoice(rigId == null ? null : readFocusTargets3dChoice(rigId));
  }, [rigId]);

  const setOn = useCallback((on: boolean) => {
    setChoice(on);
    if (rigId != null) writeFocusTargets3dChoice(rigId, on);
  }, [rigId]);

  const on = rigId != null && (choice ?? false);
  const focus = useFocusPresets(on ? rigId : null);
  const markers = useMemo(() => (on ? focusMarkers(focus.table) : []), [on, focus.table]);

  return { available: rigId != null, on, setOn, markers };
}
