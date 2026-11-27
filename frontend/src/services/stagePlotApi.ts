/**
 * The stage plot underlay's requests (docs/STAGE_PLOT.md). Through the app's
 * axios instance, so they carry the operator's token: the image itself is
 * fetched as a blob for that reason, as the patch sheet is, and shown from an
 * object URL. An <img src> to the route would go without the token.
 */
import api from './api';
import type { StagePlotCalibration, StagePlotInfo, StagePlotTransform } from '../utils/stagePlot';

export const stagePlotPath = (rigId: number) => `/rigs/${rigId}/stage-plot`;

export const stagePlotApi = {
  info: async (rigId: number): Promise<StagePlotInfo> => {
    const response = await api.get(`${stagePlotPath(rigId)}/info`);
    return response.data;
  },

  image: async (rigId: number): Promise<Blob> => {
    const response = await api.get(stagePlotPath(rigId), { responseType: 'blob' });
    return response.data as Blob;
  },

  upload: async (rigId: number, file: File): Promise<StagePlotInfo> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post(stagePlotPath(rigId), formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  remove: async (rigId: number): Promise<{ removed: boolean }> => {
    const response = await api.delete(stagePlotPath(rigId));
    return response.data;
  },

  calibrate: async (
    rigId: number,
    calibration: StagePlotCalibration,
  ): Promise<{ calibration: StagePlotCalibration; transform: StagePlotTransform }> => {
    const response = await api.put(`${stagePlotPath(rigId)}/calibration`, calibration);
    return response.data;
  },
};

/** The server's sentence from a refused request, or a fallback. */
export function refusalText(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}
