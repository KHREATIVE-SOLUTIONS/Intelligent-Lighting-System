import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { Box } from '@mui/material';
import { FIXTURE_DRAG_MIME, computeTrussLines } from '../../stores/rigEditorStore';
import type { SnapMode } from '../../stores/rigEditorStore';
import type { RigFixture, RoomShell } from '../../types';
import {
  DJ_BOOTH_TAG_SIZE, djBoothTag, holdOnPlan, planFrame, planGrid, planLabels, planPolygonPoints, planTrussTargets,
  planViewBox, roomPlan, snapToRoomGrid, snapToScannedTruss,
} from './roomPlan2d';
import type { PlanLabel, PlanPoint } from './roomPlan2d';
import {
  boxBetween, boxSelection, fixturesInBox, keysBelongElsewhere, nudgeMoves, nudgeShift, pastDragThreshold,
} from './planSelect2d';
import type { ScreenPoint } from './planSelect2d';
import PlanNudgePad from './PlanNudgePad';
import { KEYS_HINT_TEXT, LONG_PRESS_MS, isTouchPointer, keysHintDue, padShift, pressPhase } from './planTouch2d';
import type { PadDirection } from './planTouch2d';
import { holdRowShift, onPlanTarget, rowReadoutText, snapReadoutText } from './rowMove2d';
import type { PlanMove, RowShift } from './rowMove2d';
import type { LayChoice } from './rowSpace2d';
import type { SnapLine } from './previs/fixtureDrag';
import { WALL_LIMITS, wallCorners } from '../../utils/roomWallsEdit';
import type { ShellItemChanges, ShellItemKind } from '../../utils/roomShellEdit';
import { dragItem, gripCursor, gripHint, isBoxGrip, itemHandles, planItems, shapeCentre } from './roomItemDrag2d';
import type { ItemGrip, ItemShape, PlanItem } from './roomItemDrag2d';
import { isGuessed, svgMatrix } from '../../utils/stagePlot';
import type { Matrix } from '../../utils/stagePlot';

/** A stage plot image drawn under the fixtures (docs/STAGE_PLOT.md). */
export interface PlanUnderlay {
  /** An object URL of the image: the route needs the operator's token, an <image href> does not send it. */
  href: string;
  widthPx: number;
  heightPx: number;
  /** Image pixels to plan metres (utils/stagePlot.ts). */
  matrix: Matrix;
  opacity: number;
}

/** A point marked on the plan while a stage plot is calibrated: A, B or the origin. */
export interface PlanPickMark {
  x: number;
  z: number;
  label: string;
}

// The amber of a guessed position, as the 3D view's GUESS_COLOR.
const GUESS_RING = '#ffb74d';

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
// The scanned room: what a phone scan found, not what anybody placed. Grey,
// brown and teal, so its truss is not taken for the purple lines fixtures
// snap to.
const ROOM_FLOOR = '#141a2c';
const ROOM_WALL = '#90a4ae';
const ROOM_RAISED = '#8d6e63';
const ROOM_RAISED_TEXT = '#d7ccc8';
const ROOM_TRUSS = '#4db6ac';
// The tag on the DJ's booth where it is only a guess: the amber of a guessed position in the 3D view (GUESS_COLOR).
const DJ_BOOTH_GUESS = '#ffb74d';
// The selection's own blue, as the ring round a selected fixture.
const SELECTION_COLOR = '#4fc3f7';
// The corners of the walls while they can be dragged: amber, unlike anything else on the plan.
const WALL_HANDLE = '#ffca28';

const roundMm = (value: number) => Math.round(value * 1000) / 1000 + 0;

/** One press on a corner of the walls, until it is let go. */
interface CornerSession {
  /** The corner's place in the outline, from 0: what the server knows it by. */
  index: number;
  /** Where the pointer went down, on the screen: the press is a drag once it is 5 pixels from here. */
  down: ScreenPoint;
  /** The corner's position less the pointer's, so the corner does not jump to the pointer. */
  offset: { x: number; z: number };
  /** Where the drag has the corner now. */
  at: PlanPoint;
  /** True once the pointer has gone past the drag threshold. */
  moved: boolean;
}

/** One press on a room item or one of its handles, until it is let go. */
interface ItemSession {
  /** The item as it stood when it was pressed. */
  item: PlanItem;
  /** What the press has hold of: the item itself, or one of its handles. */
  grip: ItemGrip;
  /** Where the pointer went down, on the screen: the press is a drag once it is 5 pixels from here. */
  down: ScreenPoint;
  /** The grip's position less the pointer's, so the item does not jump to the pointer. */
  offset: { x: number; z: number };
  /** What the drag would send as it now stands: null where it has changed nothing. */
  changes: ShellItemChanges | null;
  /** True once the pointer has gone past the drag threshold. */
  moved: boolean;
}

interface StageView2DProps {
  width: number;
  depth: number;
  height: number;
  fixtures: RigFixture[];
  /**
   * The rig's stored room. Only one read from a room scan is drawn: its walls,
   * raised areas and overhead truss, under the fixtures (docs/ROOM_SCAN.md).
   */
  roomShell?: RoomShell | null;
  selectedIds: Set<number>;
  gridSize?: number;
  snapMode?: SnapMode;
  readonly?: boolean;
  onFixtureClick?: (id: number, multi: boolean) => void;
  onFixtureDragStart?: (id: number) => void;
  /**
   * `y` is given only when the drag put the fixture on a scanned truss line
   * or ring, whose hang height it takes, or took it off one again, when it
   * is the height the fixture was picked up at.
   */
  onFixtureDrag?: (id: number, x: number, z: number, y?: number) => void;
  /**
   * Several selected fixtures carried together, each by the same shift.
   * Without this a press on one of several selected fixtures selects and
   * drags that one alone, as it always did.
   */
  onFixturesDrag?: (moves: PlanMove[]) => void;
  onFixtureDragEnd?: (id: number) => void;
  /** A double-click on a fixture: select the whole row it is in. */
  onFixtureSelectRow?: (id: number) => void;
  /**
   * Makes these the selection: what a box dragged over empty floor took in
   * (with Shift, Ctrl or Cmd, added to what was selected). Without this a
   * drag over empty floor draws no box, as it never did.
   */
  onSelectFixtures?: (ids: number[]) => void;
  /**
   * Whether the plan answers the keyboard: R selects the row of the selected
   * fixture, M mirrors the selection (where `onMirror` is given), the arrow
   * keys nudge the selection by the grid step (Shift: ten steps) and Escape
   * clears it. Off unless asked for, so a plan shown
   * somewhere it is not being edited never takes a key. A nudge is reported
   * as a drag is: `onFixtureDragStart`, one `onFixturesDrag`, `onFixtureDragEnd`.
   */
  keyboard?: boolean;
  /**
   * Whether the keys are also offered as buttons over the plan while
   * something is selected: four arrows, a 1x / 10x switch, Select row and
   * Lay on truss, for a phone or a tablet. A tap is the matching key. Off
   * unless asked for, like the keyboard.
   */
  nudgePad?: boolean;
  /**
   * Lays the selection along the nearest scanned truss: the nudge pad's Lay
   * on truss button, which is left out when this is.
   */
  onLayRow?: () => void;
  /**
   * How far apart Lay on truss lays a row, shown in the nudge pad next to
   * its button and changed there. The choice is left out when
   * `onLayChoiceChange` is.
   */
  layChoice?: LayChoice;
  onLayChoiceChange?: (choice: LayChoice) => void;
  /**
   * Mirrors the selection left to right about the centre line: the M key
   * (with `keyboard` on) and the nudge pad's Mirror button, which is left
   * out when this is. The plan only asks; the editor makes the move.
   */
  onMirror?: () => void;
  /**
   * Spaces the selection evenly between its two ends: the nudge pad's Even
   * button, which is left out when this is and needs three selected.
   */
  onSpaceEvenly?: () => void;
  /** `y` is given only when the drop landed on a scanned truss line or ring. */
  onDropFromPalette?: (fixtureId: number, x: number, z: number, y?: number) => void;
  /**
   * Edit Room's walls mode: each corner of the scanned room's walls gets a
   * numbered handle that can be dragged, and fixtures take no press, so a
   * corner under a fixture's icon can still be reached and no light is moved
   * by mistake. Off unless asked for.
   */
  wallsEdit?: boolean;
  /**
   * A corner of the walls let go somewhere new: called once for a drag, when
   * it ends, and never for a press that stayed within 5 pixels. `index` is
   * the corner's place in the outline, from 0 (a box room's four are numbered
   * from upstage stage right, clockwise seen from above). The plan shows the
   * corner where it was dropped until what this returns has settled, then
   * draws the room it is given: a move that was refused goes back.
   */
  onWallCornerMove?: (index: number, x: number, z: number) => void | Promise<unknown>;
  /**
   * Edit Room's "Arrange room items on the plan": each raised area, truss
   * line and ring the plan draws can be pressed to select it and dragged to
   * move it; the selected one shows its handles (a line's length and
   * heading, a ring's radius) and answers the arrow keys. Fixtures take no
   * press, as in walls mode. Off unless asked for.
   */
  itemsEdit?: boolean;
  /** The item that is selected in that mode, by its key (`risers:0`), or null. */
  selectedItemKey?: string | null;
  /** A press on an item selects it; a click on empty floor, or Escape, selects none (null). */
  onItemSelect?: (key: string | null) => void;
  /**
   * An item, or one of its handles, let go somewhere new: called once for a
   * drag, when it ends, and never for a press that stayed within 5 pixels or
   * a drag that ended where it began. `kind` and `index` are the item's list
   * and its place in it as stored. `changes` holds only what the drag set:
   * the middle for a move, `length`, `heading_deg` or `radius` for a handle.
   * The plan shows the item where it was dropped until what this returns has
   * settled, then draws the room it is given: a change refused goes back.
   */
  onItemChange?: (kind: ShellItemKind, index: number, changes: ShellItemChanges) => void | Promise<unknown>;
  /**
   * An arrow key pressed with an item selected: move it by this shift (the
   * grid step; ten with Shift). One call for each press; a key held down
   * does not repeat. The shift is given, not a position, so that the editor
   * can add it to where the item is once the request before it is answered.
   */
  onItemNudge?: (kind: ShellItemKind, index: number, dx: number, dz: number) => void;
  /** A stage plot image drawn under the fixtures, or null for none. */
  underlay?: PlanUnderlay | null;
  /**
   * Calibrating the stage plot: a click on the plan is a picked point, given
   * in plan metres, and fixtures take no press (as in walls mode). Off unless given.
   */
  onPlanPick?: (x: number, z: number) => void;
  /** The points picked so far, drawn over the plan. */
  pickMarks?: PlanPickMark[];
}

