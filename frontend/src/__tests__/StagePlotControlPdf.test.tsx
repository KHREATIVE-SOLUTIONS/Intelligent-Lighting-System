// A PDF chosen in the Stage plot control: one page goes straight up as a PNG;
// more than one asks which page first (Prev/Next, a page number); an encrypted,
// damaged or empty PDF gets a plain sentence and nothing is uploaded; an image
// goes up as it always did. pdf.js is stood in for, the canvas is stubbed.
// docs/STAGE_PLOT.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import StagePlotControl from '../components/rig/StagePlotControl';
import type { StagePlotState } from '../components/rig/useStagePlot';
import { PDF_TEXT } from '../utils/pdfStagePlot';
import type { PdfDocumentLike, PdfPageLike } from '../utils/pdfStagePlot';

const loader = vi.hoisted(() => ({ loadPdfjs: vi.fn() }));
vi.mock('../utils/pdfjsLoader', () => loader);

function fakePlot(): StagePlotState {
  return {
    info: null, present: false, visible: true, opacity: 0.5, busy: false, message: null, calibrating: false,
    draft: { a: null, b: null, origin: null, distance: '', rotation: 0 }, step: 'a', draftProblem: null,
    underlay: null, onPlanPick: undefined, pickMarks: undefined,
    upload: vi.fn(async () => {}), remove: vi.fn(async () => {}), setVisible: vi.fn(), setOpacity: vi.fn(),
    commitOpacity: vi.fn(async () => {}), startCalibrate: vi.fn(), cancelCalibrate: vi.fn(), repick: vi.fn(),
    setDistance: vi.fn(), setRotation: vi.fn(), saveCalibration: vi.fn(async () => {}), clearMessage: vi.fn(),
  };
}

function fakePage(): PdfPageLike {
  return {
    getViewport: vi.fn(({ scale }: { scale: number }) => ({ width: 842 * scale, height: 595 * scale })),
    render: vi.fn(() => ({ promise: Promise.resolve(), cancel: vi.fn() })),
    cleanup: vi.fn(),
  };
}

function fakeDoc(numPages: number): PdfDocumentLike {
  return { numPages, getPage: vi.fn(async () => fakePage()), destroy: vi.fn(async () => {}) };
}

function pdfjsGives(result: PdfDocumentLike | Error) {
  const getDocument = vi.fn(() => ({
    promise: result instanceof Error ? Promise.reject(result) : Promise.resolve(result),
  }));
  loader.loadPdfjs.mockResolvedValue({ getDocument });
  return getDocument;
}

const named = (name: string) => Object.assign(new Error('pdf.js said no'), { name });
const pdfFile = (body: BlobPart[] = ['%PDF-1.7 ...'], name = 'venue.pdf') => new File(body, name, { type: 'application/pdf' });

function choose(file: File) {
  fireEvent.change(screen.getByTestId('stage-plot-file'), { target: { files: [file] } });
}

const uploaded = (plot: StagePlotState) => (plot.upload as ReturnType<typeof vi.fn>).mock.calls[0][0] as File;

