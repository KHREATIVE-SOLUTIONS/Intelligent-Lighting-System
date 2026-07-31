import {
  Box,
  Button,
  ButtonGroup,
  TextField,
  Select,
  MenuItem,
  IconButton,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  Save as SaveIcon,
  Undo as UndoIcon,
  Redo as RedoIcon,
  AutoFixHigh as AutoPatchIcon,
  FlashOn as TestIcon,
  WbIncandescent as IdentifyIcon,
  ViewInAr as View3DIcon,
  GridOn as GridIcon,
} from '@mui/icons-material';
import type { SnapMode } from '../../stores/rigEditorStore';

export type PositionSaveState = 'idle' | 'pending' | 'saving' | 'saved' | 'error';

interface RigEditorToolbarProps {
  rigName: string;
  viewMode: '2d' | '3d';
  snapMode: SnapMode;
  trussLineCount: number;
  saveState: PositionSaveState;
  onNameChange: (name: string) => void;
  onViewModeChange: (mode: '2d' | '3d') => void;
  onSnapModeChange: (mode: SnapMode) => void;
  onSave: () => void;
  onAutoPatch: () => void;
  onTestAll: () => void;
  onIdentify: () => void;
  onUndo: () => void;
  onRedo: () => void;
  canUndo: boolean;
  canRedo: boolean;
}

const SAVE_STATE_TEXT: Record<PositionSaveState, string> = {
  idle: '',
  pending: 'Unsaved changes',
  saving: 'Saving positions...',
  saved: 'Positions saved',
  error: 'Positions NOT saved - check the connection',
};

export default function RigEditorToolbar({
  rigName,
  viewMode,
  snapMode,
  trussLineCount,
  saveState,
  onNameChange,
  onViewModeChange,
  onSnapModeChange,
  onSave,
  onAutoPatch,
  onTestAll,
  onIdentify,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
}: RigEditorToolbarProps) {
  const snapHint =
    snapMode === 'truss'
      ? trussLineCount > 0
        ? `Snapping to ${trussLineCount} truss ${trussLineCount === 1 ? 'line' : 'lines'}`
        : 'No trusses found yet - fixtures move freely'
      : snapMode === 'none'
        ? 'Fixtures move freely'
        : '';

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 1, borderBottom: 1, borderColor: 'divider' }}>
      <TextField
        size="small"
        value={rigName}
        onChange={(e) => onNameChange(e.target.value)}
        variant="standard"
        sx={{ minWidth: 200 }}
        InputProps={{ style: { fontSize: '1.1rem', fontWeight: 500 } }}
      />

      <ButtonGroup size="small" sx={{ ml: 2 }}>
        <Button
          variant={viewMode === '2d' ? 'contained' : 'outlined'}
          onClick={() => onViewModeChange('2d')}
        >
          2D
        </Button>
        <Button
          variant={viewMode === '3d' ? 'contained' : 'outlined'}
          onClick={() => onViewModeChange('3d')}
          startIcon={<View3DIcon />}
        >
          3D
        </Button>
      </ButtonGroup>

      <Select
        size="small"
        value={snapMode}
        onChange={(e) => onSnapModeChange(e.target.value as SnapMode)}
        sx={{ minWidth: 100 }}
      >
        <MenuItem value="grid"><GridIcon fontSize="small" sx={{ mr: 0.5 }} /> Grid</MenuItem>
        <MenuItem value="truss">Truss{trussLineCount > 0 ? ` (${trussLineCount})` : ''}</MenuItem>
        <MenuItem value="none">Free</MenuItem>
      </Select>

      {snapHint && (
        <Typography
          variant="caption"
          color={snapMode === 'truss' && trussLineCount === 0 ? 'warning.main' : 'text.secondary'}
        >
          {snapHint}
        </Typography>
      )}

      <Box sx={{ flexGrow: 1 }} />

      {saveState !== 'idle' && (
        <Typography
          variant="caption"
          color={saveState === 'error' ? 'error.main' : saveState === 'saved' ? 'success.main' : 'text.secondary'}
          sx={{ mr: 1 }}
        >
          {SAVE_STATE_TEXT[saveState]}
        </Typography>
      )}

      <Tooltip title={canUndo ? 'Undo move' : 'Nothing to undo - move a fixture first'}>
        <span>
          <IconButton size="small" onClick={onUndo} disabled={!canUndo}>
            <UndoIcon />
          </IconButton>
        </span>
      </Tooltip>
      <Tooltip title={canRedo ? 'Redo move' : 'Nothing to redo'}>
        <span>
          <IconButton size="small" onClick={onRedo} disabled={!canRedo}>
            <RedoIcon />
          </IconButton>
        </span>
      </Tooltip>

      <Button size="small" startIcon={<AutoPatchIcon />} onClick={onAutoPatch}>
        Auto-Patch
      </Button>
      <Button size="small" startIcon={<TestIcon />} onClick={onTestAll}>
        Test All
      </Button>
      <Tooltip title="Light one fixture at a time and tap where it is on the plan">
        <Button size="small" startIcon={<IdentifyIcon />} onClick={onIdentify}>
          Identify Lights
        </Button>
      </Tooltip>
      <Button size="small" variant="contained" startIcon={<SaveIcon />} onClick={onSave}>
        Save
      </Button>
    </Box>
  );
}
