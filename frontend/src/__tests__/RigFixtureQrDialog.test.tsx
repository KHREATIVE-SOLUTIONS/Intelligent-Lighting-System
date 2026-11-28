import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import RigFixtureQrDialog from '../components/rig/RigFixtureQrDialog';
import PatchTable from '../components/rig/PatchTable';
import { rigsApi } from '../services/api';
import type { RigFixture } from '../types';

vi.mock('../services/api', () => ({
  rigsApi: { rigFixtureQrPng: vi.fn() },
}));

const api = vi.mocked(rigsApi);
const flush = () => act(async () => {});
const BLOB_URL = 'blob:http://localhost/qr-7-12';

describe('RigFixtureQrDialog', () => {
  let createObjectURL: ReturnType<typeof vi.fn>;
  let revokeObjectURL: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    createObjectURL = vi.fn(() => BLOB_URL);
    revokeObjectURL = vi.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });
    api.rigFixtureQrPng.mockResolvedValue(new Blob(['png'], { type: 'image/png' }));
  });
  afterEach(cleanup);

  it('shows the rig fixture PNG from the backend route, titled and with alt text', async () => {
    render(<RigFixtureQrDialog rigId={7} fixture={{ id: 12, name: 'Spot SL' }} onClose={() => {}} />);
    await flush();

    expect(api.rigFixtureQrPng).toHaveBeenCalledWith(7, 12);
    const dialog = screen.getByRole('dialog', { name: 'QR label: Spot SL' });
    expect(dialog).toBeTruthy();
    const img = screen.getByRole('img', { name: 'QR code label for Spot SL' }) as HTMLImageElement;
    expect(img.getAttribute('src')).toBe(BLOB_URL);
  });

  it('offers the PNG as a download named for the rig fixture', async () => {
    render(<RigFixtureQrDialog rigId={7} fixture={{ id: 12, name: 'Spot SL' }} onClose={() => {}} />);
    await flush();

    const link = screen.getByRole('link', { name: 'Download PNG' });
    expect(link.getAttribute('href')).toBe(BLOB_URL);
    expect(link.getAttribute('download')).toBe('rig_7_fixture_12_qr.png');
  });

  it('closes on Escape and frees the image', async () => {
    const onClose = vi.fn();
    const { rerender } = render(
      <RigFixtureQrDialog rigId={7} fixture={{ id: 12, name: 'Spot SL' }} onClose={onClose} />,
    );
    await flush();

    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);

    rerender(<RigFixtureQrDialog rigId={7} fixture={null} onClose={onClose} />);
    await flush();
    expect(revokeObjectURL).toHaveBeenCalledWith(BLOB_URL);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('says so when the PNG cannot be loaded', async () => {
    api.rigFixtureQrPng.mockRejectedValueOnce(new Error('404'));
    render(<RigFixtureQrDialog rigId={7} fixture={{ id: 99 }} onClose={() => {}} />);
    await flush();

    expect(screen.getByText('Could not load the QR code.')).toBeTruthy();
    expect(screen.queryByRole('img', { name: /QR code label/ })).toBeNull();
  });
});

describe('PatchTable Show QR', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(URL, { createObjectURL: vi.fn(() => BLOB_URL), revokeObjectURL: vi.fn() });
    api.rigFixtureQrPng.mockResolvedValue(new Blob(['png'], { type: 'image/png' }));
  });
  afterEach(cleanup);

  const fixtures = [
    { id: 12, rig_id: 7, fixture_id: 3, universe: 0, dmx_address: 1, name: 'Spot SL' },
    { id: 13, rig_id: 7, fixture_id: 3, universe: 0, dmx_address: 17, name: 'Spot SR' },
  ] as unknown as RigFixture[];

  it('opens the dialog for the row it is on', async () => {
    render(<PatchTable fixtures={fixtures} rigId={7} />);
    fireEvent.click(screen.getByRole('button', { name: 'Show QR for Spot SR' }));
    await flush();

    expect(api.rigFixtureQrPng).toHaveBeenCalledWith(7, 13);
    expect(screen.getByRole('dialog', { name: 'QR label: Spot SR' })).toBeTruthy();
  });

  it('has no Show QR action without a rig', () => {
    render(<PatchTable fixtures={fixtures} />);
    expect(screen.queryByRole('button', { name: /Show QR/ })).toBeNull();
  });
});