/** A finger or pen that is down on the plan, until it is lifted. */
interface TouchSession {
  /** Which pointer: a second finger is not this one. */
  pointerId: number;
  /** Where it went down, on the screen. */
  down: ScreenPoint;
  /** Where it is now: what the long-press goes by when its time is up. */
  last: ScreenPoint;
}

/** One press on empty floor, until it is let go: a click, or a selection box. */
interface BoxSession {
  /** Where the pointer went down, on the screen. */
  down: ScreenPoint;
  /** The same place on the plan: the box's first corner. */
  from: PlanPoint;
  /** Where the pointer is now on the plan: the opposite corner. */
  to: PlanPoint;
  /** Shift, Ctrl or Cmd was held at the press: the box adds to the selection. */
  additive: boolean;
  /** True once the pointer has gone past the drag threshold: until then it is a click. */
  started: boolean;
  /**
   * A finger held here for a long-press: the box it goes on to draw adds to
   * the selection, and lifted without drawing one it clears nothing.
   */
  armed: boolean;
}

/** One press on a fixture, until it is let go. */
interface DragSession {
  /** Where the pointer went down, on the screen: the press is a drag once it is 5 pixels from here. */
  down: ScreenPoint;
  /** The fixture under the pointer. */
  leadId: number;
  /** Where each fixture being carried stood when it was picked up; the lead alone unless a row is. */
  members: Array<{ id: number; x: number; y: number; z: number }>;
  /** The lead's position less the pointer's, unsnapped, so the fixture does not jump to the pointer. */
  offset: { x: number; z: number };
  /** The shift the row has now. */
  shift: RowShift;
  /** True once the drag has put a fixture on scanned truss: from then on heights are reported. */
  heightTouched: boolean;
  /** True once the pointer has gone past the drag threshold with the fixture held. */
  moved: boolean;
  /** A plain press on one of several selected fixtures: selects it alone if let go without a move. */
  collapseOnRelease: boolean;
  /**
   * True once the drag has been reported as begun (`onFixtureDragStart`). A
   * mouse press reports it at once. A finger does not until it is dragging,
   * so a tap or a long-press reports no drag at all.
   */
  started: boolean;
  /**
   * A finger on a fixture that is not being carried with a selection: it is
   * selected alone when the press turns into a drag, as a mouse press
   * selects it at once. Left until then so a long-press can add it to the
   * selection instead.
   */
  selectOnDrag: boolean;
  /** A long-press has been taken from this press: it moves nothing and selects nothing more. */
  spent: boolean;
}

