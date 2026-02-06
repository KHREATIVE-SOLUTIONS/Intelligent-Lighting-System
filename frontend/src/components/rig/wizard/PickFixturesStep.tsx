import { useState, useEffect } from 'react';
import {
  Box, Typography, Button, IconButton, Grid, TextField,
  Select, MenuItem, FormControl, InputLabel, Table, TableBody,
  TableCell, TableHead, TableRow,
} from '@mui/material';
import { Add as AddIcon, Remove as RemoveIcon, Delete as DeleteIcon } from '@mui/icons-material';
import { fixturesApi } from '../../../services/api';
import type { Fixture } from '../../../types';

interface WizardFixture {
  fixture_id: number;
  fixture_name: string;
  count: number;
  mode_id?: number;
  mode_channel_count?: number;
  group_name: string;
}

interface PickFixturesStepProps {
  fixtures: WizardFixture[];
  onChange: (fixtures: WizardFixture[]) => void;
  suggestedFixtures?: Array<{ fixture_type: string; count: number; group_name: string }>;
}

export default function PickFixturesStep({ fixtures, onChange, suggestedFixtures }: PickFixturesStepProps) {
  const [library, setLibrary] = useState<Fixture[]>([]);

  useEffect(() => {
    fixturesApi.list(1, 100).then((data) => setLibrary(data.items)).catch(() => {});
  }, []);

  // Auto-populate from suggestions if empty
  useEffect(() => {
    if (fixtures.length === 0 && suggestedFixtures && library.length > 0) {
      const mapped = suggestedFixtures.map((s) => {
        const match = library.find((f) => f.fixture_type === s.fixture_type);
        return {
          fixture_id: match?.id || 0,
          fixture_name: match ? `${match.manufacturer} ${match.model}` : `(no ${s.fixture_type} in library)`,
          count: s.count,
          mode_id: match?.modes?.[0]?.id,
          mode_channel_count: match?.modes?.[0]?.channel_count,
          group_name: s.group_name,
        };
      });
      onChange(mapped);
    }
  }, [suggestedFixtures, library]);

  const handleAdd = () => {
    onChange([...fixtures, { fixture_id: 0, fixture_name: '', count: 1, group_name: 'Default' }]);
  };

  const handleRemove = (idx: number) => {
    onChange(fixtures.filter((_, i) => i !== idx));
  };

  const handleChange = (idx: number, updates: Partial<WizardFixture>) => {
    onChange(fixtures.map((f, i) => (i === idx ? { ...f, ...updates } : f)));
  };

  const handleFixtureSelect = (idx: number, fixtureId: number) => {
    const f = library.find((fix) => fix.id === fixtureId);
    handleChange(idx, {
      fixture_id: fixtureId,
      fixture_name: f ? `${f.manufacturer} ${f.model}` : '',
      mode_id: f?.modes?.[0]?.id,
      mode_channel_count: f?.modes?.[0]?.channel_count,
    });
  };

  return (
    <Box>
      <Typography variant="h6" gutterBottom>Pick Fixtures</Typography>

      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Fixture</TableCell>
            <TableCell>Qty</TableCell>
            <TableCell>Group</TableCell>
            <TableCell></TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {fixtures.map((f, idx) => (
            <TableRow key={idx}>
              <TableCell>
                <FormControl size="small" fullWidth>
                  <Select
                    value={f.fixture_id}
                    onChange={(e) => handleFixtureSelect(idx, Number(e.target.value))}
                    displayEmpty
                  >
                    <MenuItem value={0}><em>Select fixture...</em></MenuItem>
                    {library.map((lib) => (
                      <MenuItem key={lib.id} value={lib.id}>
                        {lib.manufacturer} {lib.model}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </TableCell>
              <TableCell sx={{ width: 120 }}>
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  <IconButton size="small" onClick={() => handleChange(idx, { count: Math.max(1, f.count - 1) })}>
                    <RemoveIcon fontSize="small" />
                  </IconButton>
                  <Typography sx={{ mx: 1 }}>{f.count}</Typography>
                  <IconButton size="small" onClick={() => handleChange(idx, { count: f.count + 1 })}>
                    <AddIcon fontSize="small" />
                  </IconButton>
                </Box>
              </TableCell>
              <TableCell>
                <TextField
                  size="small"
                  value={f.group_name}
                  onChange={(e) => handleChange(idx, { group_name: e.target.value })}
                />
              </TableCell>
              <TableCell>
                <IconButton size="small" color="error" onClick={() => handleRemove(idx)}>
                  <DeleteIcon fontSize="small" />
                </IconButton>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Button startIcon={<AddIcon />} onClick={handleAdd} sx={{ mt: 1 }}>
        Add Row
      </Button>
    </Box>
  );
}
