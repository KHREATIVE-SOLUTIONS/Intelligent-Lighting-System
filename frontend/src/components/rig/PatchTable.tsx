import { useMemo } from 'react';
import {
  Box,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  Tabs,
  Tab,
} from '@mui/material';
import { Warning as WarningIcon } from '@mui/icons-material';
import type { RigFixture, PatchConflict } from '../../types';

interface PatchTableProps {
  fixtures: RigFixture[];
  conflicts?: PatchConflict[];
  selectedUniverse?: number;
  onUniverseChange?: (universe: number) => void;
}

export default function PatchTable({
  fixtures,
  conflicts = [],
  selectedUniverse = 0,
  onUniverseChange,
}: PatchTableProps) {
  // Get unique universes
  const universes = useMemo(() => {
    const unis = new Set(fixtures.map((f) => f.universe));
    if (unis.size === 0) unis.add(0);
    return Array.from(unis).sort();
  }, [fixtures]);

  // Fixtures in selected universe
  const uniFixtures = useMemo(
    () =>
      fixtures
        .filter((f) => f.universe === selectedUniverse)
        .sort((a, b) => a.dmx_address - b.dmx_address),
    [fixtures, selectedUniverse]
  );

  // Build address bar segments
  const addressBar = useMemo(() => {
    const segments: Array<{ start: number; width: number; color: string; name: string; conflict: boolean }> = [];
    const conflictIds = new Set<number>();
    conflicts.forEach((c) => {
      if (c.universe === selectedUniverse) {
        conflictIds.add(c.fixture_a_id);
        conflictIds.add(c.fixture_b_id);
      }
    });

    for (const f of uniFixtures) {
      const channelCount = f.fixture?.modes?.find((m) => m.id === f.mode_id)?.channel_count || 16;
      segments.push({
        start: f.dmx_address,
        width: channelCount,
        color: conflictIds.has(f.id) ? '#f44336' : '#4caf50',
        name: f.name || `${f.dmx_address}`,
        conflict: conflictIds.has(f.id),
      });
    }
    return segments;
  }, [uniFixtures, conflicts, selectedUniverse]);

  // Calculate usage
  const usedChannels = addressBar.reduce((sum, s) => sum + s.width, 0);

  return (
    <Box sx={{ height: '100%', overflow: 'auto' }}>
      <Typography variant="subtitle2" sx={{ px: 1, pt: 1 }}>
        DMX Patch
      </Typography>

      {universes.length > 1 && (
        <Tabs
          value={selectedUniverse}
          onChange={(_, v) => onUniverseChange?.(v)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ minHeight: 32 }}
        >
          {universes.map((u) => (
            <Tab key={u} label={`U${u}`} value={u} sx={{ minHeight: 32, minWidth: 48, py: 0 }} />
          ))}
        </Tabs>
      )}

      {/* Visual address bar */}
      <Box sx={{ px: 1, py: 0.5 }}>
        <Box
          sx={{
            width: '100%',
            height: 20,
            bgcolor: '#1a1a2e',
            borderRadius: 0.5,
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          {addressBar.map((seg, i) => (
            <Box
              key={i}
              sx={{
                position: 'absolute',
                left: `${((seg.start - 1) / 512) * 100}%`,
                width: `${(seg.width / 512) * 100}%`,
                height: '100%',
                bgcolor: seg.color,
                opacity: 0.8,
                '&:hover': { opacity: 1 },
              }}
              title={`${seg.name}: ${seg.start}-${seg.start + seg.width - 1}`}
            />
          ))}
        </Box>
        <Typography variant="caption" color="text.secondary">
          {usedChannels}/512 channels used ({((usedChannels / 512) * 100).toFixed(0)}%)
        </Typography>
      </Box>

      {/* Fixture table */}
      <TableContainer>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Addr</TableCell>
              <TableCell>Name</TableCell>
              <TableCell>Ch</TableCell>
              <TableCell></TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {uniFixtures.map((f) => {
              const mode = f.fixture?.modes?.find((m) => m.id === f.mode_id);
              const isConflict = conflicts.some(
                (c) =>
                  c.universe === selectedUniverse &&
                  (c.fixture_a_id === f.id || c.fixture_b_id === f.id)
              );
              return (
                <TableRow key={f.id} sx={isConflict ? { bgcolor: 'rgba(244,67,54,0.08)' } : {}}>
                  <TableCell>{f.dmx_address}</TableCell>
                  <TableCell sx={{ maxWidth: 100 }}>
                    <Typography variant="body2" noWrap>
                      {f.name || f.fixture?.model || `Fixture ${f.id}`}
                    </Typography>
                  </TableCell>
                  <TableCell>{mode?.channel_count || '?'}</TableCell>
                  <TableCell>
                    {isConflict && <WarningIcon color="error" fontSize="small" />}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
