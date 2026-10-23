import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, Button, Card, CardContent, Collapse, Typography } from '@mui/material';
import {
  CheckCircle as DoneIcon,
  RadioButtonUnchecked as TodoIcon,
  Warning as WarnIcon,
} from '@mui/icons-material';
import { rigsApi } from '../../services/api';
import { useHealthStore } from '../../stores/healthStore';
import { readAudioHealth, readDmxHealth } from '../../utils/showHealth';
import {
  buildSetupSteps,
  isReadyForShow,
  type ActiveRigSummary,
  type StepState,
} from '../../utils/setupChecklist';

const STATE_ICON: Record<StepState, JSX.Element> = {
  done: <DoneIcon color="success" />,
  todo: <TodoIcon color="disabled" />,
  warn: <WarnIcon color="warning" />,
};

// "Can this box run tonight on its own?" Rig, light output, audio feed and
// autopilot, each with its fix one tap away. Shrinks to one line once all four
// are good so it stays out of the way during a show.
export default function SetupChecklist() {
  const navigate = useNavigate();
  const { effects, dmx, capture, reachable, lastAnalysisAt } = useHealthStore();
  const [activeRig, setActiveRig] = useState<ActiveRigSummary | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    rigsApi
      .list(1, 100)
      .then((page) => {
        if (cancelled) return;
        const rig = page.items.find((r) => r.is_active);
        setActiveRig(rig ? { id: rig.id, name: rig.name } : null);
      })
      .catch(() => {
        // The rig step falls back to what the engine reports.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const steps = buildSetupSteps({
    effects,
    activeRig,
    dmx: readDmxHealth(dmx, reachable),
    audio: readAudioHealth(capture, reachable, lastAnalysisAt, Date.now()),
  });
  const ready = isReadyForShow(steps);
  const open = !ready || expanded;

  return (
    <Card sx={{ mb: 3 }} data-testid="setup-checklist">
      <CardContent>
        <Box component="div" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {ready ? <DoneIcon color="success" /> : <WarnIcon color="warning" />}
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            {ready ? 'Ready for the show' : 'Before the show'}
          </Typography>
          {ready && (
            <Button size="small" onClick={() => setExpanded((v) => !v)}>
              {expanded ? 'Hide' : 'Details'}
            </Button>
          )}
        </Box>
        <Collapse in={open}>
          <Box component="div" sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, mt: 2 }}>
            {steps.map((step) => (
              <Box
                component="div"
                key={step.key}
                data-testid={`setup-step-${step.key}`}
                data-state={step.state}
                sx={{ display: 'flex', alignItems: 'center', gap: 1.5, minHeight: 48 }}
              >
                {STATE_ICON[step.state]}
                <Box component="div" sx={{ flexGrow: 1 }}>
                  <Typography variant="subtitle1" fontWeight={700}>
                    {step.title}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {step.detail}
                  </Typography>
                </Box>
                {step.link && step.state !== 'done' && (
                  <Button variant="outlined" onClick={() => navigate(step.link!.to)} sx={{ minHeight: 44 }}>
                    {step.link.label}
                  </Button>
                )}
              </Box>
            ))}
          </Box>
        </Collapse>
      </CardContent>
    </Card>
  );
}
