// useStagePlot: what is stored is read, the image shown from an object URL,
// and a calibration made by clicking three points on the plan is sent in image
// pixels. A failed read is no stage plot. docs/STAGE_PLOT.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

const api = vi.hoisted(() => ({
  info: vi.fn(),
  image: vi.fn(),
  upload: vi.fn(),
  remove: vi.fn(),
  calibrate: vi.fn(),
}));

vi.mock('../services/stagePlotApi', () => ({
  stagePlotApi: api,
  refusalText: (error: { response?: { data?: { detail?: string } } }, fallback: string) =>
    error?.response?.data?.detail ?? fallback,
}));

import useStagePlot from '../components/rig/useStagePlot';

const STORED = { rig_id: 7, present: true, width_px: 400, height_px: 200, calibration: null, transform: null };

const closeTo = (actual: number[], expected: number[]) => {
  expect(actual).toHaveLength(expected.length);
  actual.forEach((n, i) => expect(n).toBeCloseTo(expected[i], 9));
};

describe('useStagePlot', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, writable: true, value: vi.fn(() => 'blob:plot') });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, writable: true, value: vi.fn() });
  });
  afterEach(() => vi.clearAllMocks());

  it('takes a failed read as no stage plot', async () => {
    api.info.mockRejectedValue(new Error('offline'));
    const { result } = renderHook(() => useStagePlot(7, 10, 8));
    await waitFor(() => expect(api.info).toHaveBeenCalledWith(7));
    expect(result.current.present).toBe(false);
    expect(result.current.underlay).toBeNull();
  });

  it('draws a plot not calibrated yet fitted to the stage, and hides it on asking', async () => {
    api.info.mockResolvedValue(STORED);
    api.image.mockResolvedValue(new Blob(['png']));
    const { result } = renderHook(() => useStagePlot(7, 10, 8));
    await waitFor(() => expect(result.current.present).toBe(true));
    const underlay = result.current.underlay!;
    expect(underlay.href).toBe('blob:plot');
    // 400 x 200 px onto 10 x 8 m: as wide as the stage, 0.025 m a pixel.
    closeTo(underlay.matrix, [0.025, 0, 0, 0.025, -5, -2.5]);
    act(() => result.current.setVisible(false));
    expect(result.current.underlay).toBeNull();
  });

  it('turns three clicks and a distance into a calibration in image pixels, and saves it', async () => {
    api.info.mockResolvedValue(STORED);
    api.image.mockResolvedValue(new Blob(['png']));
    const { result } = renderHook(() => useStagePlot(7, 10, 8));
    await waitFor(() => expect(result.current.present).toBe(true));
    expect(result.current.onPlanPick).toBeUndefined();

    act(() => result.current.startCalibrate());
    expect(result.current.step).toBe('a');
    // The plot's top-left corner, the middle of its top edge, and its middle.
    act(() => result.current.onPlanPick!(-5, -2.5));
    act(() => result.current.onPlanPick!(0, -2.5));
    act(() => result.current.onPlanPick!(0, 0));
    expect(result.current.step).toBe('done');
    expect(result.current.onPlanPick).toBeUndefined();
    expect(result.current.pickMarks!.map((m) => m.label)).toEqual(['A', 'B', 'O']);
    expect(result.current.draftProblem).toMatch(/distance/);

    act(() => result.current.setDistance('5'));
    expect(result.current.draftProblem).toBeNull();
    // 200 px is 5 m: the same 0.025 m a pixel, about the same middle.
    closeTo(result.current.underlay!.matrix, [0.025, 0, 0, 0.025, -5, -2.5]);

    api.calibrate.mockResolvedValue({
      calibration: {}, transform: { scale_m_per_px: 0.025, rotation_deg: 0, offset_x: -5, offset_z: -2.5, matrix: [0.025, 0, 0, 0.025, -5, -2.5] },
    });
    await act(async () => { await result.current.saveCalibration(); });
    expect(api.calibrate).toHaveBeenCalledTimes(1);
    const [rigId, sent] = api.calibrate.mock.calls[0];
    expect(rigId).toBe(7);
    closeTo([sent.point_a.x, sent.point_a.y, sent.point_b.x, sent.point_b.y, sent.origin.x, sent.origin.y], [0, 0, 200, 0, 200, 100]);
    expect([sent.distance_m, sent.rotation_deg, sent.opacity]).toEqual([5, 0, 0.5]);
    expect(result.current.calibrating).toBe(false);
    expect(result.current.message?.severity).toBe('success');
  });

  it('says the server\'s sentence when an upload is refused', async () => {
    api.info.mockResolvedValue({ rig_id: 7, present: false });
    api.upload.mockRejectedValue({ response: { data: { detail: 'A PDF stage plot cannot be read here.' } } });
    const { result } = renderHook(() => useStagePlot(7, 10, 8));
    await waitFor(() => expect(api.info).toHaveBeenCalled());
    await act(async () => { await result.current.upload(new File(['%PDF-'], 'plot.pdf')); });
    expect(result.current.message).toEqual({ severity: 'error', text: 'A PDF stage plot cannot be read here.' });
    expect(result.current.present).toBe(false);
  });
});
