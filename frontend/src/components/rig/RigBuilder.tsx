import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Box, Button, Checkbox, FormControlLabel, Typography, Paper, Snackbar, Alert } from '@mui/material';
import axios from 'axios';
import { rigsApi, fixturesApi, roomScanApi } from '../../services/api';
import { useRigEditorStore, computeTrussLines } from '../../stores/rigEditorStore';
import type { FixturePositionSnapshot } from '../../stores/rigEditorStore';
import RigEditorToolbar from './RigEditorToolbar';
import type { PositionSaveState } from './RigEditorToolbar';
import FixturePalette from './FixturePalette';
import StageView2D from './StageView2D';
import { paletteClickSpot, planTrussTargets, roomPlan } from './roomPlan2d';
import {
  heightIdsOf, heightsBefore, nearestTruss, rowOf, snapshotPositions, withMoves, withSnapshot,
} from './rowMove2d';
import type { PlanMove } from './rowMove2d';
import {
  DEFAULT_LAY_CHOICE, evenMoves, evenNoticeText, layRowSpaced, mirrorMoves, mirrorNoticeText, spacedLayNoticeText,
} from './rowSpace2d';
import type { LayChoice } from './rowSpace2d';
import PatchTable from './PatchTable';
import FixtureProperties from './FixtureProperties';
import IdentifyWalkthrough from './IdentifyWalkthrough';
import RoomScanDialog from './RoomScanDialog';
import { pendingCarryOverOf, undoCount } from '../../utils/roomScan';
import RoomShellEditDialog from './RoomShellEditDialog';
import {
  carriedCount, carryBoxName, carryLabel, editResultText, shellEditErrorText, shellItemKey, shellItemTitle, shellItems,
  shellUndoCount, undoButtonText, withCarry,
} from '../../utils/roomShellEdit';
import type { ShellItemChanges, ShellItemKind } from '../../utils/roomShellEdit';
import { nudgeItem, planItems } from './roomItemDrag2d';
import RoomItemHeightStrip from './RoomItemHeightStrip';
import { heightGauge } from './roomItemHeight';
import { outsideLines, outsideOf } from '../../utils/roomWallsEdit';
import type { Rig, RigFixture, Fixture, PatchConflict, RoomShell, RoomShellEdits } from '../../types';

/** Long enough that a drag is one request, short enough to feel immediate. */
const POSITION_SAVE_DEBOUNCE_MS = 400;

const roundToMm = (value: number) => Math.round(value * 1000) / 1000;

/** Two icons closer than this on the plan read as one light. */
const ICON_CLEARANCE_M = 0.6;

