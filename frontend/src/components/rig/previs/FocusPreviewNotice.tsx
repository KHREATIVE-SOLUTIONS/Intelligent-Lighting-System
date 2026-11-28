/**
 * The line over the 3D view while a focus preset is previewed
 * (docs/FOCUS_PRESETS.md, "In the app"): which target, how many heads are aimed
 * at it, the ones left at home and why, and Stop preview. Visual only.
 */
import { Alert, Box, Button, Typography } from '@mui/material';
import type { FocusPreviewPlan } from '../../../utils/focusPreview';
import { previewText } from '../../../utils/focusPreview';

export default function FocusPreviewNotice({ plan, onStop }: { plan: FocusPreviewPlan; onStop: () => void }) {
  return (
    <Alert
      severity="info"
      data-testid="focus-preview-notice"
      sx={{ mb: 1, py: 0 }}
      action={<Button color="inherit" size="small" onClick={onStop}>Stop preview</Button>}
    >
      <Typography variant="body2">{previewText(plan)}</Typography>
      {plan.home.length > 0 && (
        <Box component="ul" data-testid="focus-preview-home" sx={{ m: 0, pl: 2.5 }}>
          {plan.home.map((head, i) => (
            <Typography component="li" variant="caption" key={`${head.name}-${i}`} sx={{ display: 'list-item' }}>
              {head.name} stays at home: {head.reason}
            </Typography>
          ))}
        </Box>
      )}
    </Alert>
  );
}