export default function StageView2D({
  width,
  depth,
  fixtures,
  roomShell,
  selectedIds,
  gridSize = 0.5,
  snapMode = 'grid',
  readonly = false,
  onFixtureClick,
  onFixtureDragStart,
  onFixtureDrag,
  onFixturesDrag,
  onFixtureDragEnd,
  onFixtureSelectRow,
  onSelectFixtures,
  keyboard = false,
  nudgePad = false,
  onLayRow,
  layChoice,
  onLayChoiceChange,
  onMirror,
  onSpaceEvenly,
  onDropFromPalette,
  wallsEdit = false,
  onWallCornerMove,
  itemsEdit = false,
  selectedItemKey = null,
  onItemSelect,
  onItemChange,
  onItemNudge,
  underlay = null,
  onPlanPick,
  pickMarks,
}: StageView2DProps) {
  const picking = !!onPlanPick && !readonly;
  // A press on a room item or one of its handles, and where its drag has the item.
  const itemRef = useRef<ItemSession | null>(null);
  const [itemPreview, setItemPreview] = useState<{ key: string; shape: ItemShape; readout: string } | null>(null);
  // Fixtures take no press while the room itself is being edited on the plan,
  // or a stage plot is being calibrated on it.
  const roomEdit = wallsEdit || itemsEdit || picking;
  // A press on a corner of the walls, and where its drag has the corner.
  const cornerRef = useRef<CornerSession | null>(null);
  const [cornerPreview, setCornerPreview] = useState<{ index: number; x: number; z: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  // The plan's own box: what a press on the plan gives the focus to, so the
  // keys come back from a text field or a drop-down.
  const planRef = useRef<HTMLDivElement>(null);
  // The finger or pen that is down, and the timer that makes it a long-press.
  const touchRef = useRef<TouchSession | null>(null);
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Where a long-press on empty floor was taken, shown until the finger lifts.
  const [armedAt, setArmedAt] = useState<PlanPoint | null>(null);
  // The nudge pad's 1x / 10x switch: the touch for Shift with an arrow key.
  const [tenfold, setTenfold] = useState(false);
  // True while the focus is somewhere the plan leaves the keys to.
  const [keysAway, setKeysAway] = useState(false);
  // A press on empty floor, and the box it has drawn once it is a drag.
  const boxRef = useRef<BoxSession | null>(null);
  const [selectionBox, setSelectionBox] = useState<{ from: PlanPoint; to: PlanPoint } | null>(null);
  // The fixtures being carried: one, or a selected row. Empty when none is held.
  const [draggingIds, setDraggingIds] = useState<number[]>([]);
  const dragRef = useRef<DragSession | null>(null);
  // Set when a row drag ends, so the click that follows a release over the
  // background (a row held at a wall is not under the pointer) does not
  // deselect the row that was just moved.
  const skipBackgroundClick = useRef(false);
  const [dropPreview, setDropPreview] = useState<{ x: number; z: number; on?: string } | null>(null);
  // What the drag has snapped onto, said next to the fixture under the pointer.
  const [snapNote, setSnapNote] = useState<{ x: number; z: number; text: string } | null>(null);
  // Depth the dragged fixture started at, so its own truss stays a snap target
  // while it is lifted off it.
  const dragOriginZ = useRef<number | null>(null);

  const padding = 1;

  // The scanned room, and the part of the plan to show: the stage and its
  // margin, grown to take in a room that reaches beyond it. With no scanned
  // room the box starts at the origin and is the stage's, as it always was.
  const plan = useMemo(() => roomPlan(roomShell), [roomShell]);
  const view = useMemo(
    () => planViewBox(width, depth, padding, plan?.bounds),
    [width, depth, padding, plan],
  );
  // The walls a drag is held inside, when a scanned room is drawn; with none
  // it is held to the deck.
  const walls = plan?.walls ?? null;
  // What UPSTAGE, AUDIENCE and the scale bar are set against: the deck, or
  // the outer of the deck and the scanned walls.
  const frame = useMemo(() => planFrame(width, depth, padding, walls), [width, depth, padding, walls]);
  // The room layer's labels, nudged clear of each other.
  const labels = useMemo(() => (plan ? planLabels(plan) : null), [plan]);
  // The truss lines and rings a scan found, which a drag snaps onto. None for
  // a rig with no scanned room.
  const scannedTruss = useMemo(() => planTrussTargets(roomShell), [roomShell]);

  // The corners that can be dragged: the walls' own, numbered as the server
  // numbers them. None unless walls mode is on and the room's walls are drawn.
  const wallHandles = useMemo(
    () => (wallsEdit && !readonly && walls ? wallCorners(roomShell)?.corners ?? null : null),
    [wallsEdit, readonly, walls, roomShell],
  );
  // The walls as drawn: with a corner being dragged, or dropped and not yet
  // answered for, where the drag has it.
  const wallPoints = useMemo(() => {
    if (!walls) return null;
    if (!cornerPreview || !wallHandles || cornerPreview.index >= wallHandles.length) return wallHandles ?? walls.points;
    return wallHandles.map((corner, index) => (
      index === cornerPreview.index ? { x: cornerPreview.x, z: cornerPreview.z } : corner
    ));
  }, [walls, wallHandles, cornerPreview]);

  // The room's items that can be picked up: none unless the mode is on, and
  // null for a room with nothing in it to pick up.
  const roomItems = useMemo(() => {
    const items = itemsEdit && !readonly ? planItems(roomShell) : [];
    return items.length > 0 ? items : null;
  }, [itemsEdit, readonly, roomShell]);

  // The mode turned off under a press: the press is over, and nothing is sent.
  useEffect(() => {
    if (itemsEdit) return;
    itemRef.current = null;
    setItemPreview(null);
  }, [itemsEdit]);

  // Walls mode turned off under a press: the press is over, and nothing is sent.
  useEffect(() => {
    if (wallsEdit) return;
    cornerRef.current = null;
    setCornerPreview(null);
  }, [wallsEdit]);

  const acceptsDrop = !readonly && !!onDropFromPalette;

  // Stage coords -> SVG coords. X is 0 at centre stage, Z is 0 at centre stage and
  // grows toward the audience, which is drawn at the bottom of the plan.
  const toSvgX = useCallback((x: number) => x + width / 2 + padding, [width, padding]);
  const toSvgY = useCallback((z: number) => z + depth / 2 + padding, [depth, padding]);

  const trussLines = useMemo(() => {
    // Every fixture being carried is left out, or a row would snap to itself.
    const depths = fixtures
      .filter((f) => !draggingIds.includes(f.id))
      .map((f) => f.position_z);
    if (dragOriginZ.current !== null) depths.push(dragOriginZ.current);
    return computeTrussLines(depths);
  }, [fixtures, draggingIds]);

  const pointerToStage = useCallback(
    (clientX: number, clientY: number) => {
      if (!svgRef.current) return { x: 0, z: 0 };
      const rect = svgRef.current.getBoundingClientRect();
      const scaleX = view.width / rect.width;
      const scaleY = view.height / rect.height;
      return {
        x: view.minX + (clientX - rect.left) * scaleX - padding - width / 2,
        z: view.minY + (clientY - rect.top) * scaleY - padding - depth / 2,
      };
    },
    [view, width, depth, padding]
  );

  const applySnap = useCallback(
    (x: number, z: number, ontoScannedTruss = false): { x: number; z: number; snappedTo?: SnapLine } => {
      if (snapMode === 'none') return { x, z };
      // A drag near a truss line or ring the scan found goes onto it, as in
      // the 3D view, before the grid or the plan's own truss lines are tried.
      // Out of its reach the snap mode carries on as it always has.
      if (ontoScannedTruss && scannedTruss.length > 0) {
        const onTruss = snapToScannedTruss(x, z, scannedTruss);
        if (onTruss.snappedTo) return { x: onTruss.x, z: onTruss.z, snappedTo: onTruss.snappedTo };
      }
      if (snapMode === 'truss') {
        // No truss to hang on yet: leave the position untouched rather than
        // pretending to snap.
        if (trussLines.length === 0) return { x, z };
        const nearest = trussLines.reduce((best, line) =>
          Math.abs(line - z) < Math.abs(best - z) ? line : best
        );
        return { x, z: nearest };
      }
      // In a scanned room the grid carries on past the deck: stopping at the
      // deck's last line would bring a fixture hung out in the room onto the
      // deck the moment it was picked up.
      if (walls) return snapToRoomGrid(x, z, gridSize);
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
    [snapMode, gridSize, trussLines, width, depth, walls, scannedTruss]
  );

  // The deck, and only the deck. The band below the stage is drawn and labelled
  // AUDIENCE: a fixture dropped there renders on top of that label with its own
  // name clipped off the viewBox, and the rig would claim a light is standing in
  // the crowd.
  // With a scanned room drawn it is the room instead: inside its walls (the
  // floor outline, or the box), where the scan may have hung fixtures well
  // beyond the deck.
  const clampToPlan = useCallback(
    (x: number, z: number) => holdOnPlan(x, z, width, depth, walls),
    [width, depth, walls]
  );

  // A label of the room layer, where the layout put it; turned only when it
  // lies along a line that is not straight across.
  const roomLabel = (label: PlanLabel, fill: string) => (
    <text
      x={toSvgX(label.x)}
      y={toSvgY(label.z)}
      transform={label.angle !== 0 ? `rotate(${label.angle} ${toSvgX(label.x)} ${toSvgY(label.z)})` : undefined}
      textAnchor="middle"
      fill={fill}
      fontSize={label.size}
    >
      {label.text}
    </text>
  );

  /**
   * Where a snapped position ends up once it is held to the plan, and the
   * scanned truss it is then on: none when it was not snapped to any, or when
   * the walls held it off the truss it was snapped to.
   */
  const settle = (snapped: { x: number; z: number; snappedTo?: SnapLine }) => {
    const pos = clampToPlan(snapped.x, snapped.z);
    const on = snapped.snappedTo && onPlanTarget(snapped.snappedTo, pos.x, pos.z) ? snapped.snappedTo : null;
    return { ...pos, on };
  };

  // A press on the plan takes the focus, so the keys are the plan's again
  // after the rig's name was typed or a snap mode chosen. Only where the plan
  // answers the keyboard: anywhere else it has nothing to take the focus for.
  const focusPlan = () => {
    if (!(keyboard || itemsEdit) || readonly) return;
    const box = planRef.current;
    if (box && document.activeElement !== box) box.focus({ preventScroll: true });
  };

  /**
   * A press on a fixture. `multi` is Shift, Ctrl or Cmd held by a mouse.
   * `touch` is a finger or a pen, which has no such key: nothing is selected
   * or reported until the press has shown what it is. Let go at once it is a
   * tap and selects the fixture alone; carried 5 pixels it is a drag, as the
   * mouse's; held still for half a second it is a long-press (`takeLongPress`).
   */
  const pressFixture = (at: ScreenPoint, fixtureId: number, multi: boolean, touch: boolean) => {
    const fixture = fixtures.find((f) => f.id === fixtureId);
    if (!fixture) return;
    skipBackgroundClick.current = false;

    // Shift, Ctrl and Cmd all add to, or take from, the selection.
    const wasSelected = selectedIds.has(fixtureId);
    let carried = [fixtureId];
    let collapseOnRelease = false;
    let selectOnDrag = false;
    if (touch) {
      // A tap selects it alone, whatever was selected.
      collapseOnRelease = true;
      // One of several selected is carried with them; any other is selected
      // alone once it is being dragged, and carried alone.
      if (wasSelected && selectedIds.size > 1 && onFixturesDrag) carried = [...selectedIds];
      else selectOnDrag = true;
    } else if (multi) {
      onFixtureClick?.(fixtureId, true);
      if (onFixturesDrag) {
        // Taken out of the selection: there is nothing to carry.
        if (wasSelected) return;
        carried = [...selectedIds, fixtureId];
      }
    } else if (wasSelected && selectedIds.size > 1 && onFixturesDrag) {
      // One of several selected fixtures: the selection is kept and carried
      // together. Let go without a move, it is selected alone after all.
      carried = [...selectedIds];
      collapseOnRelease = true;
    } else {
      onFixtureClick?.(fixtureId, false);
    }

    const members = fixtures
      .filter((f) => carried.includes(f.id))
      .map((f) => ({ id: f.id, x: f.position_x, y: f.position_y, z: f.position_z }));
    dragOriginZ.current = fixture.position_z;

    // Offset is held in unsnapped coordinates; snapping is applied to the final
    // position so grid mode actually lands on the grid.
    const raw = pointerToStage(at.clientX, at.clientY);
    dragRef.current = {
      down: { clientX: at.clientX, clientY: at.clientY },
      leadId: fixtureId,
      members,
      offset: { x: fixture.position_x - raw.x, z: fixture.position_z - raw.z },
      shift: { dx: 0, dz: 0 },
      heightTouched: false,
      moved: false,
      collapseOnRelease,
      started: !touch,
      selectOnDrag,
      spent: false,
    };
    setDraggingIds(members.map((m) => m.id));
    if (!touch) onFixtureDragStart?.(fixtureId);
  };

  const handleMouseDown = (e: React.MouseEvent, fixtureId: number) => {
    // While the walls or the room's items are being moved a fixture takes no press.
    if (readonly || roomEdit) return;
    e.stopPropagation();
    pressFixture(e, fixtureId, e.shiftKey || e.ctrlKey || e.metaKey, false);
  };

  /** A press on a corner of the walls: a drag once it has gone 5 pixels, and nothing at all before. */
  const pressCorner = (at: ScreenPoint, index: number) => {
    const corner = wallHandles?.[index];
    if (!corner) return;
    skipBackgroundClick.current = false;
    const raw = pointerToStage(at.clientX, at.clientY);
    cornerRef.current = {
      index,
      down: { clientX: at.clientX, clientY: at.clientY },
      offset: { x: corner.x - raw.x, z: corner.z - raw.z },
      at: { x: corner.x, z: corner.z },
      moved: false,
    };
  };

  const handleCornerMouseDown = (e: React.MouseEvent, index: number) => {
    if (readonly || e.button !== 0) return;
    e.stopPropagation();
    pressCorner(e, index);
  };

  /**
   * A press on a room item (`grip` 'move') or on one of the selected item's
   * handles. The item is selected at once; nothing moves until the press has
   * gone 5 pixels.
   */
  const pressItem = (at: ScreenPoint, item: PlanItem, grip: ItemGrip) => {
    // A drop is still waiting for its answer: the room on screen is not yet
    // the one a new drag would start from, so the press is let pass.
    if (itemPreview && !itemRef.current) return;
    skipBackgroundClick.current = false;
    if (item.key !== selectedItemKey) onItemSelect?.(item.key);
    const raw = pointerToStage(at.clientX, at.clientY);
    const held = grip === 'move'
      ? shapeCentre(item.shape)
      : itemHandles(item.shape).find((handle) => handle.grip === grip) ?? shapeCentre(item.shape);
    itemRef.current = {
      item,
      grip,
      down: { clientX: at.clientX, clientY: at.clientY },
      offset: { x: held.x - raw.x, z: held.z - raw.z },
      changes: null,
      moved: false,
    };
  };

  const handleItemMouseDown = (e: React.MouseEvent, item: PlanItem, grip: ItemGrip) => {
    if (readonly || e.button !== 0) return;
    e.stopPropagation();
    pressItem(e, item, grip);
  };

  /** A press on empty floor, by a mouse (`additive`: Shift, Ctrl or Cmd held) or a finger. */
  const pressFloor = (at: ScreenPoint, additive: boolean) => {
    const from = pointerToStage(at.clientX, at.clientY);
    boxRef.current = {
      down: { clientX: at.clientX, clientY: at.clientY },
      from,
      to: from,
      additive,
      started: false,
      armed: false,
    };
  };

  // A press on empty floor: a click that clears the selection, unless the
  // pointer goes past the drag threshold, when it draws a selection box.
  // Nothing is prevented here: the press still takes the focus out of a text
  // field, which is what hands the keyboard back to the plan.
  const handleBackgroundMouseDown = (e: React.MouseEvent) => {
    skipBackgroundClick.current = false;
    // No selection box while the room is being edited: no fixture is selected or carried there.
    if (readonly || roomEdit || !onSelectFixtures || e.button !== 0) return;
    pressFloor(e, e.shiftKey || e.ctrlKey || e.metaKey);
  };

  /** Ends a press on empty floor. A box that was drawn selects what is in it, unless it is `cancelled`. */
  const endBox = (cancelled: boolean) => {
    const boxing = boxRef.current;
    boxRef.current = null;
    if (!boxing) return;
    if (boxing.armed) setArmedAt(null);
    if (!boxing.started) {
      // A long-press let go without a box drawn changes nothing: the click
      // that may follow it must not clear the selection it was to add to.
      if (boxing.armed) skipBackgroundClick.current = true;
      return;
    }
    setSelectionBox(null);
    // The click that follows the release is the end of this drag, not a click
    // on empty floor: it must not clear what was just selected, or kept.
    skipBackgroundClick.current = true;
    if (cancelled) return;
    onSelectFixtures?.(
      boxSelection(selectedIds, fixturesInBox(fixtures, boxing.from, boxing.to), boxing.additive),
    );
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const cornering = cornerRef.current;
    if (cornering && !readonly) {
      // A click, or the wobble of one, moves no wall: nothing is sent and no undo step is left.
      if (!cornering.moved && !pastDragThreshold(cornering.down, e)) return;
      cornering.moved = true;
      const raw = pointerToStage(e.clientX, e.clientY);
      let at = { x: raw.x + cornering.offset.x, z: raw.z + cornering.offset.z };
      // Onto the grid, as a fixture goes, unless the snap is off or Alt is held.
      if (snapMode !== 'none' && !e.altKey) at = snapToRoomGrid(at.x, at.z, gridSize);
      const held = (value: number) => roundMm(Math.min(Math.max(value, -WALL_LIMITS.reach), WALL_LIMITS.reach));
      cornering.at = { x: held(at.x), z: held(at.z) };
      setCornerPreview({ index: cornering.index, ...cornering.at });
      return;
    }

    const arranging = itemRef.current;
    if (arranging && !readonly) {
      // A click, or the wobble of one, moves no item: nothing is sent and no undo step is left.
      if (!arranging.moved && !pastDragThreshold(arranging.down, e)) return;
      arranging.moved = true;
      const raw = pointerToStage(e.clientX, e.clientY);
      // Onto the grid, as a corner of the walls goes, unless the snap is off or Alt is held. With
      // Shift held a rotate handle turns in steps of 15 degrees.
      const dragged = dragItem(
        arranging.item, arranging.grip,
        { x: raw.x + arranging.offset.x, z: raw.z + arranging.offset.z },
        { on: snapMode !== 'none' && !e.altKey, gridSize, coarse: e.shiftKey },
      );
      arranging.changes = dragged.changes;
      setItemPreview({ key: arranging.item.key, shape: dragged.shape, readout: dragged.readout });
      return;
    }

    const boxing = boxRef.current;
    if (boxing && !readonly) {
      if (!boxing.started && !pastDragThreshold(boxing.down, e)) return;
      boxing.started = true;
      boxing.to = pointerToStage(e.clientX, e.clientY);
      setSelectionBox({ from: boxing.from, to: boxing.to });
      return;
    }

    const drag = dragRef.current;
    // A press a long-press was taken from carries nothing, wherever it goes.
    if (!drag || readonly || drag.spent) return;
    const lead = drag.members.find((m) => m.id === drag.leadId);
    if (!lead) return;
    // A click, or the wobble of one, is not a drag: nothing moves, and so
    // nothing is saved or left to undo, until the pointer is 5 pixels away.
    if (!drag.moved && !pastDragThreshold(drag.down, e)) return;
    if (!drag.started) {
      // A finger that has turned out to be dragging: what a mouse press does
      // at once is done now, the selection first and then the pick-up.
      if (drag.selectOnDrag) onFixtureClick?.(drag.leadId, false);
      drag.started = true;
      onFixtureDragStart?.(drag.leadId);
    }
    drag.moved = true;
    const raw = pointerToStage(e.clientX, e.clientY);
    // Holding Alt lets go of the scanned truss for this drag, as it does in
    // the 3D view; the snap mode set to none lets go of everything.
    const snapped = applySnap(raw.x + drag.offset.x, raw.z + drag.offset.z, !e.altKey);

    if (drag.members.length > 1) {
      // A row: the lead goes where one fixture would, and every other member
      // takes the same shift, cut short where any of them would leave the room.
      const shift = holdRowShift(
        walls, width, depth, drag.members, drag.shift,
        { dx: snapped.x - lead.x, dz: snapped.z - lead.z },
      );
      drag.shift = shift;
      const target = snapped.snappedTo ?? null;
      const placed = drag.members.map((m) => {
        const x = m.x + shift.dx;
        const z = m.z + shift.dz;
        return { member: m, x, z, on: !!target && onPlanTarget(target, x, z) };
      });
      const onCount = placed.filter((p) => p.on).length;
      if (onCount > 0) drag.heightTouched = true;
      // On the truss a member takes its hang height; off it, the height it
      // was picked up at. No height is reported in a drag that met no truss.
      onFixturesDrag?.(placed.map((p): PlanMove => (
        drag.heightTouched
          ? { id: p.member.id, x: p.x, z: p.z, y: p.on && target ? target.height : p.member.y }
          : { id: p.member.id, x: p.x, z: p.z }
      )));
      setSnapNote(target && onCount > 0
        ? { x: lead.x + shift.dx, z: lead.z + shift.dz, text: rowReadoutText(target, onCount, placed.length) }
        : null);
      return;
    }

    const pos = settle(snapped);
    if (pos.on) {
      drag.heightTouched = true;
      onFixtureDrag?.(drag.leadId, pos.x, pos.z, pos.on.height);
      setSnapNote({ x: pos.x, z: pos.z, text: snapReadoutText(pos.on) });
      return;
    }
    // Off the truss again: back to the height it was picked up at.
    if (drag.heightTouched) onFixtureDrag?.(drag.leadId, pos.x, pos.z, lead.y);
    else onFixtureDrag?.(drag.leadId, pos.x, pos.z);
    setSnapNote(null);
  };

  const endDrag = (released: boolean) => {
    const cornering = cornerRef.current;
    if (cornering) {
      // Let go, or carried off the plan: either way the corner is where the drag had it.
      cornerRef.current = null;
      if (!cornering.moved) return;
      // The click that follows the release is the end of this drag.
      skipBackgroundClick.current = true;
      // One call for the whole drag: one request, and one step of the room's undo.
      const sent = onWallCornerMove?.(cornering.index, cornering.at.x, cornering.at.z);
      // Shown where it was dropped until the answer is in; then the room given is drawn.
      void Promise.resolve(sent).catch(() => undefined).then(() => setCornerPreview(null));
      return;
    }
    const arranging = itemRef.current;
    if (arranging) {
      // Let go, or carried off the plan: either way the item is where the drag had it.
      itemRef.current = null;
      if (!arranging.moved) return;
      // The click that follows the release is the end of this drag: the item stays selected.
      skipBackgroundClick.current = true;
      // Brought back to where it began: nothing to send, and no undo step.
      if (!arranging.changes) {
        setItemPreview(null);
        return;
      }
      // One call for the whole drag: one request, and one step of the room's undo.
      const sent = onItemChange?.(arranging.item.kind, arranging.item.index, arranging.changes);
      // Shown where it was dropped until the answer is in; then the room given is drawn.
      void Promise.resolve(sent).catch(() => undefined).then(() => setItemPreview(null));
      return;
    }
    // Let go, or carried off the plan: either way the box takes what it holds.
    endBox(false);
    const drag = dragRef.current;
    if (drag) {
      if (released && drag.collapseOnRelease && !drag.moved && !drag.spent) onFixtureClick?.(drag.leadId, false);
      if (drag.members.length > 1 && drag.moved) skipBackgroundClick.current = true;
      // A finger's tap or long-press was never reported as a drag begun.
      if (drag.started) onFixtureDragEnd?.(drag.leadId);
    }
    dragRef.current = null;
    setDraggingIds((ids) => (ids.length === 0 ? ids : []));
    setSnapNote(null);
    dragOriginZ.current = null;
  };

  // ---- A finger or a pen ---------------------------------------------------
  // Pointer events, for the pointers that have no Shift to hold. A mouse is
  // left to the mouse events above, which is what keeps it exactly as it was;
  // a finger's press is prevented, so the browser sends no mouse events of
  // its own after it and nothing is handled twice.

  const clearLongPress = () => {
    if (longPressTimer.current !== null) clearTimeout(longPressTimer.current);
    longPressTimer.current = null;
  };

  // Made again on every render, like the key handler, so the timer that
  // calls it sees the selection as it is when the time is up.
  const takeLongPress = useRef<() => void>(() => {});
  takeLongPress.current = () => {
    longPressTimer.current = null;
    const touch = touchRef.current;
    if (!touch) return;
    const held = (phase: 'press' | 'drag') => pressPhase(phase, touch.down, touch.last, LONG_PRESS_MS) === 'long-press';

    const drag = dragRef.current;
    if (drag) {
      if (drag.spent || !held(drag.moved ? 'drag' : 'press')) return;
      // The touch for Shift-click: the fixture is added to the selection, or
      // taken out of it. The press is then spent: it carries nothing and no
      // drag was ever reported, so nothing moves and no undo step is left.
      drag.spent = true;
      setDraggingIds((ids) => (ids.length === 0 ? ids : []));
      dragOriginZ.current = null;
      onFixtureClick?.(drag.leadId, true);
      return;
    }

    const boxing = boxRef.current;
    if (boxing && held(boxing.started ? 'drag' : 'press')) {
      // The touch for a Shift-drag over empty floor: the box this finger
      // goes on to draw adds to the selection.
      boxing.additive = true;
      boxing.armed = true;
      setArmedAt(boxing.from);
    }
  };

  const startLongPress = () => {
    clearLongPress();
    longPressTimer.current = setTimeout(() => takeLongPress.current(), LONG_PRESS_MS);
  };

  /**
   * Ends a finger's press. `lifted`: let go, as a mouse button is. `left`:
   * carried off the plan, as a mouse is, so a box takes what it held.
   * `cancelled`: the browser took the finger for something of its own, and a
   * box then selects nothing.
   */
  const endTouch = (how: 'lifted' | 'left' | 'cancelled') => {
    clearLongPress();
    touchRef.current = null;
    if (how === 'cancelled') endBox(true);
    endDrag(how === 'lifted');
  };

  /** Begins a finger's press: false for one the plan is not to take. */
  const beginTouch = (e: React.PointerEvent): boolean => {
    if (!isTouchPointer(e.pointerType) || readonly) return false;
    // No mouse events after this press, no text selection and no page pan.
    e.preventDefault();
    // A second finger while one is down is not a press of its own.
    if (touchRef.current && e.isPrimary === false) return false;
    // A press whose end never arrived is ended here, not left to block this one.
    if (touchRef.current) endTouch('cancelled');
    const at = { clientX: e.clientX, clientY: e.clientY };
    touchRef.current = { pointerId: e.pointerId, down: at, last: at };
    focusPlan();
    return true;
  };

  /** A finger on a corner of the walls: the same drag as a mouse's. */
  const handleCornerPointerDown = (e: React.PointerEvent, index: number) => {
    if (!isTouchPointer(e.pointerType) || readonly) return;
    e.stopPropagation();
    if (!beginTouch(e)) return;
    pressCorner(e, index);
  };

  /** A finger on a room item or one of its handles: the same drag as a mouse's. */
  const handleItemPointerDown = (e: React.PointerEvent, item: PlanItem, grip: ItemGrip) => {
    if (!isTouchPointer(e.pointerType) || readonly) return;
    e.stopPropagation();
    if (!beginTouch(e)) return;
    pressItem(e, item, grip);
  };

  const handleFixturePointerDown = (e: React.PointerEvent, fixtureId: number) => {
    if (!isTouchPointer(e.pointerType) || readonly || roomEdit) return;
    e.stopPropagation();
    if (!beginTouch(e)) return;
    pressFixture(e, fixtureId, false, true);
    if (dragRef.current) startLongPress();
  };

  const handleBackgroundPointerDown = (e: React.PointerEvent) => {
    if (!beginTouch(e)) return;
    skipBackgroundClick.current = false;
    // Where no selection can be set there is no box, as for a mouse: the tap
    // is the click that follows it. Nor is there one while the room is edited.
    if (!onSelectFixtures || roomEdit) return;
    pressFloor(e, false);
    startLongPress();
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    const touch = touchRef.current;
    if (!touch || e.pointerId !== touch.pointerId) return;
    touch.last = { clientX: e.clientX, clientY: e.clientY };
    // Gone 5 pixels before the time was up: a drag, and never a long-press.
    if (pastDragThreshold(touch.down, touch.last)) clearLongPress();
    handleMouseMove(e);
  };

  const handlePointerEnd = (e: React.PointerEvent, how: 'lifted' | 'left' | 'cancelled') => {
    const touch = touchRef.current;
    if (!touch || e.pointerId !== touch.pointerId) return;
    endTouch(how);
  };

  // A press abandoned when the plan goes away must not fire afterwards.
  useEffect(() => () => {
    if (longPressTimer.current !== null) clearTimeout(longPressTimer.current);
  }, []);

  const handleBackgroundClick = (e?: React.MouseEvent) => {
    if (skipBackgroundClick.current) {
      skipBackgroundClick.current = false;
      return;
    }
    // Calibrating a stage plot: the click is a point picked, and selects nothing.
    if (picking) {
      if (e) {
        const at = pointerToStage(e.clientX, e.clientY);
        onPlanPick?.(at.x, at.z);
      }
      return;
    }
    // While the room's items are arranged, empty floor lets go of the item, not of a fixture.
    if (itemsEdit && !readonly) {
      if (selectedItemKey !== null) onItemSelect?.(null);
      return;
    }
    if (!readonly) {
      onFixtureClick?.(-1, false); // Deselect
    }
  };

  /**
   * Moves the selection by one shift, held inside the room: what an arrow
   * key does, and a tap on the nudge pad's arrow. One call is one drag
   * reported, so it is one batch-update and one undo step.
   */
  const nudgeBy = (shift: RowShift) => {
    const moves = nudgeMoves(fixtures, selectedIds, shift, walls, width, depth);
    // Already against the wall it is pushed at: nothing to move, save or undo.
    if (moves.length === 0) return;
    // Reported as a drag is, from pick-up to letting go, so it is saved and
    // undone as one: a single batch-update and a single undo step.
    const lead = moves[0].id;
    onFixtureDragStart?.(lead);
    if (onFixturesDrag) onFixturesDrag(moves);
    else moves.forEach((move) => onFixtureDrag?.(move.id, move.x, move.z));
    onFixtureDragEnd?.(lead);
  };

  // The keyboard. The handler is kept in a ref and made again on every
  // render, so the one listener on the window always sees the selection and
  // the positions as they are now.
  const keyHandler = useRef<(e: KeyboardEvent) => void>(() => {});
  keyHandler.current = (e: KeyboardEvent) => {
    if (e.defaultPrevented) return;
    // Typing in a field, choosing in a drop-down, or anything in a dialog.
    if (keysBelongElsewhere(e.target) || keysBelongElsewhere(document.activeElement)) return;

    if (e.key === 'Escape') {
      // A box being drawn is let go of first, and the selection is left as it was.
      if (boxRef.current) {
        endBox(true);
        return;
      }
      if (dragRef.current) return;
      if (selectedIds.size > 0) onFixtureClick?.(-1, false);
      return;
    }

    // Ctrl+R reloads the page and Alt+Left goes back: those are the browser's.
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    // Nothing is selected or nudged under a pointer that is holding something.
    if (dragRef.current || boxRef.current) return;

    if (e.key === 'r' || e.key === 'R') {
      // The row of the first selected fixture in the rig's order, as the
      // Select row button goes by.
      const first = fixtures.find((f) => selectedIds.has(f.id));
      if (!first || !onFixtureSelectRow || e.repeat) return;
      e.preventDefault();
      onFixtureSelectRow(first.id);
      return;
    }

    if (e.key === 'm' || e.key === 'M') {
      // One press, one mirror: a key held down would mirror it back and
      // forth, an undo step and a save each time.
      if (!onMirror || e.repeat || !fixtures.some((f) => selectedIds.has(f.id))) return;
      e.preventDefault();
      onMirror();
      return;
    }

    const shift = nudgeShift(e.key, gridSize, e.shiftKey);
    // With nothing selected an arrow key is left to scroll the page.
    if (!shift || selectedIds.size === 0) return;
    e.preventDefault();
    // One press, one step: a key held down does not repeat, or it would fill
    // the undo history and send a save for every repeat. Shift goes further.
    if (e.repeat) return;
    nudgeBy(shift);
  };

  useEffect(() => {
    if (!keyboard || readonly) return undefined;
    const onKeyDown = (e: KeyboardEvent) => keyHandler.current(e);
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [keyboard, readonly]);

  // The keys while the room's items are arranged: the arrows move the
  // selected item by the grid step (Shift: ten steps), one call for each
  // press, and Escape lets go of it. A listener of its own: the plan's other
  // keys (`keyboard`) are off in this mode, where no fixture is selected.
  const itemKeyHandler = useRef<(e: KeyboardEvent) => void>(() => {});
  itemKeyHandler.current = (e: KeyboardEvent) => {
    if (e.defaultPrevented) return;
    if (keysBelongElsewhere(e.target) || keysBelongElsewhere(document.activeElement)) return;
    const selected = roomItems?.find((item) => item.key === selectedItemKey);
    if (e.key === 'Escape') {
      // Not under a drag: the item being carried stays selected.
      if (selected && !itemRef.current) onItemSelect?.(null);
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const shift = nudgeShift(e.key, gridSize, e.shiftKey);
    // With nothing selected an arrow key is left to scroll the page.
    if (!shift || !selected) return;
    e.preventDefault();
    // One press, one request and one undo step: a key held down does not
    // repeat. Nothing is nudged under a pointer that is holding an item.
    if (e.repeat || itemRef.current) return;
    onItemNudge?.(selected.kind, selected.index, shift.dx, shift.dz);
  };

  useEffect(() => {
    if (!itemsEdit || readonly) return undefined;
    const onKeyDown = (e: KeyboardEvent) => itemKeyHandler.current(e);
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [itemsEdit, readonly]);

  // The focus cue: while the focus is in a field or a drop-down the keys are
  // not the plan's, and the plan says how to get them back. Each focus event
  // says where the focus is going, so nothing is read back after the fact.
  useEffect(() => {
    if (!keyboard || readonly) {
      setKeysAway(false);
      return undefined;
    }
    setKeysAway(keysHintDue(document.activeElement));
    const onFocus = (e: FocusEvent) => setKeysAway(keysHintDue(e.target));
    // Leaving for nowhere (the page itself) is leaving for the plan's keys.
    const onBlur = (e: FocusEvent) => setKeysAway(keysHintDue(e.relatedTarget));
    // Both pairs of events, the bubbling and (captured) the plain ones: they
    // say the same thing, and not every browser has always sent the first.
    document.addEventListener('focusin', onFocus);
    document.addEventListener('focusout', onBlur);
    document.addEventListener('focus', onFocus, true);
    document.addEventListener('blur', onBlur, true);
    return () => {
      document.removeEventListener('focusin', onFocus);
      document.removeEventListener('focusout', onBlur);
      document.removeEventListener('focus', onFocus, true);
      document.removeEventListener('blur', onBlur, true);
    };
  }, [keyboard, readonly]);

  // The nudge pad: each button is its key. Nothing is nudged or selected
  // under a pointer that is holding something, as with the keys.
  const padFree = () => !dragRef.current && !boxRef.current;
  const handlePadNudge = (direction: PadDirection) => {
    const shift = padShift(direction, gridSize, tenfold);
    if (shift && padFree()) nudgeBy(shift);
  };
  const handlePadSelectRow = () => {
    // The row of the first selected fixture in the rig's order, as R goes by.
    const first = fixtures.find((f) => selectedIds.has(f.id));
    if (first && padFree()) onFixtureSelectRow?.(first.id);
  };
  const handlePadMirror = () => { if (padFree()) onMirror?.(); };
  const handlePadSpaceEvenly = () => { if (padFree()) onSpaceEvenly?.(); };
  const selectedCount = fixtures.filter((f) => selectedIds.has(f.id)).length;
  const showPad = nudgePad && !readonly && selectedCount > 0;

  // A palette drop goes onto scanned truss as a drag does, Alt letting go.
  const handleDragOver = (e: React.DragEvent) => {
    if (!acceptsDrop || !e.dataTransfer.types.includes(FIXTURE_DRAG_MIME)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    const raw = pointerToStage(e.clientX, e.clientY);
    const pos = settle(applySnap(raw.x, raw.z, !e.altKey));
    setDropPreview(pos.on ? { x: pos.x, z: pos.z, on: snapReadoutText(pos.on) } : { x: pos.x, z: pos.z });
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
    const pos = settle(applySnap(raw.x, raw.z, !e.altKey));
    // On scanned truss the new fixture hangs at the truss's height.
    if (pos.on) onDropFromPalette?.(fixtureId, pos.x, pos.z, pos.on.height);
    else onDropFromPalette?.(fixtureId, pos.x, pos.z);
  };

  // Grid lines, drawn on the same multiples of gridSize that applySnap rounds
  // to. Emitting them from the stage edge instead only lines up when half the
  // stage is a whole number of grid squares, and the depth slider steps by 0.5,
  // so half of all reachable stages would snap between two drawn lines.
  // With a scanned room drawn the grid is the room's instead (`roomGrid`
  // below): a drag snaps to it everywhere inside the walls, so it is drawn
  // everywhere inside them.
  const roomGrid = useMemo(
    () => (walls ? planGrid(walls, width, depth, gridSize) : null),
    [walls, width, depth, gridSize],
  );
  const gridLines = [];
  for (let i = -Math.floor(width / 2 / gridSize); !roomGrid && i * gridSize <= width / 2; i += 1) {
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
  for (let i = -Math.floor(depth / 2 / gridSize); !roomGrid && i * gridSize <= depth / 2; i += 1) {
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
      ref={planRef}
      // Able to hold the focus where the plan answers the keyboard, so a
      // press on it takes the keys back from a field. Not a tab stop.
      tabIndex={(keyboard || itemsEdit) && !readonly ? -1 : undefined}
      sx={{
        width: '100%',
        aspectRatio: `${view.width} / ${view.height}`,
        bgcolor: '#1a1a2e',
        borderRadius: 1,
        overflow: 'hidden',
        // What the nudge pad and the focus cue are set against.
        position: 'relative',
        outline: 'none',
      }}
    >
      <svg
        ref={svgRef}
        viewBox={`${view.minX} ${view.minY} ${view.width} ${view.height}`}
        width="100%"
        height="100%"
        // A box dragged across the plan's labels must not select their text.
        // A finger on the plan is the plan's: the browser does not pan or
        // zoom the page with it, or it would take a press away half-way.
        style={{ userSelect: 'none', touchAction: 'none', WebkitTouchCallout: 'none' }}
        onMouseDownCapture={focusPlan}
        onMouseDown={handleBackgroundMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={() => endDrag(true)}
        onMouseLeave={() => endDrag(false)}
        onPointerDown={handleBackgroundPointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={(e) => handlePointerEnd(e, 'lifted')}
        onPointerLeave={(e) => handlePointerEnd(e, 'left')}
        onPointerCancel={(e) => handlePointerEnd(e, 'cancelled')}
        // A finger held down is a long-press here, not the browser's menu.
        onContextMenu={(e) => { if (touchRef.current) e.preventDefault(); }}
        onClick={handleBackgroundClick}
        onDragOver={handleDragOver}
        onDragLeave={() => setDropPreview(null)}
        onDrop={handleDrop}
      >
        {/* The scanned room's floor, under the stage */}
        {plan?.walls && (
          <polygon
            data-testid="room-plan-floor"
            points={planPolygonPoints(wallPoints ?? plan.walls.points, toSvgX, toSvgY)}
            fill={ROOM_FLOOR}
          />
        )}

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

        {/* The stage plot underlay: above the floor, under the grid, the room and the
            fixtures. It takes no press, so dragging and dropping work through it. */}
        {underlay && (
          <g transform={`translate(${toSvgX(0)} ${toSvgY(0)}) ${svgMatrix(underlay.matrix)}`} pointerEvents="none">
            <image
              data-testid="stage-plot-underlay"
              href={underlay.href}
              x={0}
              y={0}
              width={underlay.widthPx}
              height={underlay.heightPx}
              opacity={underlay.opacity}
              preserveAspectRatio="none"
            />
          </g>
        )}

        {/* Grid: the deck's, or with a scanned room drawn the room's, across
            its floor and the deck and not in a notch outside the walls. */}
        {gridLines}
        {roomGrid && (
          <g data-testid="room-plan-grid">
            {roomGrid.map((line, index) => (
              <line
                key={`rg-${index}`}
                x1={toSvgX(line.x1)}
                y1={toSvgY(line.z1)}
                x2={toSvgX(line.x2)}
                y2={toSvgY(line.z2)}
                stroke="#333"
                strokeWidth={line.major ? 0.03 : 0.01}
                opacity={line.major ? 0.3 : 0.15}
              />
            ))}
          </g>
        )}

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

        {/* The scanned room: walls, raised areas and the truss found overhead.
            Under the fixtures, so a fixture is always what a press lands on. */}
        {plan && (
          <g data-testid="room-plan">
            {plan.walls && (
              <polygon
                data-testid="room-plan-walls"
                data-outlined={plan.walls.outlined ? 'true' : 'false'}
                points={planPolygonPoints(wallPoints ?? plan.walls.points, toSvgX, toSvgY)}
                fill="none"
                stroke={ROOM_WALL}
                strokeWidth={0.1}
              >
                <title>{plan.walls.tooltip}</title>
              </polygon>
            )}

            {plan.raised.map((area, index) => {
              // The raised area the 3D view puts the DJ on says so: "DJ", or an amber "DJ?" for a guess.
              const djTag = djBoothTag(area);
              return (
              <g key={`raised-${index}`} data-testid="room-plan-raised" data-kind={area.kind}>
                <title>{area.tooltip}</title>
                <rect
                  x={toSvgX(area.x)}
                  y={toSvgY(area.z)}
                  width={area.width}
                  height={area.depth}
                  // One at a heading is the same rectangle turned about its middle: clockwise on the
                  // plan, which is drawn with downstage at the bottom, is clockwise seen from above.
                  transform={area.heading
                    ? `rotate(${area.heading} ${toSvgX(area.centerX)} ${toSvgY(area.centerZ)})`
                    : undefined}
                  fill={ROOM_RAISED}
                  fillOpacity={0.28}
                  stroke={ROOM_RAISED}
                  strokeWidth={0.05}
                />
                {labels && roomLabel(labels.raised[index], ROOM_RAISED_TEXT)}
                {/* After its label, which stays the first text of the group. */}
                {djTag && (
                  <text
                    data-testid="room-plan-dj-booth"
                    data-source={area.djBooth}
                    x={toSvgX(djTag.x)}
                    y={toSvgY(djTag.z)}
                    textAnchor="middle"
                    fill={djTag.guess ? DJ_BOOTH_GUESS : ROOM_RAISED_TEXT}
                    fontSize={DJ_BOOTH_TAG_SIZE}
                    fontWeight="bold"
                  >
                    <title>{djTag.tooltip}</title>
                    {djTag.text}
                  </text>
                )}
              </g>
              );
            })}

            {plan.trussLines.map((line, index) => (
              <g key={`scan-truss-${index}`} data-testid="room-plan-truss-line">
                <title>{line.tooltip}</title>
                {/* Its width as scanned, faint, and its centre line over that. */}
                <line
                  x1={toSvgX(line.x1)}
                  y1={toSvgY(line.z1)}
                  x2={toSvgX(line.x2)}
                  y2={toSvgY(line.z2)}
                  stroke={ROOM_TRUSS}
                  strokeWidth={line.across}
                  strokeOpacity={0.35}
                />
                <line
                  x1={toSvgX(line.x1)}
                  y1={toSvgY(line.z1)}
                  x2={toSvgX(line.x2)}
                  y2={toSvgY(line.z2)}
                  stroke={ROOM_TRUSS}
                  strokeWidth={0.05}
                />
                {labels && roomLabel(labels.trussLines[index], ROOM_TRUSS)}
              </g>
            ))}

            {plan.trussRings.map((ring, index) => (
              <g key={`scan-ring-${index}`} data-testid="room-plan-truss-ring">
                <title>{ring.tooltip}</title>
                <circle
                  cx={toSvgX(ring.centerX)}
                  cy={toSvgY(ring.centerZ)}
                  r={ring.radius}
                  fill="none"
                  stroke={ROOM_TRUSS}
                  strokeWidth={ring.across}
                  strokeOpacity={0.35}
                />
                <circle
                  cx={toSvgX(ring.centerX)}
                  cy={toSvgY(ring.centerZ)}
                  r={ring.radius}
                  fill="none"
                  stroke={ROOM_TRUSS}
                  strokeWidth={0.05}
                />
                {labels && roomLabel(labels.trussRings[index], ROOM_TRUSS)}
              </g>
            ))}
          </g>
        )}

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
        {/* Its label goes by the scanned room's back wall when one is drawn. */}
        <text
          x={frame.centreX}
          y={frame.top - 0.25}
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
        {/* The arrow and the word stand below the deck, or below the scanned
            room's downstage wall: outside its floor, pointing the way out. */}
        <polygon
          points={`${frame.centreX - 0.28},${frame.bottom + 0.2} ${frame.centreX + 0.28},${
            frame.bottom + 0.2
          } ${frame.centreX},${frame.bottom + 0.55}`}
          fill={AUDIENCE_COLOR}
          opacity={0.9}
        />
        <text
          x={frame.centreX}
          y={frame.bottom + 0.9}
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
              onPointerDown={(e) => handleFixturePointerDown(e, f.id)}
              onClick={(e) => {
                e.stopPropagation();
                skipBackgroundClick.current = false;
              }}
              onDoubleClick={onFixtureSelectRow && !readonly && !roomEdit ? () => onFixtureSelectRow(f.id) : undefined}
              style={{ cursor: readonly || roomEdit ? 'default' : 'grab', opacity: roomEdit ? 0.45 : undefined }}
            >
              {/* Selection ring */}
              {isSelected && (
                <circle r={0.4} fill="none" stroke="#4fc3f7" strokeWidth={0.06} />
              )}

              {/* A guessed position: a dashed amber ring, until a person places it. */}
              {isGuessed(f.tags) && (
                <circle
                  data-testid={`plan-guess-ring-${f.id}`}
                  r={0.33}
                  fill="none"
                  stroke={GUESS_RING}
                  strokeWidth={0.04}
                  strokeDasharray="0.1 0.07"
                >
                  <title>Position is a guess: drag it to where it hangs</title>
                </circle>
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

        {/* The points picked while a stage plot is calibrated. */}
        {pickMarks?.map((mark) => (
          <g
            key={mark.label}
            data-testid={`stage-plot-mark-${mark.label}`}
            transform={`translate(${toSvgX(mark.x)}, ${toSvgY(mark.z)})`}
            pointerEvents="none"
          >
            <line x1={-0.3} y1={0} x2={0.3} y2={0} stroke="#ff4081" strokeWidth={0.05} />
            <line x1={0} y1={-0.3} x2={0} y2={0.3} stroke="#ff4081" strokeWidth={0.05} />
            <text x={0.2} y={-0.2} fill="#ff4081" fontSize={0.3} fontWeight="bold">{mark.label}</text>
          </g>
        ))}

        {/* Walls mode: a numbered handle on each corner of the walls, over
            the fixtures, so a corner under an icon can still be picked up. */}
        {wallHandles && wallPoints && (
          <g data-testid="wall-corners">
            {wallPoints.map((corner, index) => {
              const held = cornerPreview?.index === index;
              return (
                <g
                  key={`wall-corner-${index}`}
                  data-testid={`wall-corner-${index}`}
                  transform={`translate(${toSvgX(corner.x)}, ${toSvgY(corner.z)})`}
                  onMouseDown={(e) => handleCornerMouseDown(e, index)}
                  onPointerDown={(e) => handleCornerPointerDown(e, index)}
                  onClick={(e) => e.stopPropagation()}
                  style={{ cursor: 'move' }}
                >
                  <title>{`Corner ${index + 1} of the walls: drag it to move it`}</title>
                  <circle r={0.24} fill={WALL_HANDLE} fillOpacity={held ? 1 : 0.85} stroke="#1a1a2e" strokeWidth={0.05} />
                  <text y={0.08} textAnchor="middle" fill="#1a1a2e" fontSize={0.24} fontWeight={700} style={{ pointerEvents: 'none' }}>
                    {index + 1}
                  </text>
                  {held && (
                    <text
                      data-testid="wall-corner-readout"
                      y={-0.42}
                      textAnchor="middle"
                      fill={WALL_HANDLE}
                      fontSize={0.24}
                      style={{ pointerEvents: 'none' }}
                    >
                      {`${corner.x.toFixed(2)}, ${corner.z.toFixed(2)}`}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        )}

        {/* Arranging the room's items: each one's footprint again, over the
            fixtures (a truss is mostly under its own lights), to be pressed
            and dragged; the selected one's handles; and, while one is
            dragged, where the drag has it. The room layer underneath still
            shows where it stands until the server answers. */}
        {roomItems && (
          <g data-testid="room-items">
            {roomItems.map((item) => {
              const selected = item.key === selectedItemKey;
              const previewed = itemPreview?.key === item.key ? itemPreview : null;
              const shape = previewed?.shape ?? item.shape;
              const stroke = selected || previewed ? WALL_HANDLE : '#cfd8dc';
              const press = {
                onMouseDown: (e: React.MouseEvent) => handleItemMouseDown(e, item, 'move'),
                onPointerDown: (e: React.PointerEvent) => handleItemPointerDown(e, item, 'move'),
                onClick: (e: React.MouseEvent) => e.stopPropagation(),
              };
              const centre = shapeCentre(shape);
              const shapeId = `room-item-shape-${item.kind}-${item.index}`;
              return (
                <g
                  key={`room-item-${item.key}`}
                  data-testid={`room-item-${item.kind}-${item.index}`}
                  data-selected={selected ? 'true' : 'false'}
                >
                  <title>{gripHint('move', item.title)}</title>
                  {shape.type === 'box' && (
                    <rect
                      data-testid={shapeId}
                      x={toSvgX(shape.centerX - shape.width / 2)}
                      y={toSvgY(shape.centerZ - shape.depth / 2)}
                      width={shape.width}
                      height={shape.depth}
                      // At its heading, or at the turn a drag of its rotate handle has it.
                      transform={shape.heading
                        ? `rotate(${shape.heading} ${toSvgX(shape.centerX)} ${toSvgY(shape.centerZ)})`
                        : undefined}
                      fill={WALL_HANDLE}
                      fillOpacity={selected ? 0.16 : 0.04}
                      stroke={stroke}
                      strokeWidth={selected ? 0.07 : 0.04}
                      strokeDasharray={selected ? undefined : '0.18 0.12'}
                      style={{ cursor: 'move' }}
                      {...press}
                    />
                  )}
                  {shape.type === 'line' && (
                    <line
                      data-testid={shapeId}
                      x1={toSvgX(shape.x1)}
                      y1={toSvgY(shape.z1)}
                      x2={toSvgX(shape.x2)}
                      y2={toSvgY(shape.z2)}
                      stroke={stroke}
                      // Wide enough to press, whatever the truss measured across.
                      strokeWidth={0.45}
                      strokeOpacity={selected ? 0.55 : 0.25}
                      strokeLinecap="round"
                      style={{ cursor: 'move' }}
                      {...press}
                    />
                  )}
                  {shape.type === 'ring' && (
                    <circle
                      data-testid={shapeId}
                      cx={toSvgX(shape.centerX)}
                      cy={toSvgY(shape.centerZ)}
                      r={shape.radius}
                      fill="none"
                      stroke={stroke}
                      strokeWidth={0.45}
                      strokeOpacity={selected ? 0.55 : 0.25}
                      // The truss alone: what is inside a ring can still be pressed.
                      style={{ cursor: 'move', pointerEvents: 'stroke' }}
                      {...press}
                    />
                  )}
                  {selected && itemHandles(shape).map((handle) => (
                    <g
                      key={handle.grip}
                      data-testid={`room-item-handle-${handle.grip}`}
                      transform={`translate(${toSvgX(handle.x)}, ${toSvgY(handle.z)})`}
                      onMouseDown={(e) => handleItemMouseDown(e, item, handle.grip)}
                      onPointerDown={(e) => handleItemPointerDown(e, item, handle.grip)}
                      onClick={(e) => e.stopPropagation()}
                      // A turned raised area's edges pull along its own sides: the arrow is turned with it.
                      style={{ cursor: gripCursor(handle.grip, shape.type === 'box' ? shape.heading : 0) }}
                    >
                      <title>{gripHint(handle.grip, item.title)}</title>
                      {handle.grip === 'rotate' ? (
                        <circle r={0.2} fill="#1a1a2e" stroke={WALL_HANDLE} strokeWidth={0.07} />
                      ) : isBoxGrip(handle.grip) ? (
                        // Eight of them round one raised area: smaller, so a small riser can still be pressed between them.
                        <rect x={-0.12} y={-0.12} width={0.24} height={0.24} fill={WALL_HANDLE} stroke="#1a1a2e" strokeWidth={0.04} />
                      ) : (
                        <rect x={-0.18} y={-0.18} width={0.36} height={0.36} fill={WALL_HANDLE} stroke="#1a1a2e" strokeWidth={0.05} />
                      )}
                    </g>
                  ))}
                  {previewed && previewed.readout && (
                    <text
                      data-testid="room-item-readout"
                      x={toSvgX(centre.x)}
                      y={toSvgY(centre.z) - 0.45}
                      textAnchor="middle"
                      fill={WALL_HANDLE}
                      fontSize={0.24}
                      style={{ pointerEvents: 'none' }}
                    >
                      {previewed.readout}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        )}

        {/* The selection box being dragged over empty floor: every fixture
            whose centre is inside it is selected when it is let go. */}
        {selectionBox && (() => {
          const box = boxBetween(selectionBox.from, selectionBox.to);
          return (
            <rect
              data-testid="selection-box"
              x={toSvgX(box.minX)}
              y={toSvgY(box.minZ)}
              width={box.maxX - box.minX}
              height={box.maxZ - box.minZ}
              fill={SELECTION_COLOR}
              fillOpacity={0.12}
              stroke={SELECTION_COLOR}
              strokeWidth={0.04}
              strokeDasharray="0.15 0.1"
              style={{ pointerEvents: 'none' }}
            />
          );
        })()}

        {/* Where a finger was held on empty floor: the box it goes on to
            draw adds to the selection. Gone once the box is being drawn. */}
        {armedAt && !selectionBox && (
          <circle
            data-testid="long-press-mark"
            cx={toSvgX(armedAt.x)}
            cy={toSvgY(armedAt.z)}
            r={0.3}
            fill={SELECTION_COLOR}
            fillOpacity={0.12}
            stroke={SELECTION_COLOR}
            strokeWidth={0.04}
            strokeDasharray="0.15 0.1"
            style={{ pointerEvents: 'none' }}
          />
        )}

        {/* Landing spot for a fixture dragged in from the palette */}
        {dropPreview && (
          <g transform={`translate(${toSvgX(dropPreview.x)}, ${toSvgY(dropPreview.z)})`}>
            <circle r={0.32} fill="none" stroke="#4fc3f7" strokeWidth={0.06} strokeDasharray="0.15 0.1" />
            <text y={0.62} textAnchor="middle" fill="#4fc3f7" fontSize={0.22}>
              {`${dropPreview.x.toFixed(1)}, ${dropPreview.z.toFixed(1)}`}
            </text>
            {dropPreview.on && (
              <text data-testid="snap-readout" y={-0.5} textAnchor="middle" fill={ROOM_TRUSS} fontSize={0.24}>
                {dropPreview.on}
              </text>
            )}
          </g>
        )}

        {/* What a drag has snapped onto: the scanned truss and the height it
            hangs at, over the fixture under the pointer. */}
        {snapNote && (
          <text
            data-testid="snap-readout"
            x={toSvgX(snapNote.x)}
            y={toSvgY(snapNote.z) - 0.55}
            textAnchor="middle"
            fill={ROOM_TRUSS}
            fontSize={0.24}
            style={{ pointerEvents: 'none' }}
          >
            {snapNote.text}
          </text>
        )}

        {/* Scale indicator */}
        <line
          x1={frame.left + 0.2}
          y1={frame.top - 0.45}
          x2={frame.left + 1.2}
          y2={frame.top - 0.45}
          stroke="#666"
          strokeWidth={0.03}
        />
        <text
          x={frame.left + 0.7}
          y={frame.top - 0.6}
          textAnchor="middle"
          fill="#666"
          fontSize={0.2}
        >
          1m
        </text>
      </svg>

      {/* The focus cue: the keys are going to a field or a drop-down. It
          takes no press itself, so a click on it is a click on the plan. */}
      {keysAway && (
        <div
          data-testid="plan-keys-hint"
          role="note"
          style={{
            position: 'absolute',
            left: 8,
            bottom: 8,
            padding: '2px 8px',
            borderRadius: 4,
            background: 'rgba(26, 26, 46, 0.75)',
            color: '#b0bec5',
            fontSize: 12,
            pointerEvents: 'none',
          }}
        >
          {KEYS_HINT_TEXT}
        </div>
      )}

      {/* The keys as buttons, for a finger: after the plan, and not in it. */}
      {showPad && (
        <PlanNudgePad
          tenfold={tenfold}
          onTenfoldChange={setTenfold}
          onNudge={handlePadNudge}
          onSelectRow={onFixtureSelectRow ? handlePadSelectRow : undefined}
          onLayRow={onLayRow}
          layRowDisabled={selectedCount < 2}
          layChoice={layChoice}
          onLayChoiceChange={onLayChoiceChange}
          onMirror={onMirror ? handlePadMirror : undefined}
          onSpaceEvenly={onSpaceEvenly ? handlePadSpaceEvenly : undefined}
          spaceEvenlyDisabled={selectedCount < 3}
        />
      )}
    </Box>
  );
}
