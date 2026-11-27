// The Focus presets panel (docs/FOCUS_PRESETS.md, "In the app"): the targets with
// their place, reach and the heads that cannot reach them; adding a custom target
// (checked first, the server's refusal shown as it says it); removing one only
// after a confirm; the CSV through the authenticated client; and plain sentences
// for loading, no moving heads, and a table that cannot be read.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import FocusPresetsPanel from '../components/rig/FocusPresetsPanel';
import { focusPresetsApi } from '../services/focusPresetsApi';
import { saveBlob } from '../utils/download';
import { parseFocusPresets } from '../utils/focusPresets';
import { focusAnswer, noHeadsAnswer } from './focusPresetsFixture';

vi.mock('../services/focusPresetsApi', () => ({
  focusPresetsApi: { get: vi.fn(), csv: vi.fn(), addTarget: vi.fn(), removeTarget: vi.fn() },
}));
vi.mock('../services/stagePlotApi', () => ({
  refusalText: (error: unknown, fallback: string) => {
    const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
    return typeof detail === 'string' ? detail : fallback;
  },
}));
vi.mock('../utils/download', () => ({ saveBlob: vi.fn() }));

const api = vi.mocked(focusPresetsApi);
const save = vi.mocked(saveBlob);
const flush = async () => {
  for (let i = 0; i < 3; i += 1) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  }
};

const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  api.get.mockResolvedValue(parseFocusPresets(focusAnswer()));
});
afterEach(cleanup);

