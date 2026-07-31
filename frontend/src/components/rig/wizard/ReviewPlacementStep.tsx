import { useState } from 'react';
import {
  Alert, AlertTitle, Box, Button, Chip, Collapse, Paper, Stack, Table, TableBody,
  TableCell, TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import { StagePlan, colorForIndex } from './StageDimensionsStep';
import type { PlanMarker } from './StageDimensionsStep';
import { MOUNTING_LABELS } from './PickFixturesStep';

const CHANNELS_PER_UNIVERSE = 512;
const DEFAULT_CHANNEL_COUNT = 16;

interface Placement {
  name?: string;
  group_name?: string;
  universe?: number;
  dmx_address?: number;
  position_x?: number;
  position_y?: number;
  position_z?: number;
  channel_count?: number;
  mounting_position?: string;
  [key: string]: unknown;
}

interface ReviewPlacementStepProps {
  rigName: string;
  onRigNameChange: (name: string) => void;
  stageWidth: number;
  stageDepth: number;
  stageHeight: number;
  placements: Placement[];
}

interface UniverseSummary {
  universe: number;
  lights: number;
  firstChannel: number;
  lastChannel: number;
  used: number;
}

export default function ReviewPlacementStep({
  rigName, onRigNameChange, stageWidth, stageDepth, stageHeight, placements,
}: ReviewPlacementStepProps) {
  const [showPatch, setShowPatch] = useState(false);

  const channelsOf = (p: Placement) => p.channel_count ?? DEFAULT_CHANNEL_COUNT;

  const groupNames: string[] = [];
  placements.forEach((p) => {
    const name = p.group_name || 'Ungrouped';
    if (!groupNames.includes(name)) groupNames.push(name);
  });
  const colorOfGroup = (name?: string) =>
    colorForIndex(Math.max(0, groupNames.indexOf(name || 'Ungrouped')));

  const markers: PlanMarker[] = placements.map((p, idx) => ({
    id: `p-${idx}`,
    x: p.position_x ?? 0,
    z: p.position_z ?? 0,
    color: colorOfGroup(p.group_name),
    label: `${p.name ?? `Light ${idx + 1}`} - universe ${p.universe ?? 0}, channel ${p.dmx_address ?? 1}`,
  }));

  const totalChannels = placements.reduce((sum, p) => sum + channelsOf(p), 0);

  const universeMap = new Map<number, UniverseSummary>();
  placements.forEach((p) => {
    const universe = p.universe ?? 0;
    const start = p.dmx_address ?? 1;
    const end = start + channelsOf(p) - 1;
    const entry = universeMap.get(universe) ?? {
      universe,
      lights: 0,
      firstChannel: start,
      lastChannel: end,
      used: 0,
    };
    entry.lights += 1;
    entry.firstChannel = Math.min(entry.firstChannel, start);
    entry.lastChannel = Math.max(entry.lastChannel, end);
    entry.used += channelsOf(p);
    universeMap.set(universe, entry);
  });
  const universes = Array.from(universeMap.values()).sort((a, b) => a.universe - b.universe);
  const overfull = universes.filter((u) => u.lastChannel > CHANNELS_PER_UNIVERSE);

  const halfW = stageWidth / 2;
  const halfD = stageDepth / 2;
  const offStage = markers.filter(
    (m) => Math.abs(m.x) > halfW + 0.75 || m.z > halfD + 0.75 || m.z < -halfD - 0.75
  );

  const groupCounts = groupNames.map((name) => ({
    name,
    count: placements.filter((p) => (p.group_name || 'Ungrouped') === name).length,
    color: colorOfGroup(name),
  }));

  return (
    <Box>
      <Typography variant="h6" gutterBottom>Check it over</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        This is the rig we are about to save. Nothing here is permanent - you can move
        lights around on the floor plan afterwards.
      </Typography>

      <TextField
        label="Name this rig"
        value={rigName}
        onChange={(e) => onRigNameChange(e.target.value)}
        fullWidth
        sx={{ mb: 2 }}
        helperText="Something you will recognise, such as Main Bar or Back Room."
      />

      {placements.length === 0 ? (
        <Alert severity="warning">
          <AlertTitle>There is nothing to create yet</AlertTitle>
          No positions were worked out for this rig. Go back to the lights step, make sure
          each row has a light chosen, then press Next again.
        </Alert>
      ) : (
        <>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
            <Chip color="primary" label={`${placements.length} lights`} />
            <Chip variant="outlined" label={`${totalChannels} channels in total`} />
            <Chip
              variant="outlined"
              label={
                universes.length === 1
                  ? '1 DMX line (universe)'
                  : `${universes.length} DMX lines (universes)`
              }
            />
            <Chip variant="outlined" label={`Stage ${stageWidth} x ${stageDepth} m, ${stageHeight} m high`} />
          </Stack>

          {overfull.length > 0 && (
            <Alert severity="error" sx={{ mb: 2 }}>
              <AlertTitle>One DMX line is over its limit</AlertTitle>
              A DMX line only carries {CHANNELS_PER_UNIVERSE} channels.{' '}
              {overfull
                .map((u) => `Universe ${u.universe} needs ${u.lastChannel}`)
                .join('; ')}
              . Go back and reduce the number of lights, or split them across more lines.
            </Alert>
          )}

          <Typography variant="subtitle2" gutterBottom>
            Where the lights will be
          </Typography>
          <StagePlan
            width={stageWidth}
            depth={stageDepth}
            markers={markers}
            viewHeight={360}
            note="Each dot is one light, at the position we are about to save. Hover a dot to see its name and channel."
          />

          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 1.5, mb: 2 }}>
            {groupCounts.map((g) => (
              <Chip
                key={g.name}
                size="small"
                label={`${g.name} (${g.count})`}
                sx={{ bgcolor: g.color, color: '#101018', fontWeight: 500 }}
              />
            ))}
          </Stack>

          {offStage.length > 0 && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              <AlertTitle>
                {offStage.length === 1
                  ? '1 light is placed off the stage'
                  : `${offStage.length} lights are placed off the stage`}
              </AlertTitle>
              They are drawn outside the stage outline above. That is fine if they really
              hang out over the room - but if it looks wrong, go back and check the stage
              size and where you said each group is mounted.
            </Alert>
          )}

          <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
            <Typography variant="subtitle2" gutterBottom>
              DMX lines used
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>DMX line</TableCell>
                  <TableCell align="right">Lights</TableCell>
                  <TableCell align="right">Channels used</TableCell>
                  <TableCell align="right">Channels free</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {universes.map((u) => (
                  <TableRow key={u.universe}>
                    <TableCell>Universe {u.universe}</TableCell>
                    <TableCell align="right">{u.lights}</TableCell>
                    <TableCell align="right">
                      {u.used} (channels {u.firstChannel} to {u.lastChannel})
                    </TableCell>
                    <TableCell align="right">
                      {Math.max(0, CHANNELS_PER_UNIVERSE - u.lastChannel)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>

          <Button size="small" onClick={() => setShowPatch((v) => !v)}>
            {showPatch ? 'Hide the full list' : 'Show the full list of lights'}
          </Button>
          <Collapse in={showPatch}>
            <Box sx={{ overflowX: 'auto', mt: 1 }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>#</TableCell>
                    <TableCell>Name</TableCell>
                    <TableCell>Group</TableCell>
                    <TableCell>Where it is</TableCell>
                    <TableCell>DMX line</TableCell>
                    <TableCell align="right">Start channel</TableCell>
                    <TableCell align="right">Channels</TableCell>
                    <TableCell>Spot on the plan (m)</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {placements.map((p, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{idx + 1}</TableCell>
                      <TableCell>{p.name}</TableCell>
                      <TableCell>{p.group_name}</TableCell>
                      <TableCell>
                        {p.mounting_position
                          ? MOUNTING_LABELS[p.mounting_position] ?? p.mounting_position
                          : '-'}
                      </TableCell>
                      <TableCell>Universe {p.universe ?? 0}</TableCell>
                      <TableCell align="right">{p.dmx_address}</TableCell>
                      <TableCell align="right">{channelsOf(p)}</TableCell>
                      <TableCell>
                        {(p.position_x ?? 0).toFixed(1)} across,{' '}
                        {(p.position_z ?? 0).toFixed(1)} deep,{' '}
                        {(p.position_y ?? 0).toFixed(1)} up
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          </Collapse>
        </>
      )}
    </Box>
  );
}
