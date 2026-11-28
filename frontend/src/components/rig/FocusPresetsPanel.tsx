/**
 * "Focus presets" for a rig (docs/FOCUS_PRESETS.md, "In the app"), under the
 * console export and the handoff pack: every point the room gives to aim at,
 * how many moving heads reach it and which cannot and why, custom points added
 * and removed, and the table as the handoff pack's CSV.
 *
 * Reads only, apart from the custom targets list: nothing here moves a light
 * or sends DMX. A database rig only; a demo preset has no room to aim in.
 */
import { useState } from 'react';
import type { FormEvent } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  IconButton,
  LinearProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TableSortLabel,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { Add as AddIcon, Delete as DeleteIcon, Download as DownloadIcon } from '@mui/icons-material';
import axios from 'axios';
import { focusPresetsApi } from '../../services/focusPresetsApi';
import { saveBlob } from '../../utils/download';
import {
  EMPTY_DRAFT, aimBits, checkDraft, degreesText, dmxText, reachText, sortAims, whereText,
} from '../../utils/focusPresets';
import type { DraftErrors, FocusTarget, TargetDraft } from '../../utils/focusPresets';
import useFocusPresets from './useFocusPresets';
import { useFocusPreviewStore } from '../../stores/focusPreviewStore';

type Note = { severity: 'success' | 'error' | 'info'; text: string };

/** Preview in the 3D view: offered while a 3D view shows this rig. */
interface PreviewControl {
  canPreview: boolean;
  previewing: boolean;
  onPreview: (target: FocusTarget) => void;
  onStop: () => void;
}

