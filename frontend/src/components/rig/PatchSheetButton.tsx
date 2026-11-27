import { Button } from '@mui/material';
import { Print as PrintIcon } from '@mui/icons-material';
import { patchSheetUrl } from '../../utils/readiness';

interface PatchSheetButtonProps {
  rigId: number;
}

/**
 * "Open printable patch sheet": GET /api/rigs/{id}/patch-sheet in a new tab, one
 * universe per printed page (docs/HANDOFF_PACK.md). A plain link, so no popup
 * blocker stops it and the browser's own Print does the rest. Reads only.
 */
export default function PatchSheetButton({ rigId }: PatchSheetButtonProps) {
  return (
    <Button
      variant="outlined"
      size="small"
      startIcon={<PrintIcon />}
      component="a"
      href={patchSheetUrl(rigId)}
      target="_blank"
      rel="noopener noreferrer"
      data-testid="patch-sheet-link"
    >
      Open printable patch sheet
    </Button>
  );
}
