import { useId } from 'react';
import { Box, Typography, Slider, Grid, TextField, Stack, Chip } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import type { MountingPosition, WizardFixture } from './PickFixturesStep';

/**
 * A point on the top-down plan, in the rig's own metres.
 * x: across the stage, 0 at centre. z: depth, negative upstage (back wall),
 * positive downstage (toward the audience).
 */
export interface PlanMarker {
  id: string;
  x: number;
  z: number;
  color: string;
  label?: string;
}

export const GROUP_COLORS = [
  '#00bcd4', '#ff4081', '#ffb300', '#7c4dff',
  '#4caf50', '#ff7043', '#26c6da', '#ec407a',
];

export const colorForIndex = (index: number): string =>
  GROUP_COLORS[index % GROUP_COLORS.length];

const VIEW_W = 640;

interface StagePlanProps {
  width: number;
  depth: number;
  markers?: PlanMarker[];
  viewHeight?: number;
  /** Drawn under the plan; use it to say how exact the positions are. */
  note?: string;
}

/**
 * Top-down plan of the stage with the audience side marked, drawn in pixel
 * space so labels stay legible whether the stage is 4 m or 20 m across.
 */
export function StagePlan({ width, depth, markers = [], viewHeight = 340, note }: StagePlanProps) {
  const theme = useTheme();
  const patternId = useId().replace(/:/g, '');

  const halfW = Math.max(width, 0.5) / 2;
  const halfD = Math.max(depth, 0.5) / 2;
  const audienceDepth = Math.max(2, depth * 0.35);

  // Union of the stage, the audience strip and every marker, so nothing is clipped
  // even if a placement lands outside the deck.
  let minX = -halfW;
  let maxX = halfW;
  let minZ = -halfD;
  let maxZ = halfD + audienceDepth;
  markers.forEach((m) => {
    minX = Math.min(minX, m.x - 0.4);
    maxX = Math.max(maxX, m.x + 0.4);
    minZ = Math.min(minZ, m.z - 0.4);
    maxZ = Math.max(maxZ, m.z + 0.4);
  });

  const padX = 54;
  const padY = 40;
  const spanX = Math.max(maxX - minX, 0.5);
  const spanZ = Math.max(maxZ - minZ, 0.5);
  const scale = Math.min((VIEW_W - 2 * padX) / spanX, (viewHeight - 2 * padY) / spanZ);

  const offsetX = (VIEW_W - spanX * scale) / 2 - minX * scale;
  const offsetY = (viewHeight - spanZ * scale) / 2 - minZ * scale;
  const px = (x: number) => offsetX + x * scale;
  const py = (z: number) => offsetY + z * scale;

  const stageLeft = px(-halfW);
  const stageRight = px(halfW);
  const stageTop = py(-halfD);
  const stageBottom = py(halfD);
  const audienceBottom = py(halfD + audienceDepth);

  const muted = theme.palette.text.secondary;
  const line = theme.palette.divider;
  const arrowX = stageRight + 24;
  const arrowTip = Math.min(audienceBottom - 4, stageBottom + 28);

  return (
    <Box sx={{ width: '100%' }}>
      <svg
        viewBox={`0 0 ${VIEW_W} ${viewHeight}`}
        role="img"
        aria-label={`Top-down plan of a ${width} by ${depth} metre stage with the audience at the bottom`}
        style={{
          width: '100%',
          height: 'auto',
          display: 'block',
          background: '#12121a',
          border: `1px solid ${theme.palette.divider}`,
          borderRadius: 4,
        }}
      >
        <defs>
          <pattern
            id={`crowd-${patternId}`}
            width="8"
            height="8"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <line x1="0" y1="0" x2="0" y2="8" stroke={muted} strokeWidth="1" opacity="0.35" />
          </pattern>
        </defs>

        {/* Audience side */}
        <rect
          x={stageLeft - 8}
          y={stageBottom}
          width={stageRight - stageLeft + 16}
          height={Math.max(audienceBottom - stageBottom, 1)}
          fill={`url(#crowd-${patternId})`}
        />
        <text
          x={(stageLeft + stageRight) / 2}
          y={(stageBottom + audienceBottom) / 2 + 4}
          textAnchor="middle"
          fontSize="13"
          fill={muted}
        >
          Audience / dance floor
        </text>

        {/* Stage deck */}
        <rect
          x={stageLeft}
          y={stageTop}
          width={stageRight - stageLeft}
          height={stageBottom - stageTop}
          fill="#1c2230"
          stroke={theme.palette.primary.main}
          strokeWidth="2"
          rx="3"
        />

        {/* Back wall */}
        <line
          x1={stageLeft - 6}
          y1={stageTop}
          x2={stageRight + 6}
          y2={stageTop}
          stroke={theme.palette.primary.light}
          strokeWidth="5"
          strokeLinecap="round"
        />
        <text x={(stageLeft + stageRight) / 2} y={stageTop - 10} textAnchor="middle" fontSize="12" fill={muted}>
          Back wall / behind the performers
        </text>

        {/* Centre line */}
        <line
          x1={px(0)}
          y1={stageTop}
          x2={px(0)}
          y2={stageBottom}
          stroke={line}
          strokeWidth="1"
          strokeDasharray="4 5"
        />

        {/* Which way the crowd is */}
        <line
          x1={arrowX}
          y1={stageTop + 10}
          x2={arrowX}
          y2={arrowTip - 8}
          stroke={muted}
          strokeWidth="1.5"
        />
        <polygon
          points={`${arrowX},${arrowTip} ${arrowX - 5},${arrowTip - 9} ${arrowX + 5},${arrowTip - 9}`}
          fill={muted}
        />

        {/* Width and depth */}
        <text x={(stageLeft + stageRight) / 2} y={stageBottom + 16} textAnchor="middle" fontSize="12" fill={muted}>
          {width} m across
        </text>
        <text
          x={stageLeft - 14}
          y={(stageTop + stageBottom) / 2}
          textAnchor="middle"
          fontSize="12"
          fill={muted}
          transform={`rotate(-90 ${stageLeft - 14} ${(stageTop + stageBottom) / 2})`}
        >
          {depth} m deep
        </text>

        {/* Lights */}
        {markers.map((m) => (
          <g key={m.id}>
            <circle cx={px(m.x)} cy={py(m.z)} r={5.5} fill={m.color} stroke="#0b0b12" strokeWidth="1.2">
              {m.label && <title>{m.label}</title>}
            </circle>
          </g>
        ))}
      </svg>

      {note && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          {note}
        </Typography>
      )}
    </Box>
  );
}

