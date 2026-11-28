import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Typography,
} from '@mui/material';
import {
  Block as UnavailableIcon,
  CheckCircle as DoneIcon,
  RadioButtonUnchecked as TodoIcon,
  SkipNext as SkippedIcon,
  Warning as WarnIcon,
} from '@mui/icons-material';
import { readinessApi } from '../../services/api';
import { focusPresetsApi } from '../../services/focusPresetsApi';
import { useHealthStore } from '../../stores/healthStore';
import { readAudioHealth, readDmxHealth } from '../../utils/showHealth';
import {
  ACTION_LABELS,
  buildVenueSetupSteps,
  loadSkipped,
  saveSkipped,
  summarizeVenueSetup,
  toggleSkipped,
} from '../../utils/venueSetupChecklist';
import type {
  KeyValueStore,
  SetupRig,
  VenueActionKey,
  VenueSetupInput,
  VenueStepKey,
  VenueStepStatus,
} from '../../utils/venueSetupChecklist';
import AudioDeviceChooser from '../common/AudioDeviceChooser';
import ConsoleExportSection from '../rig/ConsoleExportSection';
import FocusPresetsPanel from '../rig/FocusPresetsPanel';

// The New venue setup checklist (docs/VENUE_SETUP.md): nine steps from an empty
// box to a rig that can be demoed and handed to a console. Every status is read
// from what the box already reports; the panel itself only reads. Each button
// opens a dialog or page that already exists. Nothing here sends DMX.

export type VenueActionHandlers = Partial<Record<VenueActionKey, () => void>>;

export interface VenueSetupChecklistProps {
  open: boolean;
  onClose: () => void;
  /** The rig being set up, or null on a page with no rig open. */
  rig: SetupRig | null;
  conflictCount?: number | null;
  stagePlot?: { present: boolean; calibrated: boolean } | null;
  /** What the host page can open. The panel adds the ones it can open itself. */
  handlers?: VenueActionHandlers;
}

const STATUS_ICON: Record<VenueStepStatus, JSX.Element> = {
  done: <DoneIcon color="success" />,
  attention: <WarnIcon color="warning" />,
  not_started: <TodoIcon color="disabled" />,
  skipped: <SkippedIcon color="disabled" />,
  unavailable: <UnavailableIcon color="disabled" />,
};

const STATUS_TEXT: Record<VenueStepStatus, string> = {
  done: 'Done',
  attention: 'Needs attention',
  not_started: 'Not started',
  skipped: 'Skipped',
  unavailable: 'Not available yet',
};

type SubDialog = 'focus' | 'export' | 'audio' | null;

const browserStore = (): KeyValueStore | null => {
  try {
    return typeof window !== 'undefined' ? window.localStorage : null;
  } catch {
    return null;
  }
};

