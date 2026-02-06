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
  Chip,
} from '@mui/material';
import {
  Menu as MenuIcon,
  Dashboard as DashboardIcon,
  Theaters as ShowsIcon,
  Settings as RigsIcon,
  Lightbulb as LightbulbIcon,
} from '@mui/icons-material';
import { useAudioStore } from '../../stores/audioStore';
import { useDMXStore } from '../../stores/dmxStore';

const DRAWER_WIDTH = 240;

const menuItems = [
  { text: 'Dashboard', icon: <DashboardIcon />, path: '/' },
  { text: 'Shows', icon: <ShowsIcon />, path: '/shows' },
  { text: 'Rigs', icon: <RigsIcon />, path: '/rigs' },
];

export default function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const isStreaming = useAudioStore((state) => state.isStreaming);
  const dmxConnected = useDMXStore((state) => state.isConnected);
  const fps = useDMXStore((state) => state.fps);

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
              onClick={() => navigate(item.path)}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.text} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
      <Divider />
      <Box component="div" sx={{ p: 2 }}>
        <Typography variant="caption" color="text.secondary" display="block" mb={1}>
          Status
        </Typography>
        <Box component="div" sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Chip
            size="small"
            label={isStreaming ? 'Audio Active' : 'Audio Idle'}
            color={isStreaming ? 'success' : 'default'}
          />
          <Chip
            size="small"
            label={dmxConnected ? `DMX ${fps.toFixed(0)} FPS` : 'DMX Offline'}
            color={dmxConnected ? 'success' : 'error'}
          />
        </Box>
      </Box>
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
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
            Intelligent Lighting Control
          </Typography>
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
          p: 3,
          width: { sm: `calc(100% - ${DRAWER_WIDTH}px)` },
          mt: '64px',
          height: 'calc(100vh - 64px)',
          overflow: 'auto',
        }}
      >
        <Outlet />
      </Box>
    </Box>
  );
}
