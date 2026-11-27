/**
 * A PDF stage plot, turned into a PNG in the browser (docs/STAGE_PLOT.md).
 *
 * The server takes images only: it has no PDF renderer. So a PDF chosen in
 * the Stage plot control is opened here with pdf.js (loaded lazily, see
 * pdfjsLoader.ts), one page is drawn on a canvas about 3000 px on its long
 * side, and that PNG goes up through the usual upload. The PNG is named after
 * the PDF and the page ("plot.pdf, page 2.png"), which the server keeps as
 * the plot's filename.
 *
 * Everything that can be worked out without a canvas is a plain function here,
 * so it is tested without one.
 */
import { loadPdfjs } from './pdfjsLoader';

/** The server's limit (backend MAX_STAGE_PLOT_BYTES). */
export const MAX_PNG_BYTES = 15 * 1024 * 1024;
/** The long side of the drawn page, in pixels: enough to read a fixture label on a plot. */
export const TARGET_LONG_SIDE_PX = 3000;
/** Below this the drawing is too coarse to calibrate against; give up rather than go smaller. */
export const MIN_LONG_SIDE_PX = 1000;
/** Draws of one page, each smaller than the one before, before giving up. */
export const MAX_DRAWS = 4;
/** A PNG's size goes roughly with its area; aim a little under the limit on the next draw. */
const SHRINK_MARGIN = 0.9;

export const PDF_TEXT = {
  empty: 'The PDF is empty (0 bytes). Export the stage plot again and choose the new file.',
  noPages: 'The PDF has no pages to show.',
  encrypted:
    'The PDF is password-protected, so it cannot be opened here. Save a copy without the password '
    + '(or export the page as a PNG or JPEG image) and choose that.',
  damaged:
    'The PDF is damaged or is not really a PDF, so it cannot be read. Export it again, or export the page '
    + 'as a PNG or JPEG image and upload that.',
  unreadable: 'The PDF could not be read. Export the page as a PNG or JPEG image and upload that.',
  drawFailed: 'The PDF page could not be drawn. Export the page as a PNG or JPEG image and upload that.',
  tooBig:
    'This page is too detailed to fit under 15 MB as an image, even at a lower resolution. '
    + 'Export the page as a JPEG image and upload that.',
  loadFailed: 'The PDF reader could not be loaded. Reload the app and try again.',
} as const;

/** A sentence for the operator, already said in PDF_TEXT. */
export class PdfStagePlotError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PdfStagePlotError';
  }
}

// Just what this file uses of pdf.js, so the tests can stand in for it.
export interface PdfViewport { width: number; height: number }
export interface PdfRenderTask { promise: Promise<unknown>; cancel?: () => void }
export interface PdfPageLike {
  getViewport(params: { scale: number }): PdfViewport;
  render(params: { canvasContext: CanvasRenderingContext2D; viewport: PdfViewport }): PdfRenderTask;
  cleanup?: () => unknown;
}
export interface PdfDocumentLike {
  numPages: number;
  getPage(pageNumber: number): Promise<PdfPageLike>;
  destroy(): unknown;
}
export interface PdfLib {
  getDocument(source: { data: Uint8Array; isEvalSupported?: boolean }): { promise: Promise<PdfDocumentLike> };
}

/** A PDF by its type or its name. The server sniffs the bytes, so one that slips past is still refused there. */
export function isPdfFile(file: File): boolean {
  return file.type === 'application/pdf' || /\.pdf$/i.test(file.name);
}

/** The operator's sentence for anything thrown while opening or drawing a PDF. */
export function pdfErrorText(error: unknown): string {
  if (error instanceof PdfStagePlotError) return error.message;
  const name = (error as { name?: unknown } | null)?.name;
  if (name === 'PasswordException') return PDF_TEXT.encrypted;
  if (name === 'InvalidPDFException' || name === 'FormatError') return PDF_TEXT.damaged;
  return PDF_TEXT.unreadable;
}

/** The PNG's name: the PDF's name and the page, cut to fit the server's 255 characters. */
export function pdfPageFileName(pdfName: string, pageNumber: number): string {
  const suffix = `, page ${pageNumber}.png`;
  const base = pdfName.trim() || 'stage plot.pdf';
  return base.slice(0, 255 - suffix.length) + suffix;
}

