// Rig writes made outside the old client paths are announced too: the QR
// scanner's scan and the RDM import go through services/api.ts, so the focus
// table and the 3D reach markers read again after them (docs/FOCUS_PRESETS.md,
// "The reach follows the rig"). The real client and its response handler run
// here; only axios's network adapter is stood in for.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, waitFor } from '@testing-library/react';
import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios';

const focus = vi.hoisted(() => ({ get: vi.fn(), csv: vi.fn(), addTarget: vi.fn(), removeTarget: vi.fn() }));
vi.mock('../services/focusPresetsApi', () => ({ focusPresetsApi: focus }));

import api, { rigsApi } from '../services/api';
import useFocusTargets3d from '../components/rig/previs/useFocusTargets3d';
import { RIG_CHANGE_DEBOUNCE_MS } from '../components/rig/useFocusPresets';
import { useFocusPreviewStore } from '../stores/focusPreviewStore';
import { focusTargets3dKey, parseFocusPresets } from '../utils/focusPresets';
import { RIG_ID } from './focusPresetsFixture';
import { VIEW_FIXTURES, previewAnswer } from './focusPreviewFixture';

/** Every request the client sent, as the adapter saw it. */
let sent: InternalAxiosRequestConfig[] = [];
const realAdapter = api.defaults.adapter;
const answerAll: AxiosAdapter = async (config) => {
  sent.push(config);
  return {
    data: { action: 'added', fixture_id: 12, fixture_name: 'Spot 12', dmx_address: 33, universe: 0 },
    status: 200, statusText: 'OK', headers: {}, config,
  };
};

const settle = () => new Promise((resolve) => setTimeout(resolve, RIG_CHANGE_DEBOUNCE_MS + 150));

function ViewProbe() {
  useFocusTargets3d(RIG_ID, VIEW_FIXTURES);
  return null;
}

beforeEach(() => {
  sent = [];
  api.defaults.adapter = answerAll;
  focus.get.mockReset().mockImplementation(async () => parseFocusPresets(previewAnswer()));
  window.localStorage.clear();
  useFocusPreviewStore.setState({ viewRigId: null, preview: null });
});

afterEach(() => {
  cleanup();
  api.defaults.adapter = realAdapter;
});

describe('a QR scan is a rig change', () => {
  it('reads the focus table once more, debounced, while the 3D markers are on', async () => {
    window.localStorage.setItem(focusTargets3dKey(RIG_ID), 'on');
    render(<ViewProbe />);
    await waitFor(() => expect(focus.get).toHaveBeenCalledTimes(1));

    await act(async () => {
      await rigsApi.scanQr(RIG_ID, '12');
    });
    expect(sent.map((c) => `${c.method} ${c.url}`)).toEqual([`post /rigs/${RIG_ID}/scan`]);
    // Debounced: not straight away.
    expect(focus.get).toHaveBeenCalledTimes(1);
    await act(settle);
    expect(focus.get).toHaveBeenCalledTimes(2);
    // And only the once.
    await act(settle);
    expect(focus.get).toHaveBeenCalledTimes(2);
  });

  it('reads nothing while the markers are off', async () => {
    render(<ViewProbe />);
    await act(async () => {
      await rigsApi.scanQr(RIG_ID, '12');
    });
    expect(sent).toHaveLength(1);
    await act(settle);
    expect(focus.get).not.toHaveBeenCalled();
  });

  it('reads nothing when the scan is refused', async () => {
    window.localStorage.setItem(focusTargets3dKey(RIG_ID), 'on');
    render(<ViewProbe />);
    await waitFor(() => expect(focus.get).toHaveBeenCalledTimes(1));
    api.defaults.adapter = async (config) => {
      const error = Object.assign(new Error('Fixture ID 99 not found'), {
        isAxiosError: true, config, response: { status: 404, statusText: 'Not Found', data: {}, headers: {}, config },
      });
      throw error;
    };
    await act(async () => {
      await expect(rigsApi.scanQr(RIG_ID, '99')).rejects.toThrow();
    });
    await act(settle);
    expect(focus.get).toHaveBeenCalledTimes(1);
  });
});

describe('an RDM import into a rig is a rig change', () => {
  it('is announced for the rig it names, though its route does not', async () => {
    window.localStorage.setItem(focusTargets3dKey(RIG_ID), 'on');
    render(<ViewProbe />);
    await waitFor(() => expect(focus.get).toHaveBeenCalledTimes(1));
    await act(async () => {
      await rigsApi.importRdmDevices(RIG_ID, [4, 9]);
    });
    expect(sent.map((c) => `${c.method} ${c.url}`)).toEqual(['post /rdm/import']);
    await act(settle);
    expect(focus.get).toHaveBeenCalledTimes(2);
  });

  // The request backend/tests/integration/test_api_rdm_import.py posts: the
  // route takes `device_ids: List[int]` as the body and `rig_id` as a query.
  it('sends the stored ids as a bare list, and the rig as a query parameter', async () => {
    await rigsApi.importRdmDevices(RIG_ID, [4, 9]);
    expect(sent).toHaveLength(1);
    const [config] = sent;
    expect(config.params).toEqual({ rig_id: RIG_ID });
    const body = typeof config.data === 'string' ? JSON.parse(config.data) : config.data;
    expect(body).toEqual([4, 9]);
    expect(Array.isArray(body)).toBe(true);
  });
});

describe('the QR labels', () => {
  it('are a read, not a rig change', async () => {
    window.localStorage.setItem(focusTargets3dKey(RIG_ID), 'on');
    render(<ViewProbe />);
    await waitFor(() => expect(focus.get).toHaveBeenCalledTimes(1));
    await act(async () => {
      await rigsApi.labelsPdf(RIG_ID);
    });
    expect(sent[0].responseType).toBe('blob');
    await act(settle);
    expect(focus.get).toHaveBeenCalledTimes(1);
  });
});
