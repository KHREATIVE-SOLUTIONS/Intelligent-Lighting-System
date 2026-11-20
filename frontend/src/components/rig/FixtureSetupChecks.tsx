import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import {
  CheckCircle as PassedIcon,
  ErrorOutline as FailedIcon,
  Stop as StopIcon,
} from '@mui/icons-material';
import { setupChecksApi } from '../../services/api';
import {
  CHECK_COPY,
  lookLabel,
  type SetupCheck,
  type SetupCheckActive,
  type SetupCheckFixture,
  type SetupCheckName,
} from '../../utils/fixtureSetupChecks';

/** Well inside the box's own silence timeout, so one lost beat does not drop the light. */
const HEARTBEAT_MS = 8000;

interface FixtureSetupChecksProps {
  rigId: number;
  /** The fixture being checked; the dialog is open while this is set. */
  fixture: SetupCheckFixture | null;
  /** Rig-wide reason a test light would stay dark (blackout, grand master). */
  rigBlockedReason?: string | null;
  onClose: () => void;
  /** The fixture's record after an answer was saved. */
  onRecorded: (fixture: SetupCheckFixture) => void;
}

const errorText = (err: unknown, fallback: string): string => {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' && detail ? detail : fallback;
};

/**
 * The patch screen's "is this one right?" for a single fixture.
 *
 * Each button holds a steady look on the fixture with the rest of the room
 * dark, and the operator says whether it did what it should. The light is
 * never blinked. Closing the dialog, leaving the page or going quiet all put
 * the fixture dark and the show back.
 */
