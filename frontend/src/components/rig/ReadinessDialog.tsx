import { useCallback, useEffect, useState } from 'react';
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
  Typography,
} from '@mui/material';
import { readinessApi } from '../../services/api';
import HandoffPackButton from './HandoffPackButton';
import {
  FIX_AUTO_GROUPS,
  FIX_LABELS,
  FIX_LOCATE,
  FIX_READDRESS,
  FIX_SET_MODES,
  fixturesText,
  headline,
  locateLabel,
  modeReasonText,
  sortedChecks,
} from '../../utils/readiness';
import type {
  ReaddressResult, ReadinessCheck, ReadinessReport, ReadinessStatus, ReadinessUndo, SetModesResult,
} from '../../utils/readiness';

const CHIP: Record<ReadinessStatus, { label: string; color: 'success' | 'warning' | 'error' }> = {
  ok: { label: 'OK', color: 'success' },
  warn: { label: 'Warn', color: 'warning' },
  fail: { label: 'Fail', color: 'error' },
};

const SEVERITY: Record<ReadinessStatus, 'success' | 'warning' | 'error'> = {
  ok: 'success',
  warn: 'warning',
  fail: 'error',
};

const PLAN_SHOWN = 12;

interface ReadinessDialogProps {
  open: boolean;
  rigId: number;
  rigName: string;
  onClose: () => void;
  /** Selects the fixtures a check names on the plan. The button is left out when this is. */
  onSelectFixtures?: (ids: number[]) => void;
  /**
   * Opens flash-and-tap with the fixtures the Positions check names. Nothing is
   * lit until Start is pressed there. The button is left out when this is.
   */
  onLocate?: (ids: number[]) => void;
  /** A fix wrote to the rig: the editor should read it again. */
  onChanged?: () => void;
}

/**
 * Venue readiness: every check the backend runs, worst first, each with the
 * fixtures it names. Opening it and Check again read only. Three fixes write:
 * Make groups; Re-address, which shows its planned moves (a dry run) before
 * anything moves; and Set modes, which shows the modes it would set, the
 * fixtures to pick by hand and any clash it would make before it sets one.
 * Each is a single step of Undo, offered beside
 * its answer (POST .../readiness/fix/undo). Locate these hands the named
 * fixtures to the flash-and-tap walkthrough.
 */
