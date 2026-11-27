// The "Stage plot" control over the 2D plan: upload, show or hide, calibrate
// (the step to click, the distance, rotation), and remove, which asks first.
// Driven by a stand-in for useStagePlot. docs/STAGE_PLOT.md.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import StagePlotControl, { PICK_TEXT, STAGE_PLOT_ACCEPT } from '../components/rig/StagePlotControl';
import type { StagePlotState } from '../components/rig/useStagePlot';

function fakePlot(over: Partial<StagePlotState> = {}): StagePlotState {
  return {
    info: null,
    present: false,
    visible: true,
    opacity: 0.5,
    busy: false,
    message: null,
    calibrating: false,
    draft: { a: null, b: null, origin: null, distance: '', rotation: 0 },
    step: 'a',
    draftProblem: null,
    underlay: null,
    onPlanPick: undefined,
    pickMarks: undefined,
    upload: vi.fn(async () => {}),
    remove: vi.fn(async () => {}),
    setVisible: vi.fn(),
    setOpacity: vi.fn(),
    commitOpacity: vi.fn(async () => {}),
    startCalibrate: vi.fn(),
    cancelCalibrate: vi.fn(),
    repick: vi.fn(),
    setDistance: vi.fn(),
    setRotation: vi.fn(),
    saveCalibration: vi.fn(async () => {}),
    clearMessage: vi.fn(),
    ...over,
  };
}

const PRESENT = {
  present: true,
  info: { rig_id: 3, present: true, width_px: 800, height_px: 600, calibration: null, transform: null },
};

describe('StagePlotControl', () => {
  afterEach(cleanup);

  it('offers an upload alone while the rig has no stage plot, and sends the file chosen', () => {
    const plot = fakePlot();
    render(<StagePlotControl plot={plot} />);
    expect(screen.getByRole('button', { name: 'Upload' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Remove' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Calibrate' })).toBeNull();
    const input = screen.getByTestId('stage-plot-file') as HTMLInputElement;
    // A PDF can be chosen, so the server's sentence about exporting it as an image is what the operator reads.
    expect(input.getAttribute('accept')).toBe(STAGE_PLOT_ACCEPT);
    expect(STAGE_PLOT_ACCEPT).toContain('application/pdf');
    const file = new File(['png'], 'plot.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });
    expect(plot.upload).toHaveBeenCalledWith(file);
  });

  it('with a plot: hide and show, and says it is not calibrated yet', () => {
    const plot = fakePlot(PRESENT);
    render(<StagePlotControl plot={plot} />);
    expect(screen.getByRole('button', { name: 'Replace' })).toBeTruthy();
    expect(screen.getByTestId('stage-plot-uncalibrated')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Hide' }));
    expect(plot.setVisible).toHaveBeenCalledWith(false);
    cleanup();
    const hidden = fakePlot({ ...PRESENT, visible: false });
    render(<StagePlotControl plot={hidden} />);
    fireEvent.click(screen.getByRole('button', { name: 'Show' }));
    expect(hidden.setVisible).toHaveBeenCalledWith(true);
  });

  it('asks before removing, and keeps the plot when told to', () => {
    const plot = fakePlot(PRESENT);
    render(<StagePlotControl plot={plot} />);
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
    expect(screen.getByText('Remove the stage plot?')).toBeTruthy();
    expect(plot.remove).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Keep it' }));
    expect(plot.remove).not.toHaveBeenCalled();
  });

  it('removes once the question is answered yes', () => {
    const plot = fakePlot(PRESENT);
    render(<StagePlotControl plot={plot} />);
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
    fireEvent.click(screen.getByTestId('stage-plot-remove-confirm'));
    expect(plot.remove).toHaveBeenCalledTimes(1);
  });

  it('starts calibrating, and says which point to click', () => {
    const plot = fakePlot(PRESENT);
    render(<StagePlotControl plot={plot} />);
    fireEvent.click(screen.getByRole('button', { name: 'Calibrate' }));
    expect(plot.startCalibrate).toHaveBeenCalled();
    cleanup();
    render(<StagePlotControl plot={fakePlot({ ...PRESENT, calibrating: true, step: 'origin', draftProblem: 'x' })} />);
    expect(screen.getByTestId('stage-plot-step').textContent).toBe(PICK_TEXT.origin);
  });

  it('takes the distance and the rotation, and saves only once the draft can be used', () => {
    const waiting = fakePlot({ ...PRESENT, calibrating: true, step: 'done', draftProblem: 'The distance must be more than 0 and at most 1000 metres.' });
    render(<StagePlotControl plot={waiting} />);
    expect((screen.getByRole('button', { name: 'Save calibration' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId('stage-plot-problem').textContent).toMatch(/distance/);
    fireEvent.change(screen.getByTestId('stage-plot-distance'), { target: { value: '4.5' } });
    expect(waiting.setDistance).toHaveBeenCalledWith('4.5');
    fireEvent.click(screen.getByRole('button', { name: 'Pick again' }));
    expect(waiting.repick).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(waiting.cancelCalibrate).toHaveBeenCalled();
    cleanup();

    const ready = fakePlot({ ...PRESENT, calibrating: true, step: 'done', draftProblem: null });
    render(<StagePlotControl plot={ready} />);
    fireEvent.click(screen.getByRole('button', { name: 'Save calibration' }));
    expect(ready.saveCalibration).toHaveBeenCalled();
    expect(screen.queryByTestId('stage-plot-problem')).toBeNull();
  });

  it('shows the server\'s sentence when something was refused', () => {
    render(<StagePlotControl plot={fakePlot({ message: { severity: 'error', text: 'A PDF stage plot cannot be read here.' } })} />);
    expect(screen.getByTestId('stage-plot-message').textContent).toContain('A PDF stage plot cannot be read here.');
  });
});