export default function RigBuilder() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [rig, setRig] = useState<Rig | null>(null);
  const [conflicts, setConflicts] = useState<PatchConflict[]>([]);
  const [loading, setLoading] = useState(true);
  const [patchUniverse, setPatchUniverse] = useState(0);
  const [saveState, setSaveState] = useState<PositionSaveState>('idle');
  const [notice, setNotice] = useState<{ severity: 'error' | 'success'; text: string } | null>(null);
  const [identifyOpen, setIdentifyOpen] = useState(false);
  const [roomScanOpen, setRoomScanOpen] = useState(false);
  const [roomEditOpen, setRoomEditOpen] = useState(false);
  // Edit Room's walls mode: the dialog is put away and the corners of the
  // room's walls are dragged on the plan, where fixtures then take no press.
  const [wallsMode, setWallsMode] = useState(false);
  // What the last drag of a corner did, or why it was refused, with what the
  // walls now leave outside them, one line each.
  const [wallsNote, setWallsNote] = useState<
    { severity: 'success' | 'warning' | 'error'; text: string; outside: string[] } | null
  >(null);
  // A change to the walls is out: one at a time, each built on the last one stored.
  const [wallsBusy, setWallsBusy] = useState(false);
  // Edit Room's "Arrange room items on the plan": the dialog is put away and
  // the room's raised areas, truss lines and rings are dragged on the plan,
  // where fixtures then take no press. Never on with walls mode.
  const [itemsMode, setItemsMode] = useState(false);
  // What the last drag or nudge of an item did, or why it was refused.
  const [itemsNote, setItemsNote] = useState<{ severity: 'success' | 'error'; text: string } | null>(null);
  // The item that is selected on the plan in that mode, by its key (`truss_lines:0`).
  const [selectedItemKey, setSelectedItemKey] = useState<string | null>(null);
  // The items whose fixtures stay behind, by key: the dialog's unticked
  // boxes as they were when it handed over, and the strip's box since. Kept
  // in a ref as well, for a request that is waiting its turn to read.
  const [itemsLeftAlone, setItemsLeftAlone] = useState<Record<string, boolean>>({});
  const itemsLeftAloneRef = useRef<Record<string, boolean>>({});
  // The changes to the room made from the plan, one after another: each is
  // sent only once the one before it has been answered and, where that one
  // moved fixtures, the rig has been read again.
  const roomQueueRef = useRef<Promise<unknown>>(Promise.resolve());
  // How far apart Lay on truss lays a row. The editor's own, not the
  // store's: it starts at Fill truss each time the editor is opened.
  const [layChoice, setLayChoice] = useState<LayChoice>(DEFAULT_LAY_CHOICE);

  const {
    viewMode, snapMode, gridSize, selectedFixtureIds,
    setViewMode, setSnapMode, selectFixture, selectFixtures, deselectAll,
    undoStack, redoStack, pushUndo, noteUndoHeights, undo, redo, clearHistory,
  } = useRigEditorStore();

  // Drags fire faster than React commits, so the pending-write bookkeeping is
  // kept in refs and the rig ref is advanced synchronously alongside setRig.
  const rigRef = useRef<Rig | null>(null);
  const dirtyIdsRef = useRef<Set<number>>(new Set());
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const paletteDragRef = useRef<Fixture | null>(null);
  const pendingUndoRef = useRef(false);

  const applyRig = useCallback((next: Rig) => {
    rigRef.current = next;
    setRig(next);
  }, []);

  const fetchRig = useCallback(async () => {
    if (!id) return;
    try {
      const data = await rigsApi.get(Number(id));
      rigRef.current = data;
      setRig(data);
      const conflictData = await rigsApi.getConflicts(Number(id));
      setConflicts(conflictData.conflicts || []);
    } catch {
      setNotice({ severity: 'error', text: 'Could not load this rig.' });
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { fetchRig(); }, [fetchRig]);

  useEffect(() => {
    clearHistory();
    dirtyIdsRef.current = new Set();
    setSaveState('idle');
  }, [id, clearHistory]);

  /** Writes the pending position edits. Returns false if any of them failed. */
  const flushPositions = useCallback(async (): Promise<boolean> => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    const current = rigRef.current;
    const pending = dirtyIdsRef.current;
    if (!current || pending.size === 0) return true;

    dirtyIdsRef.current = new Set();
    const payload = current.fixtures
      .filter((f) => pending.has(f.id))
      .map((f) => ({
        id: f.id,
        position_x: roundToMm(f.position_x),
        position_y: roundToMm(f.position_y),
        position_z: roundToMm(f.position_z),
      }));
    if (payload.length === 0) return true;

    setSaveState('saving');
    try {
      await rigsApi.batchUpdateFixtures(current.id, payload);
      setSaveState((s) => (dirtyIdsRef.current.size > 0 ? s : 'saved'));
      return true;
    } catch {
      payload.forEach((p) => dirtyIdsRef.current.add(p.id));
      setSaveState('error');
      return false;
    }
  }, []);

  const schedulePositionSave = useCallback(() => {
    setSaveState('pending');
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      saveTimerRef.current = null;
      void flushPositions();
    }, POSITION_SAVE_DEBOUNCE_MS);
  }, [flushPositions]);

  // A drag left mid-flight must not be dropped on the floor.
  useEffect(() => () => { void flushPositions(); }, [flushPositions]);

  const handleSave = async () => {
    const current = rigRef.current;
    if (!current) return;
    // A green "Rig saved." over a failed position write tells the owner their
    // work is safe when it is still only on screen, so the position result has
    // to reach the message.
    const positionsSaved = await flushPositions();
    try {
      await rigsApi.update(current.id, {
        name: current.name,
        stage_width: current.stage_width,
        stage_depth: current.stage_depth,
        stage_height: current.stage_height,
      });
      setNotice(
        positionsSaved
          ? { severity: 'success', text: 'Rig saved.' }
          : {
              severity: 'error',
              text:
                'Name and stage size saved, but the fixture positions did not - ' +
                'check the connection and press Save again.',
            }
      );
    } catch {
      setNotice({ severity: 'error', text: 'Could not save the rig.' });
    }
  };

  const handleAutoPatch = async () => {
    if (!rigRef.current) return;
    await flushPositions();
    await rigsApi.autoPatch(rigRef.current.id);
    await fetchRig();
  };

  const handleTestAll = async () => {
    if (!rigRef.current) return;
    await rigsApi.testAll(rigRef.current.id);
  };

  const handleIdentify = async () => {
    // The walkthrough writes positions of its own, so anything still pending
    // here has to land first or the two would fight over the same fixtures.
    await flushPositions();
    setIdentifyOpen(true);
  };

  const handleRoomScan = async () => {
    // Applying a scan moves unconfirmed fixtures on the server. A drag still
    // waiting to be written would land after it and put one of them back.
    await flushPositions();
    setRoomScanOpen(true);
  };

  const handleEditRoom = async () => {
    // A truss edited in the room dialog takes its fixtures along on the
    // server, and the dialog takes the keys and the plan away: a drag still
    // waiting to be written is written first, or it would land on top.
    await flushPositions();
    setRoomEditOpen(true);
  };

  /**
   * The stored room after one of its items was changed, added or deleted, or
   * after such an edit was undone, as the server answered it. Only the room
   * and the count of its edits that can be undone are replaced here. Where
   * the edit also moved fixtures the dialog says so next
   * (`handleRoomFixturesMoved`); where it did not, the positions on screen
   * and the undo steps that hold them are still true, and the rig is not
   * read again. The editor's own Undo does not take a room edit back; the
   * room has an Undo of its own in the dialog, kept on the server.
   */
  const handleRoomEdited = (shell: RoomShell, edits?: RoomShellEdits) => {
    const current = rigRef.current;
    if (current) applyRig({ ...current, room_shell: shell, room_shell_edits: edits ?? current.room_shell_edits });
  };

  /**
   * A room edit moved fixtures on the server: a truss or ring took the ones
   * hung on it along, or an undo put them back. The positions on screen are
   * stale, and so is any step of the editor's own undo that would write the
   * old ones back, as after a scan is applied: the steps are dropped and the
   * rig is read again, which is what the 2D plan and the 3D view draw from.
   * Nothing is waiting to be written: Edit Room writes any pending drag
   * before it opens, and walls mode carries no fixture.
   */
  const handleRoomFixturesMoved = () => {
    clearHistory();
    void fetchRig();
  };

  /**
   * Edit Room's "Drag corners on the plan": the dialog is in front of the
   * plan, so it is closed, and the plan puts a handle on each corner. The
   * selection is let go: nothing is selected or carried in walls mode.
   */
  const handleDragWalls = () => {
    setRoomEditOpen(false);
    deselectAll();
    setWallsNote(null);
    setItemsMode(false);
    setWallsMode(true);
  };

  const leaveItemsAlone = (next: Record<string, boolean>) => {
    itemsLeftAloneRef.current = next;
    setItemsLeftAlone(next);
  };

  /**
   * Edit Room's "Arrange room items on the plan": the dialog is in front of
   * the plan, so it is closed, and the plan lets the room's raised areas,
   * truss lines and rings be picked up. `leftAlone` is the dialog's unticked
   * "Move the fixtures ..." boxes, so a drag carries what a save there would.
   */
  const handleArrangeItems = (leftAlone: Record<string, boolean>) => {
    setRoomEditOpen(false);
    deselectAll();
    setItemsNote(null);
    setSelectedItemKey(null);
    leaveItemsAlone({ ...leftAlone });
    setWallsMode(false);
    setItemsMode(true);
  };

  /** Puts a change to the room behind the ones already out, so each builds on the last one stored. */
  const queueRoomChange = (task: () => Promise<void>): Promise<void> => {
    const run = roomQueueRef.current.then(task, task);
    roomQueueRef.current = run.catch(() => undefined);
    return run;
  };

  const itemsError = (err: unknown) => setItemsNote({
    severity: 'error',
    text: axios.isAxiosError(err)
      ? shellEditErrorText(err.response?.status, err.response?.data?.detail)
      : shellEditErrorText(undefined, undefined),
  });

  /**
   * One change to one item of the room, made on the plan: a drag that was
   * let go, or an arrow key. One PATCH and one step of the room's own undo.
   * `changesFor` is asked what to send once this change's turn has come,
   * with the room as the change before it left it, so two quick nudges are
   * two steps and not the same step twice. The fixtures hung or standing on
   * the item go with it unless its box is unticked; when any did, the rig is
   * read again before the next change, and the editor's own undo steps,
   * which hold the old positions, are dropped. A change the server refuses
   * (422, or 409 during a locate walkthrough) stores nothing: the plan goes
   * back to the room as it is, and the strip shows the server's words.
   */
  const changeRoomItem = (
    kind: ShellItemKind, index: number,
    changesFor: (shell: RoomShell | null | undefined) => ShellItemChanges | null,
  ) => queueRoomChange(async () => {
    const current = rigRef.current;
    if (!current) return;
    const item = shellItems(current.room_shell).find((entry) => entry.kind === kind && entry.index === index);
    const changes = changesFor(current.room_shell);
    if (!item || !changes) return;
    const carry = !itemsLeftAloneRef.current[shellItemKey(item)];
    try {
      const result = await roomScanApi.editShellItem(current.id, kind, index, withCarry(item, changes, carry));
      handleRoomEdited(result.room_shell, result.undo);
      const moved = carriedCount(result.fixtures_moved);
      if (moved > 0) {
        clearHistory();
        await fetchRig();
      }
      setItemsNote({
        severity: 'success',
        // Held where it already was (against the 2 m round the room): nothing was stored.
        text: result.changed === false
          ? `${shellItemTitle(item)} is where it was: nothing was changed.`
          : editResultText(item, changes, result.room_shell, {
            moved, asked: carry, areas: carriedCount(result.items_moved),
          }),
      });
    } catch (err) {
      itemsError(err);
    }
  });

  /** An item, or a handle of one, dragged and let go on the plan. */
  const handleItemChange = (kind: ShellItemKind, index: number, changes: ShellItemChanges) =>
    changeRoomItem(kind, index, () => changes);

  /** An arrow key: the item's middle, wherever the change before this one left it, shifted by a step. */
  const handleItemNudge = (kind: ShellItemKind, index: number, dx: number, dz: number) => {
    void changeRoomItem(kind, index, (shell) => {
      const item = planItems(shell).find((entry) => entry.kind === kind && entry.index === index);
      return item ? nudgeItem(item, dx, dz) : null;
    });
  };

  /**
   * The room's own Undo, from the strip over the plan while items are
   * arranged: the latest change to the room, whatever it was. It may bring
   * back a deleted item, which moves the ones after it down a place: the
   * selection and the unticked boxes go by place, so both are let go.
   */
  const handleItemsUndo = () => queueRoomChange(async () => {
    const current = rigRef.current;
    if (!current) return;
    try {
      const result = await roomScanApi.undoShellEdit(current.id);
      handleRoomEdited(result.room_shell, result.undo);
      setSelectedItemKey(null);
      leaveItemsAlone({});
      if (carriedCount(result.fixtures_restored) > 0) {
        clearHistory();
        await fetchRig();
      }
      setItemsNote({ severity: 'success', text: result.message });
    } catch (err) {
      itemsError(err);
    }
  });

  const wallsError = (err: unknown) => setWallsNote({
    severity: 'error',
    text: axios.isAxiosError(err)
      ? shellEditErrorText(err.response?.status, err.response?.data?.detail)
      : shellEditErrorText(undefined, undefined),
    outside: [],
  });

  /**
   * A corner of the walls dropped somewhere new on the plan: one request and
   * one step of the room's own undo for the whole drag. The server decides
   * whether the walls still make a room; a move it refuses is not kept, and
   * its words are shown. No fixture is moved: what the walls now leave
   * outside is listed in the strip over the plan.
   */
  const handleWallCornerMove = async (index: number, x: number, z: number) => {
    const current = rigRef.current;
    if (!current || wallsBusy) return;
    setWallsBusy(true);
    try {
      const result = await roomScanApi.moveOutlineCorner(current.id, index, { x, z });
      handleRoomEdited(result.room_shell, result.undo);
      const outside = outsideOf(result.outside);
      setWallsNote({
        severity: outside.count > 0 ? 'warning' : 'success', text: result.message, outside: outsideLines(outside),
      });
    } catch (err) {
      wallsError(err);
    } finally {
      setWallsBusy(false);
    }
  };

  /** The room's own Undo, from the strip over the plan: the latest change to the room, walls or not. */
  const handleWallsUndo = async () => {
    const current = rigRef.current;
    if (!current || wallsBusy) return;
    setWallsBusy(true);
    try {
      const result = await roomScanApi.undoShellEdit(current.id);
      handleRoomEdited(result.room_shell, result.undo);
      // The latest change may be a truss that took its fixtures along: they went back with it.
      if (carriedCount(result.fixtures_restored) > 0) handleRoomFixturesMoved();
      const outside = outsideOf(result.outside);
      setWallsNote({
        severity: outside.count > 0 ? 'warning' : 'success', text: result.message, outside: outsideLines(outside),
      });
    } catch (err) {
      wallsError(err);
    } finally {
      setWallsBusy(false);
    }
  };

  const handleFixtureClick = (fixtureId: number, multi: boolean) => {
    if (fixtureId === -1) {
      deselectAll();
    } else {
      selectFixture(fixtureId, multi);
    }
  };

  // Armed on mouse-down but only spent once something actually moves, so a plain
  // selection click never leaves an undo step that does nothing.
  const handleFixtureDragStart = () => { pendingUndoRef.current = true; };

  /**
   * One fixture, or a selected row carried together. Either way it is one
   * undo step for the whole drag and one batch-update for everything that
   * moved, and no tag is touched: a guess that is moved is still a guess.
   */
  const handleFixturesDrag = (moves: PlanMove[]) => {
    const current = rigRef.current;
    if (!current) return;
    const next = withMoves(current.fixtures, moves);
    if (next.changed.length === 0) return;

    if (pendingUndoRef.current) {
      pushUndo(snapshotPositions(current.fixtures));
      pendingUndoRef.current = false;
    }
    // A snap onto scanned truss is the one thing here that changes a height:
    // the undo step for this drag then has to know what it was.
    noteUndoHeights(heightsBefore(current.fixtures, moves));

    applyRig({ ...current, fixtures: next.fixtures });
    next.changed.forEach((fixtureId) => dirtyIdsRef.current.add(fixtureId));
    schedulePositionSave();
  };

  // `y` comes with a drag that snapped onto scanned truss: its hang height.
  const handleFixtureDrag = (fixtureId: number, x: number, z: number, y?: number) => {
    handleFixturesDrag([y === undefined ? { id: fixtureId, x, z } : { id: fixtureId, x, z, y }]);
  };

  /** Selects the whole row a fixture is in: its group, its scanned truss, or its height and depth. */
  const handleSelectRow = (fixtureId: number) => {
    const current = rigRef.current;
    if (!current) return;
    const row = rowOf(current.fixtures, fixtureId, current.room_shell);
    if (row.length > 0) selectFixtures(row);
  };

  /**
   * Makes a set of moves that a button asked for, all at once: one undo
   * step, one batch-update sent straight away, the heights the moves change
   * kept in the step, and no tag touched. Returns how many fixtures moved;
   * with none, nothing is saved and no step is left.
   */
  const commitMoves = (moves: PlanMove[]): number => {
    const current = rigRef.current;
    if (!current) return 0;
    const next = withMoves(current.fixtures, moves);
    if (next.changed.length === 0) return 0;

    pushUndo(snapshotPositions(current.fixtures));
    noteUndoHeights(heightsBefore(current.fixtures, moves));
    applyRig({ ...current, fixtures: next.fixtures });
    next.changed.forEach((fixtureId) => dirtyIdsRef.current.add(fixtureId));
    void flushPositions();
    return next.changed.length;
  };

  /**
   * Lays the selected fixtures evenly along the scanned truss nearest them
   * (`layRowOnTruss`, docs/ROOM_SCAN.md). Saved as a row move is: one undo
   * step, one batch-update, heights kept in the step where they change, and
   * no tag touched.
   */
  const handleLayRow = () => {
    const current = rigRef.current;
    if (!current) return;
    // Filled, at the row's own spacing or at a typed one: the choice next
    // to the button. Filled is `layRowOnTruss` itself.
    const lay = layRowSpaced(
      current.fixtures, selectedFixtureIds, current.room_shell,
      // The walls the plan draws and holds a drag to.
      roomPlan(current.room_shell)?.walls ?? null, current.stage_width, current.stage_depth,
      layChoice,
    );
    if (!lay.ok) {
      setNotice({ severity: 'error', text: spacedLayNoticeText(lay) });
      return;
    }
    setNotice({ severity: 'success', text: spacedLayNoticeText(lay, commitMoves(lay.moves)) });
  };

  /**
   * Mirrors the selected fixtures left to right about the centre line: the
   * stage's, or the scanned room's when one is drawn (`mirrorMoves`). One
   * undo step and one batch-update; heights and tags are not touched.
   * Nothing on a fixture says which way its pan runs but a tag and an older
   * flag that names no axis, neither of which a batch-update writes or an
   * undo step keeps, so those are left as they are.
   */
  const handleMirror = () => {
    const current = rigRef.current;
    if (!current) return;
    const walls = roomPlan(current.room_shell)?.walls ?? null;
    const mirrored = mirrorMoves(
      current.fixtures, selectedFixtureIds, walls, current.stage_width, current.stage_depth,
    );
    const changed = commitMoves(mirrored.moves);
    setNotice({
      severity: mirrored.moves.length > 0 ? 'success' : 'error',
      text: mirrorNoticeText(mirrored, changed, !!walls),
    });
  };

  /**
   * Spaces the selected fixtures evenly between the first and the last of
   * them by DMX address, which stay where they are (`evenMoves`). One undo
   * step and one batch-update; heights and tags are not touched.
   */
  const handleSpaceEvenly = () => {
    const current = rigRef.current;
    if (!current) return;
    const even = evenMoves(
      current.fixtures, selectedFixtureIds,
      roomPlan(current.room_shell)?.walls ?? null, current.stage_width, current.stage_depth,
    );
    if (!even.ok) {
      setNotice({ severity: 'error', text: evenNoticeText(even) });
      return;
    }
    setNotice({ severity: 'success', text: evenNoticeText(even, commitMoves(even.moves)) });
  };

  const handleFixtureDragEnd = () => {
    pendingUndoRef.current = false;
    void flushPositions();
  };

  const applySnapshot = useCallback((snapshot: FixturePositionSnapshot[]) => {
    const current = rigRef.current;
    if (!current) return;
    // Heights too: a drag that snapped onto scanned truss changed them.
    const next = withSnapshot(current.fixtures, snapshot);
    if (next.changed.length === 0) return;
    next.changed.forEach((fixtureId) => dirtyIdsRef.current.add(fixtureId));
    applyRig({ ...current, fixtures: next.fixtures });
    void flushPositions();
  }, [applyRig, flushPositions]);

  const handleUndo = () => {
    const current = rigRef.current;
    if (!current) return;
    // What redo goes back to keeps heights for the same fixtures the step
    // being undone does: those whose height that drag changed, and no other.
    const stack = useRigEditorStore.getState().undoStack;
    const previous = undo(snapshotPositions(current.fixtures, heightIdsOf(stack[stack.length - 1])));
    if (previous) applySnapshot(previous);
  };

  const handleRedo = () => {
    const current = rigRef.current;
    if (!current) return;
    const stack = useRigEditorStore.getState().redoStack;
    const next = redo(snapshotPositions(current.fixtures, heightIdsOf(stack[stack.length - 1])));
    if (next) applySnapshot(next);
  };

  /** Hang a new fixture at the height of its nearest neighbour, or on the deck. */
  const hangHeightNear = useCallback((z: number): number => {
    const current = rigRef.current;
    if (!current || current.fixtures.length === 0) return 0;
    const nearest = current.fixtures.reduce((best, f) =>
      Math.abs(f.position_z - z) < Math.abs(best.position_z - z) ? f : best
    );
    return nearest.position_y;
  }, []);

  /**
   * Where a fixture clicked in the palette goes: a position the app chooses
   * (rather than one the owner pointed at), nudged off any fixture already
   * there so clicking the palette twice does not stack two icons. Centre stage,
   * inside the deck; in a rig with a scanned room, inside the room's walls
   * (`paletteClickSpot`, docs/ROOM_SCAN.md).
   */
  const paletteSpot = (): { x: number; z: number } => {
    const current = rigRef.current;
    if (!current) return { x: 0, z: 0 };
    return paletteClickSpot(
      rig?.stage_width ?? 0,
      rig?.stage_depth ?? 0,
      // The walls the plan draws, so a click lands where a drop there would be let.
      roomPlan(current.room_shell)?.walls ?? null,
      current.fixtures.map((f) => ({ x: f.position_x, z: f.position_z })),
      ICON_CLEARANCE_M,
    );
  };

  // `y` comes with a drop onto scanned truss: the height the truss hangs at.
  const addFixtureAt = useCallback(async (fixtureId: number, x: number, z: number, y?: number) => {
    const current = rigRef.current;
    if (!current) return;
    await flushPositions();

    try {
      const cached = paletteDragRef.current;
      const fixture = cached && cached.id === fixtureId ? cached : await fixturesApi.get(fixtureId);
      const mode = fixture.modes?.[0];
      const channelCount = mode?.channel_count ?? 16;

      const next = await rigsApi.getNextAddress(current.id, 0, channelCount);
      if (next.address == null) {
        setNotice({
          severity: 'error',
          text: `No free space for ${fixture.model} (${channelCount} channels) in universe ${next.universe}. Free some addresses or use another universe.`,
        });
        return;
      }

      const sameModel = current.fixtures.filter((f) => f.fixture_id === fixture.id).length;
      await rigsApi.addFixture(current.id, {
        fixture_id: fixture.id,
        name: `${fixture.model} ${sameModel + 1}`,
        universe: next.universe,
        dmx_address: next.address,
        mode_id: mode?.id,
        position_x: roundToMm(x),
        position_y: y === undefined ? hangHeightNear(z) : roundToMm(y),
        position_z: roundToMm(z),
      });
      await fetchRig();
      setNotice({
        severity: 'success',
        text: `Added ${fixture.model} at address ${next.address} (universe ${next.universe}).`,
      });
    } catch {
      setNotice({ severity: 'error', text: 'Could not add that fixture to the rig.' });
    }
  }, [flushPositions, fetchRig, hangHeightNear]);

  const handleFixturePropertyChange = async (updates: Partial<RigFixture>) => {
    const current = rigRef.current;
    if (!current || selectedFixtureIds.size !== 1) return;
    const fixtureId = Array.from(selectedFixtureIds)[0];

    applyRig({
      ...current,
      fixtures: current.fixtures.map((f) =>
        f.id === fixtureId ? { ...f, ...updates } : f
      ),
    });

    try {
      await rigsApi.updateFixture(current.id, fixtureId, updates);
    } catch {
      await fetchRig(); // Revert on error
    }
  };

  const trussLineCount = useMemo(
    () => (rig ? computeTrussLines(rig.fixtures.map((f) => f.position_z)).length : 0),
    [rig]
  );

  // The 3D view is its own route. Without this the button only restyled itself
  // and the 2D plan stayed on screen, which reads as the app having frozen.
  const handleViewModeChange = useCallback(async (mode: '2d' | '3d') => {
    if (mode !== '3d') {
      setViewMode(mode);
      return;
    }
    const current = rigRef.current;
    if (!current) return;
    await flushPositions();
    navigate(`/rigs/${current.id}/visualizer`);
  }, [flushPositions, navigate, setViewMode]);

  if (loading) return <Typography>Loading...</Typography>;
  if (!rig) return <Typography>Rig not found</Typography>;

  const selectedFixtures = rig.fixtures.filter((f) => selectedFixtureIds.has(f.id));
  // The properties panel edits one fixture; with several selected there is
  // no one fixture for it to edit.
  const selectedFixture = selectedFixtures.length === 1 ? selectedFixtures[0] : undefined;
  // "Lay on truss" is offered only where a scan found truss, and names the
  // truss it would use: the one nearest the middle of what is selected.
  const scannedTruss = planTrussTargets(rig.room_shell);
  // Walls mode is only ever on over a scanned room: a room taken off, or
  // another dialog in front of the plan, is not something to drag walls under.
  const wallsOn = wallsMode && rig.room_shell?.source === 'scan' && !identifyOpen && !roomScanOpen && !roomEditOpen;
  // Arranging the room's items, on the same terms.
  const itemsOn = itemsMode && !wallsOn && rig.room_shell?.source === 'scan'
    && !identifyOpen && !roomScanOpen && !roomEditOpen;
  const selectedItem = itemsOn
    ? shellItems(rig.room_shell).find((item) => shellItemKey(item) === selectedItemKey) ?? null
    : null;
  const layTarget = nearestTruss(
    scannedTruss, selectedFixtures.map((f) => ({ x: f.position_x, z: f.position_z })),
  );

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 88px)', mx: -3, mt: -3 }}>
      <RigEditorToolbar
        rigName={rig.name}
        viewMode={viewMode}
        snapMode={snapMode}
        trussLineCount={trussLineCount}
        saveState={saveState}
        onNameChange={(name) => applyRig({ ...rig, name })}
        onViewModeChange={(mode) => { void handleViewModeChange(mode); }}
        onSnapModeChange={setSnapMode}
        onSave={handleSave}
        onAutoPatch={handleAutoPatch}
        onTestAll={handleTestAll}
        onIdentify={() => { void handleIdentify(); }}
        onRoomScan={() => { void handleRoomScan(); }}
        hasRoom={rig.room_shell?.source === 'scan'}
        onEditRoom={() => { void handleEditRoom(); }}
        selectedCount={selectedFixtures.length}
        onSelectRow={() => { if (selectedFixtures.length > 0) handleSelectRow(selectedFixtures[0].id); }}
        onLayRow={scannedTruss.length > 0 ? handleLayRow : undefined}
        layTargetName={layTarget?.name ?? null}
        layChoice={layChoice}
        onLayChoiceChange={setLayChoice}
        onMirror={handleMirror}
        onSpaceEvenly={handleSpaceEvenly}
        onUndo={handleUndo}
        onRedo={handleRedo}
        canUndo={undoStack.length > 0}
        canRedo={redoStack.length > 0}
      />

      <Box sx={{ display: 'flex', flexGrow: 1, overflow: 'hidden' }}>
        {/* Left: Fixture Palette */}
        <Paper sx={{ width: 220, flexShrink: 0, borderRadius: 0, overflow: 'auto' }}>
          <FixturePalette
            onDragStart={(fixture) => { paletteDragRef.current = fixture; }}
            onFixtureClick={(fixture) => {
              paletteDragRef.current = fixture;
              const spot = paletteSpot();
              void addFixtureAt(fixture.id, spot.x, spot.z);
            }}
          />
        </Paper>

        {/* Center: Stage View */}
        <Box sx={{ flexGrow: 1, p: 2, display: 'flex', flexDirection: 'column' }}>
          {/* Walls mode: what it is, what the last drag did, and the ways out of it. */}
          {wallsOn && (
            <Alert
              severity={wallsNote?.severity ?? 'info'}
              data-testid="walls-mode"
              sx={{ mb: 1, flexShrink: 0 }}
              action={
                <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                  <Button
                    color="inherit"
                    size="small"
                    disabled={wallsBusy || shellUndoCount(rig.room_shell_edits) === 0}
                    onClick={() => { void handleWallsUndo(); }}
                    data-testid="walls-mode-undo"
                  >
                    {undoButtonText(rig.room_shell_edits)}
                  </Button>
                  <Button
                    color="inherit"
                    size="small"
                    disabled={wallsBusy}
                    onClick={() => { setWallsMode(false); void handleEditRoom(); }}
                  >
                    Back to Edit Room
                  </Button>
                  <Button color="inherit" size="small" disabled={wallsBusy} onClick={() => setWallsMode(false)}>
                    Done with walls
                  </Button>
                </Box>
              }
            >
              {wallsNote?.text
                ?? 'Dragging the walls: drag a numbered corner to move it. It goes to the grid unless the snap is off or Alt is held. No fixture is moved, and fixtures cannot be picked up until you are done.'}
              {wallsNote && wallsNote.outside.length > 0 && (
                <Box component="ul" sx={{ m: 0, mt: 0.5, pl: 2.5 }} data-testid="walls-mode-outside">
                  {wallsNote.outside.map((line) => <li key={line}>{line}</li>)}
                </Box>
              )}
            </Alert>
          )}
          {/* Arranging the room's items: what it is, the selected item's box, what the last change did, and the ways out. */}
          {itemsOn && (
            <Alert
              severity={itemsNote?.severity ?? 'info'}
              data-testid="items-mode"
              sx={{ mb: 1, flexShrink: 0 }}
              action={
                <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                  <Button
                    color="inherit"
                    size="small"
                    disabled={shellUndoCount(rig.room_shell_edits) === 0}
                    onClick={() => { void handleItemsUndo(); }}
                    data-testid="items-mode-undo"
                  >
                    {undoButtonText(rig.room_shell_edits)}
                  </Button>
                  <Button
                    color="inherit"
                    size="small"
                    onClick={() => { setItemsMode(false); void handleEditRoom(); }}
                  >
                    Back to Edit Room
                  </Button>
                  <Button color="inherit" size="small" onClick={() => setItemsMode(false)}>
                    Done arranging
                  </Button>
                </Box>
              }
            >
              {itemsNote?.text
                ?? 'Arranging the room: drag a raised area, a truss line or a ring to move it, or press it and use the arrow keys (Shift for ten steps). A selected truss line has a square handle on one end for its length and a round one past the other for its heading; a ring has a square handle for its radius. Everything goes to the grid unless the snap is off or Alt is held. Fixtures cannot be picked up until you are done. The strip beside the plan sets the selected item\'s height: drag its handle up or down.'}
              {selectedItem && (
                <Box sx={{ mt: 0.5 }} data-testid="items-mode-selected">
                  <FormControlLabel
                    sx={{ mr: 0 }}
                    control={
                      <Checkbox
                        size="small"
                        sx={{ py: 0 }}
                        checked={!itemsLeftAlone[shellItemKey(selectedItem)]}
                        onChange={(e) => {
                          leaveItemsAlone({ ...itemsLeftAlone, [shellItemKey(selectedItem)]: !e.target.checked });
                          // The arrow keys are the plan's again, not the box's.
                          e.target.blur();
                        }}
                        inputProps={{ 'aria-label': carryBoxName(selectedItem.kind, shellItemTitle(selectedItem)) }}
                      />
                    }
                    label={
                      <Typography variant="caption">
                        {`${shellItemTitle(selectedItem)} is selected. ${carryLabel(selectedItem.kind)}`}
                      </Typography>
                    }
                  />
                </Box>
              )}
            </Alert>
          )}
          {/* The plan, and beside it, while the room's items are arranged, the height strip. The
              strip is there for the whole of the mode, selected item or not, so the plan does not
              change size under a press. */}
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', flexShrink: 0 }}>
          <Box sx={{ flexGrow: 1, minWidth: 0 }}>
          <StageView2D
            width={rig.stage_width}
            depth={rig.stage_depth}
            height={rig.stage_height}
            fixtures={rig.fixtures}
            roomShell={rig.room_shell}
            selectedIds={selectedFixtureIds}
            gridSize={gridSize}
            snapMode={snapMode}
            onFixtureClick={handleFixtureClick}
            onFixtureDragStart={handleFixtureDragStart}
            onFixtureDrag={handleFixtureDrag}
            onFixturesDrag={handleFixturesDrag}
            onFixtureDragEnd={handleFixtureDragEnd}
            onFixtureSelectRow={handleSelectRow}
            onSelectFixtures={selectFixtures}
            // R, the arrow keys and Escape act on the plan only while it is
            // what is shown, and never under a dialog that is in front of it.
            // Nor in walls mode, where nothing is selected or nudged.
            // Nor while the room's items are arranged, which has keys of its own.
            keyboard={viewMode === '2d' && !identifyOpen && !roomScanOpen && !roomEditOpen && !wallsOn && !itemsOn}
            // The same keys as buttons over the plan, for a phone or a
            // tablet: shown while something is selected, on the same terms.
            nudgePad={viewMode === '2d' && !identifyOpen && !roomScanOpen && !roomEditOpen && !wallsOn && !itemsOn}
            // Edit Room's "Arrange room items on the plan": a raised area, a
            // truss line or a ring is dragged, or nudged with the arrow keys,
            // each change one request and one step of the room's own undo.
            itemsEdit={itemsOn}
            selectedItemKey={selectedItemKey}
            onItemSelect={setSelectedItemKey}
            onItemChange={handleItemChange}
            onItemNudge={handleItemNudge}
            // Edit Room's walls mode: the corners of the walls are dragged,
            // each drag one request and one step of the room's own undo.
            wallsEdit={wallsOn}
            onWallCornerMove={handleWallCornerMove}
            onLayRow={scannedTruss.length > 0 ? handleLayRow : undefined}
            layChoice={layChoice}
            onLayChoiceChange={setLayChoice}
            // M, and the pad's Mirror and Even buttons: the plan only asks.
            onMirror={handleMirror}
            onSpaceEvenly={handleSpaceEvenly}
            onDropFromPalette={addFixtureAt}
          />
          </Box>
          {/* Heights by dragging (slice 22): the selected item's top and base, or its trim height.
              A handle let go is one change to the room, through what the plan's handles go through:
              the fixtures as the item's box says, a refusal in the strip above, and the room's undo. */}
          {itemsOn && (
            <RoomItemHeightStrip
              gauge={heightGauge(selectedItem, rig.room_shell)}
              onChange={handleItemChange}
            />
          )}
          </Box>

          {/* Bottom: Properties Panel */}
          {selectedFixtures.length > 1 && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, flexShrink: 0 }}>
              {`${selectedFixtures.length} fixtures selected. Drag any one of them, or press an arrow key, to move them together${
                scannedTruss.length > 0 ? ', or use Lay on truss to space them along the nearest scanned truss' : ''
              }. M mirrors them left to right${
                selectedFixtures.length > 2 ? ', and Space evenly spaces them between the first and the last by address' : ''
              }. Escape clears the selection. On a touch screen, use the arrows on the plan, and press and hold a fixture to add it or take it out.`}
            </Typography>
          )}
          {selectedFixture && (
            <Paper sx={{ mt: 1, flexShrink: 0 }}>
              <FixtureProperties
                fixture={selectedFixture}
                availableModes={selectedFixture.fixture?.modes}
                onChange={handleFixturePropertyChange}
              />
            </Paper>
          )}
        </Box>

        {/* Right: Patch Table */}
        <Paper sx={{ width: 280, flexShrink: 0, borderRadius: 0, overflow: 'auto' }}>
          <PatchTable
            fixtures={rig.fixtures}
            conflicts={conflicts}
            selectedUniverse={patchUniverse}
            onUniverseChange={setPatchUniverse}
          />
        </Paper>
      </Box>

      <IdentifyWalkthrough
        rigId={rig.id}
        open={identifyOpen}
        stageWidth={rig.stage_width}
        stageDepth={rig.stage_depth}
        unconfirmedCount={
          rig.fixtures.filter(
            (f) => f.is_active !== false && (f.tags ?? []).includes('position_unconfirmed')
          ).length
        }
        onClose={() => {
          setIdentifyOpen(false);
          // A walk stopped partway has still moved and confirmed lights.
          void fetchRig();
        }}
        onFinished={() => { void fetchRig(); }}
      />

      {/* A scan that is applied moves fixtures and stores a room on the server:
          the positions on screen are stale, and so is any undo step that would
          write the old ones back. */}
      <RoomScanDialog
        open={roomScanOpen}
        rigId={rig.id}
        rigName={rig.name}
        hasRoom={rig.room_shell?.source === 'scan'}
        undoMoves={undoCount(rig)}
        pendingCarryOver={pendingCarryOverOf(rig.room_shell)}
        onClose={() => setRoomScanOpen(false)}
        onChanged={() => {
          clearHistory();
          void fetchRig();
        }}
        onView3D={() => {
          setRoomScanOpen(false);
          navigate(`/rigs/${rig.id}/visualizer`);
        }}
      />

      {/* What the scan found, corrected by hand. Each stored change, and each
          one undone, comes back as the whole room, which the plan then draws
          and snaps to. A truss that took its fixtures along, or brought them
          back, has the rig read again as well. */}
      <RoomShellEditDialog
        open={roomEditOpen}
        rigId={rig.id}
        rigName={rig.name}
        shell={rig.room_shell}
        undo={rig.room_shell_edits}
        onClose={() => setRoomEditOpen(false)}
        onChanged={handleRoomEdited}
        onFixturesMoved={handleRoomFixturesMoved}
        onDragWalls={handleDragWalls}
        onArrangeItems={handleArrangeItems}
      />

      <Snackbar
        open={!!notice}
        autoHideDuration={5000}
        // Not on a click elsewhere: the click that asks for the next notice is
        // one, and would take that notice down in the same breath it went up.
        onClose={(_event, reason) => { if (reason !== 'clickaway') setNotice(null); }}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={notice?.severity ?? 'success'} onClose={() => setNotice(null)} variant="filled">
          {notice?.text}
        </Alert>
      </Snackbar>
    </Box>
  );
}