// Fractions mirror _MOUNT_LINES and the span fractions in wizard_service.py, so
// this preview lands in roughly the same places the placement call will.
const SPAN_WIDTH = 0.85;
const SPAN_DEPTH = 0.6;

/** Where a mounting position sits on the plan, in metres. */
function mountingLine(
  position: MountingPosition,
  width: number,
  depth: number
): { axis: 'x' | 'z'; fixed: number; spread: number } {
  switch (position) {
    case 'ceiling':
      return { axis: 'x', fixed: depth * 0.10, spread: width * SPAN_WIDTH };
    case 'front_truss':
      return { axis: 'x', fixed: depth * 0.35, spread: width * SPAN_WIDTH };
    case 'mid_truss':
      return { axis: 'x', fixed: 0, spread: width * SPAN_WIDTH };
    case 'back_truss':
      return { axis: 'x', fixed: depth * -0.35, spread: width * SPAN_WIDTH };
    case 'floor':
      return { axis: 'x', fixed: depth * -0.42, spread: width * SPAN_WIDTH };
    case 'side_left':
      return { axis: 'z', fixed: width * -0.48, spread: depth * SPAN_DEPTH };
    case 'side_right':
      return { axis: 'z', fixed: width * 0.48, spread: depth * SPAN_DEPTH };
    default:
      return { axis: 'x', fixed: 0, spread: width * SPAN_WIDTH };
  }
}

const clamp = (value: number, low: number, high: number) =>
  Math.min(Math.max(value, low), high);

/** 0, +1, -1, +2, -2 ... mirrors wizard_service._alternating. */
const alternating = (index: number) =>
  Math.floor((index + 1) / 2) * (index % 2 ? 1 : -1);

/**
 * Rough marker positions for groups the user has described but not yet placed.
 *
 * Mirrors `_compute_group_positions`: a second group on the same mounting
 * position is staggered TOWARD stage centre, not away from it, and both axes are
 * clamped to the deck. Getting either wrong shows the owner lights standing in
 * the crowd, or upstage of where the backend will actually put them.
 */
