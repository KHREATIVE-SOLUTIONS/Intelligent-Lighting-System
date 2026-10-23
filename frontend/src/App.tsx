import { Routes, Route } from 'react-router-dom';
import { Box } from '@mui/material';
import { lazy, Suspense, useEffect, useState } from 'react';
import { CircularProgress } from '@mui/material';
import Layout from './components/common/Layout';
import Dashboard from './components/dashboard/Dashboard';
import ShowEditor from './components/show/ShowEditor';
import ShowList from './components/show/ShowList';
import RigEditor from './components/rig/RigEditor';
import RigList from './components/rig/RigList';
import RigVisualizer from './components/rig/RigVisualizer';
import LoginScreen from './components/auth/LoginScreen';
import { authApi } from './services/api';
import { useAuthStore } from './stores/authStore';

// Lazy-loaded new components
const FixtureLibrary = lazy(() => import('./components/fixtures/FixtureLibrary'));
const FixtureDetail = lazy(() => import('./components/fixtures/FixtureDetail'));
const FixtureEditor = lazy(() => import('./components/fixtures/FixtureEditor'));
const RigBuilder = lazy(() => import('./components/rig/RigBuilder'));
const RigWizard = lazy(() => import('./components/rig/RigWizard'));

const Loading = () => (
  <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
    <CircularProgress />
  </Box>
);

function App() {
  const token = useAuthStore((state) => state.token);
  const setConfigured = useAuthStore((state) => state.setConfigured);
  const setSession = useAuthStore((state) => state.setSession);
  const clearSession = useAuthStore((state) => state.clearSession);
  const [checkedSession, setCheckedSession] = useState(false);

  useEffect(() => {
    let cancelled = false;

    authApi
      .getStatus()
      .then((status) => {
        if (cancelled) return;
        setConfigured(status.configured);
        // Dev mode (AUTH_ENABLED=false): no login required, drop straight in.
        if (!status.enabled) {
          if (!useAuthStore.getState().token) setSession('dev-auth-disabled');
          return;
        }
        if (useAuthStore.getState().token && !status.authenticated) {
          clearSession();
        }
      })
      .catch(() => {
        // Server unreachable: keep any stored token rather than forcing a re-login.
      })
      .finally(() => {
        if (!cancelled) setCheckedSession(true);
      });

    return () => {
      cancelled = true;
    };
  }, [setConfigured, setSession, clearSession]);

  if (!checkedSession) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', width: '100%' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!token) {
    return <LoginScreen />;
  }

  return (
    <Box sx={{ display: 'flex', height: '100vh' }}>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="shows" element={<ShowList />} />
          <Route path="shows/:id" element={<ShowEditor />} />
          <Route path="rigs" element={<RigList />} />
          <Route path="rigs/new/wizard" element={<Suspense fallback={<Loading />}><RigWizard /></Suspense>} />
          <Route path="rigs/:id/builder" element={<Suspense fallback={<Loading />}><RigBuilder /></Suspense>} />
          <Route path="rigs/:id" element={<RigEditor />} />
          <Route path="visualizer" element={<RigVisualizer />} />
          <Route path="rigs/:id/visualizer" element={<RigVisualizer />} />
          <Route path="fixtures" element={<Suspense fallback={<Loading />}><FixtureLibrary /></Suspense>} />
          <Route path="fixtures/new" element={<Suspense fallback={<Loading />}><FixtureEditor /></Suspense>} />
          <Route path="fixtures/:id" element={<Suspense fallback={<Loading />}><FixtureDetail /></Suspense>} />
          <Route path="fixtures/:id/edit" element={<Suspense fallback={<Loading />}><FixtureEditor /></Suspense>} />
        </Route>
      </Routes>
    </Box>
  );
}

export default App;
