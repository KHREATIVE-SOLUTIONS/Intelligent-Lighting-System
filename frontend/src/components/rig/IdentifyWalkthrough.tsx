import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  List,
  ListItem,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material';
import {
  FlashOn as FlashIcon,
  HelpOutline as CannotSeeIcon,
  CheckCircle as DoneIcon,
  PlaceOutlined as PlaceIcon,
  WarningAmber as WarningIcon,
} from '@mui/icons-material';
import { identifyApi, rigsApi } from '../../services/api';
import type { IdentifySession } from '../../services/api';

interface IdentifyWalkthroughProps {
  rigId: number;
  open: boolean;
  onClose: () => void;
  /** Stage size in metres. Fetched from the rig when not supplied. */
  stageWidth?: number;
  stageDepth?: number;
  /** Fires once the walkthrough finishes, so the caller can reload its fixtures. */
  onFinished?: (summary: IdentifySession) => void;
}

type Phase = 'intro' | 'working' | 'step' | 'done';

interface PlacedMark {
  label: string;
  x: number;
  z: number;
}

const PLAN_PADDING = 1;
const HEARTBEAT_MS = 8000;

const messageOf = (error: unknown, fallback: string): string => {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' && detail ? detail : fallback;
};

const isMissing = (error: unknown): boolean =>
  (error as { response?: { status?: number } })?.response?.status === 404;

