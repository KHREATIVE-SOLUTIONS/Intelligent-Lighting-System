import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  CardActions,
  Button,
  Tabs,
  Tab,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
} from '@mui/material';
import { templatesApi } from '../../services/api';
import type { RigTemplate } from '../../types';

interface TemplateGalleryProps {
  onClose?: () => void;
}

export default function TemplateGallery({ onClose }: TemplateGalleryProps) {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<RigTemplate[]>([]);
  const [tab, setTab] = useState(0); // 0 = All, 1 = My Saved
  const [applyDialog, setApplyDialog] = useState<RigTemplate | null>(null);
  const [rigName, setRigName] = useState('');
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    templatesApi.list().then((data) => setTemplates(data.items || [])).catch(() => {});
  }, []);

  const handleApply = async () => {
    if (!applyDialog || !rigName) return;
    setApplying(true);
    try {
      const result = await templatesApi.apply(applyDialog.id, { rig_name: rigName });
      navigate(`/rigs/${result.id}`);
      onClose?.();
    } catch (err) {
      console.error('Failed to apply template:', err);
    } finally {
      setApplying(false);
    }
  };

  const filtered = tab === 1
    ? templates.filter((t) => !t.is_system)
    : templates;

  return (
    <Box>
      <Typography variant="h6" gutterBottom>Rig Templates</Typography>

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="All Templates" />
        <Tab label="My Saved" />
      </Tabs>

      <Grid container spacing={2}>
        {filtered.map((template) => (
          <Grid item xs={12} sm={6} md={4} key={template.id}>
            <Card>
              <CardContent>
                <Typography variant="subtitle1" fontWeight="bold">
                  {template.name}
                </Typography>
                {template.venue_type && (
                  <Chip label={template.venue_type} size="small" sx={{ mb: 1 }} />
                )}
                <Typography variant="body2" color="text.secondary">
                  {template.description || 'No description'}
                </Typography>
                <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                  {template.stage_width}×{template.stage_depth}×{template.stage_height}m |{' '}
                  {(template.fixture_slots || []).reduce((sum, s) => sum + (s.count || 0), 0)} fixtures |{' '}
                  Used {template.usage_count}x
                </Typography>
                {template.is_system && <Chip label="System" size="small" variant="outlined" sx={{ mt: 0.5 }} />}
              </CardContent>
              <CardActions>
                <Button
                  size="small"
                  variant="contained"
                  onClick={() => {
                    setApplyDialog(template);
                    setRigName(`${template.name} - New Rig`);
                  }}
                >
                  Use Template
                </Button>
              </CardActions>
            </Card>
          </Grid>
        ))}
        {filtered.length === 0 && (
          <Grid item xs={12}>
            <Typography color="text.secondary" sx={{ textAlign: 'center', py: 4 }}>
              No templates found. Create one from an existing rig.
            </Typography>
          </Grid>
        )}
      </Grid>

      {/* Apply dialog */}
      <Dialog open={!!applyDialog} onClose={() => setApplyDialog(null)} maxWidth="xs" fullWidth>
        <DialogTitle>Create Rig from Template</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            Template: {applyDialog?.name}
          </Typography>
          <TextField
            fullWidth
            label="Rig Name"
            value={rigName}
            onChange={(e) => setRigName(e.target.value)}
            margin="normal"
            autoFocus
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setApplyDialog(null)}>Cancel</Button>
          <Button variant="contained" onClick={handleApply} disabled={!rigName || applying}>
            {applying ? 'Creating...' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
