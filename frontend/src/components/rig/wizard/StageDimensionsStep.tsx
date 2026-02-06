import { Box, Typography, Slider, Grid, TextField } from '@mui/material';

interface StageDimensionsStepProps {
  width: number;
  depth: number;
  height: number;
  onWidthChange: (v: number) => void;
  onDepthChange: (v: number) => void;
  onHeightChange: (v: number) => void;
}

export default function StageDimensionsStep({
  width, depth, height, onWidthChange, onDepthChange, onHeightChange,
}: StageDimensionsStepProps) {
  return (
    <Box>
      <Typography variant="h6" gutterBottom>Stage Dimensions</Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} sm={4}>
          <Typography gutterBottom>Width: {width}m</Typography>
          <Slider value={width} onChange={(_, v) => onWidthChange(v as number)} min={2} max={30} step={0.5} />
          <TextField size="small" type="number" value={width} onChange={(e) => onWidthChange(Number(e.target.value))} fullWidth inputProps={{ min: 1, max: 50, step: 0.5 }} />
        </Grid>
        <Grid item xs={12} sm={4}>
          <Typography gutterBottom>Depth: {depth}m</Typography>
          <Slider value={depth} onChange={(_, v) => onDepthChange(v as number)} min={2} max={20} step={0.5} />
          <TextField size="small" type="number" value={depth} onChange={(e) => onDepthChange(Number(e.target.value))} fullWidth inputProps={{ min: 1, max: 30, step: 0.5 }} />
        </Grid>
        <Grid item xs={12} sm={4}>
          <Typography gutterBottom>Height: {height}m</Typography>
          <Slider value={height} onChange={(_, v) => onHeightChange(v as number)} min={2} max={15} step={0.5} />
          <TextField size="small" type="number" value={height} onChange={(e) => onHeightChange(Number(e.target.value))} fullWidth inputProps={{ min: 2, max: 20, step: 0.5 }} />
        </Grid>
      </Grid>

      {/* Mini preview */}
      <Box sx={{ mt: 3, display: 'flex', justifyContent: 'center' }}>
        <Box sx={{ width: 200, height: 120, border: '1px solid', borderColor: 'divider', borderRadius: 1, position: 'relative', bgcolor: '#1a1a2e' }}>
          <Box sx={{ position: 'absolute', bottom: 4, left: '50%', transform: 'translateX(-50%)', color: '#666', fontSize: 10 }}>
            {width}m x {depth}m x {height}m
          </Box>
        </Box>
      </Box>
    </Box>
  );
}
