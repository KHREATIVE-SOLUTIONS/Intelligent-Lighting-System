import { create } from 'zustand';

/** MIME type carried by a palette drag so the stage view can accept only fixture drops. */
export const FIXTURE_DRAG_MIME = 'application/x-lighting-fixture-id';

export type SnapMode = 'grid' | 'truss' | 'none';

export interface FixturePositionSnapshot {
  id: number;
  position_x: number;
  /**
   * The height, kept only for a fixture whose height the drag itself changed
   * (a snap onto scanned truss). Absent, an undo leaves the height alone, so
   * a height set in the properties panel is never taken back by undoing a move.
   */
  position_y?: number;
  position_z: number;
}

const HISTORY_LIMIT = 50;

/** Fixtures within this distance in depth are read as hanging on the same truss. */
const TRUSS_TOLERANCE_M = 0.3;

/**
 * Derive truss lines (stage-depth values) from the depths fixtures already occupy.
 * A depth counts as a truss only when at least two fixtures share it, so a single
 * stray light never becomes a snap target.
 */
export function computeTrussLines(depths: number[]): number[] {
  const sorted = [...depths].sort((a, b) => a - b);
  const lines: number[] = [];
  let group: number[] = [];

  const close = () => {
    if (group.length >= 2) {
      lines.push(group.reduce((sum, z) => sum + z, 0) / group.length);
    }
    group = [];
  };

  for (const z of sorted) {
    if (group.length > 0 && z - group[group.length - 1] > TRUSS_TOLERANCE_M) close();
    group.push(z);
  }
  close();

  return lines;
}

interface RigEditorState {
  viewMode: '2d' | '3d';
  snapMode: SnapMode;
  gridSize: number;
  selectedFixtureIds: Set<number>;
  hoveredFixtureId: number | null;
  isDragging: boolean;
  undoStack: FixturePositionSnapshot[][];
  redoStack: FixturePositionSnapshot[][];

  setViewMode: (mode: '2d' | '3d') => void;
  setSnapMode: (mode: SnapMode) => void;
  setGridSize: (size: number) => void;
  selectFixture: (id: number, multi?: boolean) => void;
  /** Makes these the selection, in place of whatever was selected: a whole row at once. */
  selectFixtures: (ids: number[]) => void;
  deselectAll: () => void;
  setHoveredFixture: (id: number | null) => void;
  setDragging: (dragging: boolean) => void;
  pushUndo: (snapshot: FixturePositionSnapshot[]) => void;
  /**
   * Adds heights to the newest undo step, for fixtures it has none for yet:
   * the height each had before the drag that step belongs to changed it.
   */
  noteUndoHeights: (heights: Array<{ id: number; position_y: number }>) => void;
  undo: (current: FixturePositionSnapshot[]) => FixturePositionSnapshot[] | null;
  redo: (current: FixturePositionSnapshot[]) => FixturePositionSnapshot[] | null;
  clearHistory: () => void;
}

export const useRigEditorStore = create<RigEditorState>((set, get) => ({
  viewMode: '2d',
  snapMode: 'grid',
  gridSize: 0.5,
  selectedFixtureIds: new Set(),
  hoveredFixtureId: null,
  isDragging: false,
  undoStack: [],
  redoStack: [],

  setViewMode: (mode) => set({ viewMode: mode }),
  setSnapMode: (mode) => set({ snapMode: mode }),
  setGridSize: (size) => set({ gridSize: size }),

  selectFixture: (id, multi = false) =>
    set((state) => {
      const newSet = new Set(multi ? state.selectedFixtureIds : []);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return { selectedFixtureIds: newSet };
    }),

  selectFixtures: (ids) => set({ selectedFixtureIds: new Set(ids) }),

  deselectAll: () => set({ selectedFixtureIds: new Set() }),

  setHoveredFixture: (id) => set({ hoveredFixtureId: id }),
  setDragging: (dragging) => set({ isDragging: dragging }),

  pushUndo: (snapshot) =>
    set((s) => ({
      undoStack: [...s.undoStack, snapshot].slice(-HISTORY_LIMIT),
      redoStack: [],
    })),

  noteUndoHeights: (heights) =>
    set((s) => {
      if (s.undoStack.length === 0 || heights.length === 0) return s;
      const byId = new Map(heights.map((h) => [h.id, h.position_y]));
      let noted = false;
      const top = s.undoStack[s.undoStack.length - 1].map((entry) => {
        const height = byId.get(entry.id);
        // The first height noted is the one from before the drag: keep it.
        if (height === undefined || entry.position_y !== undefined) return entry;
        noted = true;
        return { ...entry, position_y: height };
      });
      return noted ? { undoStack: [...s.undoStack.slice(0, -1), top] } : s;
    }),

  undo: (current) => {
    const { undoStack } = get();
    if (undoStack.length === 0) return null;
    const previous = undoStack[undoStack.length - 1];
    set((s) => ({
      undoStack: s.undoStack.slice(0, -1),
      redoStack: [...s.redoStack, current].slice(-HISTORY_LIMIT),
    }));
    return previous;
  },

  redo: (current) => {
    const { redoStack } = get();
    if (redoStack.length === 0) return null;
    const next = redoStack[redoStack.length - 1];
    set((s) => ({
      redoStack: s.redoStack.slice(0, -1),
      undoStack: [...s.undoStack, current].slice(-HISTORY_LIMIT),
    }));
    return next;
  },

  clearHistory: () => set({ undoStack: [], redoStack: [] }),
}));