describe('FocusPresetsPanel', () => {
  it('says it is reading while the table is on its way', async () => {
    api.get.mockReturnValue(new Promise<never>(() => {}));
    render(<FocusPresetsPanel rigId={7} />);
    expect(screen.getByTestId('focus-presets-loading').textContent).toContain('Reading the focus presets');
  });

  it('lists every target with its place, whether it is default or custom, and who can reach it', async () => {
    render(<FocusPresetsPanel rigId={7} />);
    await flush();
    expect(api.get).toHaveBeenCalledWith(7);

    const booth = within(screen.getByTestId('focus-target-dj_booth'));
    expect(booth.getByText('DJ booth')).toBeTruthy();
    expect(booth.getByText('Default')).toBeTruthy();
    expect(booth.getByText('x 0, y 2.2, z -3.5 m')).toBeTruthy();
    expect(booth.getByTestId('focus-target-reach').textContent).toBe('2 of 3 moving heads can reach it.');
    // Default targets cannot be removed.
    expect(booth.queryByRole('button', { name: /remove/i })).toBeNull();

    // The heads that cannot reach it, behind a button.
    expect(booth.queryByText(/Spot 3: tilt would be/)).toBeNull();
    fireEvent.click(booth.getByRole('button', { name: 'Show the one that cannot' }));
    expect(booth.getByText('3. Spot 3: tilt would be 150 degrees; the head turns 135 each way')).toBeTruthy();

    const front = within(screen.getByTestId('focus-target-stage_front'));
    expect(front.getByTestId('focus-target-skipped').textContent).toBe(
      'Skipped: The room has no stage and no DJ booth. Add the stage as a raised area of kind stage.',
    );

    const mirror = within(screen.getByTestId('focus-target-custom_4'));
    expect(mirror.getByText('Custom')).toBeTruthy();
    expect(mirror.getByTestId('focus-target-reach').textContent).toBe('None of the 3 moving heads can reach it.');
    expect(mirror.getByRole('button', { name: 'Show the 3 that cannot' })).toBeTruthy();
    expect(mirror.getByRole('button', { name: 'Remove Mirror ball' })).toBeTruthy();

    expect(within(screen.getByTestId('focus-target-straight_down')).getByText('The floor under each head.')).toBeTruthy();
    expect(screen.getByTestId('focus-presets-left-out').textContent).toContain('Spot 9 (it has no position in the rig)');
    expect(screen.queryByTestId('focus-presets-empty')).toBeNull();
  });

  it('says so when the rig has no moving heads', async () => {
    api.get.mockResolvedValue(parseFocusPresets(noHeadsAnswer()));
    render(<FocusPresetsPanel rigId={7} />);
    await flush();
    expect(screen.getByTestId('focus-presets-empty').textContent).toContain('no moving heads with a position');
    expect(within(screen.getByTestId('focus-target-dance_floor')).getByTestId('focus-target-reach').textContent)
      .toBe('No moving heads to aim at it.');
  });

  it('adds a custom target as numbers, reads the table again and says so', async () => {
    api.addTarget.mockResolvedValue({ target: { id: 5 } });
    render(<FocusPresetsPanel rigId={7} />);
    await flush();

    type('Name', '  Bar  ');
    type('x (m)', '2,5');
    type('y (m)', '1.2');
    type('z (m)', '-4');
    fireEvent.click(screen.getByRole('button', { name: 'Add target' }));
    await flush();

    expect(api.addTarget).toHaveBeenCalledWith(7, { name: 'Bar', x: 2.5, y: 1.2, z: -4 });
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId('focus-presets-note').textContent).toBe('Bar added.');
    expect((screen.getByLabelText('Name') as HTMLInputElement).value).toBe('');
  });

  it('shows what is wrong with each field before asking the server', async () => {
    render(<FocusPresetsPanel rigId={7} />);
    await flush();

    type('x (m)', 'left');
    type('y (m)', '-1');
    fireEvent.click(screen.getByRole('button', { name: 'Add target' }));
    await flush();

    expect(api.addTarget).not.toHaveBeenCalled();
    expect(screen.getByText('Give the target a name.')).toBeTruthy();
    expect(screen.getByText('x must be a number of metres, like 1.5 or -2.')).toBeTruthy();
    expect(screen.getByText('y is height above the floor and cannot be below it.')).toBeTruthy();
    expect(screen.getByText('Give z in metres.')).toBeTruthy();

    // Typing in a field clears its sentence.
    type('x (m)', '1');
    expect(screen.queryByText('x must be a number of metres, like 1.5 or -2.')).toBeNull();
  });

  it("shows the server's refusal in its own words", async () => {
    api.addTarget.mockRejectedValue({ response: { status: 422, data: { detail: 'x must be a number of metres.' } } });
    render(<FocusPresetsPanel rigId={7} />);
    await flush();

    type('Name', 'Bar');
    type('x (m)', '1');
    type('y (m)', '1');
    type('z (m)', '1');
    fireEvent.click(screen.getByRole('button', { name: 'Add target' }));
    await flush();

    expect(screen.getByTestId('focus-target-form-error').textContent).toBe('x must be a number of metres.');
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  it('removes a custom target only after the confirm', async () => {
    api.removeTarget.mockResolvedValue({ removed: 4 });
    render(<FocusPresetsPanel rigId={7} />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Remove Mirror ball' }));
    expect(screen.getByText('Remove Mirror ball?')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Keep it' }));
    await flush();
    expect(api.removeTarget).not.toHaveBeenCalled();

    // hidden: the closing dialog may still have the page behind it aria-hidden for its exit transition.
    fireEvent.click(screen.getByRole('button', { name: 'Remove Mirror ball', hidden: true }));
    fireEvent.click(screen.getByTestId('focus-target-remove-confirm'));
    await flush();

    expect(api.removeTarget).toHaveBeenCalledWith(7, 4);
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId('focus-presets-note').textContent).toBe('Mirror ball removed.');
  });

  it('downloads the CSV through the authenticated client', async () => {
    api.csv.mockResolvedValue({ blob: new Blob(['target,']), filename: 'Club_focus-presets.csv' });
    render(<FocusPresetsPanel rigId={7} />);
    await flush();

    fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }));
    await flush();

    expect(api.csv).toHaveBeenCalledWith(7);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0][1]).toBe('Club_focus-presets.csv');
    expect(screen.getByTestId('focus-presets-note').textContent).toBe('Club_focus-presets.csv downloaded.');
  });

  it('says so when the CSV does not come, and saves nothing', async () => {
    api.csv.mockRejectedValue(new Error('network'));
    render(<FocusPresetsPanel rigId={7} />);
    await flush();
    fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }));
    await flush();
    expect(save).not.toHaveBeenCalled();
    expect(screen.getByTestId('focus-presets-note').textContent).toBe('The focus presets CSV did not download. Try again.');
  });

  it('says the table could not be read, and reads it again on Try again', async () => {
    api.get.mockRejectedValueOnce(new Error('500'));
    render(<FocusPresetsPanel rigId={7} />);
    await flush();

    expect(screen.getByTestId('focus-presets-error').textContent).toContain(
      'The focus presets could not be read. Check the connection and try again.',
    );
    expect(screen.queryByTestId('focus-presets-list')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await flush();
    expect(screen.queryByTestId('focus-presets-error')).toBeNull();
    expect(screen.getByTestId('focus-target-dj_booth')).toBeTruthy();
  });
});
