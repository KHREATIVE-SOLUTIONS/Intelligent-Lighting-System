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
import { audioApi, demoApi, readinessApi } from '../../services/api';
import { focusPresetsApi } from '../../services/focusPresetsApi';
import { useHealthStore } from '../../stores/healthStore';
import { outputVerifiablyIdle, planDemoReady, runDemoReadyPlan } from '../../utils/demoReady';
import type { DemoActionResult, DemoOutcome, DemoReadyAudio, DemoReadyPlan } from '../../utils/demoReady';
import { readAudioHealth, readDmxHealth } from '../../utils/showHealth';
import {
  ACTION_LABELS,
  buildVenueSetupSteps,
  loadSkipped,
  saveSkipped,
  summarizeVenueSetup,
  toggleSkipped,
  venueSetupProgress,
} from '../../utils/venueSetupChecklist';
import type {
  KeyValueStore,
  SetupRig,
  VenueActionKey,
  VenueSetupInput,
  VenueStepKey,
  VenueStepStatus,
} from '../../utils/venueSetupChecklist';
import AudioDeviceChooser, { readLastDevice, sortCaptureDevices } from '../common/AudioDeviceChooser';
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

/** Get demo-ready: reading the box, the plan shown, then its results as they come in. */
type DemoState =
  | { step: 'planning' }
  | { step: 'plan'; plan: DemoReadyPlan }
  | { step: 'running' | 'done'; plan: DemoReadyPlan; results: DemoActionResult[] };

