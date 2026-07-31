import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert, AlertTitle, Box, Button, Chip, CircularProgress, FormControl,
  Grid, IconButton, InputLabel, MenuItem, Paper, Select, Stack, TextField,
  Tooltip, Typography,
} from '@mui/material';
import {
  Add as AddIcon,
  Remove as RemoveIcon,
  Delete as DeleteIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';
import { fixturesApi } from '../../../services/api';
import type { Fixture } from '../../../types';

/**
 * Where a group of lights is physically mounted. The placement maths reads this
 * instead of guessing from the group name, so renaming a group never moves it.
 */
export type MountingPosition =
  | 'front_truss'
  | 'mid_truss'
  | 'back_truss'
  | 'ceiling'
  | 'side_left'
  | 'side_right'
  | 'floor';

export interface MountingOption {
  value: MountingPosition;
  label: string;
  hint: string;
}

export const MOUNTING_POSITIONS: MountingOption[] = [
  {
    value: 'front_truss',
    label: 'Bar at the front of the stage',
    hint: 'Hanging above the front edge, shining back at the performers.',
  },
  {
    value: 'mid_truss',
    label: 'Bar over the middle of the stage',
    hint: 'Hanging halfway back, straight above the performers.',
  },
  {
    value: 'back_truss',
    label: 'Bar behind the performers',
    hint: 'At the back wall, shining forwards or up the backdrop.',
  },
  {
    value: 'ceiling',
    label: 'Fixed to the ceiling',
    hint: 'On the room ceiling above the stage - the highest thing in the room.',
  },
  {
    value: 'side_left',
    label: 'Left side of the stage',
    hint: 'On a stand or wall to your left as you look at the stage.',
  },
  {
    value: 'side_right',
    label: 'Right side of the stage',
    hint: 'On a stand or wall to your right as you look at the stage.',
  },
  {
    value: 'floor',
    label: 'Standing on the floor',
    hint: 'Sitting on the deck, shining upwards.',
  },
];

export const MOUNTING_LABELS: Record<string, string> = MOUNTING_POSITIONS.reduce(
  (acc, option) => ({ ...acc, [option.value]: option.label }),
  {} as Record<string, string>
);

/** Plain-English names for the library's fixture_type codes. */
export const FIXTURE_TYPE_LABELS: Record<string, string> = {
  moving_head: 'moving light',
  led_par: 'LED par can',
  led_bar: 'LED bar',
  wash: 'wash light',
  spot: 'spotlight',
  beam: 'narrow beam',
  strobe: 'strobe',
  laser: 'laser',
  effect: 'effect light',
  dimmer: 'dimmer channel',
  other: 'light',
};

export const describeType = (type?: string): string =>
  (type && FIXTURE_TYPE_LABELS[type]) || type || 'light';

/**
 * Ordered substitutes for each fixture type, nearest first. A venue's library
 * rarely holds every type a preset asks for, so a preset must degrade to the
 * closest thing on the shelf rather than dead-ending the wizard.
 */
const TYPE_FALLBACKS: Record<string, string[]> = {
  moving_head: ['spot', 'beam', 'wash', 'led_par', 'led_bar', 'effect', 'strobe', 'laser', 'dimmer', 'other'],
  spot: ['moving_head', 'beam', 'wash', 'led_par', 'led_bar', 'effect', 'strobe', 'laser', 'dimmer', 'other'],
  beam: ['spot', 'moving_head', 'laser', 'effect', 'wash', 'led_par', 'led_bar', 'strobe', 'dimmer', 'other'],
  wash: ['led_par', 'led_bar', 'moving_head', 'spot', 'beam', 'dimmer', 'effect', 'strobe', 'laser', 'other'],
  led_par: ['wash', 'led_bar', 'spot', 'moving_head', 'beam', 'dimmer', 'effect', 'strobe', 'laser', 'other'],
  led_bar: ['led_par', 'wash', 'strobe', 'effect', 'spot', 'moving_head', 'beam', 'dimmer', 'laser', 'other'],
  strobe: ['effect', 'led_bar', 'led_par', 'beam', 'wash', 'spot', 'moving_head', 'laser', 'dimmer', 'other'],
  laser: ['beam', 'effect', 'moving_head', 'spot', 'strobe', 'led_bar', 'wash', 'led_par', 'dimmer', 'other'],
  effect: ['laser', 'strobe', 'led_bar', 'beam', 'moving_head', 'spot', 'wash', 'led_par', 'dimmer', 'other'],
  dimmer: ['led_par', 'wash', 'led_bar', 'spot', 'moving_head', 'beam', 'effect', 'strobe', 'laser', 'other'],
  other: ['led_par', 'wash', 'spot', 'moving_head', 'led_bar', 'beam', 'effect', 'strobe', 'laser', 'dimmer'],
};

// Mirrors _DEFAULT_MOUNTING_BY_TYPE in wizard_service.py, so a group defaults to
// the same place whichever side fills it in. Never inferred from the group name.
const DEFAULT_MOUNTING: Record<string, MountingPosition> = {
  led_par: 'front_truss',
  spot: 'front_truss',
  dimmer: 'front_truss',
  wash: 'mid_truss',
  moving_head: 'mid_truss',
  other: 'mid_truss',
  beam: 'back_truss',
  strobe: 'back_truss',
  laser: 'back_truss',
  led_bar: 'floor',
  effect: 'ceiling',
};

const isMountingPosition = (value?: string): value is MountingPosition =>
  Boolean(value) && MOUNTING_POSITIONS.some((option) => option.value === value);

/**
 * Where a group starts out. A venue preset that states its own mounting position
 * wins; otherwise the fixture type decides. Shown to the user and overridable.
 */
export function defaultMounting(fixtureType?: string, stated?: string): MountingPosition {
  if (isMountingPosition(stated)) return stated;
  return (fixtureType && DEFAULT_MOUNTING[fixtureType]) || 'mid_truss';
}

export interface WizardFixture {
  fixture_id: number;
  fixture_name: string;
  count: number;
  mode_id?: number;
  mode_channel_count?: number;
  group_name: string;
  mounting_position: MountingPosition;
  /** Type the venue preset asked for. Kept only so a substitution can be explained. */
  requested_type?: string;
}

/**
 * Why this step will not let the user continue, in words that name the fix.
 * Returns null when the step is complete.
 */
export function fixtureStepBlocker(fixtures: WizardFixture[]): string | null {
  if (fixtures.length === 0) {
    return 'Add at least one light before you continue.';
  }
  const unfilled = fixtures
    .map((f, index) => ({ f, index }))
    .filter(({ f }) => !(f.fixture_id > 0));
  if (unfilled.length === 0) return null;

  const described = unfilled
    .map(({ f, index }) => `row ${index + 1}${f.group_name ? ` (${f.group_name})` : ''}`)
    .join(', ');
  return unfilled.length === 1
    ? `No light is chosen for ${described}. Pick one from the drop-down, or delete that row.`
    : `No light is chosen for ${described}. Pick one for each, or delete those rows.`;
}

interface TypeMatch {
  fixture: Fixture | null;
  exact: boolean;
}

function matchType(library: Fixture[], fixtureType: string): TypeMatch {
  const exact = library.find((f) => f.fixture_type === fixtureType);
  if (exact) return { fixture: exact, exact: true };
  for (const alternative of TYPE_FALLBACKS[fixtureType] ?? []) {
    const near = library.find((f) => f.fixture_type === alternative);
    if (near) return { fixture: near, exact: false };
  }
  return { fixture: null, exact: false };
}

interface PickFixturesStepProps {
  fixtures: WizardFixture[];
  onChange: (fixtures: WizardFixture[]) => void;
  suggestedFixtures?: Array<{
    fixture_type: string;
    count: number;
    group_name: string;
    mounting_position?: string;
  }>;
}

export default function PickFixturesStep({
  fixtures, onChange, suggestedFixtures,
}: PickFixturesStepProps) {
  const [library, setLibrary] = useState<Fixture[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const appliedSuggestions = useRef<unknown>(null);

  const loadLibrary = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      // The list endpoint caps size at 100, so a large library needs several passes.
      const collected: Fixture[] = [];
      for (let page = 1; page <= 20; page += 1) {
        const data = await fixturesApi.list(page, 100);
        const items = data.items ?? [];
        collected.push(...items);
        if (items.length === 0 || collected.length >= (data.total ?? collected.length)) break;
      }
      setLibrary(collected);
    } catch (err: any) {
      setLoadError(
        err?.response?.data?.detail ||
        err?.message ||
        'The light library could not be reached.'
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLibrary();
  }, [loadLibrary]);

  // Fill the list from the venue preset once, the first time the library arrives.
  useEffect(() => {
    if (!suggestedFixtures || library.length === 0) return;
    if (appliedSuggestions.current === suggestedFixtures) return;
    if (fixtures.length > 0) return;

    appliedSuggestions.current = suggestedFixtures;
    onChange(
      suggestedFixtures.map((s) => {
        const { fixture: match } = matchType(library, s.fixture_type);
        return {
          fixture_id: match?.id ?? 0,
          fixture_name: match ? `${match.manufacturer} ${match.model}` : '',
          count: s.count,
          mode_id: match?.modes?.[0]?.id,
          mode_channel_count: match?.modes?.[0]?.channel_count,
          group_name: s.group_name,
          mounting_position: defaultMounting(s.fixture_type, s.mounting_position),
          requested_type: s.fixture_type,
        };
      })
    );
  }, [suggestedFixtures, library, fixtures.length, onChange]);

  const handleAdd = () => {
    onChange([
      ...fixtures,
      {
        fixture_id: 0,
        fixture_name: '',
        count: 1,
        group_name: `Group ${fixtures.length + 1}`,
        mounting_position: 'mid_truss',
      },
    ]);
  };

  const handleRemove = (idx: number) => {
    onChange(fixtures.filter((_, i) => i !== idx));
  };

  const handleChange = (idx: number, updates: Partial<WizardFixture>) => {
    onChange(fixtures.map((f, i) => (i === idx ? { ...f, ...updates } : f)));
  };

  const handleFixtureSelect = (idx: number, fixtureId: number) => {
    const picked = library.find((fix) => fix.id === fixtureId);
    handleChange(idx, {
      fixture_id: fixtureId,
      fixture_name: picked ? `${picked.manufacturer} ${picked.model}` : '',
      mode_id: picked?.modes?.[0]?.id,
      mode_channel_count: picked?.modes?.[0]?.channel_count,
      // The user has spoken; stop explaining what the preset originally wanted.
      requested_type: undefined,
    });
  };

  const handleModeSelect = (idx: number, modeId: number) => {
    const row = fixtures[idx];
    const picked = library.find((fix) => fix.id === row.fixture_id);
    const mode = picked?.modes?.find((m) => m.id === modeId);
    handleChange(idx, {
      mode_id: modeId,
      mode_channel_count: mode?.channel_count,
    });
  };

  const dropUnfillable = () => {
    onChange(fixtures.filter((f) => f.fixture_id > 0));
  };

  const substituted = fixtures.filter((f) => {
    if (!f.requested_type || !(f.fixture_id > 0)) return false;
    const chosen = library.find((l) => l.id === f.fixture_id);
    return Boolean(chosen && chosen.fixture_type !== f.requested_type);
  });
  const unfilled = fixtures.filter((f) => !(f.fixture_id > 0));
  const totalLights = fixtures.reduce((sum, f) => sum + (f.fixture_id > 0 ? f.count : 0), 0);
  const totalChannels = fixtures.reduce(
    (sum, f) => sum + (f.fixture_id > 0 ? f.count * (f.mode_channel_count || 16) : 0),
    0
  );

  return (
    <Box>
      <Typography variant="h6" gutterBottom>Choose your lights</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Tell us what you own and roughly where each set of lights hangs. You can change
        any of this later.
      </Typography>

      {loading && (
        <Stack direction="row" spacing={1.5} alignItems="center" sx={{ my: 3 }}>
          <CircularProgress size={20} />
          <Typography variant="body2" color="text.secondary">
            Loading your light library...
          </Typography>
        </Stack>
      )}

      {!loading && loadError && (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" startIcon={<RefreshIcon />} onClick={loadLibrary}>
              Try again
            </Button>
          }
        >
          <AlertTitle>We could not load your light library</AlertTitle>
          {loadError} Until it loads there is nothing to choose from, so this step cannot
          be finished.
        </Alert>
      )}

      {!loading && !loadError && library.length === 0 && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          <AlertTitle>There are no lights in your library yet</AlertTitle>
          Add at least one from the Fixture Library page, then come back here. Nothing on
          this step will work until the library has something in it.
        </Alert>
      )}

      {substituted.length > 0 && (
        <Alert severity="info" sx={{ mb: 2 }}>
          <AlertTitle>
            {substituted.length === 1
              ? 'One suggestion was swapped for the nearest thing you own'
              : `${substituted.length} suggestions were swapped for the nearest thing you own`}
          </AlertTitle>
          The venue preset asked for something your library does not have. We picked the
          closest match so you can carry on. Each swap is marked below.
        </Alert>
      )}

      {unfilled.length > 0 && !loading && (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          action={
            <Button color="inherit" size="small" onClick={dropUnfillable}>
              Drop {unfilled.length === 1 ? 'it' : 'them'}
            </Button>
          }
        >
          <AlertTitle>
            {unfilled.length === 1
              ? '1 row still has no light chosen'
              : `${unfilled.length} rows still have no light chosen`}
          </AlertTitle>
          Pick something from the drop-down, or drop the {unfilled.length === 1 ? 'row' : 'rows'}
          {' '}and carry on without {unfilled.length === 1 ? 'it' : 'them'}.
        </Alert>
      )}

      <Stack spacing={2}>
        {fixtures.map((f, idx) => {
          const chosen = library.find((l) => l.id === f.fixture_id);
          const modes = chosen?.modes ?? [];
          const isSubstitute = Boolean(
            f.requested_type && chosen && chosen.fixture_type !== f.requested_type
          );
          const isUnfillable = Boolean(f.requested_type && !chosen);
          const mounting = MOUNTING_POSITIONS.find((m) => m.value === f.mounting_position);

          return (
            <Paper
              key={idx}
              variant="outlined"
              sx={{
                p: 2,
                borderColor: f.fixture_id > 0 ? 'divider' : 'warning.main',
              }}
            >
              <Grid container spacing={2} alignItems="flex-start">
                <Grid item xs={12} md={5}>
                  <FormControl size="small" fullWidth>
                    <InputLabel id={`fixture-label-${idx}`}>Which light</InputLabel>
                    <Select
                      labelId={`fixture-label-${idx}`}
                      label="Which light"
                      value={library.some((l) => l.id === f.fixture_id) ? f.fixture_id : 0}
                      onChange={(e) => handleFixtureSelect(idx, Number(e.target.value))}
                    >
                      <MenuItem value={0}><em>Choose a light...</em></MenuItem>
                      {library.map((lib) => (
                        <MenuItem key={lib.id} value={lib.id}>
                          {lib.manufacturer} {lib.model} &nbsp;
                          <Typography component="span" variant="caption" color="text.secondary">
                            ({describeType(lib.fixture_type)})
                          </Typography>
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  {modes.length > 1 && (
                    <FormControl size="small" fullWidth sx={{ mt: 1.5 }}>
                      <InputLabel id={`mode-label-${idx}`}>Channel mode</InputLabel>
                      <Select
                        labelId={`mode-label-${idx}`}
                        label="Channel mode"
                        value={modes.some((m) => m.id === f.mode_id) ? f.mode_id : modes[0].id}
                        onChange={(e) => handleModeSelect(idx, Number(e.target.value))}
                      >
                        {modes.map((m) => (
                          <MenuItem key={m.id} value={m.id}>
                            {m.name} - {m.channel_count} channels
                          </MenuItem>
                        ))}
                      </Select>
                      <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                        Match the setting on the back of the light itself.
                      </Typography>
                    </FormControl>
                  )}
                </Grid>

                <Grid item xs={6} md={2}>
                  <Typography variant="caption" color="text.secondary">How many</Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', mt: 0.5 }}>
                    <IconButton
                      size="small"
                      aria-label="one fewer"
                      onClick={() => handleChange(idx, { count: Math.max(1, f.count - 1) })}
                    >
                      <RemoveIcon fontSize="small" />
                    </IconButton>
                    <Typography sx={{ mx: 1, minWidth: 20, textAlign: 'center' }}>{f.count}</Typography>
                    <IconButton
                      size="small"
                      aria-label="one more"
                      onClick={() => handleChange(idx, { count: f.count + 1 })}
                    >
                      <AddIcon fontSize="small" />
                    </IconButton>
                  </Box>
                </Grid>

                <Grid item xs={12} md={4}>
                  <FormControl size="small" fullWidth>
                    <InputLabel id={`mount-label-${idx}`}>Where they are</InputLabel>
                    <Select
                      labelId={`mount-label-${idx}`}
                      label="Where they are"
                      value={f.mounting_position}
                      onChange={(e) =>
                        handleChange(idx, { mounting_position: e.target.value as MountingPosition })
                      }
                    >
                      {MOUNTING_POSITIONS.map((option) => (
                        <MenuItem key={option.value} value={option.value}>
                          {option.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  {mounting && (
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                      {mounting.hint}
                    </Typography>
                  )}
                </Grid>

                <Grid item xs={6} md={1} sx={{ textAlign: 'right' }}>
                  <Tooltip title="Remove this row">
                    <IconButton
                      size="small"
                      color="error"
                      aria-label="remove this row"
                      onClick={() => handleRemove(idx)}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Grid>

                <Grid item xs={12}>
                  <TextField
                    size="small"
                    fullWidth
                    label="Call this group"
                    value={f.group_name}
                    onChange={(e) => handleChange(idx, { group_name: e.target.value })}
                    helperText="Just a name you will recognise later, such as Front Wash or Dance Floor."
                  />
                </Grid>

                {isSubstitute && chosen && (
                  <Grid item xs={12}>
                    <Alert severity="info" variant="outlined">
                      You have no {describeType(f.requested_type)} in your library, so we
                      picked the closest thing you do own: {chosen.manufacturer} {chosen.model}
                      {' '}({describeType(chosen.fixture_type)}). Change it above if you have
                      something better, or remove the row.
                    </Alert>
                  </Grid>
                )}

                {isUnfillable && (
                  <Grid item xs={12}>
                    <Alert
                      severity="warning"
                      variant="outlined"
                      action={
                        <Button color="inherit" size="small" onClick={() => handleRemove(idx)}>
                          Remove row
                        </Button>
                      }
                    >
                      Nothing in your library can stand in for a {describeType(f.requested_type)}.
                      Pick a light yourself, or remove this row and carry on without it.
                    </Alert>
                  </Grid>
                )}
              </Grid>
            </Paper>
          );
        })}
      </Stack>

      <Stack direction="row" spacing={2} alignItems="center" sx={{ mt: 2 }}>
        <Button startIcon={<AddIcon />} onClick={handleAdd} variant="outlined">
          Add another light
        </Button>
        {totalLights > 0 && (
          <>
            <Chip size="small" label={`${totalLights} lights`} />
            <Chip size="small" label={`${totalChannels} channels`} />
          </>
        )}
      </Stack>
    </Box>
  );
}
