import { useState } from 'react';
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
import PickFixturesStep from './wizard/PickFixturesStep';
import ReviewPlacementStep from './wizard/ReviewPlacementStep';
import type { VenuePreset } from '../../types';

const STEPS = ['Venue Type', 'Stage Size', 'Pick Fixtures', 'Review & Create'];

interface WizardFixture {
  fixture_id: number;
  fixture_name: string;
  count: number;
  mode_id?: number;
  mode_channel_count?: number;
  group_name: string;
}

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

  const handlePresetSelect = (preset: VenuePreset) => {
    setSelectedPreset(preset);
    setStageWidth(preset.stage_width);
    setStageDepth(preset.stage_depth);
    setStageHeight(preset.stage_height);
    setRigName(`${preset.name} Rig`);
  };

  const handleNext = async () => {
    if (activeStep === 2) {
      // Compute placements before review
      try {
        const data = await wizardApi.autoPlace({
          stage_width: stageWidth,
          stage_depth: stageDepth,
          stage_height: stageHeight,
          fixtures: fixtures.map((f) => ({
            fixture_id: f.fixture_id,
            count: f.count,
            group_name: f.group_name,
            mode_id: f.mode_id,
            mode_channel_count: f.mode_channel_count || 16,
          })),
        });
        setPlacements(data.placements || []);
      } catch {
        setError('Failed to compute placements');
        return;
      }
    }
    setActiveStep((prev) => prev + 1);
  };

  const handleBack = () => setActiveStep((prev) => prev - 1);

  const handleCreate = async () => {
    setCreating(true);
    setError('');
    try {
      const result = await wizardApi.createRig({
        rig_name: rigName,
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

  const canNext = () => {
    switch (activeStep) {
      case 0: return true; // Preset is optional
      case 1: return stageWidth > 0 && stageDepth > 0 && stageHeight > 0;
      case 2: return fixtures.length > 0 && fixtures.every((f) => f.fixture_id > 0);
      case 3: return rigName.length > 0 && placements.length > 0;
      default: return false;
    }
  };

  return (
    <Box sx={{ maxWidth: 900, mx: 'auto' }}>
      <Typography variant="h5" gutterBottom>
        Quick Rig Setup
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

      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
        <Button onClick={() => navigate('/rigs')} color="inherit">
          Cancel
        </Button>
        <Box sx={{ display: 'flex', gap: 1 }}>
          {activeStep > 0 && (
            <Button onClick={handleBack}>Back</Button>
          )}
          {activeStep < STEPS.length - 1 ? (
            <Button variant="contained" onClick={handleNext} disabled={!canNext()}>
              Next
            </Button>
          ) : (
            <Button variant="contained" onClick={handleCreate} disabled={!canNext() || creating}>
              {creating ? 'Creating...' : 'Create Rig'}
            </Button>
          )}
        </Box>
      </Box>
    </Box>
  );
}