export default function VenueSetupChecklist({
  open,
  onClose,
  rig,
  conflictCount = null,
  stagePlot = null,
  handlers = {},
}: VenueSetupChecklistProps) {
  const navigate = useNavigate();
  const { effects, dmx, capture, box, reachable, lastAnalysisAt } = useHealthStore();
  const rigId = rig?.id ?? null;

  const [readiness, setReadiness] = useState<VenueSetupInput['readiness']>(null);
  const [focus, setFocus] = useState<VenueSetupInput['focus']>(null);
  const [loading, setLoading] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [skipped, setSkipped] = useState<Set<VenueStepKey>>(() => loadSkipped(browserStore(), rigId));
  const [sub, setSub] = useState<SubDialog>(null);

  useEffect(() => { setSkipped(loadSkipped(browserStore(), rigId)); }, [rigId]);

  // Read only while the panel is open, and again after one of its own dialogs closes.
  useEffect(() => {
    if (!open || rigId === null) {
      setReadiness(null);
      setFocus(null);
      return;
    }
    let live = true;
    setLoading(true);
    Promise.allSettled([readinessApi.get(rigId), focusPresetsApi.get(rigId)]).then(([r, f]) => {
      if (!live) return;
      setReadiness(r.status === 'fulfilled' ? r.value.counts : null);
      setFocus(f.status === 'fulfilled' ? { heads: f.value.heads, targets: f.value.targets.length } : null);
      setLoading(false);
    });
    return () => { live = false; };
  }, [open, rigId, refresh]);

  // The panel's own openers, under whatever the host passes.
  const actions = useMemo<VenueActionHandlers>(() => {
    const own: VenueActionHandlers = {
      // Only goes to the demo view: loading a demo preset onto a live rig is the demo view's call.
      openDemo: () => navigate('/visualizer'),
      newRig: () => navigate('/rigs/new/wizard'),
      importRig: () => navigate('/rigs?import=1'),
      patchSheetImport: () => navigate('/rigs?import=1'),
      audioInput: () => setSub('audio'),
    };
    if (rigId !== null) {
      own.focusPresets = () => setSub('focus');
      own.consoleExport = () => setSub('export');
      own.handoffPack = () => setSub('export');
    }
    return { ...own, ...handlers };
  }, [handlers, navigate, rigId]);

  const steps = buildVenueSetupSteps({
    rig,
    demoRunning: effects?.live_rig_demo ?? null,
    conflictCount,
    stagePlot,
    readiness,
    focus,
    audio: readAudioHealth(capture, reachable, lastAnalysisAt, Date.now(), box),
    bpm: effects?.bpm ?? null,
    output: readDmxHealth(dmx, reachable, box),
    skipped,
    available: new Set(Object.keys(actions) as VenueActionKey[]),
  });
  const summary = summarizeVenueSetup(steps);

  const run = (key: VenueActionKey) => {
    const handler = actions[key];
    if (!handler) return;
    // A page dialog goes in front of the plan, so the checklist steps aside;
    // the panel's own dialogs open over it.
    if (!['focusPresets', 'consoleExport', 'handoffPack', 'audioInput'].includes(key) || handlers[key]) onClose();
    handler();
  };

  const toggleSkip = (key: VenueStepKey) => {
    const next = toggleSkipped(skipped, key);
    setSkipped(next);
    saveSkipped(browserStore(), rigId, next);
  };

  const closeSub = () => {
    setSub(null);
    setRefresh((n) => n + 1);
  };

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth data-testid="venue-setup-checklist">
        <DialogTitle>
          New venue setup
          <Typography variant="body2" color="text.secondary">
            {rig ? `"${rig.name}": ` : ''}
            {summary.done} of {summary.total} done
            {summary.attention > 0 ? `, ${summary.attention} need attention` : ''}
            {summary.skipped > 0 ? `, ${summary.skipped} skipped` : ''}.
            {summary.next ? ` Next: ${summary.next.number} ${summary.next.title}.` : ''}
          </Typography>
        </DialogTitle>
        {loading && <LinearProgress />}
        <DialogContent dividers>
          <Box component="div" sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {steps.map((step) => (
              <Box
                component="div"
                key={step.key}
                data-testid={`venue-step-${step.key}`}
                data-status={step.status}
                sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5 }}
              >
                <Box component="div" sx={{ pt: 0.25 }}>{STATUS_ICON[step.status]}</Box>
                <Box component="div" sx={{ flexGrow: 1, minWidth: 0 }}>
                  <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Typography variant="subtitle1" fontWeight={700}>
                      {step.number}. {step.title}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">{STATUS_TEXT[step.status]}</Typography>
                  </Box>
                  <Typography variant="body2" color="text.secondary">{step.detail}</Typography>
                  <Box component="div" sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 1 }}>
                    {step.actions.map((key) => (
                      <Button
                        key={key}
                        size="small"
                        variant={summary.next?.key === step.key ? 'contained' : 'outlined'}
                        onClick={() => run(key)}
                      >
                        {ACTION_LABELS[key]}
                      </Button>
                    ))}
                    {step.missing.map((key) => (
                      <Chip
                        key={key}
                        size="small"
                        variant="outlined"
                        label={`${ACTION_LABELS[key]}: not available yet`}
                        title="This build has no screen for this yet"
                      />
                    ))}
                    {step.status !== 'done' && (
                      <Button size="small" color="inherit" onClick={() => toggleSkip(step.key)}>
                        {step.status === 'skipped' ? 'Unskip' : 'Skip'}
                      </Button>
                    )}
                  </Box>
                </Box>
              </Box>
            ))}
          </Box>
        </DialogContent>
        <DialogActions>
          {rigId !== null && <Button onClick={() => setRefresh((n) => n + 1)}>Check again</Button>}
          <Button onClick={onClose}>Close</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={sub === 'focus'} onClose={closeSub} maxWidth="md" fullWidth>
        <DialogTitle>Focus presets</DialogTitle>
        <DialogContent>{sub === 'focus' && rigId !== null && <FocusPresetsPanel rigId={rigId} />}</DialogContent>
        <DialogActions><Button onClick={closeSub}>Close</Button></DialogActions>
      </Dialog>

      <Dialog open={sub === 'export'} onClose={closeSub} maxWidth="sm" fullWidth>
        <DialogTitle>Export to a console</DialogTitle>
        <DialogContent>{sub === 'export' && rigId !== null && <ConsoleExportSection target={{ rigId }} />}</DialogContent>
        <DialogActions><Button onClick={closeSub}>Close</Button></DialogActions>
      </Dialog>

      <Dialog open={sub === 'audio'} onClose={closeSub} maxWidth="sm" fullWidth>
        <DialogTitle>Audio input</DialogTitle>
        <DialogContent>{sub === 'audio' && <AudioDeviceChooser />}</DialogContent>
        <DialogActions><Button onClick={closeSub}>Close</Button></DialogActions>
      </Dialog>
    </>
  );
}

/** The checklist's view of a rig the API returned. */
export function setupRigOf(rig: {
  id: number;
  name: string;
  fixtures: { universe?: number | null; dmx_address?: number | null; is_active?: boolean; tags?: string[] | null }[];
  room_shell?: { source?: string } | null;
}): SetupRig {
  return {
    id: rig.id,
    name: rig.name,
    fixtures: rig.fixtures,
    hasScannedRoom: rig.room_shell?.source === 'scan',
  };
}
