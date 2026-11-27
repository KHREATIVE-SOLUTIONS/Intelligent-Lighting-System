/**
 * The height strip beside the 2D plan while the room's items are arranged
 * (slice 22): an elevation of the selected raised area, truss line or ring,
 * the floor at the bottom and the ceiling at the top, with a handle to drag
 * for each height it has. A raised area has its top and its base (0 stands
 * on the floor, more floats); a line or a ring has its trim height.
 *
 * A drag is drawn as it goes, with the live value beside the handle, and is
 * reported once, when it is let go, through `onChange`: one request and one
 * step of the room's own undo, like every other handle of the mode. The strip
 * shows the item where it was dropped until what `onChange` returns has
 * settled, then draws the room it is given: a change the server refused goes
 * back. The numbers are in roomItemHeight.ts; docs/ROOM_SCAN.md.
 *
 * Pointer events, so a mouse, a finger and a pen are one code path, and the
 * move and the release are listened for on the window: a drag up and down a
 * narrow strip leaves it sideways at once.
 */
import { useEffect, useRef, useState } from 'react';
import { Box, Button, Typography } from '@mui/material';
import type { ShellItemChanges, ShellItemKind } from '../../utils/roomShellEdit';
import {
  HEIGHT_SHIFT_SNAP_M, HEIGHT_SNAP_M, dragHeight, heightGripHint, heightGripLabel,
} from './roomItemHeight';
import type { HeightGauge, HeightGrip } from './roomItemHeight';

interface RoomItemHeightStripProps {
  /** The selected item, or null when none is selected or the selected one stores no height. */
  gauge: HeightGauge | null;
  /**
   * A handle let go somewhere new: called once for a drag, when it ends, and
   * never for a press that stayed within 5 pixels or a drag that ended where
   * it began. `changes` holds `height` or `base_height` alone.
   */
  onChange?: (kind: ShellItemKind, index: number, changes: ShellItemChanges) => void | Promise<unknown>;
}

// The strip's own drawing units: one is a pixel when the strip is shown at its usual size.
const VIEW_W = 120;
const VIEW_H = 320;
const FLOOR_Y = 296;
const SCALE_TOP_Y = 24;
const SPAN = FLOOR_Y - SCALE_TOP_Y;
// A handle a finger can press: 44 by 30, the two of a raised area side by side so a thin deck's do not overlap.
const HANDLE_W = 44;
const HANDLE_H = 30;
const HANDLE_X: Record<HeightGrip, number> = { base: 30, top: 90, trim: 60 };
const DRAG_THRESHOLD_PX = 5;
const ACCENT = '#ffb74d';
const INK = '#cfd8dc';

/** One press on a handle, until it is let go. */
interface Session {
  gauge: HeightGauge;
  grip: HeightGrip;
  /** Where the pointer went down, on the screen. */
  downX: number;
  downY: number;
  /** Which pointer: another finger is not this one. */
  pointerId: number | undefined;
  /** How many screen pixels a metre is, fixed when the press began. */
  pxPerMetre: number;
  /** Where the handle stood when it was pressed, in metres above the floor. */
  from: number;
  /** What the drag would send as it now stands: null where it has changed nothing. */
  changes: ShellItemChanges | null;
  /** True once the pointer has gone past the drag threshold. */
  moved: boolean;
}

interface Preview {
  key: string;
  grip: HeightGrip;
  base: number | null;
  top: number;
  readout: string;
}

