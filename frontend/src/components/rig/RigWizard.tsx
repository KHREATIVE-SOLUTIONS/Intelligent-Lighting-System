import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Stepper,
  Step,
  StepLabel,
  Button,
  Paper,
  Alert,
} from '@mui/material';
import { wizardApi } from '../../services/api';
import VenueTypeStep from './wizard/VenueTypeStep';
import StageDimensionsStep from './wizard/StageDimensionsStep';
import PickFixturesStep, { fixtureStepBlocker } from './wizard/PickFixturesStep';
import ReviewPlacementStep from './wizard/ReviewPlacementStep';
import type { MountingPosition, WizardFixture } from './wizard/PickFixturesStep';
import type { VenuePreset } from '../../types';

const STEPS = ['Your room', 'Stage size', 'Your lights', 'Check & create'];

const DEFAULT_CHANNEL_COUNT = 16;

export default function RigWizard() {
  const navigate = useNavigate();
  const [activeStep, setActiveStep] = useState(0);
  const [error, setError] = useState('');

  // Wizard state
  const [selectedPreset, setSelectedPreset] = useState<VenuePreset | null>(null);
  const [stageWidth, setStageWidth] = useState(10);
  const [stageDepth, setStageDepth] = useState(8);
  const [stageHeight, setStageHeight] = useState(6);
  const [fixtures, setFixtures] = useState<WizardFixture[]>([]);
  const [placements, setPlacements] = useState<any[]>([]);
  const [rigName, setRigName] = useState('');
  const [creating, setCreating] = useState(false);
  const [placing, setPlacing] = useState(false);

  const handlePresetSelect = (preset: VenuePreset) => {
    if (selectedPreset?.key === preset.key) return;
    setSelectedPreset(preset);
    setStageWidth(preset.stage_width);
    setStageDepth(preset.stage_depth);
    setStageHeight(preset.stage_height);
    setRigName(`${preset.name} Rig`);
    // A different room type means a different suggested kit; the lights step
    // refills itself from the new preset.
    setFixtures([]);
    setPlacements([]);
  };

  const handlePresetClear = () => {
    setSelectedPreset(null);
    setFixtures([]);
    setPlacements([]);
  };

  const handleNext = async () => {
    if (activeStep === 2) {
      setPlacing(true);
      setError('');
      try {
        const data = await wizardApi.autoPlace({
          stage_width: stageWidth,
          stage_depth: stageDepth,
          stage_height: stageHeight,
          fixtures: fixtures.map((f) => ({
            fixture_id: f.fixture_id,
            count: f.count,
            group_name: f.group_name,
            mounting_position: f.mounting_position,
            mode_id: f.mode_id,
            mode_channel_count: f.mode_channel_count || DEFAULT_CHANNEL_COUNT,
          })),
        });
        setPlacements(enrichPlacements(data.placements || [], fixtures));
      } catch (err: any) {
        setError(
          err?.response?.data?.detail ||
          'We could not work out where to put the lights. Check the box is still reachable and try again.'
        );
        return;
      } finally {
        setPlacing(false);
      }
    }
    setActiveStep((prev) => prev + 1);
  };

  const handleBack = () => setActiveStep((prev) => prev - 1);

  // The stage-size step comes before the lights step, so on the way forward
  // `fixtures` is still empty and the plan would be a bare outline. The preset
  // already declares the kit and where each group hangs - the same three fields
  // indicativeMarkers reads - so the plan shows that until the real picks exist.
  const planFixtures = useMemo<WizardFixture[]>(() => {
    if (fixtures.length > 0) return fixtures;
    if (!selectedPreset) return [];
    return (selectedPreset.suggested_fixtures || []).map((s, index) => ({
      fixture_id: -1 - index,
      fixture_name: s.group_name,
      count: s.count,
      group_name: s.group_name,
      mounting_position: (s.mounting_position as MountingPosition) || 'mid_truss',
      requested_type: s.fixture_type,
    }));
  }, [fixtures, selectedPreset]);

  const handleCreate = async () => {
    setCreating(true);
    setError('');
    try {
      const result = await wizardApi.createRig({
        rig_name: rigName.trim(),
        venue: selectedPreset?.name,
        stage_width: stageWidth,
        stage_depth: stageDepth,
        stage_height: stageHeight,
        placements,
      });
      navigate(`/rigs/${result.id}`);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create rig');
    } finally {
      setCreating(false);
    }
  };

  const blockReason = (): string | null => {
    switch (activeStep) {
      case 0:
        return null; // Picking a room type is optional.
      case 1:
        if (!(stageWidth > 0)) return 'Enter how many metres the stage is across.';
        if (!(stageDepth > 0)) return 'Enter how many metres deep the stage is.';
        if (!(stageHeight > 0)) return 'Enter how high off the floor the lights hang.';
        return null;
      case 2:
        return fixtureStepBlocker(fixtures);
      case 3:
        if (rigName.trim().length === 0) return 'Give this rig a name before you create it.';
        if (placements.length === 0) {
          return 'There are no lights to save. Go back to the lights step and choose at least one.';
        }
        return null;
      default:
        return null;
    }
  };

  const reason = blockReason();
  const busy = placing || creating;

  return (
    <Box sx={{ maxWidth: 900, mx: 'auto' }}>
      <Typography variant="h5" gutterBottom>
        Set up your lights
      </Typography>

      <Stepper activeStep={activeStep} sx={{ mb: 3 }}>
        {STEPS.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      <Paper sx={{ p: 3, mb: 3 }}>
        {activeStep === 0 && (
          <VenueTypeStep
            selected={selectedPreset}
            onSelect={handlePresetSelect}
            onClear={handlePresetClear}
          />
        )}
        {activeStep === 1 && (
          <StageDimensionsStep
            width={stageWidth}
            depth={stageDepth}
            height={stageHeight}
            onWidthChange={setStageWidth}
            onDepthChange={setStageDepth}
            onHeightChange={setStageHeight}
            fixtures={planFixtures}
          />
        )}
        {activeStep === 2 && (
          <PickFixturesStep
            fixtures={fixtures}
            onChange={setFixtures}
            suggestedFixtures={selectedPreset?.suggested_fixtures}
          />
        )}
        {activeStep === 3 && (
          <ReviewPlacementStep
            rigName={rigName}
            onRigNameChange={setRigName}
            stageWidth={stageWidth}
            stageDepth={stageDepth}
            stageHeight={stageHeight}
            placements={placements}
          />
        )}
      </Paper>

      {reason && (
        <Alert severity="info" sx={{ mb: 2 }}>
          {activeStep < STEPS.length - 1 ? 'Next is greyed out: ' : 'Create Rig is greyed out: '}
          {reason}
        </Alert>
      )}

      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button onClick={() => navigate('/rigs')} color="inherit">
          Cancel
        </Button>
        <Box sx={{ display: 'flex', gap: 1 }}>
          {activeStep > 0 && (
            <Button onClick={handleBack} disabled={busy}>Back</Button>
          )}
          {activeStep < STEPS.length - 1 ? (
            <Button variant="contained" onClick={handleNext} disabled={reason !== null || busy}>
              {placing ? 'Working out positions...' : 'Next'}
            </Button>
          ) : (
            <Button variant="contained" onClick={handleCreate} disabled={reason !== null || busy}>
              {creating ? 'Creating...' : 'Create Rig'}
            </Button>
          )}
        </Box>
      </Box>
    </Box>
  );
}

/**
 * Carry the per-group facts the placement endpoint does not echo back onto each
 * placement, so the review screen can total channels and the backend receives the
 * mounting position with the rig.
 *
 * compute_placement emits `count` placements per group, in the order the groups
 * were sent, so index alignment is exact whenever the totals match. The group-name
 * lookup is the fallback for when they do not.
 */
function enrichPlacements(placements: any[], fixtures: WizardFixture[]): any[] {
  const expanded: WizardFixture[] = [];
  fixtures.forEach((f) => {
    for (let i = 0; i < f.count; i += 1) expanded.push(f);
  });
  const aligned = expanded.length === placements.length;

  return placements.map((p, idx) => {
    const source = (aligned ? expanded[idx] : undefined)
      ?? fixtures.find((f) => f.group_name === p.group_name);
    return {
      ...p,
      mounting_position: p.mounting_position ?? source?.mounting_position,
      channel_count:
        p.channel_count ?? source?.mode_channel_count ?? DEFAULT_CHANNEL_COUNT,
    };
  });
}