export default function IdentifyWalkthrough({
  rigId,
  open,
  onClose,
  stageWidth,
  stageDepth,
  onFinished,
}: IdentifyWalkthroughProps) {
  const [phase, setPhase] = useState<Phase>('intro');
  const [session, setSession] = useState<IdentifySession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [placed, setPlaced] = useState<PlacedMark[]>([]);
  // A double tap on a touch plan is one gesture that fires two clicks. Without
  // this the second one answers the light the first just moved on to, and that
  // light is never lit, never asked about and never recorded.
  const [busy, setBusy] = useState(false);
  const [width, setWidth] = useState(stageWidth ?? 10);
  const [depth, setDepth] = useState(stageDepth ?? 8);

  const svgRef = useRef<SVGSVGElement>(null);
  // The unload handler and the cleanup effect both need the live session id
  // without re-subscribing on every state change.
  const sessionRef = useRef<IdentifySession | null>(null);
  sessionRef.current = session;
  // State does not commit before the second click of a double tap arrives, so
  // the guard has to be a ref; `busy` only drives the buttons' disabled styling.
  const busyRef = useRef(false);

  const viewWidth = width + PLAN_PADDING * 2;
  const viewDepth = depth + PLAN_PADDING * 2;

  useEffect(() => {
    if (stageWidth) setWidth(stageWidth);
    if (stageDepth) setDepth(stageDepth);
  }, [stageWidth, stageDepth]);

  useEffect(() => {
    if (!open || stageWidth || stageDepth) return;
    let cancelled = false;
    rigsApi
      .get(rigId)
      .then((rig) => {
        if (cancelled) return;
        if (rig.stage_width) setWidth(rig.stage_width);
        if (rig.stage_depth) setDepth(rig.stage_depth);
      })
      .catch(() => {
        // Falls back to the default stage size; the walkthrough still works.
      });
    return () => {
      cancelled = true;
    };
  }, [open, rigId, stageWidth, stageDepth]);

  const applyState = useCallback(
    (next: IdentifySession) => {
      setSession(next);
      setWidth(next.stage_width || width);
      setDepth(next.stage_depth || depth);
      if (next.complete) {
        setPhase('done');
        onFinished?.(next);
      } else {
        setPhase('step');
      }
    },
    [depth, onFinished, width]
  );

  const handleFailure = useCallback((err: unknown, fallback: string) => {
    if (isMissing(err)) {
      setSession(null);
      setPhase('intro');
      setError('That walkthrough stopped because the page went quiet. Start it again.');
      return;
    }
    setError(messageOf(err, fallback));
  }, []);

  // Keeps the session alive. Silence releases the fixture and hands the room
  // back to the show, so the browser has to keep saying it is still here.
  useEffect(() => {
    if (phase !== 'step' || !session) return;
    const timer = window.setInterval(() => {
      const active = sessionRef.current;
      if (!active) return;
      identifyApi
        .heartbeat(rigId, active.session_id)
        .then((next) => setSession(next))
        .catch((err) => handleFailure(err, 'Lost contact with the lighting box.'));
    }, HEARTBEAT_MS);
    return () => window.clearInterval(timer);
  }, [phase, session?.session_id, rigId, handleFailure]);

  // A closed tab must not leave a light on.
  useEffect(() => {
    const release = () => {
      const active = sessionRef.current;
      if (active) identifyApi.endOnUnload(rigId, active.session_id);
    };
    window.addEventListener('pagehide', release);
    return () => window.removeEventListener('pagehide', release);
  }, [rigId]);

  // Nor must a caller that simply hides the dialog, or unmounts the whole page.
  useEffect(() => {
    if (open) return;
    const active = sessionRef.current;
    if (!active) return;
    sessionRef.current = null;
    setSession(null);
    setPhase('intro');
    identifyApi.end(rigId, active.session_id).catch(() => undefined);
  }, [open, rigId]);

  useEffect(
    () => () => {
      const active = sessionRef.current;
      if (active) identifyApi.endOnUnload(rigId, active.session_id);
    },
    [rigId]
  );

  const finish = useCallback(() => {
    const active = sessionRef.current;
    sessionRef.current = null;
    setSession(null);
    setPlaced([]);
    setPhase('intro');
    setError(null);
    if (active) {
      identifyApi.end(rigId, active.session_id).catch(() => {
        // The server watchdog releases it either way.
      });
    }
    onClose();
  }, [onClose, rigId]);

  const start = async () => {
    setError(null);
    setPlaced([]);
    setPhase('working');
    try {
      applyState(await identifyApi.start(rigId));
    } catch (err) {
      setPhase('intro');
      setError(messageOf(err, 'Could not start the walkthrough.'));
    }
  };

  const runStep = async (action: () => Promise<IdentifySession>, fallback: string) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      applyState(await action());
    } catch (err) {
      handleFailure(err, fallback);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const step = session?.current ?? null;

  const handlePlanClick = (event: React.MouseEvent<SVGSVGElement>) => {
    if (!session || !step || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const svgX = ((event.clientX - rect.left) / rect.width) * viewWidth - PLAN_PADDING;
    const svgZ = ((event.clientY - rect.top) / rect.height) * viewDepth - PLAN_PADDING;
    // Contract §1: origin at stage centre, +z downstage toward the audience,
    // which is the bottom of this plan.
    const x = Math.round((svgX - width / 2) * 10) / 10;
    const z = Math.round((svgZ - depth / 2) * 10) / 10;
    if (busyRef.current) return;
    setPlaced((marks) => [...marks, { label: step.label, x, z }]);
    void runStep(
      () => identifyApi.recordPosition(rigId, session.session_id, {
        position_x: x,
        position_z: z,
        fixture_id: step.fixture_id,
      }),
      'Could not save that position.'
    );
  };

  const renderPlan = () => {
    const lines = [];
    for (let x = 0; x <= width + 0.001; x += 1) {
      lines.push(
        <line
          key={`v${x}`}
          x1={x + PLAN_PADDING}
          y1={PLAN_PADDING}
          x2={x + PLAN_PADDING}
          y2={depth + PLAN_PADDING}
          stroke="#2b3a55"
          strokeWidth={0.02}
        />
      );
    }
    for (let z = 0; z <= depth + 0.001; z += 1) {
      lines.push(
        <line
          key={`h${z}`}
          x1={PLAN_PADDING}
          y1={z + PLAN_PADDING}
          x2={width + PLAN_PADDING}
          y2={z + PLAN_PADDING}
          stroke="#2b3a55"
          strokeWidth={0.02}
        />
      );
    }

    return (
      <Box sx={{ width: '100%', bgcolor: '#12121f', borderRadius: 1, overflow: 'hidden' }}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${viewWidth} ${viewDepth}`}
          width="100%"
          style={{ display: 'block', cursor: 'crosshair', touchAction: 'manipulation' }}
          onClick={handlePlanClick}
        >
          <rect
            x={PLAN_PADDING}
            y={PLAN_PADDING}
            width={width}
            height={depth}
            fill="#181a2e"
            stroke="#3d5a80"
            strokeWidth={0.05}
          />
          {lines}
          <text
            x={viewWidth / 2}
            y={PLAN_PADDING - 0.25}
            textAnchor="middle"
            fill="#8fa3bf"
            fontSize={0.35}
          >
            BACK WALL
          </text>
          <text
            x={viewWidth / 2}
            y={viewDepth - 0.25}
            textAnchor="middle"
            fill="#8fa3bf"
            fontSize={0.35}
          >
            WHERE THE AUDIENCE STANDS
          </text>

          {placed.map((mark, index) => (
            <g
              key={`${mark.label}-${index}`}
              transform={`translate(${mark.x + width / 2 + PLAN_PADDING}, ${
                mark.z + depth / 2 + PLAN_PADDING
              })`}
            >
              <circle r={0.22} fill="#4caf50" opacity={0.85} />
              <text y={0.55} textAnchor="middle" fill="#9fb8a0" fontSize={0.24}>
                {mark.label}
              </text>
            </g>
          ))}
        </svg>
      </Box>
    );
  };

  const renderIntro = () => (
    <Stack spacing={2}>
      <Typography variant="body1">
        We will turn on one light at a time. Look up, find the light that just came on, then tap
        that spot on the plan. Repeat until every light has a place.
      </Typography>
      <Typography variant="body2" color="text.secondary">
        Nothing flashes or strobes - each light simply stays on until you tell us where it is. The
        rest of the room stays dark so the one that is lit is obvious. If a light never comes on,
        tap "I can't see it" and we will make a note of it: that usually means it is unplugged or
        set to the wrong address.
      </Typography>
      {error && <Alert severity="error">{error}</Alert>}
    </Stack>
  );

  const renderStep = () => {
    if (!session || !step) return null;
    const progress = (session.step_number / Math.max(1, session.total)) * 100;

    return (
      <Stack spacing={2}>
        <Box>
          <Stack direction="row" alignItems="center" justifyContent="space-between" mb={0.5}>
            <Typography variant="subtitle1" fontWeight="bold">
              Light {session.step_number} of {session.total}
            </Typography>
            <Chip
              size="small"
              icon={<FlashIcon />}
              color={step.flashing ? 'primary' : 'default'}
              label={step.flashing ? 'On now' : 'Off - tap "Turn it on again"'}
            />
          </Stack>
          <LinearProgress variant="determinate" value={progress} />
        </Box>

        {step.can_flash ? (
          <Typography variant="h6">Which light just came on? Tap it on the plan.</Typography>
        ) : (
          <Alert severity="warning" icon={<WarningIcon />}>
            {step.blocked_reason ??
              'We cannot turn this light on from here.'}{' '}
            You can still tap where it is, or mark it as not working.
          </Alert>
        )}

        {renderPlan()}

        <Typography variant="caption" color="text.secondary">
          {step.label} - universe {step.universe}, address {step.dmx_address}
        </Typography>

        {error && <Alert severity="error">{error}</Alert>}

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <Button
            variant="outlined"
            startIcon={<FlashIcon />}
            disabled={!step.can_flash || busy}
            onClick={() =>
              runStep(
                () => identifyApi.flash(rigId, session.session_id, step.fixture_id),
                'Could not turn that light on again.'
              )
            }
          >
            Turn it on again
          </Button>
          <Button
            variant="outlined"
            color="warning"
            startIcon={<CannotSeeIcon />}
            disabled={busy}
            onClick={() =>
              runStep(
                () => identifyApi.skip(rigId, session.session_id, undefined, step.fixture_id),
                'Could not record that.'
              )
            }
          >
            I can't see it
          </Button>
          <Button
            variant="text"
            startIcon={<PlaceIcon />}
            disabled={busy}
            onClick={() =>
              runStep(
                () => identifyApi.keep(rigId, session.session_id, step.fixture_id),
                'Could not move to the next light.'
              )
            }
          >
            It is already in the right place
          </Button>
        </Stack>
      </Stack>
    );
  };

  const renderDone = () => {
    if (!session) return null;
    return (
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} alignItems="center">
          <DoneIcon color="success" />
          <Typography variant="h6">
            {session.placed} of {session.total} lights placed
          </Typography>
        </Stack>

        {session.no_response > 0 ? (
          <Alert severity="warning">
            {session.no_response} light{session.no_response === 1 ? '' : 's'} never came on. Check
            that each one has power and that its address matches the list below - it is much
            cheaper to find this now than during a show.
          </Alert>
        ) : (
          <Alert severity="success">Every light responded. Your plan matches the room.</Alert>
        )}

        {session.unresponsive.length > 0 && (
          <List dense>
            {session.unresponsive.map((entry) => (
              <ListItem key={entry.fixture_id} disableGutters>
                <ListItemText
                  primary={entry.label}
                  secondary={`Universe ${entry.universe}, address ${entry.dmx_address} - ${entry.reason}`}
                />
              </ListItem>
            ))}
          </List>
        )}

        {error && <Alert severity="error">{error}</Alert>}
      </Stack>
    );
  };

  return (
    <Dialog open={open} onClose={finish} maxWidth="sm" fullWidth>
      <DialogTitle>Find my lights</DialogTitle>
      <DialogContent dividers>
        {phase === 'working' && (
          <Stack alignItems="center" py={4}>
            <CircularProgress />
          </Stack>
        )}
        {phase === 'intro' && renderIntro()}
        {phase === 'step' && renderStep()}
        {phase === 'done' && renderDone()}
      </DialogContent>
      <DialogActions>
        <Button onClick={finish}>{phase === 'done' ? 'Close' : 'Stop'}</Button>
        {phase === 'intro' && (
          <Button variant="contained" onClick={start}>
            Start
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
