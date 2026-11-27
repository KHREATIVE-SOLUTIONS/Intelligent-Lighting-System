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
import {
  FIX_AUTO_GROUPS,
  FIX_LABELS,
  FIX_LOCATE,
  FIX_READDRESS,
  fixturesText,
  headline,
  locateLabel,
  sortedChecks,
} from '../../utils/readiness';
import type { ReaddressResult, ReadinessCheck, ReadinessReport, ReadinessStatus } from '../../utils/readiness';

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
 * fixtures it names. Opening it and Check again read only. Two fixes write,
 * each asked for first because the rig has no undo for groups or addresses:
 * Make groups, and Re-address, which shows its planned moves (a dry run)
 * before anything moves. Locate these hands the named fixtures to the
 * flash-and-tap walkthrough.
 */
export default function ReadinessDialog({
  open, rigId, rigName, onClose, onSelectFixtures, onLocate, onChanged,
}: ReadinessDialogProps) {
  const [report, setReport] = useState<ReadinessReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState<string | null>(null);
  const [plan, setPlan] = useState<ReaddressResult | null>(null);
  const [fixing, setFixing] = useState(false);
  const [fixNote, setFixNote] = useState<{ severity: 'success' | 'error'; text: string } | null>(null);

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
    setFixNote(null);
    void load();
  }, [open, load]);

  const cancel = () => {
    setAsking(null);
    setPlan(null);
  };

  const makeGroups = async () => {
    cancel();
    setFixing(true);
    try {
      const result = await readinessApi.autoGroups(rigId);
      setFixNote({ severity: 'success', text: result.message });
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
      if (result.moves.length > 0) onChanged?.();
      await load();
    } catch {
      setFixNote({ severity: 'error', text: 'Re-address did not run: nothing was changed. Try again.' });
    } finally {
      setFixing(false);
    }
  };

  const pressFix = (check: ReadinessCheck) => {
    if (check.fix === FIX_AUTO_GROUPS) setAsking(FIX_AUTO_GROUPS);
    else if (check.fix === FIX_READDRESS) void planReaddress();
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
      no fixture is taken out of a group, and groups named any other way are left alone. There is no
      undo for this: the answer lists each fixture changed.
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
              Only the fixtures that clash move; every other address stays. There is no undo for
              this: set each one to its new address on the fixture itself.
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
            {fixNote && <Alert severity={fixNote.severity} sx={{ mb: 1 }}>{fixNote.text}</Alert>}
            {sortedChecks(report.checks).map(renderCheck)}
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              These checks read the rig and write nothing; the exports are built in memory. What each
              check means: {report.operator_guide}.
            </Typography>
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={() => { void load(); }} disabled={loading || fixing}>Check again</Button>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
