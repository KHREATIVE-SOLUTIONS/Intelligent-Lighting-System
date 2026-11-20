import { useState } from 'react';
import { Alert, Button, Snackbar } from '@mui/material';
import { PlayArrow as ActivateIcon } from '@mui/icons-material';
import { rigsApi } from '../../services/api';
import { pollShowHealth } from '../../hooks/useShowHealth';

// Puts a rig on the running show: no restart. Shown for every rig, the active
// one included, because pressing it again is how an edited rig reaches the
// stage. Says what happened either way; a refused rig comes back with the
// reason from the box, and the show stays on the rig it had.

export interface ActivationFeedback {
  severity: 'success' | 'info' | 'error';
  message: string;
}

export interface RigActivator {
  (rigId: number): Promise<{ name?: string; live?: boolean; fixtures?: unknown[] }>;
}

/** Activate a rig and put what happened into words. Never rejects. */
export async function activateRig(
  rigId: number,
  activate: RigActivator = rigsApi.activate
): Promise<ActivationFeedback> {
  try {
    const rig = await activate(rigId);
    const name = rig.name ? `"${rig.name}"` : 'The rig';
    if (rig.live === false) {
      return {
        severity: 'info',
        message: `${name} is marked active, but it has no fixtures to drive, so the show stays on its current rig.`,
      };
    }
    const count = rig.fixtures?.length;
    return {
      severity: 'success',
      message: `${name} is live${count ? ` with ${count} fixture${count === 1 ? '' : 's'}` : ''}. No restart needed.`,
    };
  } catch (error) {
    const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
    return {
      severity: 'error',
      message:
        typeof detail === 'string' && detail
          ? detail
          : 'Could not activate the rig. The show is still on the rig it had.',
    };
  }
}

interface ActivateRigButtonProps {
  rigId: number;
  /** The rig already carries the active mark: pressing applies its edits. */
  isActive: boolean;
  size?: 'small' | 'medium';
  variant?: 'text' | 'outlined' | 'contained';
  /** Called after the box answers, so the page can show the new state. */
  onDone?: (feedback: ActivationFeedback) => void;
  // Stand-ins for tests.
  activate?: RigActivator;
  refreshStatus?: () => Promise<void>;
}

export default function ActivateRigButton({
  rigId,
  isActive,
  size = 'small',
  variant = 'text',
  onDone,
  activate = rigsApi.activate,
  refreshStatus = pollShowHealth,
}: ActivateRigButtonProps) {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<ActivationFeedback | null>(null);

  const handleClick = async () => {
    setBusy(true);
    const result = await activateRig(rigId, activate);
    setFeedback(result);
    setBusy(false);
    if (result.severity !== 'error') {
      // Read the engine's status now instead of at the next poll, so the 3D
      // view and the status bar follow the new rig straight away.
      void refreshStatus().catch(() => {});
    }
    onDone?.(result);
  };

  return (
    <>
      <Button
        size={size}
        variant={variant}
        startIcon={<ActivateIcon />}
        disabled={busy}
        onClick={handleClick}
        title={
          isActive
            ? 'Send this rig, with its latest edits, to the running show'
            : 'Make this the rig the show runs, without a restart'
        }
        data-testid={`activate-rig-${rigId}`}
      >
        {busy ? 'Activating…' : isActive ? 'Apply to show' : 'Activate'}
      </Button>
      <Snackbar
        open={feedback !== null}
        autoHideDuration={feedback?.severity === 'error' ? null : 6000}
        onClose={(_, reason) => {
          if (reason !== 'clickaway') setFeedback(null);
        }}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        {feedback ? (
          <Alert
            severity={feedback.severity}
            variant="filled"
            onClose={() => setFeedback(null)}
            data-testid="activate-rig-feedback"
          >
            {feedback.message}
          </Alert>
        ) : undefined}
      </Snackbar>
    </>
  );
}