/** The scale that draws a page of this size (at scale 1) about TARGET_LONG_SIDE_PX on its long side. */
export function firstScale(width: number, height: number): number {
  const longSide = Math.max(width, height);
  return longSide > 0 ? TARGET_LONG_SIDE_PX / longSide : 1;
}

/** The next scale after a draw came out at `bytes`, over `limit`. */
export function smallerScale(scale: number, bytes: number, limit: number = MAX_PNG_BYTES): number {
  return scale * Math.sqrt(limit / bytes) * SHRINK_MARGIN;
}

/** Draws a page at a size and gives it back as a PNG. The browser's canvas, or a stand-in in tests. */
export type DrawPage = (page: PdfPageLike, viewport: PdfViewport, width: number, height: number) => Promise<Blob>;

export const drawOnCanvas: DrawPage = async (page, viewport, width, height) => {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  try {
    const context = canvas.getContext('2d');
    if (!context) throw new PdfStagePlotError(PDF_TEXT.drawFailed);
    // pdf.js paints the page white first, so the PNG has no see-through background.
    await page.render({ canvasContext: context, viewport }).promise;
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
    if (!blob) throw new PdfStagePlotError(PDF_TEXT.drawFailed);
    return blob;
  } finally {
    // Some browsers keep a big canvas's memory until it is shrunk.
    canvas.width = 0;
    canvas.height = 0;
  }
};

export interface DrawnPage { blob: Blob; width: number; height: number; scale: number }

/**
 * The page as a PNG about TARGET_LONG_SIDE_PX on its long side, drawn smaller
 * until it is within MAX_PNG_BYTES. PdfStagePlotError(tooBig) when it cannot be
 * within MAX_DRAWS draws or would go below MIN_LONG_SIDE_PX.
 */
export async function drawPageAsPng(page: PdfPageLike, draw: DrawPage = drawOnCanvas): Promise<DrawnPage> {
  const atOne = page.getViewport({ scale: 1 });
  let scale = firstScale(atOne.width, atOne.height);
  for (let tries = 0; tries < MAX_DRAWS; tries += 1) {
    const viewport = page.getViewport({ scale });
    const width = Math.max(1, Math.round(viewport.width));
    const height = Math.max(1, Math.round(viewport.height));
    if (tries > 0 && Math.max(width, height) < MIN_LONG_SIDE_PX) break;
    let blob: Blob;
    try {
      blob = await draw(page, viewport, width, height);
    } catch (error) {
      throw error instanceof PdfStagePlotError ? error : new PdfStagePlotError(PDF_TEXT.drawFailed);
    }
    if (blob.size <= MAX_PNG_BYTES) return { blob, width, height, scale };
    scale = smallerScale(scale, blob.size);
  }
  throw new PdfStagePlotError(PDF_TEXT.tooBig);
}

async function readBytes(file: Blob): Promise<Uint8Array> {
  if (typeof file.arrayBuffer === 'function') return new Uint8Array(await file.arrayBuffer());
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(file);
  });
}

/** The PDF opened, with at least one page. Throws; pdfErrorText says why in a sentence. */
export async function openPdf(file: File): Promise<PdfDocumentLike> {
  if (file.size === 0) throw new PdfStagePlotError(PDF_TEXT.empty);
  let lib: PdfLib;
  try {
    lib = await loadPdfjs();
  } catch {
    throw new PdfStagePlotError(PDF_TEXT.loadFailed);
  }
  const data = await readBytes(file);
  // No script in a PDF is run: pdf.js is told not to evaluate anything it finds.
  const doc = await lib.getDocument({ data, isEvalSupported: false }).promise;
  if (doc.numPages < 1) {
    void doc.destroy();
    throw new PdfStagePlotError(PDF_TEXT.noPages);
  }
  return doc;
}

/** One page of an open PDF as a PNG file named after the PDF and the page, ready for the upload. */
export async function pdfPageAsPngFile(
  doc: PdfDocumentLike,
  pageNumber: number,
  pdfName: string,
  draw: DrawPage = drawOnCanvas,
): Promise<File> {
  const page = await doc.getPage(pageNumber);
  try {
    const { blob } = await drawPageAsPng(page, draw);
    return new File([blob], pdfPageFileName(pdfName, pageNumber), { type: 'image/png' });
  } finally {
    page.cleanup?.();
  }
}