export default function FixtureSetupChecks({
  rigId,
  fixture,
  rigBlockedReason = null,
  onClose,
  onRecorded,
}: FixtureSetupChecksProps) {
  const [active, setActive] = useState<SetupCheckActive | null>(null);
  const [blocked, setBlocked] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // What the unmount and unload handlers need, without re-subscribing them on
  // every state change.
  const holdingRef = useRef(false);
  holdingRef.current = active !== null;

  const fixtureId = fixture?.fixture_id ?? null;

  useEffect(() => {
    setActive(null);
    setError(null);
    setNotice(null);
    setBlocked(null);
  }, [fixtureId]);

  // Keep the held light alive while the dialog is open, and notice when the
  // box has let go of it by itself.
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(() => {
      setupChecksApi
        .heartbeat(rigId)
        .then((state) => {
          if (!state.active) {
            setActive(null);
            setNotice('The light was switched off and the show put back. Press a button to light it again.');
          } else {
            setBlocked(state.active.output_blocked_reason ?? state.output_blocked_reason);
          }
        })
        .catch(() => undefined);
    }, HEARTBEAT_MS);
    return () => clearInterval(timer);
  }, [active, rigId]);

  // A tab that goes away must not leave a fixture lit and the show parked.
  useEffect(() => {
    const onPageHide = () => {
      if (holdingRef.current) setupChecksApi.releaseOnUnload(rigId);
    };
    window.addEventListener('pagehide', onPageHide);
    return () => {
      window.removeEventListener('pagehide', onPageHide);
      if (holdingRef.current) setupChecksApi.releaseOnUnload(rigId);
    };
  }, [rigId]);

  const release = useCallback(async () => {
    setActive(null);
    try {
      await setupChecksApi.release(rigId);
    } catch {
      // The box times the hold out on its own; nothing useful to tell the operator.
    }
  }, [rigId]);

  const handleClose = () => {
    if (holdingRef.current) void release();
    onClose();
  };

  const showLook = async (check: SetupCheckName, look: string) => {
    if (!fixture) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const state = await setupChecksApi.show(rigId, fixture.fixture_id, check, look);
      setActive(state.active);
      setBlocked(state.active?.output_blocked_reason ?? state.output_blocked_reason);
    } catch (err) {
      setActive(null);
      setError(errorText(err, 'Could not light this fixture. Check the connection to the box.'));
    } finally {
      setBusy(false);
    }
  };

  const record = async (check: SetupCheckName, passed: boolean | null) => {
    if (!fixture) return;
    setError(null);
    try {
      onRecorded(await setupChecksApi.recordResult(rigId, fixture.fixture_id, check, passed));
    } catch (err) {
      setError(errorText(err, 'Could not save that answer.'));
    }
  };

  const renderCheck = (check: SetupCheck) => {
    const copy = CHECK_COPY[check.check];
    const holdingThis = active?.check === check.check;
    return (
      <Box key={check.check} data-testid={`setup-check-${check.check}`}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
          <Typography variant="subtitle2">{copy.title}</Typography>
          {check.result === 'ok' && <Chip size="small" color="success" icon={<PassedIcon />} label="Passed" />}
          {check.result === 'fail' && <Chip size="small" color="error" icon={<FailedIcon />} label="Failed" />}
        </Stack>

        {!check.available ? (
          <Typography variant="body2" color="text.secondary">
            {check.reason}
          </Typography>
        ) : (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {copy.question}
              {check.check === 'flash' && fixture?.has_shutter && copy.shutterNote
                ? ` ${copy.shutterNote}`
                : ''}
            </Typography>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <ToggleButtonGroup
                size="small"
                exclusive
                value={holdingThis ? active?.look : null}
                // Pressing the look that is already up leaves it up: stopping
                // is its own button, so nothing here can blink the light.
                onChange={(_, look: string | null) => {
                  if (look) void showLook(check.check, look);
                }}
                disabled={busy}
                aria-label={`${copy.title} looks`}
              >
                {check.looks.map((look) => (
                  <ToggleButton key={look} value={look} sx={{ textTransform: 'none', px: 1.5 }}>
                    {lookLabel(look)}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
              <Box sx={{ flexGrow: 1 }} />
              <Button
                size="small"
                color="success"
                variant={check.result === 'ok' ? 'contained' : 'outlined'}
                onClick={() => void record(check.check, check.result === 'ok' ? null : true)}
              >
                Yes
              </Button>
              <Button
                size="small"
                color="error"
                variant={check.result === 'fail' ? 'contained' : 'outlined'}
                onClick={() => void record(check.check, check.result === 'fail' ? null : false)}
              >
                No
              </Button>
            </Stack>
          </>
        )}
      </Box>
    );
  };

  const blockedReason = blocked ?? fixture?.output_blocked_reason ?? rigBlockedReason;

  return (
    <Dialog open={fixture !== null} onClose={handleClose} maxWidth="xs" fullWidth>
      {fixture && (
        <>
          <DialogTitle sx={{ pb: 0.5 }}>
            Check {fixture.label}
            <Typography variant="caption" color="text.secondary" display="block">
              Universe {fixture.universe}, address {fixture.dmx_address}
              {fixture.channel_count ? `, ${fixture.channel_count} channels` : ''}
            </Typography>
          </DialogTitle>
          <DialogContent>
            <Stack spacing={1.5} divider={<Divider flexItem />}>
              <Box>
                {blockedReason && (
                  <Alert severity="warning" sx={{ mb: 1 }} data-testid="setup-check-blocked">
                    {blockedReason}
                  </Alert>
                )}
                {error && (
                  <Alert severity="error" sx={{ mb: 1 }} onClose={() => setError(null)}>
                    {error}
                  </Alert>
                )}
                {notice && (
                  <Alert severity="info" sx={{ mb: 1 }} onClose={() => setNotice(null)}>
                    {notice}
                  </Alert>
                )}
                <Typography variant="body2" color="text.secondary">
                  {active
                    ? 'This light is held on and the rest of the room is dark. The show comes back when you stop or close this.'
                    : 'Lighting this fixture pauses the show and darkens the rest of the room until you stop.'}
                </Typography>
              </Box>
              {fixture.checks.map(renderCheck)}
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button
              color="error"
              startIcon={<StopIcon />}
              disabled={!active}
              onClick={() => void release()}
            >
              Stop the light
            </Button>
            <Box sx={{ flexGrow: 1 }} />
            <Button onClick={handleClose}>Done</Button>
          </DialogActions>
        </>
      )}
    </Dialog>
  );
}
