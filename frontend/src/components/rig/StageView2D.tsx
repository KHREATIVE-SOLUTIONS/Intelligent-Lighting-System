import { useState, useCallback, useMemo, useRef } from 'react';
import { Box } from '@mui/material';
import { FIXTURE_DRAG_MIME, computeTrussLines } from '../../stores/rigEditorStore';
import type { SnapMode } from '../../stores/rigEditorStore';
import type { RigFixture } from '../../types';

const FIXTURE_TYPE_COLORS: Record<string, string> = {
  moving_head: '#e91e63',
  led_par: '#4caf50',
  led_bar: '#2196f3',
  wash: '#ff9800',
  spot: '#9c27b0',
  beam: '#f44336',
  strobe: '#ffeb3b',
  laser: '#00bcd4',
  other: '#9e9e9e',
};

const AUDIENCE_COLOR = '#ffb74d';
const TRUSS_COLOR = '#7e57c2';

interface StageView2DProps {
  width: number;
  depth: number;
  height: number;
  fixtures: RigFixture[];
  selectedIds: Set<number>;
  gridSize?: number;
  snapMode?: SnapMode;
  readonly?: boolean;
  onFixtureClick?: (id: number, multi: boolean) => void;
  onFixtureDragStart?: (id: number) => void;
  onFixtureDrag?: (id: number, x: number, z: number) => void;
  onFixtureDragEnd?: (id: number) => void;
  onDropFromPalette?: (fixtureId: number, x: number, z: number) => void;
}

