/**
 * pdf.js, loaded only when a PDF stage plot is chosen (docs/STAGE_PLOT.md).
 *
 * The library and its worker are imported lazily, so the app's first load and
 * every test that does not pick a PDF never touch them; the tests mock this
 * module. The worker is the copy bundled by Vite (`?url` gives its built
 * address), so nothing is fetched from the network.
 */
import type { PdfLib } from './pdfStagePlot';

let loading: Promise<PdfLib> | null = null;

export function loadPdfjs(): Promise<PdfLib> {
  if (!loading) {
    loading = (async () => {
      const [lib, worker] = await Promise.all([
        import('pdfjs-dist'),
        import('pdfjs-dist/build/pdf.worker.min.mjs?url'),
      ]);
      lib.GlobalWorkerOptions.workerSrc = worker.default;
      return lib as unknown as PdfLib;
    })();
    // A failed load (a chunk that did not arrive) may be tried again.
    loading.catch(() => { loading = null; });
  }
  return loading;
}
