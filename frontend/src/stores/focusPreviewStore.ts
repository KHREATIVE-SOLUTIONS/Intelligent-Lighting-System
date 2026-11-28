/**
 * Which focus preset is being previewed in the 3D view, if any
 * (docs/FOCUS_PRESETS.md, "In the app"). Shared because the Focus presets
 * panel lives in a dialog over the view and is gone once the dialog closes,
 * while the preview should stay on until it is stopped.
 *
 * Holds names only: the 3D view reads the aims from its own focus table, so a
 * refresh after a rig change moves a running preview too. Nothing here sends
 * DMX or touches the engine.
 */
import { create } from 'zustand';

export interface FocusPreview {
  rigId: number;
  key: string;
}

interface FocusPreviewStore {
  /** The rig the open 3D view draws, or null when no 3D view is open. */
  viewRigId: number | null;
  preview: FocusPreview | null;
  /** Called by the 3D view when it opens a rig; the returned call when it leaves it, which stops the preview. */
  attachView: (rigId: number) => () => void;
  /** Previews a target; a second one switches. */
  start: (rigId: number, key: string) => void;
  stop: () => void;
}

export const useFocusPreviewStore = create<FocusPreviewStore>((set, get) => ({
  viewRigId: null,
  preview: null,
  attachView: (rigId) => {
    set({ viewRigId: rigId, preview: get().preview?.rigId === rigId ? get().preview : null });
    return () => {
      if (get().viewRigId !== rigId) return;
      set({ viewRigId: null, preview: null });
    };
  },
  start: (rigId, key) => set({ preview: { rigId, key } }),
  stop: () => set({ preview: null }),
}));
