import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Box, Typography, Paper, Snackbar, Alert } from '@mui/material';
import { rigsApi, fixturesApi } from '../../services/api';
import { useRigEditorStore, computeTrussLines } from '../../stores/rigEditorStore';
import type { FixturePositionSnapshot } from '../../stores/rigEditorStore';
import RigEditorToolbar from './RigEditorToolbar';
import type { PositionSaveState } from './RigEditorToolbar';
import FixturePalette from './FixturePalette';
import StageView2D from './StageView2D';
import { paletteClickSpot, planTrussTargets, roomPlan } from './roomPlan2d';
import {
  heightIdsOf, heightsBefore, layNoticeText, layRowOnTruss, nearestTruss, rowOf, snapshotPositions, withMoves,
  withSnapshot,
} from './rowMove2d';
import type { PlanMove } from './rowMove2d';
import PatchTable from './PatchTable';
import FixtureProperties from './FixtureProperties';
import IdentifyWalkthrough from './IdentifyWalkthrough';
import RoomScanDialog from './RoomScanDialog';
import { undoCount } from '../../utils/roomScan';
import type { Rig, RigFixture, Fixture, PatchConflict } from '../../types';

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
   * Lays the selected fixtures evenly along the scanned truss nearest them
   * (`layRowOnTruss`, docs/ROOM_SCAN.md). Saved as a row move is: one undo
   * step, one batch-update, heights kept in the step where they change, and
   * no tag touched.
   */
  const handleLayRow = () => {
    const current = rigRef.current;
    if (!current) return;
    const lay = layRowOnTruss(
      current.fixtures, selectedFixtureIds, current.room_shell,
      // The walls the plan draws and holds a drag to.
      roomPlan(current.room_shell)?.walls ?? null, current.stage_width, current.stage_depth,
    );
    if (!lay.ok) {
      setNotice({ severity: 'error', text: layNoticeText(lay) });
      return;
    }
    const next = withMoves(current.fixtures, lay.moves);
    setNotice({ severity: 'success', text: layNoticeText(lay, next.changed.length) });
    if (next.changed.length === 0) return;

    pushUndo(snapshotPositions(current.fixtures));
    noteUndoHeights(heightsBefore(current.fixtures, lay.moves));
    applyRig({ ...current, fixtures: next.fixtures });
    next.changed.forEach((fixtureId) => dirtyIdsRef.current.add(fixtureId));
    void flushPositions();
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
        selectedCount={selectedFixtures.length}
        onSelectRow={() => { if (selectedFixtures.length > 0) handleSelectRow(selectedFixtures[0].id); }}
        onLayRow={scannedTruss.length > 0 ? handleLayRow : undefined}
        layTargetName={layTarget?.name ?? null}
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
            keyboard={viewMode === '2d' && !identifyOpen && !roomScanOpen}
            // The same keys as buttons over the plan, for a phone or a
            // tablet: shown while something is selected, on the same terms.
            nudgePad={viewMode === '2d' && !identifyOpen && !roomScanOpen}
            onLayRow={scannedTruss.length > 0 ? handleLayRow : undefined}
            onDropFromPalette={addFixtureAt}
          />

          {/* Bottom: Properties Panel */}
          {selectedFixtures.length > 1 && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, flexShrink: 0 }}>
              {`${selectedFixtures.length} fixtures selected. Drag any one of them, or press an arrow key, to move them together${
                scannedTruss.length > 0 ? ', or use Lay on truss to space them along the nearest scanned truss' : ''
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

      <Snackbar
        open={!!notice}
        autoHideDuration={5000}
        onClose={() => setNotice(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={notice?.severity ?? 'success'} onClose={() => setNotice(null)} variant="filled">
          {notice?.text}
        </Alert>
      </Snackbar>
    </Box>
  );
}
