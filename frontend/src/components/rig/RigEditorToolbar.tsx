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
  MeetingRoom as RoomScanIcon,
  EditLocationAlt as EditRoomIcon,
  FactCheck as ReadinessIcon,
  DeviceHub as RdmIcon,
  QrCodeScanner as QrIcon,
} from '@mui/icons-material';
import type { SnapMode } from '../../stores/rigEditorStore';
import { DEFAULT_LAY_CHOICE, LAY_MODES, LAY_MODE_LABELS, parseSpacing } from './rowSpace2d';
import type { LayChoice, LayMode } from './rowSpace2d';

export type PositionSaveState = 'idle' | 'pending' | 'saving' | 'saved' | 'error';

/** How each spacing lays a row, for the Lay on truss tooltip. */
const LAY_HOW: Record<LayMode, string> = {
  fill: 'evenly spaced over its whole length',
  keep: 'at the spacing they have now, centred on it',
  set: 'at the spacing typed, centred on it',
};

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
  /** Opens the room scan dialog. The button is left out when this is. */
  onRoomScan?: () => void;
  /** Whether a scanned room is already stored on the rig. */
  hasRoom?: boolean;
  /**
   * Opens the dialog that renames, moves or deletes what the scan found. The
   * button is left out when this is, and for a rig with no scanned room.
   */
  onEditRoom?: () => void;
  /** Opens the venue readiness checks. The button is left out when this is. */
  onReadiness?: () => void;
  /** Opens RDM discovery, to add the devices it found to this rig. The button is left out when this is. */
  onDiscoverRdm?: () => void;
  /** Opens the QR scanner, to add fixtures by their labels. The button is left out when this is. */
  onScanQr?: () => void;
  /** Selects the whole row the selected fixture is in. The button is left out when this is. */
  onSelectRow?: () => void;
  /** How many fixtures are selected: the button needs one to go by. */
  selectedCount?: number;
  /** Lays the selected fixtures along the nearest scanned truss. The button is left out when this is. */
  onLayRow?: () => void;
  /** The truss the selection would be laid along, for the tooltip. The button needs one. */
  layTargetName?: string | null;
  /**
   * How far apart Lay on truss lays a row: the whole truss shared out, the
   * row's own spacing, or one typed in metres. The choice is left out when
   * `onLayChoiceChange` is.
   */
  layChoice?: LayChoice;
  onLayChoiceChange?: (choice: LayChoice) => void;
  /** Mirrors the selected fixtures left to right. The button is left out when this is. */
  onMirror?: () => void;
  /** Spaces the selected fixtures evenly between their ends. The button is left out when this is. */
  onSpaceEvenly?: () => void;
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
  onRoomScan,
  hasRoom = false,
  onEditRoom,
  onReadiness,
  onDiscoverRdm,
  onScanQr,
  onSelectRow,
  selectedCount = 0,
  onLayRow,
  layTargetName = null,
  layChoice = DEFAULT_LAY_CHOICE,
  onLayChoiceChange,
  onMirror,
  onSpaceEvenly,
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

      {onSelectRow && (
        <Tooltip
          title={
            selectedCount > 0
              ? 'Select every fixture in the same row: its group, its scanned truss, or its height and depth (R on the keyboard, or a double-click on a fixture, does the same). Then drag one, or press an arrow key, to move them all: one grid step, ten with Shift. Shift-click or Ctrl-click adds one at a time; Escape clears the selection'
              : 'Select a fixture first, then this (or R on the keyboard) selects the rest of its row. Dragging over empty floor draws a box that selects every fixture in it; hold Shift to add to the selection. On a touch screen, press and hold a fixture to add it to the selection or take it out, and press and hold empty floor before dragging a box that adds to it'
          }
        >
          <span>
            <Button size="small" onClick={onSelectRow} disabled={selectedCount === 0}>
              Select row
            </Button>
          </span>
        </Tooltip>
      )}

      {onLayRow && (
        <Tooltip
          title={
            selectedCount > 1 && layTargetName
              ? `Lay the ${selectedCount} selected fixtures along ${layTargetName}, the scanned truss nearest their middle: ${LAY_HOW[layChoice.mode]}, in address order, at its hang height. One Undo puts them back`
              : 'Select two or more fixtures (Select row, or Shift-click), then this spaces them evenly along the nearest scanned truss'
          }
        >
          <span>
            <Button size="small" onClick={onLayRow} disabled={selectedCount < 2 || !layTargetName}>
              Lay on truss
            </Button>
          </span>
        </Tooltip>
      )}

      {onLayRow && onLayChoiceChange && (
        <>
          <Select
            native
            size="small"
            variant="standard"
            value={layChoice.mode}
            onChange={(e) => onLayChoiceChange({ ...layChoice, mode: e.target.value as LayMode })}
            inputProps={{
              'aria-label': 'Lay on truss spacing',
              title: 'Fill truss shares the whole truss out. Keep spacing and Set spacing centre the row on the middle of the truss, and move nothing if it does not fit',
            }}
            sx={{ fontSize: '0.8125rem' }}
          >
            {LAY_MODES.map((mode) => (
              <option key={mode} value={mode}>{LAY_MODE_LABELS[mode]}</option>
            ))}
          </Select>
          {layChoice.mode === 'set' && (
            <TextField
              size="small"
              variant="standard"
              value={layChoice.metres}
              onChange={(e) => onLayChoiceChange({ ...layChoice, metres: e.target.value })}
              error={parseSpacing(layChoice.metres) === null}
              inputProps={{ 'aria-label': 'Spacing in metres', inputMode: 'decimal', style: { textAlign: 'right' } }}
              InputProps={{ endAdornment: <Typography variant="caption" sx={{ ml: 0.5 }}>m</Typography> }}
              sx={{ width: 64 }}
            />
          )}
        </>
      )}

      {onMirror && (
        <Tooltip
          title={
            selectedCount > 0
              ? `Mirror the selected ${selectedCount === 1 ? 'fixture' : 'fixtures'} left to right about the centre line${hasRoom ? ' of the scanned room' : ''} (M on the keyboard does the same). Heights are kept, and a place that would be outside the room is held at its wall. One Undo puts them back`
              : 'Select one or more fixtures, then this (or M on the keyboard) mirrors them left to right about the centre line'
          }
        >
          <span>
            <Button size="small" onClick={onMirror} disabled={selectedCount === 0}>
              Mirror
            </Button>
          </span>
        </Tooltip>
      )}

      {onSpaceEvenly && (
        <Tooltip
          title={
            selectedCount > 2
              ? `Space the ${selectedCount} selected fixtures evenly: the first and the last by DMX address stay where they are, and the rest go at equal steps on the straight line between them, in address order. Heights are kept. One Undo puts them back`
              : 'Select three or more fixtures, then this spaces them evenly between the first and the last by DMX address'
          }
        >
          <span>
            <Button size="small" onClick={onSpaceEvenly} disabled={selectedCount < 3}>
              Space evenly
            </Button>
          </span>
        </Tooltip>
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
      {onDiscoverRdm && (
        <Tooltip title="Find fixtures on the DMX line by RDM and add the ones you pick to this rig, at the address each reports">
          <Button size="small" startIcon={<RdmIcon />} onClick={onDiscoverRdm}>
            Discover RDM
          </Button>
        </Tooltip>
      )}
      {onScanQr && (
        <Tooltip title="Add fixtures by scanning their QR labels with the camera, a USB scanner, or by typing the code">
          <Button size="small" startIcon={<QrIcon />} onClick={onScanQr}>
            Scan QR
          </Button>
        </Tooltip>
      )}
      <Tooltip title="Light one fixture at a time and tap where it is on the plan">
        <Button size="small" startIcon={<IdentifyIcon />} onClick={onIdentify}>
          Identify Lights
        </Button>
      </Tooltip>
      {onReadiness && (
        <Tooltip title="Can this rig be programmed? Positions, addresses, profiles, room, groups and exports, checked in one place. Reads only">
          <Button size="small" startIcon={<ReadinessIcon />} onClick={onReadiness}>
            Readiness
          </Button>
        </Tooltip>
      )}
      {onRoomScan && (
        <Tooltip
          title={
            hasRoom
              ? 'This rig has a scanned room stored. Read another scan, or remove it'
              : 'Read a phone scan of the room: walls, stage, truss. You see the suggestion before anything is stored'
          }
        >
          <Button size="small" startIcon={<RoomScanIcon />} onClick={onRoomScan}>
            Room Scan
          </Button>
        </Tooltip>
      )}
      {onEditRoom && hasRoom && (
        <Tooltip title="Rename, move or delete what the room scan found: a stage, a riser, a truss. No fixture moves with it">
          <Button size="small" startIcon={<EditRoomIcon />} onClick={onEditRoom}>
            Edit Room
          </Button>
        </Tooltip>
      )}
      <Button size="small" variant="contained" startIcon={<SaveIcon />} onClick={onSave}>
        Save
      </Button>
    </Box>
  );
}