export default function RoomItemHeightStrip({ gauge, onChange }: RoomItemHeightStripProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const sessionRef = useRef<Session | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  // The touch for Shift: steps of 0.25 m until it is pressed again.
  const [coarse, setCoarse] = useState(false);
  const coarseRef = useRef(coarse);
  coarseRef.current = coarse;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  // What takes the window's listeners off again; null while no handle is held.
  const releaseRef = useRef<(() => void) | null>(null);

  // The strip taken away under a press: the press is over, and nothing is sent.
  useEffect(() => () => {
    releaseRef.current?.();
    sessionRef.current = null;
  }, []);

  const scaleTop = gauge?.scaleTop ?? 1;
  const yOf = (metres: number) => FLOOR_Y - (Math.min(Math.max(metres, 0), scaleTop) / scaleTop) * SPAN;

  /** How many screen pixels a metre is in the strip as it is laid out now. */
  const pxPerMetre = () => {
    const rect = svgRef.current?.getBoundingClientRect();
    // Not laid out (or a test's empty box): a drawing unit is taken for a pixel.
    const pxPerUnit = rect && rect.height > 0 ? rect.height / VIEW_H : 1;
    return (SPAN / scaleTop) * pxPerUnit;
  };

  const endPress = (send: boolean) => {
    const session = sessionRef.current;
    sessionRef.current = null;
    releaseRef.current?.();
    releaseRef.current = null;
    if (!session || !session.moved) return;
    // Brought back to where it began, or taken by the browser: nothing to send, and no undo step.
    if (!send || !session.changes) {
      setPreview(null);
      return;
    }
    // One call for the whole drag: one request, and one step of the room's undo.
    const sent = onChangeRef.current?.(session.gauge.kind, session.gauge.index, session.changes);
    // Shown where it was dropped until the answer is in; then the room given is drawn.
    void Promise.resolve(sent).catch(() => undefined).then(() => setPreview(null));
  };

  const movePress = (e: PointerEvent) => {
    const session = sessionRef.current;
    if (!session) return;
    if (session.pointerId !== undefined && e.pointerId !== undefined && e.pointerId !== session.pointerId) return;
    // A click, or the wobble of one, changes no height: nothing is sent and no undo step is left.
    if (!session.moved
      && Math.hypot(e.clientX - session.downX, e.clientY - session.downY) < DRAG_THRESHOLD_PX) return;
    session.moved = true;
    // Up the screen is up the room.
    const metres = session.from + (session.downY - e.clientY) / session.pxPerMetre;
    const dragged = dragHeight(session.gauge, session.grip, metres, e.shiftKey || coarseRef.current);
    session.changes = dragged.changes;
    setPreview({
      key: session.gauge.key, grip: session.grip, base: dragged.base, top: dragged.top, readout: dragged.readout,
    });
  };

  const pressHandle = (e: React.PointerEvent, grip: HeightGrip) => {
    if (!gauge) return;
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    // A drop is still waiting for its answer: the room on screen is not yet
    // the one a new drag would start from, so the press is let pass.
    if (preview && !sessionRef.current) return;
    const handle = gauge.handles.find((entry) => entry.grip === grip);
    if (!handle) return;
    // No mouse events after this press, no text selected, no page pan, and the
    // focus stays where it is: the plan's arrow keys go on answering.
    e.preventDefault();
    e.stopPropagation();
    // A press whose end never arrived is ended here, not left to block this one.
    if (sessionRef.current) endPress(false);
    sessionRef.current = {
      gauge,
      grip,
      downX: e.clientX,
      downY: e.clientY,
      pointerId: e.pointerId,
      pxPerMetre: pxPerMetre(),
      from: handle.value,
      changes: null,
      moved: false,
    };
    const onMove = (event: PointerEvent) => movePress(event);
    const onUp = (event: PointerEvent) => {
      const session = sessionRef.current;
      if (session && session.pointerId !== undefined && event.pointerId !== undefined
        && event.pointerId !== session.pointerId) return;
      endPress(true);
    };
    const onCancel = () => endPress(false);
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onCancel);
    releaseRef.current = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onCancel);
    };
  };

  // A drop that belongs to an item no longer shown is not drawn on another.
  const shown = gauge && preview && preview.key === gauge.key ? preview : null;
  const base = shown ? shown.base : gauge?.base ?? null;
  const top = shown ? shown.top : gauge?.top ?? 0;
  const valueOf = (grip: HeightGrip) => (grip === 'base' ? base ?? 0 : top);

  // A tick at each metre, or at every other one in a tall room.
  const tickStep = scaleTop > 12 ? 5 : scaleTop > 6 ? 2 : 1;
  const ticks: number[] = [];
  for (let metre = 0; gauge && metre <= scaleTop + 1e-9; metre += tickStep) ticks.push(metre);

  return (
    <Box
      data-testid="item-height-strip"
      sx={{
        width: 136, flexShrink: 0, bgcolor: '#1a1a2e', borderRadius: 1, p: 1,
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.5,
      }}
    >
      <Typography variant="caption" sx={{ color: INK, textAlign: 'center', lineHeight: 1.2 }} data-testid="item-height-title">
        {gauge ? `Height: ${gauge.title}` : 'Height'}
      </Typography>
      {!gauge && (
        <Typography variant="caption" sx={{ color: INK, opacity: 0.7, textAlign: 'center' }} data-testid="item-height-empty">
          Select a raised area, a truss line or a ring on the plan to set its height here by dragging.
        </Typography>
      )}
      {gauge && (
        <svg
          ref={svgRef}
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          width={VIEW_W}
          height={VIEW_H}
          // A finger on the strip is the strip's: the browser does not pan or zoom the page with it.
          style={{ userSelect: 'none', touchAction: 'none', WebkitTouchCallout: 'none', display: 'block' }}
          data-testid="item-height-svg"
        >
          {/* The scale: a tick and a number at each metre. */}
          {ticks.map((metre) => (
            <g key={`tick-${metre}`}>
              <line x1={0} y1={yOf(metre)} x2={6} y2={yOf(metre)} stroke={INK} strokeWidth={1} opacity={0.5} />
              <text x={8} y={yOf(metre) + 3} fill={INK} fontSize={9} opacity={0.6} style={{ pointerEvents: 'none' }}>
                {metre}
              </text>
            </g>
          ))}
          {/* The ceiling, where the room stores one. */}
          {gauge.ceiling !== null && (
            <g data-testid="item-height-ceiling">
              <line
                x1={0} y1={yOf(gauge.ceiling)} x2={VIEW_W} y2={yOf(gauge.ceiling)}
                stroke={INK} strokeWidth={1.5} strokeDasharray="6 4"
              />
              <text
                x={VIEW_W - 2} y={yOf(gauge.ceiling) - 4} textAnchor="end" fill={INK} fontSize={9}
                style={{ pointerEvents: 'none' }}
              >
                {`ceiling ${gauge.ceiling.toFixed(2)} m`}
              </text>
            </g>
          )}
          {/* The floor. */}
          <line x1={0} y1={FLOOR_Y} x2={VIEW_W} y2={FLOOR_Y} stroke={INK} strokeWidth={2} />
          <text x={VIEW_W - 2} y={FLOOR_Y + 12} textAnchor="end" fill={INK} fontSize={9} style={{ pointerEvents: 'none' }}>
            floor
          </text>

          {/* The item: a raised area from its base to its top, or the underside of a truss. */}
          {gauge.kind === 'risers' ? (
            <rect
              data-testid="item-height-body"
              x={44}
              y={yOf(top)}
              width={32}
              height={Math.max(2, yOf(base ?? 0) - yOf(top))}
              fill={ACCENT}
              fillOpacity={0.28}
              stroke={ACCENT}
              strokeWidth={1.5}
            />
          ) : (
            <g data-testid="item-height-body">
              <line x1={20} y1={yOf(top)} x2={100} y2={yOf(top)} stroke={ACCENT} strokeWidth={4} strokeLinecap="round" />
              {/* What hangs it: a drop from the top of the strip to the truss. */}
              <line x1={60} y1={SCALE_TOP_Y - 8} x2={60} y2={yOf(top)} stroke={ACCENT} strokeWidth={1} opacity={0.5} />
            </g>
          )}

          {/* The handles, over everything else. */}
          {gauge.handles.map((handle) => {
            const value = valueOf(handle.grip);
            const held = shown?.grip === handle.grip;
            return (
              <g
                key={handle.grip}
                data-testid={`item-height-handle-${handle.grip}`}
                data-value={value.toFixed(3)}
                transform={`translate(${HANDLE_X[handle.grip]}, ${yOf(value)})`}
                onPointerDown={(e) => pressHandle(e, handle.grip)}
                style={{ cursor: 'ns-resize', touchAction: 'none' }}
              >
                <title>{heightGripHint(handle.grip, gauge.title)}</title>
                <rect
                  x={-HANDLE_W / 2}
                  y={-HANDLE_H / 2}
                  width={HANDLE_W}
                  height={HANDLE_H}
                  rx={6}
                  fill={held ? ACCENT : '#1a1a2e'}
                  stroke={ACCENT}
                  strokeWidth={2}
                />
                <text
                  y={-2}
                  textAnchor="middle"
                  fill={held ? '#1a1a2e' : ACCENT}
                  fontSize={9}
                  style={{ pointerEvents: 'none' }}
                >
                  {heightGripLabel(handle.grip)}
                </text>
                <text
                  y={10}
                  textAnchor="middle"
                  fill={held ? '#1a1a2e' : INK}
                  fontSize={10}
                  style={{ pointerEvents: 'none' }}
                >
                  {value.toFixed(2)}
                </text>
              </g>
            );
          })}
        </svg>
      )}
      {gauge && (
        <Typography
          variant="caption"
          sx={{ color: shown ? ACCENT : INK, textAlign: 'center', minHeight: '1.4em' }}
          data-testid="item-height-readout"
        >
          {shown?.readout || 'Drag a handle up or down'}
        </Typography>
      )}
      {gauge && (
        <Button
          size="small"
          color="inherit"
          variant={coarse ? 'outlined' : 'text'}
          sx={{ color: INK, fontSize: 11, py: 0, textTransform: 'none' }}
          aria-pressed={coarse}
          onClick={(e) => {
            setCoarse((now) => !now);
            // The arrow keys are the plan's again, not the button's.
            e.currentTarget.blur();
          }}
          data-testid="item-height-step"
        >
          {`Step ${(coarse ? HEIGHT_SHIFT_SNAP_M : HEIGHT_SNAP_M).toFixed(2)} m`}
        </Button>
      )}
    </Box>
  );
}
