import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import ActivateRigButton, { activateRig } from '../components/rig/ActivateRigButton';

// What the box sends back when it refuses a rig.
const refusal = (detail: unknown) => ({ response: { status: 422, data: { detail } } });

describe('activateRig', () => {
  it('says the rig is live and that no restart is needed', async () => {
    const feedback = await activateRig(4, async () => ({ name: 'Main room', live: true, fixtures: [1, 2, 3] }));

    expect(feedback.severity).toBe('success');
    expect(feedback.message).toBe('"Main room" is live with 3 fixtures. No restart needed.');
  });

  it('says so when the rig was marked active but could not go on stage', async () => {
    const feedback = await activateRig(4, async () => ({ name: 'Empty', live: false, fixtures: [] }));

    expect(feedback.severity).toBe('info');
    expect(feedback.message).toContain('no fixtures to drive');
    expect(feedback.message).toContain('stays on its current rig');
  });

  it("passes on the box's reason when the rig is refused", async () => {
    const reason = "Rig 'Patio' was not activated and the show is unchanged. Fix this first: 'Spot 2' at 10-25 overlaps 'Spot 1' at 1-16 on universe 0";
    const feedback = await activateRig(4, () => Promise.reject(refusal(reason)));

    expect(feedback).toEqual({ severity: 'error', message: reason });
  });

  it('still says the show is unchanged when the box gives no reason', async () => {
    const feedback = await activateRig(4, () => Promise.reject(new Error('Network Error')));

    expect(feedback.severity).toBe('error');
    expect(feedback.message).toContain('still on the rig it had');
  });
});

describe('ActivateRigButton', () => {
  afterEach(cleanup);

  it('is there for a rig that is not active, and activates it', async () => {
    const activate = vi.fn(async () => ({ name: 'Main room', live: true, fixtures: [1, 2] }));
    const refreshStatus = vi.fn(async () => {});
    const onDone = vi.fn();
    render(
      <ActivateRigButton rigId={7} isActive={false} activate={activate} refreshStatus={refreshStatus} onDone={onDone} />
    );

    const button = screen.getByTestId('activate-rig-7');
    expect(button.textContent).toContain('Activate');
    fireEvent.click(button);

    await waitFor(() => expect(screen.getByTestId('activate-rig-feedback')).toBeTruthy());
    expect(activate).toHaveBeenCalledWith(7);
    expect(screen.getByTestId('activate-rig-feedback').textContent).toContain('"Main room" is live with 2 fixtures');
    // The engine's status is read again at once, which is what the 3D view follows.
    expect(refreshStatus).toHaveBeenCalledTimes(1);
    expect(onDone).toHaveBeenCalledWith(expect.objectContaining({ severity: 'success' }));
  });

  it('stays visible on the active rig, to apply its edits', () => {
    render(<ActivateRigButton rigId={7} isActive activate={vi.fn()} refreshStatus={vi.fn()} />);

    const button = screen.getByTestId('activate-rig-7');
    expect(button.textContent).toContain('Apply to show');
    expect((button as HTMLButtonElement).disabled).toBe(false);
  });

  it('shows why a rig was refused and does not report a change', async () => {
    const activate = vi.fn(() => Promise.reject(refusal("Rig 'Patio' was not activated and the show is unchanged.")));
    const refreshStatus = vi.fn(async () => {});
    render(<ActivateRigButton rigId={9} isActive={false} activate={activate} refreshStatus={refreshStatus} />);

    fireEvent.click(screen.getByTestId('activate-rig-9'));

    await waitFor(() => expect(screen.getByTestId('activate-rig-feedback')).toBeTruthy());
    expect(screen.getByTestId('activate-rig-feedback').textContent).toContain('was not activated');
    expect(refreshStatus).not.toHaveBeenCalled();
    // Ready to be pressed again once the rig is fixed.
    expect((screen.getByTestId('activate-rig-9') as HTMLButtonElement).disabled).toBe(false);
  });
});
