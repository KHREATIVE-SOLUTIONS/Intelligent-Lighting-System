// A PDF stage plot drawn as a PNG in the browser: which files are PDFs, the
// sentence for each way a PDF fails, the PNG's name, and the scale (about
// 3000 px on the long side, smaller until the PNG is within the server's
// 15 MB). pdf.js is stood in for. docs/STAGE_PLOT.md.
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  MAX_DRAWS, MAX_PNG_BYTES, MIN_LONG_SIDE_PX, PDF_TEXT, PdfStagePlotError, TARGET_LONG_SIDE_PX,
  drawPageAsPng, firstScale, isPdfFile, openPdf, pdfErrorText, pdfPageAsPngFile, pdfPageFileName, smallerScale,
} from '../utils/pdfStagePlot';
import type { DrawPage, PdfDocumentLike, PdfPageLike } from '../utils/pdfStagePlot';

const loader = vi.hoisted(() => ({ loadPdfjs: vi.fn() }));
vi.mock('../utils/pdfjsLoader', () => loader);

// A4 landscape, in PDF points.
const A4_W = 842;
const A4_H = 595;

function fakePage(width = A4_W, height = A4_H): PdfPageLike {
  return {
    getViewport: vi.fn(({ scale }: { scale: number }) => ({ width: width * scale, height: height * scale })),
    render: vi.fn(() => ({ promise: Promise.resolve() })),
    cleanup: vi.fn(),
  };
}

function fakeDoc(numPages: number, page: PdfPageLike = fakePage()): PdfDocumentLike {
  return { numPages, getPage: vi.fn(async () => page), destroy: vi.fn(async () => {}) };
}

/** A draw whose PNG is `bytesPerPixel` for every pixel. */
function drawSized(bytesPerPixel: number) {
  return vi.fn<Parameters<DrawPage>, ReturnType<DrawPage>>(
    async (_page, _viewport, width, height) => ({ size: width * height * bytesPerPixel }) as Blob,
  );
}

const pdfFile = (body: BlobPart[] = ['%PDF-1.7 ...'], name = 'venue.pdf') => new File(body, name, { type: 'application/pdf' });
const named = (name: string) => Object.assign(new Error('pdf.js said no'), { name });

describe('which files are PDFs', () => {
  it('by type or by name, whatever the case of the extension', () => {
    expect(isPdfFile(pdfFile())).toBe(true);
    expect(isPdfFile(new File(['x'], 'PLOT.PDF', { type: '' }))).toBe(true);
    expect(isPdfFile(new File(['x'], 'plot', { type: 'application/pdf' }))).toBe(true);
    expect(isPdfFile(new File(['x'], 'plot.png', { type: 'image/png' }))).toBe(false);
    expect(isPdfFile(new File(['x'], 'plot.pdf.jpg', { type: 'image/jpeg' }))).toBe(false);
  });
});

describe('the sentence for a PDF that cannot be used', () => {
  it('says password-protected, damaged, or could not be read', () => {
    expect(pdfErrorText(named('PasswordException'))).toBe(PDF_TEXT.encrypted);
    expect(pdfErrorText(named('InvalidPDFException'))).toBe(PDF_TEXT.damaged);
    expect(pdfErrorText(named('FormatError'))).toBe(PDF_TEXT.damaged);
    expect(pdfErrorText(new Error('something else'))).toBe(PDF_TEXT.unreadable);
    expect(pdfErrorText(undefined)).toBe(PDF_TEXT.unreadable);
    expect(pdfErrorText(new PdfStagePlotError(PDF_TEXT.empty))).toBe(PDF_TEXT.empty);
    expect(PDF_TEXT.encrypted).toMatch(/password/);
    expect(PDF_TEXT.damaged).toMatch(/damaged/);
    expect(PDF_TEXT.empty).toMatch(/empty/);
  });
});

describe('the PNG made from a page', () => {
  it('is named after the PDF and the page, within 255 characters', () => {
    expect(pdfPageFileName('venue.pdf', 2)).toBe('venue.pdf, page 2.png');
    expect(pdfPageFileName('  ', 1)).toBe('stage plot.pdf, page 1.png');
    const long = pdfPageFileName(`${'x'.repeat(300)}.pdf`, 12);
    expect(long.length).toBe(255);
    expect(long.endsWith(', page 12.png')).toBe(true);
  });

  it('is a PNG file of the drawn page, and the page is let go after', async () => {
    const page = fakePage();
    const doc = fakeDoc(3, page);
    const draw = vi.fn<Parameters<DrawPage>, ReturnType<DrawPage>>(async () => new Blob(['png'], { type: 'image/png' }));

    const file = await pdfPageAsPngFile(doc, 3, 'venue.pdf', draw);

    expect(doc.getPage).toHaveBeenCalledWith(3);
    expect(file.type).toBe('image/png');
    expect(file.name).toBe('venue.pdf, page 3.png');
    expect(file.size).toBe(3);
    expect(page.cleanup).toHaveBeenCalled();
  });
});

