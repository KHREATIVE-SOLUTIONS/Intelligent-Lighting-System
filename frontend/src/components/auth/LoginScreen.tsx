import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import axios from 'axios';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Paper,
  TextField,
  Typography,
} from '@mui/material';
import { Lightbulb as LightbulbIcon } from '@mui/icons-material';
import { authApi } from '../../services/api';
import { useAuthStore } from '../../stores/authStore';

const describeError = (error: unknown, fallback: string): string => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string' && detail) return detail;
    if (!error.response) return 'Cannot reach the lighting system. Is it still running?';
    if (error.response.status === 401) return 'That password was not accepted.';
    if (error.response.status === 429) return 'Too many tries. Wait a minute, then try again.';
    return `The lighting system replied with an error (${error.response.status}).`;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
};

export default function LoginScreen() {
  const configured = useAuthStore((state) => state.configured);
  const setConfigured = useAuthStore((state) => state.setConfigured);
  const setSession = useAuthStore((state) => state.setSession);

  const [checking, setChecking] = useState(configured === null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [setupCode, setSetupCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const checkStatus = useCallback(async () => {
    setChecking(true);
    setStatusError(null);
    try {
      const status = await authApi.getStatus();
      setConfigured(status.configured);
    } catch (err) {
      setStatusError(describeError(err, 'Could not ask the lighting system whether it is set up.'));
    } finally {
      setChecking(false);
    }
  }, [setConfigured]);

  useEffect(() => {
    if (configured === null) {
      void checkStatus();
    }
  }, [configured, checkStatus]);

  const isFirstRun = configured === false;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;

    setError(null);

    if (!password) {
      setError('Enter a password.');
      return;
    }

    if (isFirstRun) {
      if (!setupCode.trim()) {
        setError('Enter the setup code from the server console.');
        return;
      }
      if (password.length < 4) {
        setError('Use at least 4 characters.');
        return;
      }
      if (password !== confirmPassword) {
        setError('The two passwords do not match.');
        return;
      }
    }

    setBusy(true);
    try {
      if (isFirstRun) {
        const token = await authApi.setup(setupCode.trim(), password);
        setSession(token ?? (await authApi.login(password)));
      } else {
        setSession(await authApi.login(password));
      }
    } catch (err) {
      setError(describeError(err, 'Sign in failed.'));
      setBusy(false);
    }
  };

  return (
    <Box
      component="div"
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '100%',
        height: '100vh',
        p: 2,
      }}
    >
      <Paper sx={{ p: 4, width: '100%', maxWidth: 440 }}>
        <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3 }}>
          <LightbulbIcon sx={{ color: 'primary.main' }} />
          <Typography variant="h5">Lighting System</Typography>
        </Box>

        {checking ? (
          <Box component="div" sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
            <CircularProgress />
          </Box>
        ) : statusError ? (
          <Box component="div">
            <Alert severity="error" sx={{ mb: 2 }}>
              {statusError}
            </Alert>
            <Button variant="contained" fullWidth onClick={() => void checkStatus()}>
              Try again
            </Button>
          </Box>
        ) : (
          <Box component="form" onSubmit={handleSubmit}>
            {isFirstRun ? (
              <>
                <Typography variant="h6" gutterBottom>
                  Set your password
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Nobody has set a password on this lighting system yet. Choose one now — you will
                  need it every time you open this page.
                </Typography>
                <Alert severity="info" sx={{ mb: 2 }}>
                  Your setup code is printed in the console window on the computer running the
                  lighting system — the window that shows the start-up messages. Look for the line
                  that says &ldquo;Setup code&rdquo; and type it in below.
                </Alert>
                <TextField
                  label="Setup code"
                  value={setupCode}
                  onChange={(e) => setSetupCode(e.target.value)}
                  fullWidth
                  autoFocus
                  margin="normal"
                  autoComplete="off"
                />
                <TextField
                  label="New password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  fullWidth
                  margin="normal"
                  autoComplete="new-password"
                />
                <TextField
                  label="Type it again"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  fullWidth
                  margin="normal"
                  autoComplete="new-password"
                />
              </>
            ) : (
              <>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Enter your password to control the lights.
                </Typography>
                <TextField
                  label="Password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  fullWidth
                  autoFocus
                  margin="normal"
                  autoComplete="current-password"
                />
              </>
            )}

            {error && (
              <Alert severity="error" sx={{ mt: 2 }}>
                {error}
              </Alert>
            )}

            <Button
              type="submit"
              variant="contained"
              fullWidth
              size="large"
              disabled={busy}
              sx={{ mt: 3 }}
            >
              {busy ? <CircularProgress size={24} /> : isFirstRun ? 'Save password' : 'Unlock'}
            </Button>

            {!isFirstRun && (
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 2 }}>
                Forgotten the password? It can only be reset from the computer the lighting system
                runs on. The README explains how.
              </Typography>
            )}
          </Box>
        )}
      </Paper>
    </Box>
  );
}
