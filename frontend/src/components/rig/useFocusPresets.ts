/**
 * A rig's focus presets table (docs/FOCUS_PRESETS.md, "In the app"), shared by
 * the Focus presets panel and the 3D view's target markers as useStagePlot is
 * shared by the plan and the 3D floor.
 *
 * Adding or removing a custom target reads the whole table again: who can
 * reach a point is worked out on the server. Each change is announced
 * (focusTargetsSync.ts), and a change announced by another hook showing the
 * same rig is read here, so the 3D markers follow the panel without a reload.
 * Any rig write the app's client makes (a fixture moved or turned in the 2D
 * plan or the 3D view, any rig save, a room edit) is announced too, and read
 * here once the writes settle (RIG_CHANGE_DEBOUNCE_MS), so the reach colours
 * are never left showing where the heads used to be.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { focusPresetsApi } from '../../services/focusPresetsApi';
import { refusalText } from '../../services/stagePlotApi';
import type { FocusTable, NewTarget } from '../../utils/focusPresets';
import { announceFocusTargetsChange, onFocusTargetsChange, onRigChange } from '../../utils/focusTargetsSync';

/** How long after the last rig write the table is read again. */
export const RIG_CHANGE_DEBOUNCE_MS = 400;

export type FocusPresetsStatus = 'idle' | 'loading' | 'ready' | 'error';

export interface FocusPresetsState {
  status: FocusPresetsStatus;
  table: FocusTable | null;
  /** Why the table could not be read, in a sentence. */
  error: string | null;
  reload: () => void;
  /** Resolves to null when added, or the reason it was not. */
  add: (target: NewTarget) => Promise<string | null>;
  /** Resolves to null when removed, or the reason it was not. */
  remove: (targetId: number) => Promise<string | null>;
}

const status404 = (error: unknown) => axios.isAxiosError(error) && error.response?.status === 404;

function readError(error: unknown): string {
  return status404(error)
    ? 'This rig is no longer there.'
    : 'The focus presets could not be read. Check the connection and try again.';
}

/** rigId null reads nothing: a demo rig, or the 3D markers switched off. */
export default function useFocusPresets(rigId: number | null | undefined): FocusPresetsState {
  const [table, setTable] = useState<FocusTable | null>(null);
  const [status, setStatus] = useState<FocusPresetsStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  // The newest read wins: an older answer that lands late is dropped.
  const seq = useRef(0);
  const self = useRef({}).current;
  const shown = useRef<FocusTable | null>(null);
  shown.current = table;

  const read = useCallback(async (id: number, quiet: boolean) => {
    seq.current += 1;
    const mine = seq.current;
    if (!quiet) setStatus('loading');
    try {
      const next = await focusPresetsApi.get(id);
      if (seq.current !== mine) return;
      setTable(next);
      setError(null);
      setStatus('ready');
    } catch (err) {
      if (seq.current !== mine) return;
      // A quiet read (after a change elsewhere) keeps what is shown.
      if (quiet && shown.current) return;
      setError(readError(err));
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    setTable(null);
    setError(null);
    if (rigId == null) {
      seq.current += 1;
      setStatus('idle');
      return undefined;
    }
    void read(rigId, false);
    const off = onFocusTargetsChange(rigId, self, () => { void read(rigId, true); });
    // A fixture moved or turned, or the room edited: read again once the
    // writes settle, so a drag's run of saves is one read, not one each.
    let wait: ReturnType<typeof setTimeout> | null = null;
    const offRig = onRigChange(rigId, () => {
      if (wait !== null) clearTimeout(wait);
      wait = setTimeout(() => {
        wait = null;
        void read(rigId, true);
      }, RIG_CHANGE_DEBOUNCE_MS);
    });
    return () => {
      seq.current += 1;
      off();
      offRig();
      if (wait !== null) clearTimeout(wait);
    };
  }, [rigId, self, read]);

  const reload = useCallback(() => {
    if (rigId != null) void read(rigId, false);
  }, [rigId, read]);

  const add = useCallback(async (target: NewTarget) => {
    if (rigId == null) return 'There is no rig to add it to.';
    try {
      await focusPresetsApi.addTarget(rigId, target);
    } catch (err) {
      return status404(err) ? 'This rig is no longer there.' : refusalText(err, 'The target could not be added. Try again.');
    }
    announceFocusTargetsChange(rigId, self);
    await read(rigId, true);
    return null;
  }, [rigId, self, read]);

  const remove = useCallback(async (targetId: number) => {
    if (rigId == null) return 'There is no rig to remove it from.';
    try {
      await focusPresetsApi.removeTarget(rigId, targetId);
    } catch (err) {
      if (!status404(err)) return refusalText(err, 'The target could not be removed. Try again.');
      // Gone already (removed in another tab): read the table again so it is not shown.
      await read(rigId, true);
      return 'That target was already removed.';
    }
    announceFocusTargetsChange(rigId, self);
    await read(rigId, true);
    return null;
  }, [rigId, self, read]);

  return { status, table, error, reload, add, remove };
}
