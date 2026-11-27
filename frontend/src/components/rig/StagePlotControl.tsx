/**
 * The "Stage plot" control over the 2D plan (docs/STAGE_PLOT.md): upload an
 * image of the stage plot, show or hide it under the fixtures, calibrate it
 * (two points and the metres between them, the stage's origin, rotation and
 * opacity), and remove it, which asks first. Driven by useStagePlot.
 */
import { useRef, useState } from 'react';
import {
  Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, Slider,
  TextField, Typography,
} from '@mui/material';
import type { PickStep, StagePlotState } from './useStagePlot';

export const STAGE_PLOT_ACCEPT = 'image/png,image/jpeg,image/webp,application/pdf';

export const PICK_TEXT: Record<PickStep, string> = {
  a: 'Click point A on the plot: one end of a length you know (a truss, the stage edge).',
  b: 'Click point B: the other end of that length.',
  origin: 'Click the stage centre on the plot: that point becomes the middle of the stage (the origin).',
  done: 'Type the distance between A and B, turn the plot if it needs it, then save.',
};

interface StagePlotControlProps {
  plot: StagePlotState;
  disabled?: boolean;
}

export default function StagePlotControl({ plot, disabled = false }: StagePlotControlProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const off = disabled || plot.busy;

  const choose = () => fileRef.current?.click();

  return (
    <Box data-testid="stage-plot-control" sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, mb: 1 }}>
      <input
        ref={fileRef}
        type="file"
        accept={STAGE_PLOT_ACCEPT}
        hidden
        data-testid="stage-plot-file"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = '';
          if (file) void plot.upload(file);
        }}
      />
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <Typography variant="caption" sx={{ fontWeight: 'bold' }}>Stage plot</Typography>
        <Button size="small" variant="outlined" disabled={off || plot.calibrating} onClick={choose}>
          {plot.present ? 'Replace' : 'Upload'}
        </Button>
        {plot.present && (
          <>
            <Button
              size="small"
              disabled={off || plot.calibrating}
              onClick={() => plot.setVisible(!plot.visible)}
              aria-pressed={plot.visible}
            >
              {plot.visible ? 'Hide' : 'Show'}
            </Button>
            <Button size="small" disabled={off || plot.calibrating} onClick={plot.startCalibrate}>
              {plot.info?.transform ? 'Recalibrate' : 'Calibrate'}
            </Button>
            <Button size="small" color="error" disabled={off || plot.calibrating} onClick={() => setConfirmRemove(true)}>
              Remove
            </Button>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 160 }}>
              <Typography variant="caption" id="stage-plot-opacity">Opacity</Typography>
              <Slider
                size="small"
                min={0.05}
                max={1}
                step={0.05}
                value={plot.opacity}
                disabled={off}
                onChange={(_, v) => plot.setOpacity(v as number)}
                onChangeCommitted={() => { void plot.commitOpacity(); }}
                aria-labelledby="stage-plot-opacity"
                sx={{ width: 100 }}
              />
            </Box>
            {!plot.info?.transform && !plot.calibrating && (
              <Typography variant="caption" color="warning.main" data-testid="stage-plot-uncalibrated">
                Not calibrated: drawn fitted to the stage.
              </Typography>
            )}
          </>
        )}
      </Box>

      {plot.calibrating && (
        <Alert severity="info" data-testid="stage-plot-calibrate" sx={{ '& .MuiAlert-message': { width: '100%' } }}>
          <Typography variant="body2" data-testid="stage-plot-step">{PICK_TEXT[plot.step]}</Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap', mt: 1 }}>
            <TextField
              size="small"
              label="Distance A to B (m)"
              value={plot.draft.distance}
              onChange={(e) => plot.setDistance(e.target.value)}
              inputProps={{ inputMode: 'decimal', 'data-testid': 'stage-plot-distance' }}
              sx={{ width: 170 }}
            />
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="caption" id="stage-plot-rotation">Rotate {Math.round(plot.draft.rotation)}°</Typography>
              <Slider
                size="small"
                min={-180}
                max={180}
                step={1}
                value={plot.draft.rotation}
                onChange={(_, v) => plot.setRotation(v as number)}
                aria-labelledby="stage-plot-rotation"
                sx={{ width: 140 }}
              />
            </Box>
            <Button size="small" onClick={plot.repick} disabled={plot.busy}>Pick again</Button>
            <Button size="small" onClick={plot.cancelCalibrate} disabled={plot.busy}>Cancel</Button>
            <Button
              size="small"
              variant="contained"
              disabled={plot.busy || plot.draftProblem !== null}
              onClick={() => { void plot.saveCalibration(); }}
            >
              Save calibration
            </Button>
          </Box>
          {plot.step === 'done' && plot.draftProblem && (
            <Typography variant="caption" color="warning.main" data-testid="stage-plot-problem">
              {plot.draftProblem}
            </Typography>
          )}
        </Alert>
      )}

      {plot.message && (
        <Alert severity={plot.message.severity} onClose={plot.clearMessage} data-testid="stage-plot-message">
          {plot.message.text}
        </Alert>
      )}

      <Dialog open={confirmRemove} onClose={() => setConfirmRemove(false)}>
        <DialogTitle>Remove the stage plot?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            The image and its calibration are taken off this rig. Fixtures stay where they are.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmRemove(false)}>Keep it</Button>
          <Button
            color="error"
            onClick={() => { setConfirmRemove(false); void plot.remove(); }}
            data-testid="stage-plot-remove-confirm"
          >
            Remove
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
