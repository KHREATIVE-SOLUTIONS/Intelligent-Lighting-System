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
  fixturesText,
  headline,
  sortedChecks,
} from '../../utils/readiness';
import type { ReadinessCheck, ReadinessReport, ReadinessStatus } from '../../utils/readiness';

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

interface ReadinessDialogProps {
  open: boolean;
  rigId: number;
  rigName: string;
  onClose: () => void;
  /** Selects the fixtures a check names on the plan. The button is left out when this is. */
  onSelectFixtures?: (ids: number[]) => void;
  /** A fix wrote to the rig: the editor should read it again. */
  onChanged?: () => void;
}

/**
 * Venue readiness: every check the backend runs, worst first, each with the
 * fixtures it names. Opening it and Check again read only. The one write is
 * Make groups, asked for first because the rig has no undo for groups.
 */
export default function ReadinessDialog({
  open, rigId, rigName, onClose, onSelectFixtures, onChanged,
}: ReadinessDialogProps) {
  const [report, setReport] = useState<ReadinessReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState<string | null>(null);
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
    setFixNote(null);
    void load();
  }, [open, load]);

  const runFix = async (fix: string) => {
    if (fix !== FIX_AUTO_GROUPS) return;
    setAsking(null);
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

  const renderCheck = (check: ReadinessCheck) => {
    const chip = CHIP[check.status];
    const count = fixturesText(check);
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
        {(check.fixture_ids.length > 0 || check.fix) && (
          <Box sx={{ display: 'flex', gap: 1, mt: 0.75, ml: 7.5 }}>
            {onSelectFixtures && check.fixture_ids.length > 0 && (
              <Button size="small" variant="outlined" onClick={() => onSelectFixtures(check.fixture_ids)}>
                Select on plan
              </Button>
            )}
            {check.fix && FIX_LABELS[check.fix] && (
              <Button
                size="small"
                variant="contained"
                disabled={fixing}
                onClick={() => setAsking(check.fix)}
              >
                {FIX_LABELS[check.fix]}
              </Button>
            )}
          </Box>
        )}
        {asking && asking === check.fix && (
          <Alert
            severity="info"
            sx={{ mt: 1, ml: 7.5 }}
            action={
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button color="inherit" size="small" onClick={() => { void runFix(check.fix as string); }}>
                  Make them
                </Button>
                <Button color="inherit" size="small" onClick={() => setAsking(null)}>
                  Cancel
                </Button>
              </Box>
            }
          >
            Give each placed fixture that is in no group a group named for where it hangs and what it is,
            such as "Front truss Spots". Groups already in the rig are left as they are. There is no undo
            for this: the answer lists each fixture changed.
          </Alert>
        )}
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
