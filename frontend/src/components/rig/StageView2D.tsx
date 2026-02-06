import { useState, useCallback, useRef } from 'react';
import { Box } from '@mui/material';
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

interface StageView2DProps {
  width: number;
  depth: number;
  height: number;
  fixtures: RigFixture[];
  selectedIds: Set<number>;
  gridSize?: number;
  readonly?: boolean;
  onFixtureClick?: (id: number, multi: boolean) => void;
  onFixtureDrag?: (id: number, x: number, z: number) => void;
  onDropFromPalette?: (fixtureId: number, x: number, z: number) => void;
}

export default function StageView2D({
  width,
  depth,
  fixtures,
  selectedIds,
  gridSize = 0.5,
  readonly = false,
  onFixtureClick,
  onFixtureDrag,
}: StageView2DProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, z: 0 });

  const padding = 1;
  const viewWidth = width + padding * 2;
  const viewDepth = depth + padding * 2;

  const svgToStage = useCallback(
    (clientX: number, clientY: number) => {
      if (!svgRef.current) return { x: 0, z: 0 };
      const rect = svgRef.current.getBoundingClientRect();
      const scaleX = viewWidth / rect.width;
      const scaleY = viewDepth / rect.height;
      const svgX = (clientX - rect.left) * scaleX - padding;
      const svgZ = (clientY - rect.top) * scaleY - padding;
      // Snap to grid
      const x = Math.round((svgX - width / 2) / gridSize) * gridSize;
      const z = Math.round(svgZ / gridSize) * gridSize;
      return { x, z };
    },
    [viewWidth, viewDepth, width, gridSize, padding]
  );

  const handleMouseDown = (e: React.MouseEvent, fixtureId: number) => {
    if (readonly) return;
    e.stopPropagation();
    const fixture = fixtures.find((f) => f.id === fixtureId);
    if (!fixture) return;

    onFixtureClick?.(fixtureId, e.shiftKey);
    setDraggingId(fixtureId);

    const pos = svgToStage(e.clientX, e.clientY);
    setDragOffset({
      x: fixture.position_x - pos.x,
      z: fixture.position_z - pos.z,
    });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (draggingId === null || readonly) return;
    const pos = svgToStage(e.clientX, e.clientY);
    onFixtureDrag?.(
      draggingId,
      pos.x + dragOffset.x,
      pos.z + dragOffset.z
    );
  };

  const handleMouseUp = () => {
    setDraggingId(null);
  };

  const handleBackgroundClick = () => {
    if (!readonly) {
      onFixtureClick?.(-1, false); // Deselect
    }
  };

  // Grid lines
  const gridLines = [];
  for (let x = 0; x <= width; x += gridSize) {
    gridLines.push(
      <line
        key={`gv-${x}`}
        x1={x + padding}
        y1={padding}
        x2={x + padding}
        y2={depth + padding}
        stroke="#333"
        strokeWidth={x % 1 === 0 ? 0.03 : 0.01}
        opacity={x % 1 === 0 ? 0.3 : 0.15}
      />
    );
  }
  for (let z = 0; z <= depth; z += gridSize) {
    gridLines.push(
      <line
        key={`gh-${z}`}
        x1={padding}
        y1={z + padding}
        x2={width + padding}
        y2={z + padding}
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
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onClick={handleBackgroundClick}
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

        {/* Center line */}
        <line
          x1={width / 2 + padding}
          y1={padding}
          x2={width / 2 + padding}
          y2={depth + padding}
          stroke="#0f3460"
          strokeWidth={0.04}
          strokeDasharray="0.2 0.1"
        />

        {/* Front of stage label */}
        <text
          x={width / 2 + padding}
          y={padding - 0.2}
          textAnchor="middle"
          fill="#666"
          fontSize={0.3}
        >
          FRONT
        </text>

        {/* Fixtures */}
        {fixtures.map((f) => {
          const fixtureType = f.fixture?.fixture_type || 'other';
          const color = FIXTURE_TYPE_COLORS[fixtureType] || '#9e9e9e';
          const isSelected = selectedIds.has(f.id);
          const stageX = f.position_x + width / 2 + padding;
          const stageZ = f.position_z + padding;

          return (
            <g
              key={f.id}
              transform={`translate(${stageX}, ${stageZ})`}
              onMouseDown={(e) => handleMouseDown(e, f.id)}
              style={{ cursor: readonly ? 'default' : 'grab' }}
            >
              {/* Selection ring */}
              {isSelected && (
                <circle r={0.4} fill="none" stroke="#4fc3f7" strokeWidth={0.06} />
              )}

              {/* Fixture icon */}
              <circle r={0.25} fill={color} opacity={0.9} />
              <circle r={0.25} fill="none" stroke={isSelected ? '#4fc3f7' : '#fff'} strokeWidth={0.04} />

              {/* Direction indicator */}
              <line
                x1={0}
                y1={0}
                x2={0}
                y2={-0.35}
                stroke={color}
                strokeWidth={0.04}
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

        {/* Scale indicator */}
        <line
          x1={padding + 0.2}
          y1={viewDepth - 0.3}
          x2={padding + 1.2}
          y2={viewDepth - 0.3}
          stroke="#666"
          strokeWidth={0.03}
        />
        <text
          x={padding + 0.7}
          y={viewDepth - 0.15}
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