const OUTCOME_TEXT: Record<DemoOutcome, string> = { done: 'Done', skipped: 'Skipped', failed: 'Failed' };

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

  const [demo, setDemo] = useState<DemoState | null>(null);

  // Get demo-ready, step one: read the box (readiness and audio, nothing
  // written) and show the plan. Nothing runs until the operator confirms.
  const planDemo = async () => {
    setDemo({ step: 'planning' });
    const [report, status, devices] = await Promise.allSettled([
      rigId !== null ? readinessApi.get(rigId) : Promise.resolve(null),
      audioApi.getCaptureStatus(),
      audioApi.getCaptureDevices(),
    ]);
    let audio: DemoReadyAudio | null = null;
    if (status.status === 'fulfilled' && devices.status === 'fulfilled') {
      audio = {
        // A feed sent to the box counts as heard, as the status bar reads it.
        running: !!status.value.running || box?.services?.audio_input === 'live',
        ...sortCaptureDevices(devices.value),
        remembered: { name: status.value.remembered_device, hostapi: status.value.remembered_hostapi },
        browserName: readLastDevice(),
      };
    }
    const plan = planDemoReady({
      rig,
      demoRunning: effects?.live_rig_demo ?? null,
      outputIdle: outputVerifiablyIdle(dmx, reachable, box),
      readiness: report.status === 'fulfilled' ? report.value : null,
      audio,
    });
    // Closed while reading: stay closed.
    setDemo((current) => (current?.step === 'planning' ? { step: 'plan', plan } : current));
  };

  // Step two, on confirm: each action in turn, a line for each, then read the statuses again.
  const runDemo = async (plan: DemoReadyPlan) => {
    const results: DemoActionResult[] = [];
    setDemo({ step: 'running', plan, results });
    await runDemoReadyPlan(
      plan,
      rigId,
      {
        applyDemoPreset: demoApi.applyPreset,
        readReadiness: readinessApi.get,
        makeGroups: readinessApi.autoGroups,
        startCapture: audioApi.startCapture,
        readFocus: focusPresetsApi.get,
      },
      (result) => {
        results.push(result);
        setDemo({ step: 'running', plan, results: [...results] });
      },
    );
    setDemo({ step: 'done', plan, results: [...results] });
    setRefresh((n) => n + 1);
  };

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth data-testid="venue-setup-checklist">
        <DialogTitle>
          New venue setup
          <Typography variant="body2" color="text.secondary" data-testid="venue-setup-progress">
            {rig ? `"${rig.name}": ` : ''}
            {venueSetupProgress(summary)}
          </Typography>
          <Typography variant="body2" color="text.secondary" data-testid="venue-setup-next">
            {summary.next
              ? `Next: ${summary.next.number}. ${summary.next.title}`
              : 'Nothing left to open: every step is done, skipped or not available yet.'}
          </Typography>
        </DialogTitle>
        {loading && <LinearProgress />}
        <DialogContent dividers>
          <Box component="div" sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {steps.map((step) => {
              const isNext = summary.next?.key === step.key;
              return (
              <Box
                component="div"
                key={step.key}
                data-testid={`venue-step-${step.key}`}
                data-status={step.status}
                data-next={isNext ? 'true' : undefined}
                sx={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 1.5,
                  ...(isNext ? { borderLeft: 3, borderColor: 'primary.main', pl: 1, ml: -1.375 } : {}),
                }}
              >
                <Box component="div" sx={{ pt: 0.25 }}>{STATUS_ICON[step.status]}</Box>
                <Box component="div" sx={{ flexGrow: 1, minWidth: 0 }}>
                  <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Typography variant="subtitle1" fontWeight={700}>
                      {step.number}. {step.title}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">{STATUS_TEXT[step.status]}</Typography>
                    {isNext && <Chip size="small" color="primary" label="Next" data-testid="venue-setup-next-chip" />}
                  </Box>
                  <Typography variant="body2" color="text.secondary">{step.detail}</Typography>
                  <Box component="div" sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 1 }}>
                    {step.actions.map((key) => (
                      <Button
                        key={key}
                        size="small"
                        variant={isNext ? 'contained' : 'outlined'}
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
              );
            })}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button
            variant="contained"
            data-testid="venue-setup-demo-ready"
            disabled={demo !== null}
            onClick={() => { void planDemo(); }}
            sx={{ mr: 'auto' }}
          >
            Get demo-ready
          </Button>
          {rigId !== null && <Button onClick={() => setRefresh((n) => n + 1)}>Check again</Button>}
          <Button onClick={onClose}>Close</Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={demo !== null}
        onClose={() => { if (demo?.step !== 'running') setDemo(null); }}
        maxWidth="sm"
        fullWidth
        data-testid="demo-ready-dialog"
      >
        <DialogTitle>Get demo-ready</DialogTitle>
        {(demo?.step === 'planning' || demo?.step === 'running') && <LinearProgress />}
        <DialogContent dividers>
          {demo?.step === 'planning' && (
            <Typography variant="body2">Reading the readiness checks and the audio inputs. Nothing is changed.</Typography>
          )}
          {demo && demo.step !== 'planning' && (
            <Box component="div" sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              {demo.step === 'plan' ? (
                <Box component="div" data-testid="demo-ready-plan">
                  <Typography variant="subtitle2">
                    {demo.plan.actions.length > 0 ? 'It will, in this order:' : 'Nothing to do by itself: everything it could do is done.'}
                  </Typography>
                  {demo.plan.actions.map((a) => (
                    <Typography key={`${a.kind}-${a.label}`} variant="body2" data-testid={`demo-ready-action-${a.kind}`}>
                      {a.label}: {a.detail}
                    </Typography>
                  ))}
                </Box>
              ) : (
                <Box component="div" data-testid="demo-ready-results">
                  <Typography variant="subtitle2">{demo.step === 'running' ? 'Running...' : 'Finished. The checklist has been read again.'}</Typography>
                  {demo.results.map((r) => (
                    <Typography
                      key={`${r.kind}-${r.label}`}
                      variant="body2"
                      color={r.outcome === 'failed' ? 'error' : undefined}
                      data-testid={`demo-ready-result-${r.kind}`}
                      data-outcome={r.outcome}
                    >
                      {r.label}: {OUTCOME_TEXT[r.outcome]}. {r.message}
                    </Typography>
                  ))}
                </Box>
              )}
              {demo.plan.skipped.length > 0 && (
                <Box component="div" data-testid="demo-ready-skipped">
                  <Typography variant="subtitle2">Left as it is:</Typography>
                  {demo.plan.skipped.map((s) => (
                    <Typography key={s.kind} variant="body2" color="text.secondary">{s.label}: {s.detail}</Typography>
                  ))}
                </Box>
              )}
              <Box component="div" data-testid="demo-ready-manual">
                <Typography variant="subtitle2">Stays with you (never done by this button):</Typography>
                {demo.plan.manual.map((m) => (
                  <Typography key={m.key} variant="body2" color="text.secondary" data-testid={`demo-ready-manual-${m.key}`}>
                    {m.label}: {m.detail}
                  </Typography>
                ))}
              </Box>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          {demo?.step === 'plan' && (
            <>
              <Button onClick={() => setDemo(null)}>Cancel</Button>
              <Button
                variant="contained"
                data-testid="demo-ready-confirm"
                disabled={demo.plan.actions.length === 0}
                onClick={() => { void runDemo(demo.plan); }}
              >
                Do {demo.plan.actions.length === 1 ? 'it' : `these ${demo.plan.actions.length}`}
              </Button>
            </>
          )}
          {(demo?.step === 'done' || demo?.step === 'planning') && (
            <Button data-testid="demo-ready-close" onClick={() => setDemo(null)}>Close</Button>
          )}
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
