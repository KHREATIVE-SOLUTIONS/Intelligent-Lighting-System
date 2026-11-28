/**
 * The focus targets for the 3D view (docs/FOCUS_PRESETS.md, "In the app"): the
 * table read with the same hook the Focus presets panel uses, so a target
 * added or removed there appears on, or goes from, the view without a reload;
 * and whether the operator wants them shown, per rig in localStorage
 * (`focusTargets3d:{rigId}`). Until they choose, they are off, and nothing is
 * read.
 *
 * Also the preset being previewed (focusPreviewStore): while one is, the table
 * is read whether or not the markers are on, and `preview` says where each
 * head is aimed. A refresh after a rig change moves the preview with it; a
 * target that is gone stops it. Visual only: nothing here sends DMX.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import useFocusPresets from '../useFocusPresets';
import { focusMarkers, readFocusTargets3dChoice, writeFocusTargets3dChoice } from '../../../utils/focusPresets';
import type { FocusMarker } from '../../../utils/focusPresets';
import { previewPlan } from '../../../utils/focusPreview';
import type { FocusPreviewPlan, ViewFixture } from '../../../utils/focusPreview';
import { useFocusPreviewStore } from '../../../stores/focusPreviewStore';

export interface FocusTargets3dState {
  /** False for a demo rig: it has no stored room to aim in. */
  available: boolean;
  on: boolean;
  setOn: (on: boolean) => void;
  /** What FocusTargetMarkers draws; empty while off. */
  markers: FocusMarker[];
  /** The preset being previewed on this rig, or null. */
  preview: FocusPreviewPlan | null;
  stopPreview: () => void;
}

const NO_FIXTURES: ViewFixture[] = [];

export default function useFocusTargets3d(
  rigId: number | null | undefined,
  fixtures: ViewFixture[] = NO_FIXTURES,
): FocusTargets3dState {
  const [choice, setChoice] = useState<boolean | null>(() => (rigId == null ? null : readFocusTargets3dChoice(rigId)));

  useEffect(() => {
    setChoice(rigId == null ? null : readFocusTargets3dChoice(rigId));
  }, [rigId]);

  const setOn = useCallback((on: boolean) => {
    setChoice(on);
    if (rigId != null) writeFocusTargets3dChoice(rigId, on);
  }, [rigId]);

  const previewing = useFocusPreviewStore((s) => (rigId != null && s.preview?.rigId === rigId ? s.preview.key : null));
  const stopPreview = useFocusPreviewStore((s) => s.stop);

  const on = rigId != null && (choice ?? false);
  const focus = useFocusPresets(on || previewing !== null ? rigId : null);
  const markers = useMemo(() => (on ? focusMarkers(focus.table) : []), [on, focus.table]);

  const target = previewing !== null ? focus.table?.targets.find((t) => t.key === previewing) ?? null : null;
  const preview = useMemo(
    () => (target && !target.skipped ? previewPlan(target, fixtures) : null),
    [target, fixtures],
  );

  // The previewed target was removed, or the room can no longer place it.
  const gone = previewing !== null && focus.status === 'ready' && (!target || !!target.skipped);
  useEffect(() => {
    if (gone) stopPreview();
  }, [gone, stopPreview]);

  return { available: rigId != null, on, setOn, markers, preview, stopPreview };
}