/** Every head against one target: fixture, pan and tilt in degrees, and DMX, sortable by fixture. */
function HeadTable({ target }: { target: FocusTarget }) {
  const [direction, setDirection] = useState<'asc' | 'desc'>('asc');
  const rows = sortAims(target.aims, direction);
  return (
    <Table size="small" data-testid={`focus-heads-${target.key}`} aria-label={`Each head against ${target.name}`}>
      <TableHead>
        <TableRow>
          <TableCell sortDirection={direction}>
            <TableSortLabel
              active
              direction={direction}
              onClick={() => setDirection((d) => (d === 'asc' ? 'desc' : 'asc'))}
            >
              Fixture
            </TableSortLabel>
          </TableCell>
          <TableCell align="right">Pan</TableCell>
          <TableCell align="right">Tilt</TableCell>
          <TableCell align="right">Pan DMX</TableCell>
          <TableCell align="right">Tilt DMX</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.map((aim) => (
          <TableRow key={`${aim.fixture_id}-${aim.rigFixtureId ?? aim.name}`} data-testid="focus-head-row">
            <TableCell>
              {aim.fixture_id}. {aim.name}
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                {aim.mount}, {aimBits(aim)}-bit{aim.reachable ? '' : `. Cannot reach: ${aim.reason}`}
              </Typography>
            </TableCell>
            <TableCell align="right">{degreesText(aim.reachable ? aim.pan_deg : null)}</TableCell>
            <TableCell align="right">{degreesText(aim.reachable ? aim.tilt_deg : null)}</TableCell>
            <TableCell align="right">{aim.reachable ? dmxText(aim.pan_dmx, aim.pan_fine_dmx) : '-'}</TableCell>
            <TableCell align="right">{aim.reachable ? dmxText(aim.tilt_dmx, aim.tilt_fine_dmx) : '-'}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function TargetRow({ target, heads, onRemove, busy, preview }: {
  target: FocusTarget;
  heads: number;
  onRemove: (target: FocusTarget) => void;
  busy: boolean;
  preview: PreviewControl;
}) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(false);
  const detailId = `focus-heads-panel-${target.key}`;
  const cannot = target.unreachable.length;
  const listId = `focus-unreachable-${target.key}`;
  const previewable = !target.skipped && target.aims.length > 0;
  return (
    <Box
      data-testid={`focus-target-${target.key}`}
      sx={{ py: 1, borderBottom: 1, borderColor: 'divider', '&:last-of-type': { borderBottom: 0 } }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Typography variant="body2" fontWeight="bold" sx={{ flexGrow: 1 }}>
          {target.name}
        </Typography>
        <Chip size="small" variant="outlined" label={target.custom ? 'Custom' : 'Default'} />
        {previewable && (preview.previewing ? (
          <Button size="small" color="warning" variant="contained" onClick={preview.onStop}>
            Stop preview
          </Button>
        ) : (
          <Tooltip
            title={preview.canPreview
              ? 'Aim the heads at it in the 3D view. Nothing is sent to the lights.'
              : "Open this rig's 3D view to preview a preset there."}
          >
            <span>
              <Button
                size="small"
                variant="outlined"
                aria-label={`Preview ${target.name}`}
                disabled={!preview.canPreview}
                onClick={() => preview.onPreview(target)}
              >
                Preview
              </Button>
            </span>
          </Tooltip>
        ))}
        {target.custom && target.customId !== null && (
          <Tooltip title="Remove this target">
            <span>
              <IconButton
                size="small"
                aria-label={`Remove ${target.name}`}
                disabled={busy}
                onClick={() => onRemove(target)}
              >
                <DeleteIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        )}
      </Box>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
        {whereText(target)}
      </Typography>
      {target.skipped ? (
        <Typography variant="caption" color="warning.main" sx={{ display: 'block' }} data-testid="focus-target-skipped">
          Skipped: {target.skipped}
        </Typography>
      ) : (
        <Typography variant="caption" sx={{ display: 'block' }} data-testid="focus-target-reach">
          {reachText(target, heads)}
        </Typography>
      )}
      {cannot > 0 && (
        <>
          <Button
            size="small"
            sx={{ px: 0, minWidth: 0, textTransform: 'none' }}
            aria-expanded={open}
            aria-controls={listId}
            onClick={() => setOpen((o) => !o)}
          >
            {open ? 'Hide' : 'Show'} the {cannot === 1 ? 'one' : cannot} that cannot
          </Button>
          <Collapse in={open} unmountOnExit>
            <Box component="ul" id={listId} sx={{ m: 0, pl: 2.5 }}>
              {target.unreachable.map((item) => (
                <Typography component="li" variant="caption" key={item.fixture_id} sx={{ display: 'list-item' }}>
                  {item.fixture_id}. {item.name}: {item.reason}
                </Typography>
              ))}
            </Box>
          </Collapse>
        </>
      )}
      {previewable && (
        <>
          <Button
            size="small"
            sx={{ px: 0, ml: cannot > 0 ? 2 : 0, minWidth: 0, textTransform: 'none' }}
            aria-expanded={detail}
            aria-controls={detailId}
            onClick={() => setDetail((d) => !d)}
          >
            {detail ? 'Hide' : 'Show'} pan, tilt and DMX for each head
          </Button>
          <Collapse in={detail} unmountOnExit>
            <Box id={detailId} sx={{ overflowX: 'auto' }}>
              <HeadTable target={target} />
            </Box>
          </Collapse>
        </>
      )}
    </Box>
  );
}

export default function FocusPresetsPanel({ rigId }: { rigId: number }) {
  const focus = useFocusPresets(rigId);
  const [draft, setDraft] = useState<TargetDraft>(EMPTY_DRAFT);
  const [errors, setErrors] = useState<DraftErrors>({});
  const [busy, setBusy] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [note, setNote] = useState<Note | null>(null);
  const [confirm, setConfirm] = useState<FocusTarget | null>(null);
  const { table, status } = focus;
  const viewRigId = useFocusPreviewStore((s) => s.viewRigId);
  const previewKey = useFocusPreviewStore((s) => (s.preview?.rigId === rigId ? s.preview.key : null));
  const startPreview = useFocusPreviewStore((s) => s.start);
  const stopPreview = useFocusPreviewStore((s) => s.stop);
  const canPreview = viewRigId === rigId;
  const previewed = previewKey !== null ? table?.targets.find((t) => t.key === previewKey) ?? null : null;

  const edit = (field: keyof TargetDraft) => (event: { target: { value: string } }) => {
    const value = event.target.value;
    setDraft((d) => ({ ...d, [field]: value }));
    setErrors((e) => ({ ...e, [field]: undefined, form: undefined }));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setNote(null);
    const check = checkDraft(draft, table?.customCount ?? 0);
    if (!check.ok) {
      setErrors(check.errors);
      return;
    }
    setErrors({});
    setBusy(true);
    const refused = await focus.add(check.target);
    setBusy(false);
    if (refused) {
      setErrors({ form: refused });
      return;
    }
    setDraft(EMPTY_DRAFT);
    setNote({ severity: 'success', text: `${check.target.name} added.` });
  };

  const remove = async (target: FocusTarget) => {
    setConfirm(null);
    if (target.customId === null) return;
    setNote(null);
    setBusy(true);
    const refused = await focus.remove(target.customId);
    setBusy(false);
    setNote(refused ? { severity: 'error', text: refused } : { severity: 'success', text: `${target.name} removed.` });
  };

  const downloadCsv = async () => {
    setDownloading(true);
    setNote(null);
    try {
      const file = await focusPresetsApi.csv(rigId);
      saveBlob(file.blob, file.filename);
      setNote({ severity: 'success', text: `${file.filename} downloaded.` });
    } catch (err) {
      const status404 = axios.isAxiosError(err) && err.response?.status === 404;
      setNote({
        severity: 'error',
        text: status404 ? 'This rig is no longer there.' : 'The focus presets CSV did not download. Try again.',
      });
    } finally {
      setDownloading(false);
    }
  };

  const fieldProps = (field: keyof TargetDraft) => ({
    size: 'small' as const,
    value: draft[field],
    onChange: edit(field),
    error: !!errors[field],
    helperText: errors[field] ?? ' ',
    disabled: busy,
  });

  return (
    <Box data-testid="focus-presets">
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 0.5 }}>
        <Typography variant="subtitle2" sx={{ flexGrow: 1 }}>
          Focus presets
        </Typography>
        <Button
          size="small"
          variant="outlined"
          startIcon={downloading ? <CircularProgress size={14} /> : <DownloadIcon />}
          disabled={downloading}
          onClick={() => { void downloadCsv(); }}
        >
          Download CSV
        </Button>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Pan and tilt for each moving head, worked out from where it is in the rig. Nothing here moves a light.
        Touch every preset up in the room.
      </Typography>

      {note && (
        <Alert severity={note.severity} data-testid="focus-presets-note" sx={{ mb: 1 }} onClose={() => setNote(null)}>
          {note.text}
        </Alert>
      )}

      {previewKey !== null && (
        <Alert
          severity="info"
          data-testid="focus-preview-active"
          sx={{ mb: 1 }}
          action={<Button color="inherit" size="small" onClick={stopPreview}>Stop preview</Button>}
        >
          Previewing {previewed?.name ?? 'a target'} in the 3D view. Nothing is sent to the lights.
        </Alert>
      )}

      {status === 'loading' && (
        <Box data-testid="focus-presets-loading" sx={{ mb: 1 }}>
          <Typography variant="body2">Reading the focus presets...</Typography>
          <LinearProgress sx={{ mt: 0.5 }} />
        </Box>
      )}

      {status === 'error' && (
        <Alert
          severity="error"
          data-testid="focus-presets-error"
          sx={{ mb: 1 }}
          action={<Button color="inherit" size="small" onClick={focus.reload}>Try again</Button>}
        >
          {focus.error}
        </Alert>
      )}

      {table && (
        <>
          {table.heads === 0 && (
            <Alert severity="info" data-testid="focus-presets-empty" sx={{ mb: 1 }}>
              This rig has no moving heads with a position, so there is nothing to aim. The targets stay here for
              when it has some.
            </Alert>
          )}
          {table.leftOut.length > 0 && (
            <Alert severity="info" data-testid="focus-presets-left-out" sx={{ mb: 1 }}>
              Left out of every preset: {table.leftOut.map((item) => `${item.name} (${item.reason})`).join(', ')}.
            </Alert>
          )}
          <Box data-testid="focus-presets-list" sx={{ mb: 1.5 }}>
            {table.targets.map((target) => (
              <TargetRow
                key={target.key}
                target={target}
                heads={table.heads}
                onRemove={setConfirm}
                busy={busy}
                preview={{
                  canPreview,
                  previewing: previewKey === target.key,
                  onPreview: (t) => startPreview(rigId, t.key),
                  onStop: stopPreview,
                }}
              />
            ))}
          </Box>

          <Box component="form" noValidate onSubmit={(event: FormEvent) => { void submit(event); }} aria-label="Add a focus target">
            <Typography variant="body2" fontWeight="bold" gutterBottom>
              Add a target
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
              Metres on the rig's axes: x across, y up from the floor, z from upstage (minus) to the crowd (plus).
            </Typography>
            {errors.form && (
              <Alert severity="error" data-testid="focus-target-form-error" sx={{ mb: 1 }}>
                {errors.form}
              </Alert>
            )}
            <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', rowGap: 1 }}>
              <TextField label="Name" {...fieldProps('name')} sx={{ minWidth: 160, flexGrow: 1 }} />
              <TextField label="x (m)" inputProps={{ inputMode: 'decimal' }} {...fieldProps('x')} sx={{ width: 110 }} />
              <TextField label="y (m)" inputProps={{ inputMode: 'decimal' }} {...fieldProps('y')} sx={{ width: 110 }} />
              <TextField label="z (m)" inputProps={{ inputMode: 'decimal' }} {...fieldProps('z')} sx={{ width: 110 }} />
              <Box>
                <Button
                  type="submit"
                  variant="outlined"
                  startIcon={busy ? <CircularProgress size={14} /> : <AddIcon />}
                  disabled={busy}
                  sx={{ mt: 0.25 }}
                >
                  Add target
                </Button>
              </Box>
            </Stack>
          </Box>
        </>
      )}

      <Dialog open={confirm !== null} onClose={() => setConfirm(null)}>
        <DialogTitle>Remove {confirm?.name ?? 'this target'}?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Its preset goes from the next grandMA2 script and handoff pack, and the presets after it move up one.
            Nothing else in the rig changes.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirm(null)}>Keep it</Button>
          <Button
            color="error"
            data-testid="focus-target-remove-confirm"
            onClick={() => { if (confirm) void remove(confirm); }}
          >
            Remove
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
