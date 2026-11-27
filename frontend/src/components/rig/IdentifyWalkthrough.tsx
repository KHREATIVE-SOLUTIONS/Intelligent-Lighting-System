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
  TextField,
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
  /**
   * How many lights sit on a generated guess (the position_unconfirmed tag).
   * Above zero, the intro offers to check just those, a row at a time.
   */
  unconfirmedCount?: number;
  /**
   * Walk exactly these lights (the Readiness panel's Locate these), a row at a
   * time as locate mode walks. Nothing is lit until Start is pressed.
   */
  fixtureIds?: number[];
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
  unconfirmedCount = 0,
  fixtureIds,
}: IdentifyWalkthroughProps) {
  const named = fixtureIds && fixtureIds.length > 0 ? fixtureIds : null;
  const [heightInput, setHeightInput] = useState('');
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

  // The height box follows the row: a new row shows its own trim.
  const rowNumber = session?.row?.number ?? null;
  const rowHeight = session?.row?.height ?? null;
  useEffect(() => {
    setHeightInput(rowHeight === null ? '' : String(rowHeight));
  }, [rowNumber, rowHeight]);

  const start = async (only?: 'unconfirmed', ids?: number[]) => {
    setError(null);
    setPlaced([]);
    setPhase('working');
    try {
      applyState(await (ids ? identifyApi.start(rigId, only, ids) : identifyApi.start(rigId, only)));
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
  const row = session?.row ?? null;

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

  const renderPlan = (tappable = true) => {
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
          style={{
            display: 'block',
            cursor: tappable ? 'crosshair' : 'default',
            touchAction: 'manipulation',
          }}
          onClick={tappable ? handlePlanClick : undefined}
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

          {/* The row being located, as the plan currently has it. */}
          {row && row.fixtures.length > 1 && (
            <line
              x1={row.fixtures[0].position_x + width / 2 + PLAN_PADDING}
              y1={row.fixtures[0].position_z + depth / 2 + PLAN_PADDING}
              x2={row.fixtures[row.fixtures.length - 1].position_x + width / 2 + PLAN_PADDING}
              y2={row.fixtures[row.fixtures.length - 1].position_z + depth / 2 + PLAN_PADDING}
              stroke="#5c7cba"
              strokeWidth={0.04}
              strokeDasharray="0.15 0.15"
              opacity={row.can_fit ? 0.9 : 0}
            />
          )}
          {row?.fixtures.map((entry) => (
            <circle
              key={`row-${entry.fixture_id}`}
              cx={entry.position_x + width / 2 + PLAN_PADDING}
              cy={entry.position_z + depth / 2 + PLAN_PADDING}
              r={0.12}
              fill={entry.unconfirmed ? '#181a2e' : '#4caf50'}
              stroke={entry.unconfirmed ? '#ffb74d' : '#4caf50'}
              strokeWidth={0.04}
            />
          ))}

          {/* Where the plan has the light that is on now. "It is where the plan
              shows it" has to have something to point at. */}
          {step && (
            <g
              transform={`translate(${step.position_x + width / 2 + PLAN_PADDING}, ${
                step.position_z + depth / 2 + PLAN_PADDING
              })`}
            >
              <circle r={0.3} fill="none" stroke="#ffd54f" strokeWidth={0.06} />
              <text y={-0.45} textAnchor="middle" fill="#ffd54f" fontSize={0.24}>
                {step.unconfirmed ? 'our guess' : 'on the plan'}
              </text>
            </g>
          )}

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
      {named && (
        <Alert severity="info" data-testid="identify-named">
          The readiness check named {named.length} light{named.length === 1 ? '' : 's'} whose
          position nobody has confirmed. Start walks just {named.length === 1 ? 'that one' : 'those'},
          a row at a time.
        </Alert>
      )}
      {!named && unconfirmedCount > 0 && (
        <Alert severity="info">
          {unconfirmedCount} light{unconfirmedCount === 1 ? ' sits' : 's sit'} where we guessed{' '}
          {unconfirmedCount === 1 ? 'it' : 'they'} would be when the patch sheet was imported. You
          can check just those: a row at a time, the two ends first, and we space the lights in
          between for you.
        </Alert>
      )}
      {error && <Alert severity="error">{error}</Alert>}
    </Stack>
  );

  const renderMirrorOffer = () => {
    if (!session?.mirror_offer) return null;
    const count = session.mirror_offer.fixtures;
    return (
      <Alert
        severity="info"
        action={
          <Stack direction="row" spacing={0.5}>
            <Button
              size="small"
              color="inherit"
              disabled={busy}
              onClick={() =>
                runStep(
                  () => identifyApi.mirror(rigId, session.session_id, true),
                  'Could not flip the plan.'
                )
              }
            >
              Flip them
            </Button>
            <Button
              size="small"
              color="inherit"
              disabled={busy}
              onClick={() =>
                runStep(
                  () => identifyApi.mirror(rigId, session.session_id, false),
                  'Could not record that.'
                )
              }
            >
              Leave them
            </Button>
          </Stack>
        }
      >
        Those two taps ran right to left, but we drew that row left to right. The sheet's left may
        be the plan's right. Flip the {count} guessed position{count === 1 ? '' : 's'} still to
        check?
      </Alert>
    );
  };

  const renderRowHeader = () => {
    if (!session || !row) return null;
    const parsed = Number(heightInput);
    const usable = heightInput.trim() !== '' && Number.isFinite(parsed) && parsed >= 0 && parsed <= 100;
    return (
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
        <Typography variant="body2" sx={{ flexGrow: 1 }}>
          Row {row.number} of {row.of}: <strong>{row.group}</strong> ({row.fixtures.length} light
          {row.fixtures.length === 1 ? '' : 's'})
        </Typography>
        <TextField
          size="small"
          type="number"
          label="Row height (m)"
          value={heightInput}
          onChange={(event) => setHeightInput(event.target.value)}
          inputProps={{ min: 0, max: 100, step: 0.1 }}
          sx={{ width: 140 }}
        />
        <Button
          size="small"
          disabled={busy || !usable || parsed === row.height}
          onClick={() =>
            runStep(
              () => identifyApi.rowHeight(rigId, session.session_id, parsed),
              'Could not save that height.'
            )
          }
        >
          Set
        </Button>
      </Stack>
    );
  };

  const renderFitOffer = () => {
    if (!session || !row) return null;
    const between = row.fixtures.length - 2;
    return (
      <Stack spacing={2}>
        {renderRowHeader()}
        {renderMirrorOffer()}
        <Typography variant="h6">
          Both ends of this row are found. Space the {between} light{between === 1 ? '' : 's'} in
          between evenly along the line joining them?
        </Typography>
        <Typography variant="body2" color="text.secondary">
          No light is on right now. If you say yes, we will then light the row one at a time so you
          can see that it runs in order. Nothing counts as checked until you have seen that.
        </Typography>
        {renderPlan(false)}
        {error && <Alert severity="error">{error}</Alert>}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <Button
            variant="contained"
            disabled={busy}
            onClick={() =>
              runStep(
                () => identifyApi.fitRow(rigId, session.session_id, true),
                'Could not space that row.'
              )
            }
          >
            Yes, space them
          </Button>
          <Button
            variant="outlined"
            disabled={busy}
            onClick={() =>
              runStep(
                () => identifyApi.fitRow(rigId, session.session_id, false),
                'Could not record that.'
              )
            }
          >
            No, I will tap each one
          </Button>
        </Stack>
      </Stack>
    );
  };

  const renderRowCheck = () => {
    if (!session || !row) return null;
    const how =
      row.direction === 'left_to_right'
        ? 'from the left of this plan to the right'
        : 'from one end of the row to the other';
    return (
      <Stack spacing={2}>
        {renderRowHeader()}
        {renderMirrorOffer()}
        <Typography variant="h6">Watch the row. Did the light move along it in order?</Typography>
        <Typography variant="body2" color="text.secondary">
          One light at a time comes on, {how}, each for about {row.step_seconds} seconds, then the
          row goes dark. If it skipped about or went the wrong way, say no and you can tap each
          light yourself.
        </Typography>
        {renderPlan(false)}
        {error && <Alert severity="error">{error}</Alert>}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <Button
            variant="contained"
            disabled={busy}
            onClick={() =>
              runStep(
                () => identifyApi.rowCheck(rigId, session.session_id, true),
                'Could not record that.'
              )
            }
          >
            Yes, it ran in order
          </Button>
          <Button
            variant="outlined"
            color="warning"
            disabled={busy}
            onClick={() =>
              runStep(
                () => identifyApi.rowCheck(rigId, session.session_id, false),
                'Could not record that.'
              )
            }
          >
            No, it did not
          </Button>
          <Button
            variant="text"
            startIcon={<FlashIcon />}
            disabled={busy}
            onClick={() =>
              runStep(
                () => identifyApi.flash(rigId, session.session_id),
                'Could not run the row again.'
              )
            }
          >
            Run it again
          </Button>
        </Stack>
      </Stack>
    );
  };

  const renderStep = () => {
    if (!session) return null;
    if (row?.stage === 'fit_offer') return renderFitOffer();
    if (row?.stage === 'check') return renderRowCheck();
    if (!step) return null;
    const progress = (session.step_number / Math.max(1, session.total)) * 100;

    return (
      <Stack spacing={2}>
        {renderRowHeader()}
        {renderMirrorOffer()}
        {row && row.stage === 'each' && row.fit_blocked_reason && (
          <Alert severity="info">{row.fit_blocked_reason}</Alert>
        )}
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
                () => identifyApi.confirm(rigId, session.session_id, step.fixture_id),
                'Could not move to the next light.'
              )
            }
          >
            It is where the plan shows it
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
            {session.placed + session.confirmed + session.fitted} of {session.total} lights located
          </Typography>
        </Stack>

        <Typography variant="body2" color="text.secondary">
          {session.placed} tapped, {session.confirmed} agreed as drawn, {session.fitted} spaced along
          a row and checked.
        </Typography>

        {session.still_unconfirmed > 0 && (
          <Alert severity="info">
            {session.still_unconfirmed} light{session.still_unconfirmed === 1 ? ' is' : 's are'}{' '}
            still on a guessed position. Run this again to check{' '}
            {session.still_unconfirmed === 1 ? 'it' : 'them'}.
          </Alert>
        )}

        {session.not_located_count > 0 && (
          <Alert severity="warning">
            {session.not_located_count} light{session.not_located_count === 1 ? ' is' : 's are'}{' '}
            switched off in the patch, so we could not turn{' '}
            {session.not_located_count === 1 ? 'it' : 'them'} on to find{' '}
            {session.not_located_count === 1 ? 'it' : 'them'}:
            <List dense disablePadding>
              {session.not_located.map((entry) => (
                <ListItem key={entry.fixture_id} disableGutters>
                  <ListItemText
                    primary={entry.label}
                    secondary={`Universe ${entry.universe}, address ${entry.dmx_address} - ${entry.reason}`}
                  />
                </ListItem>
              ))}
            </List>
          </Alert>
        )}

        {session.no_response > 0 ? (
          <Alert severity="warning">
            {session.no_response} light{session.no_response === 1 ? '' : 's'} never came on. Check
            that each one has power and that its address matches the list below - it is much
            cheaper to find this now than during a show.
          </Alert>
        ) : (
          <Alert severity="success">Every light we turned on responded.</Alert>
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
        {phase === 'intro' && (named || unconfirmedCount > 0) && (
          <Button onClick={() => void start()}>Go through every light</Button>
        )}
        {phase === 'intro' && named && (
          <Button variant="contained" onClick={() => void start('unconfirmed', named)}>
            Check these {named.length}
          </Button>
        )}
        {phase === 'intro' && !named && (
          <Button
            variant="contained"
            onClick={() => void start(unconfirmedCount > 0 ? 'unconfirmed' : undefined)}
          >
            {unconfirmedCount > 0 ? `Check the ${unconfirmedCount} guessed` : 'Start'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