describe('StagePlotControl with a PDF', () => {
  beforeEach(() => {
    // jsdom has no canvas: a context that pdf.js (stood in for) draws on, and a PNG out of it.
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({} as never);
    vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation(function toBlob(callback: BlobCallback) {
      callback(new Blob(['png bytes'], { type: 'image/png' }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    loader.loadPdfjs.mockReset();
  });

  it('uploads a one-page PDF as a PNG named after it, without asking for a page', async () => {
    const doc = fakeDoc(1);
    const getDocument = pdfjsGives(doc);
    const plot = fakePlot();
    render(<StagePlotControl plot={plot} />);

    choose(pdfFile());

    await waitFor(() => expect(plot.upload).toHaveBeenCalledTimes(1));
    const png = uploaded(plot);
    expect(png.type).toBe('image/png');
    expect(png.name).toBe('venue.pdf, page 1.png');
    expect(getDocument).toHaveBeenCalledTimes(1);
    expect(doc.getPage).toHaveBeenCalledWith(1);
    expect(doc.destroy).toHaveBeenCalled();
    expect(screen.queryByTestId('stage-plot-pdf-picker')).toBeNull();
    expect(screen.queryByTestId('stage-plot-pdf-error')).toBeNull();
  });

  it('asks which page of a longer PDF, with Prev, Next and a page number, and uploads that page', async () => {
    const doc = fakeDoc(3);
    pdfjsGives(doc);
    const plot = fakePlot();
    render(<StagePlotControl plot={plot} />);

    choose(pdfFile());

    expect(await screen.findByText('Which page is the stage plot?')).toBeTruthy();
    expect(screen.getByText(/venue\.pdf has 3 pages/)).toBeTruthy();
    const pageBox = screen.getByTestId('stage-plot-pdf-page') as HTMLInputElement;
    expect(pageBox.value).toBe('1');
    expect((screen.getByRole('button', { name: 'Prev' }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByTestId('stage-plot-pdf-preview')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(pageBox.value).toBe('2');
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(pageBox.value).toBe('3');
    expect((screen.getByRole('button', { name: 'Next' }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Prev' }));
    expect(pageBox.value).toBe('2');

    // A page the PDF does not have cannot be used.
    fireEvent.change(pageBox, { target: { value: '9' } });
    expect(screen.getByTestId('stage-plot-pdf-page-problem').textContent).toMatch(/1 to 3/);
    expect((screen.getByRole('button', { name: /^Use page/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(plot.upload).not.toHaveBeenCalled();

    fireEvent.change(pageBox, { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: 'Use page 3' }));

    await waitFor(() => expect(plot.upload).toHaveBeenCalledTimes(1));
    expect(uploaded(plot).name).toBe('venue.pdf, page 3.png');
    expect(doc.getPage).toHaveBeenLastCalledWith(3);
    expect(doc.destroy).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByTestId('stage-plot-pdf-picker')).toBeNull());
  });

  it('cancelling the page question uploads nothing and lets the PDF go', async () => {
    const doc = fakeDoc(2);
    pdfjsGives(doc);
    const plot = fakePlot();
    render(<StagePlotControl plot={plot} />);

    choose(pdfFile());
    await screen.findByText('Which page is the stage plot?');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(screen.queryByText('Which page is the stage plot?')).toBeNull());
    expect(plot.upload).not.toHaveBeenCalled();
    expect(doc.destroy).toHaveBeenCalled();
  });

  it.each([
    ['password-protected', () => pdfjsGives(named('PasswordException')), pdfFile(), PDF_TEXT.encrypted],
    ['damaged', () => pdfjsGives(named('InvalidPDFException')), pdfFile(), PDF_TEXT.damaged],
    ['empty', () => pdfjsGives(fakeDoc(1)), pdfFile([]), PDF_TEXT.empty],
    ['without pages', () => pdfjsGives(fakeDoc(0)), pdfFile(), PDF_TEXT.noPages],
  ])('says so in a sentence for a %s PDF, and uploads nothing', async (_what, arrange, file, text) => {
    arrange();
    const plot = fakePlot();
    render(<StagePlotControl plot={plot} />);

    choose(file);

    expect((await screen.findByTestId('stage-plot-pdf-error')).textContent).toBe(text);
    expect(plot.upload).not.toHaveBeenCalled();
    expect(screen.queryByTestId('stage-plot-converting')).toBeNull();
  });

  it('says the page could not be drawn when the browser gives no canvas', async () => {
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    pdfjsGives(fakeDoc(1));
    const plot = fakePlot();
    render(<StagePlotControl plot={plot} />);

    choose(pdfFile());

    expect((await screen.findByTestId('stage-plot-pdf-error')).textContent).toBe(PDF_TEXT.drawFailed);
    expect(plot.upload).not.toHaveBeenCalled();
  });

  it('sends an image as it is, at once, without loading pdf.js', () => {
    const plot = fakePlot();
    render(<StagePlotControl plot={plot} />);
    const photo = new File(['jpeg'], 'plot.jpg', { type: 'image/jpeg' });

    choose(photo);

    expect(plot.upload).toHaveBeenCalledWith(photo);
    expect(loader.loadPdfjs).not.toHaveBeenCalled();
  });
});
