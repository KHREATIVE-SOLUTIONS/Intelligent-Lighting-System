import { Routes, Route } from 'react-router-dom';
import { Box } from '@mui/material';
import Layout from './components/common/Layout';
import Dashboard from './components/dashboard/Dashboard';
import ShowEditor from './components/show/ShowEditor';
import ShowList from './components/show/ShowList';
import RigEditor from './components/rig/RigEditor';
import RigList from './components/rig/RigList';
import RigVisualizer from './components/rig/RigVisualizer';

function App() {
  return (
    <Box sx={{ display: 'flex', height: '100vh' }}>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="shows" element={<ShowList />} />
          <Route path="shows/:id" element={<ShowEditor />} />
          <Route path="rigs" element={<RigList />} />
          <Route path="rigs/:id" element={<RigEditor />} />
          <Route path="rigs/:id/visualizer" element={<RigVisualizer />} />
        </Route>
      </Routes>
    </Box>
  );
}

export default App;
