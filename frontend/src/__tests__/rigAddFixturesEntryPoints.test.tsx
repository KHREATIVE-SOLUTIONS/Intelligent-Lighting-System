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
import QRScanner, { labelsErrorOf, scanResultOf } from '../components/rig/QRScanner';
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
    // Named by their text: the tooltips describe them (describeChild), they do not rename them.
    fireEvent.click(screen.getByRole('button', { name: 'Discover RDM' }));
    fireEvent.click(screen.getByRole('button', { name: 'Scan QR' }));
    expect(onDiscoverRdm).toHaveBeenCalledTimes(1);
    expect(onScanQr).toHaveBeenCalledTimes(1);
  });

  it('leaves both out where no handler is given', () => {
    toolbar();
    expect(screen.queryByText('Discover RDM')).toBeNull();
    expect(screen.queryByText('Scan QR')).toBeNull();
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
    // Called once the list has been read again, which can be after the message shows.
    await waitFor(() => expect(onImport).toHaveBeenCalledWith([4], 1));
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
    await waitFor(() => expect(onScan).toHaveBeenCalledWith(31, true));
  });
});

describe('Generate Labels', () => {
  // An axios error as the client gives it for a blob request: the body is a Blob.
  const blobError = (body: string, type = 'application/json') => ({
    isAxiosError: true,
    response: { status: 404, data: new Blob([body], { type }) },
  });

  let created: Blob[];
  let downloads: string[];
  const realCreate = URL.createObjectURL;
  const realRevoke = URL.revokeObjectURL;
  const realClick = HTMLAnchorElement.prototype.click;
  beforeEach(() => {
    created = [];
    downloads = [];
    URL.createObjectURL = vi.fn((b: Blob) => { created.push(b); return 'blob:labels'; }) as typeof URL.createObjectURL;
    URL.revokeObjectURL = vi.fn();
    HTMLAnchorElement.prototype.click = function click(this: HTMLAnchorElement) { downloads.push(this.download); };
  });
  afterEach(() => {
    URL.createObjectURL = realCreate;
    URL.revokeObjectURL = realRevoke;
    HTMLAnchorElement.prototype.click = realClick;
  });

  it('reads the route\'s detail out of an error blob', async () => {
    expect(await labelsErrorOf(blobError('{"detail":"Rig not found"}'))).toBe('Rig not found');
    expect(await labelsErrorOf(blobError('{"detail":[{"msg":"String should match pattern"}]}')))
      .toBe('String should match pattern');
    expect(await labelsErrorOf(blobError('Internal Server Error', 'text/plain'))).toBe('Internal Server Error');
    expect(await labelsErrorOf(blobError(''))).toBe('Failed to generate labels.');
    expect(await labelsErrorOf(new Error('offline'))).toBe('Failed to generate labels.');
  });

  it('saves the PDF the route answers as rig_N_labels.pdf', async () => {
    const pdf = new Blob(['%PDF-1.4'], { type: 'application/pdf' });
    calls.labelsPdf.mockResolvedValue(pdf);
    render(<QRScanner rigId={RIG_ID} open onClose={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Generate Labels' }));
    await waitFor(() => expect(downloads).toEqual(['rig_7_labels.pdf']));
    expect(calls.labelsPdf).toHaveBeenCalledWith(RIG_ID);
    expect(created).toEqual([pdf]);
  });

  it('still saves JSON as .json', async () => {
    calls.labelsPdf.mockResolvedValue(new Blob(['{}'], { type: 'application/json' }));
    render(<QRScanner rigId={RIG_ID} open onClose={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Generate Labels' }));
    await waitFor(() => expect(downloads).toEqual(['rig_7_labels.json']));
  });

  it('shows the route\'s own message when it refuses', async () => {
    calls.labelsPdf.mockRejectedValue(blobError('{"detail":"Rig not found"}'));
    render(<QRScanner rigId={RIG_ID} open onClose={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Generate Labels' }));
    expect(await screen.findByText('Rig not found')).toBeTruthy();
    expect(downloads).toEqual([]);
  });
});