describe('the scale a page is drawn at', () => {
  it('puts the long side at about 3000 px, landscape or portrait', () => {
    expect(firstScale(A4_W, A4_H) * A4_W).toBeCloseTo(TARGET_LONG_SIDE_PX);
    expect(firstScale(A4_H, A4_W) * A4_W).toBeCloseTo(TARGET_LONG_SIDE_PX);
    expect(firstScale(0, 0)).toBe(1);
  });

  it('shrinks by the square root of how far over the limit, and a little more', () => {
    // Four times the limit: half the scale, then 0.9 of that.
    expect(smallerScale(2, MAX_PNG_BYTES * 4)).toBeCloseTo(2 * 0.5 * 0.9);
  });

  it('draws once at 3000 px when the PNG is within 15 MB', async () => {
    const draw = drawSized(1);

    const drawn = await drawPageAsPng(fakePage(), draw);

    expect(draw).toHaveBeenCalledTimes(1);
    // 595 points at 3000 / 842 px a point.
    expect(drawn.height).toBe(2120);
    expect(drawn.width).toBe(3000);
    expect(drawn.blob.size).toBeLessThanOrEqual(MAX_PNG_BYTES);
  });

  it('draws smaller when the PNG would be over 15 MB, and uploads the one within it', async () => {
    // 3000 x 2120 x 4 bytes is about 25 MB.
    const draw = drawSized(4);

    const drawn = await drawPageAsPng(fakePage(), draw);

    expect(draw).toHaveBeenCalledTimes(2);
    const [, , firstWidth] = draw.mock.calls[0];
    const [, , secondWidth, secondHeight] = draw.mock.calls[1];
    expect(firstWidth).toBe(3000);
    expect(secondWidth).toBeLessThan(3000);
    expect(secondWidth).toBeGreaterThan(MIN_LONG_SIDE_PX);
    expect(drawn.height).toBe(secondHeight);
    expect(drawn.width).toBe(secondWidth);
    expect(drawn.blob.size).toBeLessThanOrEqual(MAX_PNG_BYTES);
    expect(drawn.width).toBe(Math.round(A4_W * drawn.scale));
  });

  it('gives up with a sentence after a few draws that stay over 15 MB', async () => {
    const draw = vi.fn<Parameters<DrawPage>, ReturnType<DrawPage>>(async () => ({ size: MAX_PNG_BYTES + 5_000_000 }) as Blob);

    await expect(drawPageAsPng(fakePage(), draw)).rejects.toThrow(PDF_TEXT.tooBig);
    expect(draw).toHaveBeenCalledTimes(MAX_DRAWS);
  });

  it('gives up rather than draw below 1000 px on the long side', async () => {
    // So far over that the next scale would be tiny.
    const draw = drawSized(1000);

    await expect(drawPageAsPng(fakePage(), draw)).rejects.toThrow(PDF_TEXT.tooBig);
    expect(draw).toHaveBeenCalledTimes(1);
  });

  it('says the page could not be drawn when the canvas fails', async () => {
    const draw = vi.fn<Parameters<DrawPage>, ReturnType<DrawPage>>(async () => { throw new Error('no canvas'); });

    await expect(drawPageAsPng(fakePage(), draw)).rejects.toThrow(PDF_TEXT.drawFailed);
  });
});

describe('opening a PDF', () => {
  afterEach(() => { loader.loadPdfjs.mockReset(); });

  it('refuses an empty file without loading pdf.js', async () => {
    await expect(openPdf(pdfFile([]))).rejects.toThrow(PDF_TEXT.empty);
    expect(loader.loadPdfjs).not.toHaveBeenCalled();
  });

  it('says so when pdf.js cannot be loaded', async () => {
    loader.loadPdfjs.mockRejectedValue(new Error('chunk failed'));

    await expect(openPdf(pdfFile())).rejects.toThrow(PDF_TEXT.loadFailed);
  });

  it('gives pdf.js the bytes, with script evaluation off', async () => {
    const doc = fakeDoc(2);
    const getDocument = vi.fn(() => ({ promise: Promise.resolve(doc) }));
    loader.loadPdfjs.mockResolvedValue({ getDocument });

    expect(await openPdf(pdfFile(['%PDF-1.7']))).toBe(doc);

    const [source] = getDocument.mock.calls[0] as unknown as [{ data: Uint8Array; isEvalSupported: boolean }];
    expect(source.isEvalSupported).toBe(false);
    expect(new TextDecoder().decode(source.data)).toBe('%PDF-1.7');
  });

  it('refuses a PDF with no pages, and lets it go', async () => {
    const doc = fakeDoc(0);
    loader.loadPdfjs.mockResolvedValue({ getDocument: () => ({ promise: Promise.resolve(doc) }) });

    await expect(openPdf(pdfFile())).rejects.toThrow(PDF_TEXT.noPages);
    expect(doc.destroy).toHaveBeenCalled();
  });

  it('passes on what pdf.js threw for an encrypted PDF, for pdfErrorText to say', async () => {
    loader.loadPdfjs.mockResolvedValue({ getDocument: () => ({ promise: Promise.reject(named('PasswordException')) }) });

    const error = await openPdf(pdfFile()).catch((e: unknown) => e);
    expect(pdfErrorText(error)).toBe(PDF_TEXT.encrypted);
  });
});
