import {
  Box,
  Button,
  ButtonGroup,
  TextField,
  Select,
  MenuItem,
  IconButton,
  Tooltip,
} from '@mui/material';
import {
  Save as SaveIcon,
  Undo as UndoIcon,
  Redo as RedoIcon,
  AutoFixHigh as AutoPatchIcon,
  FlashOn as TestIcon,
  ViewInAr as View3DIcon,
  GridOn as GridIcon,
} from '@mui/icons-material';

interface RigEditorToolbarProps {
  rigName: string;
  viewMode: '2d' | '3d';
  snapMode: string;
  onNameChange: (name: string) => void;
  onViewModeChange: (mode: '2d' | '3d') => void;
  onSnapModeChange: (mode: string) => void;
  onSave: () => void;
  onAutoPatch: () => void;
  onTestAll: () => void;
  onUndo: () => void;
  onRedo: () => void;
  canUndo: boolean;
  canRedo: boolean;
}

export default function RigEditorToolbar({
  rigName,
  viewMode,
  snapMode,
  onNameChange,
  onViewModeChange,
  onSnapModeChange,
  onSave,
  onAutoPatch,
  onTestAll,
  onUndo,
  onRedo,
  canUndo,
  canRedo,
}: RigEditorToolbarProps) {
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
        onChange={(e) => onSnapModeChange(e.target.value)}
        sx={{ minWidth: 100 }}
      >
        <MenuItem value="grid"><GridIcon fontSize="small" sx={{ mr: 0.5 }} /> Grid</MenuItem>
        <MenuItem value="truss">Truss</MenuItem>
        <MenuItem value="none">Free</MenuItem>
      </Select>

      <Box sx={{ flexGrow: 1 }} />

      <Tooltip title="Undo">
        <span>
          <IconButton size="small" onClick={onUndo} disabled={!canUndo}>
            <UndoIcon />
          </IconButton>
        </span>
      </Tooltip>
      <Tooltip title="Redo">
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
      <Button size="small" variant="contained" startIcon={<SaveIcon />} onClick={onSave}>
        Save
      </Button>
    </Box>
  );
}
