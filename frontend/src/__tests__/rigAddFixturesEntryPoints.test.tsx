// The rig builder's ways to add fixtures from the line or from their labels:
// the Discover RDM and Scan QR buttons, and the two dialogs they open, read
// and sent the way their routes take them (backend/app/api/endpoints/
// discovery.py and qr_scanning.py).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

const calls = vi.hoisted(() => ({
  devices: vi.fn(), start: vi.fn(), stop: vi.fn(), identify: vi.fn(),
  importRdmDevices: vi.fn(), scanQr: vi.fn(), labelsPdf: vi.fn(),
}));
vi.mock('../services/api', () => ({
  rdmApi: { devices: calls.devices, start: calls.start, stop: calls.stop, identify: calls.identify },
  rigsApi: { importRdmDevices: calls.importRdmDevices, scanQr: calls.scanQr, labelsPdf: calls.labelsPdf },
}));

import RigEditorToolbar from '../components/rig/RigEditorToolbar';
import RDMDiscovery, { deviceRows } from '../components/rig/RDMDiscovery';
import QRScanner, { scanResultOf } from '../components/rig/QRScanner';
import type { RdmSavedDevice } from '../services/api';

const RIG_ID = 7;

function toolbar(extra: Partial<Parameters<typeof RigEditorToolbar>[0]> = {}) {
  const noop = () => {};
  return render(
    <RigEditorToolbar
      rigName="Club" viewMode="2d" snapMode="grid" trussLineCount={0} saveState="idle"
      onNameChange={noop} onViewModeChange={noop} onSnapModeChange={noop} onSave={noop}
      onAutoPatch={noop} onTestAll={noop} onIdentify={noop}
      onUndo={noop} onRedo={noop} canUndo={false} canRedo={false}
      {...extra}
    />,
  );
}

const stored = (over: Partial<RdmSavedDevice>): RdmSavedDevice => ({
  id: 1, uid: '4d41:00000001', manufacturer: 'Acme', model: 'Wash 7', label: 'SR wash',
  dmx_footprint: 8, dmx_address: 17, universe: 1, is_imported: false, matched_fixture_id: null,
  last_seen: null, ...over,
});

beforeEach(() => {
  Object.values(calls).forEach((fn) => fn.mockReset());
});
afterEach(cleanup);

describe('the toolbar entry points', () => {
  it('opens RDM discovery and the QR scanner', () => {
    const onDiscoverRdm = vi.fn();
    const onScanQr = vi.fn();
    toolbar({ onDiscoverRdm, onScanQr });
    fireEvent.click(screen.getByRole('button', { name: /discover rdm/i }));
    fireEvent.click(screen.getByRole('button', { name: /scan qr/i }));
    expect(onDiscoverRdm).toHaveBeenCalledTimes(1);
    expect(onScanQr).toHaveBeenCalledTimes(1);
  });

  it('leaves both out where no handler is given', () => {
    toolbar();
    expect(screen.queryByRole('button', { name: /discover rdm/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /scan qr/i })).toBeNull();
  });
});

describe('RDM discovery', () => {
  it('builds rows from the stored devices, which carry the id the import takes', () => {
    const rows = deviceRows([stored({ id: 4, matched_fixture_id: 12 }), stored({ id: 9, is_imported: true })]);
    expect(rows.map((r) => [r.id, r.status, r.imported])).toEqual([[4, 'matched', false], [9, 'unmatched', true]]);
  });

  it('imports the picked devices by stored id, and reports the route\'s own count', async () => {
    calls.devices.mockResolvedValue({
      scanning: false, live_devices: [],
      saved_devices: [stored({ id: 4, uid: '4d41:00000004' }), stored({ id: 9, uid: '4d41:00000009', is_imported: true })],
    });
    calls.importRdmDevices.mockResolvedValue({ imported: 1 });
    const onImport = vi.fn();
    render(<RDMDiscovery rigId={RIG_ID} onImport={onImport} />);

    const pick = await screen.findByRole('checkbox', { name: 'Select 4d41:00000004' });
    // Already imported: shown, not pickable.
    expect((screen.getByRole('checkbox', { name: 'Select 4d41:00000009' }) as HTMLInputElement).disabled).toBe(true);
    fireEvent.click(pick);
    fireEvent.click(screen.getByRole('button', { name: /import selected \(1\)/i }));

    await waitFor(() => expect(calls.importRdmDevices).toHaveBeenCalledWith(RIG_ID, [4]));
    expect(await screen.findByText(/added 1 device to the rig/i)).toBeTruthy();
    expect(onImport).toHaveBeenCalledWith([4], 1);
  });

  it('says plainly that a scan finds nothing without an RDM interface', async () => {
    calls.devices.mockResolvedValue({ scanning: false, live_devices: [], saved_devices: [] });
    render(<RDMDiscovery rigId={RIG_ID} />);
    expect(await screen.findByText(/cannot talk to one yet/i)).toBeTruthy();
  });
});

describe('the QR scanner', () => {
  it('reads the scan route\'s answer', () => {
    expect(scanResultOf({ action: 'added', rig_fixture_id: 31, dmx_address: 17, message: 'Added Spot 3 at address 17' }, 5))
      .toEqual({ rig_fixture_id: 31, added: true, message: 'Added Spot 3 at address 17', timestamp: 5 });
    expect(scanResultOf({ action: 'identified', rig_fixture_id: 31, message: 'Fixture already in rig at address 17' }, 5).added)
      .toBe(false);
  });

  it('takes a typed code where the browser cannot read one from the camera', async () => {
    calls.scanQr.mockResolvedValue({ action: 'added', rig_fixture_id: 31, dmx_address: 17, message: 'Added Spot 3 at address 17' });
    const onScan = vi.fn();
    render(<QRScanner rigId={RIG_ID} open onClose={() => {}} onScan={onScan} />);

    // jsdom has no BarcodeDetector, as Chrome and Edge on Windows have none.
    expect(screen.getByText(/cannot read qr codes from the camera/i)).toBeTruthy();
    fireEvent.change(screen.getByRole('textbox', { name: 'QR code or fixture ID' }), { target: { value: ' 12 ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add' }));

    await waitFor(() => expect(calls.scanQr).toHaveBeenCalledWith(RIG_ID, '12'));
    expect(await screen.findAllByText('Added Spot 3 at address 17')).not.toHaveLength(0);
    expect(onScan).toHaveBeenCalledWith(31, true);
  });
});