export default function ReadinessDialog({
  open, rigId, rigName, onClose, onSelectFixtures, onLocate, onChanged,
}: ReadinessDialogProps) {
  const [report, setReport] = useState<ReadinessReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState<string | null>(null);
  const [plan, setPlan] = useState<ReaddressResult | null>(null);
  const [modesPlan, setModesPlan] = useState<SetModesResult | null>(null);
  const [fixing, setFixing] = useState(false);
  const [fixNote, setFixNote] = useState<{ severity: 'success' | 'error'; text: string } | null>(null);
  // The undo a fix pressed here answered with. Only offered after a fix in this
  // panel, so the button always sits beside the answer it takes back.
  const [undo, setUndo] = useState<ReadinessUndo | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setReport(await readinessApi.get(rigId));
    } catch {
      setError('Could not read the readiness checks. Check the connection and try again.');
    } finally {
      setLoading(false);
    }
  }, [rigId]);

  useEffect(() => {
    if (!open) return;
    // The last report is of the rig as it was: opened again, it waits for the new one.
    setReport(null);
    setAsking(null);
    setPlan(null);
    setModesPlan(null);
    setFixNote(null);
    setUndo(null);
    void load();
  }, [open, load]);

  const cancel = () => {
    setAsking(null);
    setPlan(null);
    setModesPlan(null);
  };

  const makeGroups = async () => {
    cancel();
    setFixing(true);
    try {
      const result = await readinessApi.autoGroups(rigId);
      setFixNote({ severity: 'success', text: result.message });
      setUndo(result.undo ?? null);
      if (result.changed.length > 0) onChanged?.();
      await load();
    } catch {
      setFixNote({ severity: 'error', text: 'Make groups did not run: nothing was changed. Try again.' });
    } finally {
      setFixing(false);
    }
  };

  /** Re-address first asks the backend for its plan; nothing moves until Apply. */
  const planReaddress = async () => {
    setAsking(FIX_READDRESS);
    setPlan(null);
    setFixNote(null);
    setFixing(true);
    try {
      setPlan(await readinessApi.readdress(rigId, true));
    } catch {
      setAsking(null);
      setFixNote({ severity: 'error', text: 'Could not work out the new addresses: nothing was changed. Try again.' });
    } finally {
      setFixing(false);
    }
  };

  const applyReaddress = async () => {
    cancel();
    setFixing(true);
    try {
      const result = await readinessApi.readdress(rigId, false);
      setFixNote({ severity: 'success', text: result.message });
      setUndo(result.undo ?? null);
      if (result.moves.length > 0) onChanged?.();
      await load();
    } catch {
      setFixNote({ severity: 'error', text: 'Re-address did not run: nothing was changed. Try again.' });
    } finally {
      setFixing(false);
    }
  };

  /** Set modes first asks for its plan, like Re-address; no mode is set until Apply. */
  const planSetModes = async () => {
    setAsking(FIX_SET_MODES);
    setModesPlan(null);
    setFixNote(null);
    setFixing(true);
    try {
      setModesPlan(await readinessApi.setModes(rigId, true));
    } catch {
      setAsking(null);
      setFixNote({ severity: 'error', text: 'Could not work out the DMX modes: nothing was changed. Try again.' });
    } finally {
      setFixing(false);
    }
  };

  const applySetModes = async () => {
    cancel();
    setFixing(true);
    try {
      const result = await readinessApi.setModes(rigId, false);
      setFixNote({ severity: 'success', text: result.message });
      setUndo(result.undo ?? null);
      if (result.proposals.length > 0) onChanged?.();
      await load();
    } catch {
      setFixNote({ severity: 'error', text: 'Set modes did not run: nothing was changed. Try again.' });
    } finally {
      setFixing(false);
    }
  };

  /** Takes back the last fix as one step. Refused (409) when a fixture it changed was changed since. */
  const undoFix = async () => {
    cancel();
    setFixing(true);
    try {
      const result = await readinessApi.undoFix(rigId);
      setUndo(null); // spent
      setFixNote({ severity: 'success', text: result.message });
      if (result.restored.length > 0) onChanged?.();
      await load();
    } catch (e) {
      const detail = (e as { response?: { status?: number; data?: { detail?: { message?: string } } } }).response;
      // Refused: the rig changed since, so this undo can no longer be offered. Any other
      // failure wrote nothing and the record is still on the rig, so Undo stays to try again.
      if (detail?.status === 409) setUndo(null);
      setFixNote({
        severity: 'error',
        text: detail?.status === 409 && detail.data?.detail?.message
          ? detail.data.detail.message
          : 'Undo did not run: nothing was changed. Try again.',
      });
    } finally {
      setFixing(false);
    }
  };

  const pressFix = (check: ReadinessCheck) => {
    if (check.fix === FIX_AUTO_GROUPS) setAsking(FIX_AUTO_GROUPS);
    else if (check.fix === FIX_READDRESS) void planReaddress();
    else if (check.fix === FIX_SET_MODES) void planSetModes();
    else if (check.fix === FIX_LOCATE) onLocate?.(check.fixture_ids);
  };

  const fixButton = (check: ReadinessCheck) => {
    if (!check.fix || !FIX_LABELS[check.fix]) return null;
    if (check.fix === FIX_LOCATE && (!onLocate || check.fixture_ids.length === 0)) return null;
    return (
      <Button size="small" variant="contained" disabled={fixing} onClick={() => pressFix(check)}>
        {check.fix === FIX_LOCATE ? locateLabel(check) : FIX_LABELS[check.fix]}
      </Button>
    );
  };

  const confirmActions = (label: string, onConfirm: () => void, testId: string) => (
    <Box sx={{ display: 'flex', gap: 1 }}>
      <Button color="inherit" size="small" data-testid={testId} onClick={onConfirm}>
        {label}
      </Button>
      <Button color="inherit" size="small" onClick={cancel}>
        Cancel
      </Button>
    </Box>
  );

  const renderGroupsAsk = () => (
    <Alert
      severity="info"
      sx={{ mt: 1, ml: 7.5 }}
      action={confirmActions('Make them', () => { void makeGroups(); }, 'readiness-confirm-auto-groups')}
    >
      Give each placed fixture that is in no group a group named for where it hangs and what it is,
      such as "Front truss Spots". A fixture joins a group of exactly that name if the rig has one;
      no fixture is taken out of a group, and groups named any other way are left alone. The answer
      lists each fixture changed, and Undo puts them all back in one step.
    </Alert>
  );

  const renderReaddressPlan = () => {
    if (!plan) {
      return (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1, ml: 7.5 }}>
          <CircularProgress size={16} />
          <Typography variant="body2">Working out free addresses...</Typography>
        </Box>
      );
    }
    const moves = plan.moves;
    const guessed = moves.filter((m) => m.guessed).length;
    return (
      <Alert
        severity="info"
        data-testid="readiness-readdress-plan"
        sx={{ mt: 1, ml: 7.5 }}
        action={moves.length > 0
          ? confirmActions(`Move ${moves.length}`, () => { void applyReaddress(); }, 'readiness-confirm-readdress')
          : confirmActions('Close', cancel, 'readiness-readdress-close')}
      >
        {moves.length === 0 ? (
          <Typography variant="body2">{plan.message}</Typography>
        ) : (
          <>
            <Typography variant="body2" sx={{ mb: 0.5 }}>
              Only the fixtures that clash move; every other address stays. Set each one to its new
              address on the fixture itself (Undo puts the rig's addresses back in one step).
            </Typography>
            <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
              {moves.slice(0, PLAN_SHOWN).map((m) => (
                <li key={m.id}>
                  <Typography variant="body2">
                    {m.name || `Fixture ${m.id}`}: {m.from_label} to {m.to_label}
                    {m.reason === 'past_end' ? ' (ran past channel 512)' : ''}
                  </Typography>
                </li>
              ))}
            </Box>
            {moves.length > PLAN_SHOWN && (
              <Typography variant="body2">and {moves.length - PLAN_SHOWN} more.</Typography>
            )}
            {guessed > 0 && (
              <Typography variant="body2" sx={{ mt: 0.5 }}>
                {guessed} of them {guessed === 1 ? 'has' : 'have'} no DMX mode: the clash was found with a
                guessed footprint and may not be real. Picking the mode first may be the better fix.
              </Typography>
            )}
            {plan.left.map((entry) => (
              <Typography key={entry.id} variant="body2" sx={{ mt: 0.5 }}>{entry.message}</Typography>
            ))}
          </>
        )}
      </Alert>
    );
  };

  const renderSetModesPlan = () => {
    if (!modesPlan) {
      return (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1, ml: 7.5 }}>
          <CircularProgress size={16} />
          <Typography variant="body2">Working out the DMX modes...</Typography>
        </Box>
      );
    }
    const { proposals, by_hand: byHand, clashes } = modesPlan;
    return (
      <Alert
        severity={clashes.length > 0 ? 'warning' : 'info'}
        data-testid="readiness-set-modes-plan"
        sx={{ mt: 1, ml: 7.5 }}
        action={proposals.length > 0
          ? confirmActions(`Set ${proposals.length}`, () => { void applySetModes(); }, 'readiness-confirm-set-modes')
          : confirmActions('Close', cancel, 'readiness-set-modes-close')}
      >
        {proposals.length === 0 && byHand.length === 0 && (
          <Typography variant="body2">{modesPlan.message}</Typography>
        )}
        {proposals.length > 0 && (
          <>
            <Typography variant="body2" sx={{ mb: 0.5 }}>
              Only where one mode is possible. No address moves (Undo puts the modes back in one step).
            </Typography>
            <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
              {proposals.slice(0, PLAN_SHOWN).map((p) => (
                <li key={p.id}>
                  <Typography variant="body2">
                    {p.name}: {p.mode_name_before ?? 'no mode'} to {p.mode_name} ({p.channel_count}ch),{' '}
                    {modeReasonText(p)}
                  </Typography>
                </li>
              ))}
            </Box>
            {proposals.length > PLAN_SHOWN && (
              <Typography variant="body2">and {proposals.length - PLAN_SHOWN} more.</Typography>
            )}
          </>
        )}
        {byHand.length > 0 && (
          <Box data-testid="readiness-set-modes-by-hand" sx={{ mt: proposals.length > 0 ? 1 : 0 }}>
            <Typography variant="body2" sx={{ mb: 0.5 }}>
              Pick by hand in the patch editor ({byHand.length}); these are not changed:
            </Typography>
            <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
              {byHand.slice(0, PLAN_SHOWN).map((b) => (
                <li key={b.id}>
                  <Typography variant="body2">
                    {b.name}: {b.candidates.length > 0
                      ? b.candidates.map((c) => `${c.name} (${c.channel_count}ch)`).join(', ')
                      : 'its profile has no DMX modes'}
                  </Typography>
                </li>
              ))}
            </Box>
            {byHand.length > PLAN_SHOWN && (
              <Typography variant="body2">and {byHand.length - PLAN_SHOWN} more.</Typography>
            )}
          </Box>
        )}
        {clashes.length > 0 && (
          <Box data-testid="readiness-set-modes-clashes" sx={{ mt: 1 }}>
            <Typography variant="body2">
              With the new footprints, {clashes.length} address clash{clashes.length === 1 ? '' : 'es'} would
              show. No address is moved: run Re-address afterwards.
            </Typography>
            {clashes.slice(0, PLAN_SHOWN).map((c) => (
              <Typography key={`${c.kind}-${c.fixture_ids.join('-')}`} variant="body2">{c.message}</Typography>
            ))}
          </Box>
        )}
      </Alert>
    );
  };

  const renderCheck = (check: ReadinessCheck) => {
    const chip = CHIP[check.status];
    const count = fixturesText(check);
    const button = fixButton(check);
    return (
      <Box
        key={check.id}
        data-testid={`readiness-check-${check.id}`}
        sx={{ py: 1.25, borderBottom: 1, borderColor: 'divider' }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Chip size="small" label={chip.label} color={chip.color} sx={{ minWidth: 52 }} />
          <Typography variant="subtitle2" sx={{ flexGrow: 1 }}>{check.title}</Typography>
          {count && <Typography variant="caption" color="text.secondary">{count}</Typography>}
        </Box>
        <Typography variant="body2" sx={{ mt: 0.5, ml: 7.5 }}>{check.message}</Typography>
        {((onSelectFixtures && check.fixture_ids.length > 0) || button) && (
          <Box sx={{ display: 'flex', gap: 1, mt: 0.75, ml: 7.5 }}>
            {onSelectFixtures && check.fixture_ids.length > 0 && (
              <Button size="small" variant="outlined" onClick={() => onSelectFixtures(check.fixture_ids)}>
                Select on plan
              </Button>
            )}
            {button}
          </Box>
        )}
        {asking === FIX_AUTO_GROUPS && check.fix === FIX_AUTO_GROUPS && renderGroupsAsk()}
        {asking === FIX_READDRESS && check.fix === FIX_READDRESS && renderReaddressPlan()}
        {asking === FIX_SET_MODES && check.fix === FIX_SET_MODES && renderSetModesPlan()}
      </Box>
    );
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Venue readiness: {rigName}</DialogTitle>
      <DialogContent dividers>
        {loading && !report && (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress size={28} />
          </Box>
        )}
        {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
        {report && (
          <>
            <Alert severity={SEVERITY[report.status]} data-testid="readiness-headline" sx={{ mb: 1 }}>
              {headline(report)}
            </Alert>
            {fixNote && (
              <Alert
                severity={fixNote.severity}
                data-testid="readiness-fix-note"
                sx={{ mb: 1 }}
                action={undo && (
                  <Button
                    color="inherit"
                    size="small"
                    data-testid="readiness-undo"
                    disabled={fixing}
                    onClick={() => { void undoFix(); }}
                  >
                    {undo.label}
                  </Button>
                )}
              >
                {fixNote.text}
              </Alert>
            )}
            {sortedChecks(report.checks).map(renderCheck)}
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              These checks read the rig and write nothing; the exports are built in memory. What each
              check means: {report.operator_guide}.
            </Typography>
          </>
        )}
        {/* Never waits on the report: a rig whose checks cannot be read can still be handed off. */}
        <Box sx={{ mt: 2 }}>
          <HandoffPackButton rigId={rigId} failCount={report?.counts.fail} />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => { void load(); }} disabled={loading || fixing}>Check again</Button>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
