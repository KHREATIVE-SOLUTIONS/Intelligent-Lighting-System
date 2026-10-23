import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import {
  Box,
  Drawer,
  AppBar,
  Toolbar,
  Typography,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  IconButton,
  Divider,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
} from '@mui/material';
import {
  Menu as MenuIcon,
  Dashboard as DashboardIcon,
  Theaters as ShowsIcon,
  Settings as RigsIcon,
  Lightbulb as LightbulbIcon,
  Visibility as VisualizerIcon,
  Logout as LogoutIcon,
  UnfoldLess as FoldIcon,
  UnfoldMore as UnfoldIcon,
} from '@mui/icons-material';
import { useAuthStore } from '../../stores/authStore';
import { disconnectAllWebSockets } from '../../services/websocket';
import { useShowHealth } from '../../hooks/useShowHealth';
import StatusBar from './StatusBar';
import MasterControl from '../dashboard/MasterControl';
import AutopilotControl from '../dashboard/AutopilotControl';

const DRAWER_WIDTH = 240;

// The visualizer needs the screen height, so the pinned controls start folded
// there; everywhere else they start open. Blackout shows either way.
type FoldKind = 'visualizer' | 'default';
export const foldKindFor = (pathname: string): FoldKind =>
  pathname.includes('visualizer') ? 'visualizer' : 'default';

const menuItems = [
  { text: 'Dashboard', icon: <DashboardIcon />, path: '/' },
  { text: 'Visualizer', icon: <VisualizerIcon />, path: '/visualizer' },
  { text: 'Shows', icon: <ShowsIcon />, path: '/shows' },
  { text: 'Rigs', icon: <RigsIcon />, path: '/rigs' },
  { text: 'Fixtures', icon: <LightbulbIcon />, path: '/fixtures' },
];

export default function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [confirmLogout, setConfirmLogout] = useState(false);
  const [folded, setFolded] = useState<Record<FoldKind, boolean>>({ visualizer: true, default: false });
  const navigate = useNavigate();
  const location = useLocation();
  const clearSession = useAuthStore((state) => state.clearSession);
  const foldKind = foldKindFor(location.pathname);
  const controlsFolded = folded[foldKind];
  const toggleFold = () => setFolded((prev) => ({ ...prev, [foldKind]: !prev[foldKind] }));

  useShowHealth();

  const handleLogout = () => {
    setConfirmLogout(false);
    disconnectAllWebSockets();
    clearSession();
  };

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  const drawer = (
    <Box component="div">
      <Toolbar>
        <LightbulbIcon sx={{ mr: 1, color: 'primary.main' }} />
        <Typography variant="h6" noWrap>
          Lighting System
        </Typography>
      </Toolbar>
      <Divider />
      <List>
        {menuItems.map((item) => (
          <ListItem key={item.text} disablePadding>
            <ListItemButton
              selected={location.pathname === item.path}
              onClick={() => {
                navigate(item.path);
                setMobileOpen(false);
              }}
              sx={{ minHeight: 52 }}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.text} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
      <Divider />
      <List>
        <ListItem disablePadding>
          {/* Lives in the drawer, behind a confirm: a stray tap mid-show must not drop the session. */}
          <ListItemButton onClick={() => setConfirmLogout(true)}>
            <ListItemIcon>
              <LogoutIcon />
            </ListItemIcon>
            <ListItemText primary="Log out" />
          </ListItemButton>
        </ListItem>
      </List>
    </Box>
  );

  return (
    <Box component="div" sx={{ display: 'flex', width: '100%' }}>
      <AppBar
        position="fixed"
        sx={{
          width: { sm: `calc(100% - ${DRAWER_WIDTH}px)` },
          ml: { sm: `${DRAWER_WIDTH}px` },
        }}
      >
        <Toolbar>
          <IconButton
            color="inherit"
            edge="start"
            onClick={handleDrawerToggle}
            sx={{ mr: 2, display: { sm: 'none' } }}
          >
            <MenuIcon />
          </IconButton>
          <Typography
            variant="h6"
            noWrap
            component="div"
            sx={{ flexGrow: 1, display: { xs: 'none', md: 'block' } }}
          >
            Intelligent Lighting Control
          </Typography>
          <Box component="div" sx={{ flexGrow: { xs: 1, md: 0 } }}>
            <StatusBar />
          </Box>
        </Toolbar>
      </AppBar>

      <Box
        component="nav"
        sx={{ width: { sm: DRAWER_WIDTH }, flexShrink: { sm: 0 } }}
      >
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', sm: 'none' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: DRAWER_WIDTH },
          }}
        >
          {drawer}
        </Drawer>
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', sm: 'block' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: DRAWER_WIDTH },
          }}
          open
        >
          {drawer}
        </Drawer>
      </Box>

      <Box
        component="main"
        sx={{
          flexGrow: 1,
          px: 3,
          pb: 3,
          width: { sm: `calc(100% - ${DRAWER_WIDTH}px)` },
          mt: '64px',
          height: 'calc(100vh - 64px)',
          overflow: 'auto',
        }}
      >
        {/* Blackout, grand master and the autopilot takeovers stay pinned on every page. */}
        <Box
          component="div"
          sx={{
            position: 'sticky',
            top: 0,
            zIndex: (theme) => theme.zIndex.appBar - 1,
            mx: -3,
            px: 3,
            pt: 1,
            pb: controlsFolded ? 1 : 2,
            mb: 1,
            bgcolor: 'background.default',
          }}
        >
          <Box component="div" sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            <MasterControl
              compact={controlsFolded}
              trailing={
                <IconButton
                  onClick={toggleFold}
                  aria-label={controlsFolded ? 'Show all show controls' : 'Fold show controls'}
                  aria-expanded={!controlsFolded}
                  title={controlsFolded ? 'Show all controls' : 'Fold controls'}
                  size="large"
                  sx={{ ml: 'auto' }}
                >
                  {controlsFolded ? <UnfoldIcon /> : <FoldIcon />}
                </IconButton>
              }
            />
            {!controlsFolded && <AutopilotControl />}
          </Box>
        </Box>
        <Outlet />
      </Box>

      <Dialog open={confirmLogout} onClose={() => setConfirmLogout(false)}>
        <DialogTitle>Log out of this screen?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            The lights keep running on the box. This screen stops showing live status until
            someone logs back in.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmLogout(false)} autoFocus>
            Stay logged in
          </Button>
          <Button onClick={handleLogout} color="error">
            Log out
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
