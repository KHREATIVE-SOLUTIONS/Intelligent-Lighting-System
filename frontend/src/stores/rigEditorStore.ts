import { create } from 'zustand';

interface RigEditorState {
  viewMode: '2d' | '3d';
  snapMode: 'grid' | 'truss' | 'none';
  gridSize: number;
  selectedFixtureIds: Set<number>;
  hoveredFixtureId: number | null;
  isDragging: boolean;
  undoStack: any[];
  redoStack: any[];

  setViewMode: (mode: '2d' | '3d') => void;
  setSnapMode: (mode: 'grid' | 'truss' | 'none') => void;
  setGridSize: (size: number) => void;
  selectFixture: (id: number, multi?: boolean) => void;
  deselectAll: () => void;
  setHoveredFixture: (id: number | null) => void;
  setDragging: (dragging: boolean) => void;
  pushUndo: (state: any) => void;
  undo: () => any | null;
  redo: () => any | null;
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

  deselectAll: () => set({ selectedFixtureIds: new Set() }),

  setHoveredFixture: (id) => set({ hoveredFixtureId: id }),
  setDragging: (dragging) => set({ isDragging: dragging }),

  pushUndo: (state) =>
    set((s) => ({
      undoStack: [...s.undoStack.slice(-50), state],
      redoStack: [],
    })),

  undo: () => {
    const { undoStack } = get();
    if (undoStack.length === 0) return null;
    const last = undoStack[undoStack.length - 1];
    set((s) => ({
      undoStack: s.undoStack.slice(0, -1),
      redoStack: [...s.redoStack, last],
    }));
    return last;
  },

  redo: () => {
    const { redoStack } = get();
    if (redoStack.length === 0) return null;
    const last = redoStack[redoStack.length - 1];
    set((s) => ({
      redoStack: s.redoStack.slice(0, -1),
      undoStack: [...s.undoStack, last],
    }));
    return last;
  },
}));
