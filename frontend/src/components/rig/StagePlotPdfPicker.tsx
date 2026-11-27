/**
 * Which page of a PDF is the stage plot: Prev/Next, a page number, and a small
 * picture of that page. Shown by StagePlotControl when the chosen PDF has more
 * than one page. docs/STAGE_PLOT.md.
 */
import { useEffect, useRef, useState } from 'react';
import {
  Box, Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, TextField, Typography,
} from '@mui/material';
import type { PdfDocumentLike, PdfRenderTask } from '../../utils/pdfStagePlot';

/** The preview's long side, in pixels. */
export const PREVIEW_LONG_SIDE_PX = 360;

/** The page number typed, or null when it is not a page of this PDF. */
export function parsePageNumber(typed: string, pages: number): number | null {
  if (!/^\s*\d+\s*$/.test(typed)) return null;
  const page = Number(typed);
  return page >= 1 && page <= pages ? page : null;
}

function PagePreview({ doc, pageNumber }: { doc: PdfDocumentLike; pageNumber: number }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let live = true;
    let task: PdfRenderTask | null = null;
    (async () => {
      try {
        const page = await doc.getPage(pageNumber);
        const canvas = ref.current;
        if (!live || !canvas) return;
        const atOne = page.getViewport({ scale: 1 });
        const viewport = page.getViewport({ scale: PREVIEW_LONG_SIDE_PX / Math.max(atOne.width, atOne.height, 1) });
        canvas.width = Math.max(1, Math.round(viewport.width));
        canvas.height = Math.max(1, Math.round(viewport.height));
        const context = canvas.getContext('2d');
        if (!context) return;
        task = page.render({ canvasContext: context, viewport });
        await task.promise;
      } catch {
        // Only a preview: the page is drawn again, full size, when it is chosen.
      }
    })();
    return () => {
      live = false;
      task?.cancel?.();
    };
  }, [doc, pageNumber]);

  return (
    <canvas
      ref={ref}
      data-testid="stage-plot-pdf-preview"
      aria-label={`Page ${pageNumber}`}
      style={{ maxWidth: '100%', maxHeight: PREVIEW_LONG_SIDE_PX, border: '1px solid rgba(128,128,128,0.5)', background: '#fff' }}
    />
  );
}

interface StagePlotPdfPickerProps {
  doc: PdfDocumentLike;
  fileName: string;
  busy?: boolean;
  onChoose: (pageNumber: number) => void;
  onCancel: () => void;
}

export default function StagePlotPdfPicker({ doc, fileName, busy = false, onChoose, onCancel }: StagePlotPdfPickerProps) {
  const pages = doc.numPages;
  const [page, setPage] = useState(1);
  const [typed, setTyped] = useState('1');
  const typedPage = parsePageNumber(typed, pages);

  const go = (next: number) => {
    const clamped = Math.min(pages, Math.max(1, next));
    setPage(clamped);
    setTyped(String(clamped));
  };

  return (
    <Dialog open onClose={busy ? undefined : onCancel} data-testid="stage-plot-pdf-picker">
      <DialogTitle>Which page is the stage plot?</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 1 }}>
          {fileName} has {pages} pages. Choose the one with the stage plot on it.
        </DialogContentText>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <Button size="small" onClick={() => go(page - 1)} disabled={busy || page <= 1}>Prev</Button>
          <TextField
            size="small"
            label="Page"
            value={typed}
            onChange={(e) => {
              setTyped(e.target.value);
              const next = parsePageNumber(e.target.value, pages);
              if (next !== null) setPage(next);
            }}
            error={typedPage === null}
            inputProps={{ inputMode: 'numeric', 'data-testid': 'stage-plot-pdf-page' }}
            sx={{ width: 90 }}
          />
          <Typography variant="body2">of {pages}</Typography>
          <Button size="small" onClick={() => go(page + 1)} disabled={busy || page >= pages}>Next</Button>
        </Box>
        {typedPage === null && (
          <Typography variant="caption" color="warning.main" data-testid="stage-plot-pdf-page-problem">
            Type a page number from 1 to {pages}.
          </Typography>
        )}
        <Box sx={{ display: 'flex', justifyContent: 'center' }}>
          <PagePreview doc={doc} pageNumber={page} />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={busy}>Cancel</Button>
        <Button variant="contained" onClick={() => onChoose(page)} disabled={busy || typedPage === null}>
          Use page {page}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
