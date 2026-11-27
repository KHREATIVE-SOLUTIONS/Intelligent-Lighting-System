/**
 * Focus presets requests (docs/FOCUS_PRESETS.md). Through the app's axios
 * instance, so they carry the operator's token; the CSV is fetched as a blob
 * for that reason and saved from it, as the handoff pack is. Reads change
 * nothing; adding or removing a custom target writes only that list. Nothing
 * here sends DMX.
 */
import api from './api';
import { filenameFromDisposition } from '../utils/consoleExport';
import {
  focusPresetsCsvPath, focusPresetsPath, focusTargetPath, focusTargetsPath, parseFocusPresets,
} from '../utils/focusPresets';
import type { FocusTable, NewTarget } from '../utils/focusPresets';

export const focusPresetsApi = {
  get: async (rigId: number): Promise<FocusTable> => {
    const response = await api.get(focusPresetsPath(rigId));
    return parseFocusPresets(response.data);
  },

  csv: async (rigId: number): Promise<{ blob: Blob; filename: string }> => {
    const response = await api.get(focusPresetsCsvPath(rigId), { responseType: 'blob' });
    return {
      blob: response.data as Blob,
      filename: filenameFromDisposition(response.headers?.['content-disposition'], `rig_${rigId}_focus-presets.csv`),
    };
  },

  /** 201 with the new target; a 422 carries the reason as a sentence in `detail`. */
  addTarget: async (rigId: number, target: NewTarget): Promise<{ target: { id: number } }> => {
    const response = await api.post(focusTargetsPath(rigId), target);
    return response.data;
  },

  /** 404 when the rig has no custom target with that id. */
  removeTarget: async (rigId: number, targetId: number): Promise<{ removed: number }> => {
    const response = await api.delete(focusTargetPath(rigId, targetId));
    return response.data;
  },
};
