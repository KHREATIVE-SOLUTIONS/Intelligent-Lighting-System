import { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  TextField,
  List,
  ListItem,
  ListItemText,
  ListSubheader,
  InputAdornment,
  Collapse,
  IconButton,
} from '@mui/material';
import {
  Search as SearchIcon,
  ExpandMore,
  ExpandLess,
  DragIndicator,
} from '@mui/icons-material';
import { fixturesApi } from '../../services/api';
import type { Fixture } from '../../types';

interface FixturePaletteProps {
  onDragStart?: (fixture: Fixture) => void;
  onFixtureClick?: (fixture: Fixture) => void;
}

export default function FixturePalette({ onDragStart, onFixtureClick }: FixturePaletteProps) {
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [search, setSearch] = useState('');
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set(['moving_head', 'led_par', 'led_bar']));

  useEffect(() => {
    fixturesApi.list(1, 100).then((data) => setFixtures(data.items)).catch(() => {});
  }, []);

  const toggleType = (type: string) => {
    setExpandedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  // Group by fixture type
  const grouped = fixtures
    .filter((f) =>
      !search ||
      f.manufacturer.toLowerCase().includes(search.toLowerCase()) ||
      f.model.toLowerCase().includes(search.toLowerCase())
    )
    .reduce<Record<string, Fixture[]>>((acc, f) => {
      const type = f.fixture_type || 'other';
      if (!acc[type]) acc[type] = [];
      acc[type].push(f);
      return acc;
    }, {});

  return (
    <Box sx={{ height: '100%', overflow: 'auto' }}>
      <Box sx={{ p: 1 }}>
        <Typography variant="subtitle2" sx={{ px: 1, mb: 1 }}>
          Fixture Palette
        </Typography>
        <TextField
          size="small"
          fullWidth
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
        />
      </Box>

      <List dense sx={{ pt: 0 }}>
        {Object.entries(grouped).map(([type, items]) => (
          <Box key={type}>
            <ListItem
              component="div"
              onClick={() => toggleType(type)}
              sx={{ cursor: 'pointer', bgcolor: 'action.hover' }}
            >
              <ListItemText
                primary={`${type.replace('_', ' ')} (${items.length})`}
                primaryTypographyProps={{ variant: 'caption', fontWeight: 'bold', textTransform: 'uppercase' }}
              />
              <IconButton size="small">
                {expandedTypes.has(type) ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
              </IconButton>
            </ListItem>
            <Collapse in={expandedTypes.has(type)}>
              <List dense disablePadding>
                {items.map((f) => (
                  <ListItem
                    key={f.id}
                    sx={{ pl: 2, cursor: 'grab' }}
                    draggable
                    onDragStart={() => onDragStart?.(f)}
                    onClick={() => onFixtureClick?.(f)}
                  >
                    <DragIndicator fontSize="small" sx={{ mr: 1, color: 'text.disabled' }} />
                    <ListItemText
                      primary={f.model}
                      secondary={f.manufacturer}
                      primaryTypographyProps={{ variant: 'body2', noWrap: true }}
                      secondaryTypographyProps={{ variant: 'caption', noWrap: true }}
                    />
                  </ListItem>
                ))}
              </List>
            </Collapse>
          </Box>
        ))}
        {Object.keys(grouped).length === 0 && (
          <ListItem>
            <ListItemText secondary="No fixtures in library" />
          </ListItem>
        )}
      </List>
    </Box>
  );
}
