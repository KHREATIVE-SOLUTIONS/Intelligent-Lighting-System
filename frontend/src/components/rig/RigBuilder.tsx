import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Box, Typography, Paper } from '@mui/material';
import { rigsApi } from '../../services/api';
import { useRigEditorStore } from '../../stores/rigEditorStore';
import RigEditorToolbar from './RigEditorToolbar';
import FixturePalette from './FixturePalette';
import StageView2D from './StageView2D';
import PatchTable from './PatchTable';
import FixtureProperties from './FixtureProperties';
import type { Rig, PatchConflict } from '../../types';

export default function RigBuilder() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [rig, setRig] = useState<Rig | null>(null);
  const [conflicts, setConflicts] = useState<PatchConflict[]>([]);
  const [loading, setLoading] = useState(true);
  const [patchUniverse, setPatchUniverse] = useState(0);

  const {
    viewMode, snapMode, gridSize, selectedFixtureIds,
    setViewMode, setSnapMode, selectFixture, deselectAll,
    undoStack, redoStack, pushUndo, undo, redo,
  } = useRigEditorStore();

  const fetchRig = useCallback(async () => {
    if (!id) return;
    try {
      const data = await rigsApi.get(Number(id));
      setRig(data);
      const conflictData = await rigsApi.getConflicts(Number(id));
      setConflicts(conflictData.conflicts || []);
    } catch {
      console.error('Failed to fetch rig');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { fetchRig(); }, [fetchRig]);

  const handleSave = async () => {
    if (!rig) return;
    await rigsApi.update(rig.id, {
      name: rig.name,
      stage_width: rig.stage_width,
      stage_depth: rig.stage_depth,
      stage_height: rig.stage_height,
    });
  };

  const handleAutoPatch = async () => {
    if (!rig) return;
    await rigsApi.autoPatch(rig.id);
    await fetchRig();
  };

  const handleTestAll = async () => {
    if (!rig) return;
    await rigsApi.testAll(rig.id);
  };

  const handleFixtureClick = (fixtureId: number, multi: boolean) => {
    if (fixtureId === -1) {
      deselectAll();
    } else {
      selectFixture(fixtureId, multi);
    }
  };

  const handleFixtureDrag = async (fixtureId: number, x: number, z: number) => {
    if (!rig) return;
    // Optimistic update
    setRig({
      ...rig,
      fixtures: rig.fixtures.map((f) =>
        f.id === fixtureId ? { ...f, position_x: x, position_z: z } : f
      ),
    });
  };

  const handleFixturePropertyChange = async (updates: any) => {
    if (!rig || selectedFixtureIds.size !== 1) return;
    const fixtureId = Array.from(selectedFixtureIds)[0];

    // Optimistic UI update
    setRig({
      ...rig,
      fixtures: rig.fixtures.map((f) =>
        f.id === fixtureId ? { ...f, ...updates } : f
      ),
    });

    // API update
    try {
      await rigsApi.updateFixture(rig.id, fixtureId, updates);
    } catch {
      await fetchRig(); // Revert on error
    }
  };

  if (loading) return <Typography>Loading...</Typography>;
  if (!rig) return <Typography>Rig not found</Typography>;

  const selectedFixture = rig.fixtures.find((f) => selectedFixtureIds.has(f.id));

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 88px)', mx: -3, mt: -3 }}>
      <RigEditorToolbar
        rigName={rig.name}
        viewMode={viewMode}
        snapMode={snapMode}
        onNameChange={(name) => setRig({ ...rig, name })}
        onViewModeChange={setViewMode}
        onSnapModeChange={setSnapMode}
        onSave={handleSave}
        onAutoPatch={handleAutoPatch}
        onTestAll={handleTestAll}
        onUndo={() => undo()}
        onRedo={() => redo()}
        canUndo={undoStack.length > 0}
        canRedo={redoStack.length > 0}
      />

      <Box sx={{ display: 'flex', flexGrow: 1, overflow: 'hidden' }}>
        {/* Left: Fixture Palette */}
        <Paper sx={{ width: 220, flexShrink: 0, borderRadius: 0, overflow: 'auto' }}>
          <FixturePalette />
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
            onFixtureClick={handleFixtureClick}
            onFixtureDrag={handleFixtureDrag}
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
    </Box>
  );
}