export default function StageView2D({
  width,
  depth,
  fixtures,
  selectedIds,
  gridSize = 0.5,
  snapMode = 'grid',
  readonly = false,
  onFixtureClick,
  onFixtureDragStart,
  onFixtureDrag,
  onFixtureDragEnd,
  onDropFromPalette,
}: StageView2DProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, z: 0 });
  const [dropPreview, setDropPreview] = useState<{ x: number; z: number } | null>(null);
  // Depth the dragged fixture started at, so its own truss stays a snap target
  // while it is lifted off it.
  const dragOriginZ = useRef<number | null>(null);

  const padding = 1;
  const viewWidth = width + padding * 2;
  const viewDepth = depth + padding * 2;

  const acceptsDrop = !readonly && !!onDropFromPalette;

  // Stage coords -> SVG coords. X is 0 at centre stage, Z is 0 at centre stage and
  // grows toward the audience, which is drawn at the bottom of the plan.
  const toSvgX = useCallback((x: number) => x + width / 2 + padding, [width, padding]);
  const toSvgY = useCallback((z: number) => z + depth / 2 + padding, [depth, padding]);

  const trussLines = useMemo(() => {
    const depths = fixtures
      .filter((f) => f.id !== draggingId)
      .map((f) => f.position_z);
    if (dragOriginZ.current !== null) depths.push(dragOriginZ.current);
    return computeTrussLines(depths);
  }, [fixtures, draggingId]);

  const pointerToStage = useCallback(
    (clientX: number, clientY: number) => {
      if (!svgRef.current) return { x: 0, z: 0 };
      const rect = svgRef.current.getBoundingClientRect();
      const scaleX = viewWidth / rect.width;
      const scaleY = viewDepth / rect.height;
      return {
        x: (clientX - rect.left) * scaleX - padding - width / 2,
        z: (clientY - rect.top) * scaleY - padding - depth / 2,
      };
    },
    [viewWidth, viewDepth, width, depth, padding]
  );

  const applySnap = useCallback(
    (x: number, z: number) => {
      if (snapMode === 'none') return { x, z };
      if (snapMode === 'truss') {
        // No truss to hang on yet: leave the position untouched rather than
        // pretending to snap.
        if (trussLines.length === 0) return { x, z };
        const nearest = trussLines.reduce((best, line) =>
          Math.abs(line - z) < Math.abs(best - z) ? line : best
        );
        return { x, z: nearest };
      }
      // Only the grid lines the plan actually draws, which stop at the last whole
      // square inside the stage. Rounding without that lands a fixture dragged to
      // the edge of, say, a 5.5 m stage on z=3.0 - off the deck and between two
      // lines - and the clamp that follows leaves it between them anyway.
      const onGrid = (value: number, half: number) => {
        const limit = Math.floor(half / gridSize) * gridSize;
        return Math.min(Math.max(Math.round(value / gridSize) * gridSize, -limit), limit);
      };
      return { x: onGrid(x, width / 2), z: onGrid(z, depth / 2) };
    },
    [snapMode, gridSize, trussLines, width, depth]
  );

  // The deck, and only the deck. The band below the stage is drawn and labelled
  // AUDIENCE: a fixture dropped there renders on top of that label with its own
  // name clipped off the viewBox, and the rig would claim a light is standing in
  // the crowd.
  const clampToPlan = useCallback(
    (x: number, z: number) => ({
      x: Math.min(Math.max(x, -width / 2), width / 2),
      z: Math.min(Math.max(z, -depth / 2), depth / 2),
    }),
    [width, depth]
  );

  const handleMouseDown = (e: React.MouseEvent, fixtureId: number) => {
    if (readonly) return;
    e.stopPropagation();
    const fixture = fixtures.find((f) => f.id === fixtureId);
    if (!fixture) return;

    onFixtureClick?.(fixtureId, e.shiftKey);
    setDraggingId(fixtureId);
    dragOriginZ.current = fixture.position_z;

    // Offset is held in unsnapped coordinates; snapping is applied to the final
    // position so grid mode actually lands on the grid.
    const raw = pointerToStage(e.clientX, e.clientY);
    setDragOffset({
      x: fixture.position_x - raw.x,
      z: fixture.position_z - raw.z,
    });
    onFixtureDragStart?.(fixtureId);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (draggingId === null || readonly) return;
    const raw = pointerToStage(e.clientX, e.clientY);
    const snapped = applySnap(raw.x + dragOffset.x, raw.z + dragOffset.z);
    const pos = clampToPlan(snapped.x, snapped.z);
    onFixtureDrag?.(draggingId, pos.x, pos.z);
  };

  const endDrag = () => {
    if (draggingId !== null) onFixtureDragEnd?.(draggingId);
    setDraggingId(null);
    dragOriginZ.current = null;
  };

  const handleBackgroundClick = () => {
    if (!readonly) {
      onFixtureClick?.(-1, false); // Deselect
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    if (!acceptsDrop || !e.dataTransfer.types.includes(FIXTURE_DRAG_MIME)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    const raw = pointerToStage(e.clientX, e.clientY);
    const snapped = applySnap(raw.x, raw.z);
    setDropPreview(clampToPlan(snapped.x, snapped.z));
  };

  const handleDrop = (e: React.DragEvent) => {
    if (!acceptsDrop) return;
    const payload = e.dataTransfer.getData(FIXTURE_DRAG_MIME);
    setDropPreview(null);
    if (!payload) return;
    e.preventDefault();
    const fixtureId = Number(payload);
    if (!Number.isFinite(fixtureId)) return;
    const raw = pointerToStage(e.clientX, e.clientY);
    const snapped = applySnap(raw.x, raw.z);
    const pos = clampToPlan(snapped.x, snapped.z);
    onDropFromPalette?.(fixtureId, pos.x, pos.z);
  };

  // Grid lines, drawn on the same multiples of gridSize that applySnap rounds
  // to. Emitting them from the stage edge instead only lines up when half the
  // stage is a whole number of grid squares, and the depth slider steps by 0.5,
  // so half of all reachable stages would snap between two drawn lines.
  const gridLines = [];
  for (let i = -Math.floor(width / 2 / gridSize); i * gridSize <= width / 2; i += 1) {
    const x = i * gridSize;
    gridLines.push(
      <line
        key={`gv-${x}`}
        x1={toSvgX(x)}
        y1={padding}
        x2={toSvgX(x)}
        y2={depth + padding}
        stroke="#333"
        strokeWidth={x % 1 === 0 ? 0.03 : 0.01}
        opacity={x % 1 === 0 ? 0.3 : 0.15}
      />
    );
  }
  for (let i = -Math.floor(depth / 2 / gridSize); i * gridSize <= depth / 2; i += 1) {
    const z = i * gridSize;
    gridLines.push(
      <line
        key={`gh-${z}`}
        x1={padding}
        y1={toSvgY(z)}
        x2={width + padding}
        y2={toSvgY(z)}
        stroke="#333"
        strokeWidth={z % 1 === 0 ? 0.03 : 0.01}
        opacity={z % 1 === 0 ? 0.3 : 0.15}
      />
    );
  }

  return (
    <Box
      sx={{
        width: '100%',
        aspectRatio: `${viewWidth} / ${viewDepth}`,
        bgcolor: '#1a1a2e',
        borderRadius: 1,
        overflow: 'hidden',
      }}
    >
      <svg
        ref={svgRef}
        viewBox={`0 0 ${viewWidth} ${viewDepth}`}
        width="100%"
        height="100%"
        onMouseMove={handleMouseMove}
        onMouseUp={endDrag}
        onMouseLeave={endDrag}
        onClick={handleBackgroundClick}
        onDragOver={handleDragOver}
        onDragLeave={() => setDropPreview(null)}
        onDrop={handleDrop}
      >
        {/* Stage floor */}
        <rect
          x={padding}
          y={padding}
          width={width}
          height={depth}
          fill="#16213e"
          stroke="#0f3460"
          strokeWidth={0.05}
        />

        {/* Grid */}
        {gridLines}

        {/* Centre lines (stage origin) */}
        <line
          x1={toSvgX(0)}
          y1={padding}
          x2={toSvgX(0)}
          y2={depth + padding}
          stroke="#0f3460"
          strokeWidth={0.04}
          strokeDasharray="0.2 0.1"
        />
        <line
          x1={padding}
          y1={toSvgY(0)}
          x2={width + padding}
          y2={toSvgY(0)}
          stroke="#0f3460"
          strokeWidth={0.03}
          strokeDasharray="0.2 0.1"
        />

        {/* Truss lines, shown whenever they can be snapped to */}
        {snapMode === 'truss' &&
          trussLines.map((z) => (
            <g key={`truss-${z.toFixed(3)}`}>
              <line
                x1={padding}
                y1={toSvgY(z)}
                x2={width + padding}
                y2={toSvgY(z)}
                stroke={TRUSS_COLOR}
                strokeWidth={0.06}
                strokeDasharray="0.4 0.2"
                opacity={0.8}
              />
              <text
                x={width + padding - 0.1}
                y={toSvgY(z) - 0.12}
                textAnchor="end"
                fill={TRUSS_COLOR}
                fontSize={0.22}
              >
                TRUSS
              </text>
            </g>
          ))}

        {/* Upstage / back wall */}
        <line
          x1={padding}
          y1={padding}
          x2={width + padding}
          y2={padding}
          stroke="#5c6bc0"
          strokeWidth={0.08}
        />
        <text
          x={toSvgX(0)}
          y={padding - 0.25}
          textAnchor="middle"
          fill="#8c9eff"
          fontSize={0.3}
          letterSpacing={0.06}
        >
          UPSTAGE — BACK WALL
        </text>

        {/* Downstage edge and the audience beyond it */}
        <line
          x1={padding}
          y1={depth + padding}
          x2={width + padding}
          y2={depth + padding}
          stroke={AUDIENCE_COLOR}
          strokeWidth={0.08}
        />
        <polygon
          points={`${toSvgX(0) - 0.28},${depth + padding + 0.2} ${toSvgX(0) + 0.28},${
            depth + padding + 0.2
          } ${toSvgX(0)},${depth + padding + 0.55}`}
          fill={AUDIENCE_COLOR}
          opacity={0.9}
        />
        <text
          x={toSvgX(0)}
          y={depth + padding + 0.9}
          textAnchor="middle"
          fill={AUDIENCE_COLOR}
          fontSize={0.34}
          letterSpacing={0.08}
        >
          AUDIENCE
        </text>

        {/* Fixtures */}
        {fixtures.map((f) => {
          const fixtureType = f.fixture?.fixture_type || 'other';
          const color = FIXTURE_TYPE_COLORS[fixtureType] || '#9e9e9e';
          const isSelected = selectedIds.has(f.id);

          return (
            <g
              key={f.id}
              transform={`translate(${toSvgX(f.position_x)}, ${toSvgY(f.position_z)})`}
              onMouseDown={(e) => handleMouseDown(e, f.id)}
              onClick={(e) => e.stopPropagation()}
              style={{ cursor: readonly ? 'default' : 'grab' }}
            >
              {/* Selection ring */}
              {isSelected && (
                <circle r={0.4} fill="none" stroke="#4fc3f7" strokeWidth={0.06} />
              )}

              {/* Fixture icon */}
              <circle r={0.25} fill={color} opacity={0.9} />
              <circle r={0.25} fill="none" stroke={isSelected ? '#4fc3f7' : '#fff'} strokeWidth={0.04} />

              {/* Direction indicator. rotation_y is the wizard's yaw about +Y:
                  0 aims downstage (+Z, toward the audience, down the plan) and
                  +90 aims toward +X. Drawing the line from -Z under the same
                  rotate() negated the heading and pointed every wizard-placed
                  fixture exactly backwards. */}
              <line
                x1={0}
                y1={0}
                x2={0}
                y2={0.35}
                stroke={color}
                strokeWidth={0.04}
                transform={`rotate(${-(f.rotation_y || 0)})`}
              />

              {/* Label */}
              <text
                y={0.55}
                textAnchor="middle"
                fill="#ccc"
                fontSize={0.22}
              >
                {f.name || `${f.dmx_address}`}
              </text>
            </g>
          );
        })}

        {/* Landing spot for a fixture dragged in from the palette */}
        {dropPreview && (
          <g transform={`translate(${toSvgX(dropPreview.x)}, ${toSvgY(dropPreview.z)})`}>
            <circle r={0.32} fill="none" stroke="#4fc3f7" strokeWidth={0.06} strokeDasharray="0.15 0.1" />
            <text y={0.62} textAnchor="middle" fill="#4fc3f7" fontSize={0.22}>
              {`${dropPreview.x.toFixed(1)}, ${dropPreview.z.toFixed(1)}`}
            </text>
          </g>
        )}

        {/* Scale indicator */}
        <line
          x1={padding + 0.2}
          y1={padding - 0.45}
          x2={padding + 1.2}
          y2={padding - 0.45}
          stroke="#666"
          strokeWidth={0.03}
        />
        <text
          x={padding + 0.7}
          y={padding - 0.6}
          textAnchor="middle"
          fill="#666"
          fontSize={0.2}
        >
          1m
        </text>
      </svg>
    </Box>
  );
}
