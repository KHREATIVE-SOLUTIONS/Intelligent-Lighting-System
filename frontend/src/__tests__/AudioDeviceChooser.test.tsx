import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import AudioDeviceChooser, {
  pickInitialDevice,
  sortCaptureDevices,
} from '../components/common/AudioDeviceChooser';
import { audioApi, type AudioCaptureDevice } from '../services/api';

vi.mock('../services/api', () => ({
  audioApi: {
    getCaptureDevices: vi.fn(),
    getCaptureStatus: vi.fn(),
    startCapture: vi.fn(),
    stopCapture: vi.fn(),
  },
}));

const api = vi.mocked(audioApi);

const device = (
  index: number,
  name: string,
  hostapi: string,
  extra: Partial<AudioCaptureDevice> = {}
): AudioCaptureDevice => ({
  index,
  name,
  hostapi,
  max_input_channels: 2,
  max_output_channels: 0,
  is_loopback: false,
  device_type: 'sounddevice',
  platform: 'win32',
  ...extra,
});

// What a Windows laptop with a USB interface plugged in reports: the loopback
// of its speakers, then the interface's line-in once per host API.
const WINDOWS_DEVICES: AudioCaptureDevice[] = [
  device(0, 'Speakers (Realtek Audio) [Loopback]', 'WASAPI Loopback (pyaudiowpatch)', {
    is_loopback: true,
    device_type: 'pyaudio_loopback',
  }),
  device(1, 'Line In (USB Audio CODEC)', 'MME'),
  device(2, 'Speakers (Realtek Audio)', 'MME', { max_input_channels: 0, max_output_channels: 2 }),
  device(3, 'Line In (USB Audio CODEC)', 'Windows DirectSound'),
  device(4, 'Line In (USB Audio CODEC)', 'Windows WASAPI'),
  device(5, 'Line In (USB Audio CODEC)', 'Windows WDM-KS'),
  device(6, 'Stereo Mix (Realtek Audio)', 'Windows WASAPI', { is_loopback: true }),
];

const idle = { running: false, available: true, device_index: null, device_name: null, capture_method: 'none' };

describe('sortCaptureDevices', () => {
  it('offers a Windows line-in once, through a host API that shares the device', () => {
    const { inputs, loopback } = sortCaptureDevices(WINDOWS_DEVICES);

    expect(inputs.map((d) => d.index)).toEqual([4]);
    expect(loopback.map((d) => d.index)).toEqual([0]);
  });

  it('never offers kernel streaming or ASIO, even with no WASAPI entry', () => {
    const { inputs } = sortCaptureDevices([
      device(1, 'Line In (USB Audio CODEC)', 'MME'),
      device(2, 'Line In (USB Audio CODEC)', 'Windows WDM-KS'),
      device(3, 'Mixer ASIO', 'ASIO'),
    ]);

    expect(inputs.map((d) => d.index)).toEqual([1]);
  });

  it('leaves other platforms alone', () => {
    const mac = [
      device(0, 'Scarlett 2i2 USB', 'Core Audio', { platform: 'darwin' }),
      device(1, 'BlackHole 2ch', 'Core Audio', { platform: 'darwin', is_loopback: true }),
    ];
    const { inputs, loopback } = sortCaptureDevices(mac);

    expect(inputs.map((d) => d.index)).toEqual([0]);
    expect(loopback.map((d) => d.index)).toEqual([1]);
  });
});

describe('pickInitialDevice', () => {
  const all = [WINDOWS_DEVICES[4], WINDOWS_DEVICES[0]];

  it('opens on the device the box remembers, ahead of this browser', () => {
    const picked = pickInitialDevice(
      all,
      { name: 'Speakers (Realtek Audio) [Loopback]', hostapi: 'WASAPI Loopback (pyaudiowpatch)' },
      'Line In (USB Audio CODEC)'
    );

    expect(picked?.index).toBe(0);
  });

  it('falls back to what this browser last started', () => {
    expect(pickInitialDevice(all, {}, 'Line In (USB Audio CODEC)')?.index).toBe(4);
  });

  it('keeps loopback as the Windows default when nothing is remembered', () => {
    // Inputs are listed first, but a line-in has to be picked on purpose.
    expect(pickInitialDevice(all, {}, null)?.index).toBe(0);
    expect(pickInitialDevice(all, { name: 'Unplugged thing' }, null)?.index).toBe(0);
  });

  it('opens on the first device on other platforms, as before', () => {
    const mac = [
      device(0, 'Scarlett 2i2 USB', 'Core Audio', { platform: 'darwin' }),
      device(1, 'BlackHole 2ch', 'Core Audio', { platform: 'darwin', is_loopback: true }),
    ];

    expect(pickInitialDevice(mac, {}, null)?.index).toBe(0);
  });
});

describe('AudioDeviceChooser', () => {
  beforeEach(() => {
    window.localStorage.clear();
    api.getCaptureDevices.mockResolvedValue(WINDOWS_DEVICES);
    api.startCapture.mockResolvedValue({ status: 'started' });
  });
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('restores the remembered line-in and starts capture from it', async () => {
    api.getCaptureStatus.mockResolvedValue({
      ...idle,
      remembered_device: 'Line In (USB Audio CODEC)',
      remembered_hostapi: 'Windows WASAPI',
    });
    render(<AudioDeviceChooser />);

    await screen.findByText('Line In (USB Audio CODEC)');
    fireEvent.click(screen.getByRole('button', { name: /start capture/i }));

    await waitFor(() => expect(api.startCapture).toHaveBeenCalledWith(4));
  });

  it('restores loopback when that is what was last used', async () => {
    api.getCaptureStatus.mockResolvedValue({
      ...idle,
      remembered_device: 'Speakers (Realtek Audio) [Loopback]',
      remembered_hostapi: 'WASAPI Loopback (pyaudiowpatch)',
    });
    render(<AudioDeviceChooser />);

    await screen.findByText('Speakers (Realtek Audio) [Loopback]');
    fireEvent.click(screen.getByRole('button', { name: /start capture/i }));

    await waitFor(() => expect(api.startCapture).toHaveBeenCalledWith(0));
  });

  it('starts from loopback when nothing was ever picked', async () => {
    api.getCaptureStatus.mockResolvedValue(idle);
    render(<AudioDeviceChooser />);

    await screen.findByText('Speakers (Realtek Audio) [Loopback]');
    fireEvent.click(screen.getByRole('button', { name: /start capture/i }));

    await waitFor(() => expect(api.startCapture).toHaveBeenCalledWith(0));
  });

  it('lists the line-in and the loopback device together', async () => {
    api.getCaptureStatus.mockResolvedValue(idle);
    render(<AudioDeviceChooser />);

    // Nothing remembered: it opens on loopback once the list arrives.
    await screen.findByText('Speakers (Realtek Audio) [Loopback]');
    fireEvent.mouseDown(screen.getByRole('combobox'));

    const options = (await screen.findAllByRole('option')).map((o) => o.textContent);
    expect(options).toContain('Line In (USB Audio CODEC)');
    expect(options).toContain('Speakers (Realtek Audio) [Loopback]');
    expect(options.filter((o) => o === 'Line In (USB Audio CODEC)')).toHaveLength(1);
  });
});