export function indicativeMarkers(
  fixtures: WizardFixture[],
  width: number,
  depth: number
): PlanMarker[] {
  const used: Record<string, number> = {};
  const markers: PlanMarker[] = [];

  const halfWidth = width / 2;
  const halfDepth = depth / 2;
  const depthStep = Math.min(0.6, depth * 0.08);
  const widthStep = Math.min(0.3, width * 0.02);

  fixtures.forEach((f, groupIndex) => {
    if (f.count <= 0) return;
    const position = f.mounting_position ?? 'mid_truss';
    const slot = used[position] ?? 0;
    used[position] = slot + 1;

    const { axis, fixed, spread } = mountingLine(position, width, depth);
    const acrossLimit = axis === 'x' ? halfWidth : halfDepth;
    const lineLimit = axis === 'x' ? halfDepth : halfWidth;
    const lineStep = axis === 'x' ? depthStep : widthStep;
    const phaseStep = axis === 'x' ? widthStep : depthStep;

    const towardCentre = fixed >= 0 ? -1 : 1;
    const line = clamp(fixed + towardCentre * slot * lineStep, -lineLimit, lineLimit);
    const phase = alternating(slot) * phaseStep;
    const color = colorForIndex(groupIndex);

    for (let i = 0; i < f.count; i += 1) {
      const spanned = f.count === 1 ? 0 : -spread / 2 + (i * spread) / (f.count - 1);
      const along = clamp(spanned + phase, -acrossLimit, acrossLimit);
      markers.push({
        id: `${groupIndex}-${i}`,
        x: axis === 'x' ? along : line,
        z: axis === 'x' ? line : along,
        color,
        label: `${f.group_name} ${i + 1}`,
      });
    }
  });

  return markers;
}

interface StageDimensionsStepProps {
  width: number;
  depth: number;
  height: number;
  onWidthChange: (v: number) => void;
  onDepthChange: (v: number) => void;
  onHeightChange: (v: number) => void;
  fixtures?: WizardFixture[];
}

export default function StageDimensionsStep({
  width, depth, height, onWidthChange, onDepthChange, onHeightChange, fixtures = [],
}: StageDimensionsStepProps) {
  const markers = indicativeMarkers(fixtures, width, depth);
  const groups = fixtures.filter((f) => f.count > 0);

  return (
    <Box>
      <Typography variant="h6" gutterBottom>How big is the stage?</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Pace it out or estimate. Close is good enough - it only decides how far apart the
        lights are spread.
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12} sm={4}>
          <Typography gutterBottom>Across (left to right): {width} m</Typography>
          <Slider value={width} onChange={(_, v) => onWidthChange(v as number)} min={2} max={30} step={0.5} />
          <TextField size="small" type="number" value={width} onChange={(e) => onWidthChange(Number(e.target.value))} fullWidth inputProps={{ min: 1, max: 50, step: 0.5 }} />
        </Grid>
        <Grid item xs={12} sm={4}>
          <Typography gutterBottom>Front to back: {depth} m</Typography>
          <Slider value={depth} onChange={(_, v) => onDepthChange(v as number)} min={2} max={20} step={0.5} />
          <TextField size="small" type="number" value={depth} onChange={(e) => onDepthChange(Number(e.target.value))} fullWidth inputProps={{ min: 1, max: 30, step: 0.5 }} />
        </Grid>
        <Grid item xs={12} sm={4}>
          <Typography gutterBottom>How high the lights hang: {height} m</Typography>
          <Slider value={height} onChange={(_, v) => onHeightChange(v as number)} min={2} max={15} step={0.5} />
          <TextField size="small" type="number" value={height} onChange={(e) => onHeightChange(Number(e.target.value))} fullWidth inputProps={{ min: 2, max: 20, step: 0.5 }} />
        </Grid>
      </Grid>

      <Box sx={{ mt: 3 }}>
        <Typography variant="subtitle2" gutterBottom>
          Looking down on the room from above
        </Typography>
        <StagePlan
          width={width}
          depth={depth}
          markers={markers}
          note={
            markers.length > 0
              ? `Each dot is one light, placed roughly from what you told us on the lights step. Everything hangs about ${height} m up, which you cannot see from above.`
              : `Height (${height} m) does not show on a view from above - it is how far off the deck the bars hang.`
          }
        />
        {groups.length > 0 && (
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1.5 }}>
            {groups.map((f, index) => (
              <Chip
                key={`${f.group_name}-${index}`}
                size="small"
                variant="outlined"
                label={`${f.group_name} (${f.count})`}
                sx={{ borderColor: colorForIndex(fixtures.indexOf(f)), color: 'text.primary' }}
              />
            ))}
          </Stack>
        )}
      </Box>
    </Box>
  );
}
