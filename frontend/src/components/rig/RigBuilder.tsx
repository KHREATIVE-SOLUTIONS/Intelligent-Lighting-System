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
import PatchTable from './PatchTable';
import FixtureProperties from './FixtureProperties';
import IdentifyWalkthrough from './IdentifyWalkthrough';
import type { Rig, RigFixture, Fixture, PatchConflict } from '../../types';

/** Long enough that a drag is one request, short enough to feel immediate. */
const POSITION_SAVE_DEBOUNCE_MS = 400;

const snapshotPositions = (fixtures: RigFixture[]): FixturePositionSnapshot[] =>
  fixtures.map((f) => ({ id: f.id, position_x: f.position_x, position_z: f.position_z }));

const roundToMm = (value: number) => Math.round(value * 1000) / 1000;

/** Two icons closer than this on the plan read as one light. */
const ICON_CLEARANCE_M = 0.6;

const clampSpan = (value: number, span: number) =>
  Math.min(Math.max(value, -span / 2), span / 2);

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

  const {
    viewMode, snapMode, gridSize, selectedFixtureIds,
    setViewMode, setSnapMode, selectFixture, deselectAll,
    undoStack, redoStack, pushUndo, undo, redo, clearHistory,
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

  const handleFixtureDrag = (fixtureId: number, x: number, z: number) => {
    const current = rigRef.current;
    if (!current) return;
    const moved = current.fixtures.find((f) => f.id === fixtureId);
    if (!moved || (moved.position_x === x && moved.position_z === z)) return;

    if (pendingUndoRef.current) {
      pushUndo(snapshotPositions(current.fixtures));
      pendingUndoRef.current = false;
    }

    applyRig({
      ...current,
      fixtures: current.fixtures.map((f) =>
        f.id === fixtureId ? { ...f, position_x: x, position_z: z } : f
      ),
    });
    dirtyIdsRef.current.add(fixtureId);
    schedulePositionSave();
  };

  const handleFixtureDragEnd = () => {
    pendingUndoRef.current = false;
    void flushPositions();
  };

  const applySnapshot = useCallback((snapshot: FixturePositionSnapshot[]) => {
    const current = rigRef.current;
    if (!current) return;
    const byId = new Map(snapshot.map((s) => [s.id, s]));
    let changed = false;

    const fixtures = current.fixtures.map((f) => {
      const target = byId.get(f.id);
      if (!target) return f;
      if (target.position_x === f.position_x && target.position_z === f.position_z) return f;
      changed = true;
      dirtyIdsRef.current.add(f.id);
      return { ...f, position_x: target.position_x, position_z: target.position_z };
    });

    if (!changed) return;
    applyRig({ ...current, fixtures });
    void flushPositions();
  }, [applyRig, flushPositions]);

  const handleUndo = () => {
    const current = rigRef.current;
    if (!current) return;
    const previous = undo(snapshotPositions(current.fixtures));
    if (previous) applySnapshot(previous);
  };

  const handleRedo = () => {
    const current = rigRef.current;
    if (!current) return;
    const next = redo(snapshotPositions(current.fixtures));
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
   * Nudge a position the app chose (rather than one the owner pointed at) off any
   * fixture already there, so clicking the palette twice does not stack two icons.
   */
  const clearSpotNear = (x: number, z: number): { x: number; z: number } => {
    const current = rigRef.current;
    if (!current) return { x, z };
    const taken = (px: number, pz: number) =>
      current.fixtures.some((f) => Math.hypot(f.position_x - px, f.position_z - pz) < ICON_CLEARANCE_M);
    if (!taken(x, z)) return { x, z };

    for (let ring = 1; ring <= 6; ring += 1) {
      const step = ring * ICON_CLEARANCE_M;
      for (const [dx, dz] of [[step, 0], [-step, 0], [0, step], [0, -step], [step, step], [-step, -step]]) {
        const cx = clampSpan(x + dx, rig?.stage_width ?? 0);
        const cz = clampSpan(z + dz, rig?.stage_depth ?? 0);
        if (!taken(cx, cz)) return { x: cx, z: cz };
      }
    }
    return { x, z };
  };

  const addFixtureAt = useCallback(async (fixtureId: number, x: number, z: number) => {
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
        position_y: hangHeightNear(z),
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

  const selectedFixture = rig.fixtures.find((f) => selectedFixtureIds.has(f.id));

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
              const spot = clearSpotNear(0, 0);
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
            selectedIds={selectedFixtureIds}
            gridSize={gridSize}
            snapMode={snapMode}
            onFixtureClick={handleFixtureClick}
            onFixtureDragStart={handleFixtureDragStart}
            onFixtureDrag={handleFixtureDrag}
            onFixtureDragEnd={handleFixtureDragEnd}
            onDropFromPalette={addFixtureAt}
          />

          {/* Bottom: Properties Panel */}
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
        onClose={() => setIdentifyOpen(false)}
        onFinished={() => { void fetchRig(); }}
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
