import { useState, useCallback, useRef } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  Tabs,
  Tab,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  LinearProgress,
  Alert,
  Paper,
  Stack,
  Divider,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
} from '@mui/material';
import {
  Upload as UploadIcon,
  Download as DownloadIcon,
  CloudUpload as CloudUploadIcon,
  Description as FileIcon,
  CheckCircle as CheckIcon,
  Warning as WarningIcon,
  InsertDriveFile as JsonIcon,
  TableChart as CsvIcon,
  PictureAsPdf as PdfIcon,
  Close as CloseIcon,
} from '@mui/icons-material';
import { importExportApi, fixturesApi } from '../../services/api';
import axios from 'axios';

interface ImportExportDialogProps {
  open: boolean;
  onClose: () => void;
  rigId?: number;
}

type ImportFormat = 'gdtf' | 'mvr' | 'console_xml' | 'console_csv';

interface ParsedImportData {
  fixtureCount: number;
  fixtures: Array<{ name: string; manufacturer?: string; matched: boolean }>;
  unrecognized: string[];
  format: string;
}

export default function ImportExportDialog({
  open,
  onClose,
  rigId,
}: ImportExportDialogProps) {
  const [tab, setTab] = useState(0);
  const [importFormat, setImportFormat] = useState<ImportFormat>('mvr');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [parsedData, setParsedData] = useState<ParsedImportData | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const formatOptions: Array<{ value: ImportFormat; label: string; extension: string }> = [
    { value: 'gdtf', label: 'GDTF', extension: '.gdtf' },
    { value: 'mvr', label: 'MVR', extension: '.mvr' },
    { value: 'console_xml', label: 'Console Patch (XML)', extension: '.xml' },
    { value: 'console_csv', label: 'Console Patch (CSV)', extension: '.csv' },
  ];

  const getAcceptedExtensions = (): string => {
    const format = formatOptions.find((f) => f.value === importFormat);
    return format?.extension || '*';
  };

  const resetState = () => {
    setSelectedFile(null);
    setParsedData(null);
    setError(null);
    setSuccess(null);
    setImporting(false);
    setExporting(null);
  };

  const handleTabChange = (_: React.SyntheticEvent, newValue: number) => {
    setTab(newValue);
    resetState();
  };

  const handleFileSelect = (file: File) => {
    setSelectedFile(file);
    setError(null);
    setSuccess(null);

    // Simulate parsing preview based on file name and format
    const preview: ParsedImportData = {
      fixtureCount: 0,
      fixtures: [],
      unrecognized: [],
      format: importFormat,
    };

    // In a real implementation, we would parse the file on the server
    // For now, show a placeholder preview
    const extension = file.name.split('.').pop()?.toLowerCase();
    if (extension === 'gdtf') {
      preview.fixtureCount = 1;
      preview.fixtures = [{ name: file.name.replace('.gdtf', ''), matched: true }];
    } else {
      preview.fixtureCount = 0;
      preview.fixtures = [];
    }

    setParsedData(preview);
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);

      const files = e.dataTransfer.files;
      if (files.length > 0) {
        handleFileSelect(files[0]);
      }
    },
    [importFormat]
  );

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleImport = async () => {
    if (!selectedFile) return;

    setImporting(true);
    setError(null);
    setSuccess(null);

    try {
      switch (importFormat) {
        case 'gdtf': {
          // For GDTF, we create the fixture definition from the file
          const formData = new FormData();
          formData.append('file', selectedFile);
          await fixturesApi.create({ manufacturer: 'Imported', model: selectedFile.name.replace('.gdtf', '') });
          break;
        }
        case 'mvr':
          await importExportApi.importMVR(selectedFile);
          break;
        case 'console_xml':
          await importExportApi.importConsolePatch(selectedFile, 'xml');
          break;
        case 'console_csv':
          await importExportApi.importConsolePatch(selectedFile, 'csv');
          break;
      }

      setSuccess(`Successfully imported from ${selectedFile.name}`);
      setParsedData(null);
      setSelectedFile(null);
    } catch (err) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || 'Import failed. Please check the file format and try again.');
      } else {
        setError('Import failed. An unexpected error occurred.');
      }
    } finally {
      setImporting(false);
    }
  };

  const triggerDownload = (data: Blob | string, filename: string, mimeType: string) => {
    const blob = typeof data === 'string' ? new Blob([data], { type: mimeType }) : data;
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleExportJSON = async () => {
    if (!rigId) return;
    setExporting('json');
    setError(null);
    try {
      const data = await importExportApi.exportJSON(rigId);
      triggerDownload(JSON.stringify(data, null, 2), `rig_${rigId}.json`, 'application/json');
      setSuccess('JSON export downloaded successfully.');
    } catch (err) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || 'JSON export failed.');
      } else {
        setError('JSON export failed.');
      }
    } finally {
      setExporting(null);
    }
  };

  const handleExportCSV = async () => {
    if (!rigId) return;
    setExporting('csv');
    setError(null);
    try {
      const data = await importExportApi.exportCSV(rigId);
      triggerDownload(data, `rig_${rigId}.csv`, 'text/csv');
      setSuccess('CSV export downloaded successfully.');
    } catch (err) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || 'CSV export failed.');
      } else {
        setError('CSV export failed.');
      }
    } finally {
      setExporting(null);
    }
  };

  const handleExportPDF = async () => {
    if (!rigId) return;
    setExporting('pdf');
    setError(null);
    try {
      const response = await axios.get(`/api/rigs/${rigId}/export/pdf`, {
        responseType: 'blob',
      });
      triggerDownload(response.data, `rig_${rigId}.pdf`, 'application/pdf');
      setSuccess('PDF export downloaded successfully.');
    } catch (err) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || 'PDF export failed.');
      } else {
        setError('PDF export failed.');
      }
    } finally {
      setExporting(null);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        Import / Export
      </DialogTitle>

      <Tabs
        value={tab}
        onChange={handleTabChange}
        sx={{ px: 3, borderBottom: 1, borderColor: 'divider' }}
      >
        <Tab icon={<UploadIcon />} iconPosition="start" label="Import" />
        {rigId !== undefined && (
          <Tab icon={<DownloadIcon />} iconPosition="start" label="Export" />
        )}
      </Tabs>

      <DialogContent sx={{ minHeight: 320 }}>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
        {success && (
          <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
            {success}
          </Alert>
        )}

        {/* Import Tab */}
        {tab === 0 && (
          <Box>
            <FormControl fullWidth sx={{ mb: 3 }}>
              <InputLabel>Import Format</InputLabel>
              <Select
                value={importFormat}
                onChange={(e) => {
                  setImportFormat(e.target.value as ImportFormat);
                  setSelectedFile(null);
                  setParsedData(null);
                }}
                label="Import Format"
              >
                {formatOptions.map((opt) => (
                  <MenuItem key={opt.value} value={opt.value}>
                    {opt.label} ({opt.extension})
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            {/* Drag-and-drop area */}
            <Paper
              variant="outlined"
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              sx={{
                p: 4,
                textAlign: 'center',
                cursor: 'pointer',
                borderStyle: 'dashed',
                borderWidth: 2,
                borderColor: isDragging ? 'primary.main' : 'divider',
                bgcolor: isDragging ? 'action.hover' : 'background.default',
                transition: 'all 0.2s',
                '&:hover': {
                  borderColor: 'primary.light',
                  bgcolor: 'action.hover',
                },
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept={getAcceptedExtensions()}
                onChange={handleFileInputChange}
                style={{ display: 'none' }}
              />
              <CloudUploadIcon sx={{ fontSize: 48, color: 'text.secondary', mb: 1 }} />
              <Typography variant="body1" gutterBottom>
                {selectedFile
                  ? selectedFile.name
                  : 'Drag and drop a file here, or click to browse'}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Accepted format: {getAcceptedExtensions()}
              </Typography>
            </Paper>

            {/* File info */}
            {selectedFile && (
              <Box sx={{ mt: 2 }}>
                <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                  <FileIcon color="primary" fontSize="small" />
                  <Typography variant="body2" fontWeight="bold">
                    {selectedFile.name}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    ({(selectedFile.size / 1024).toFixed(1)} KB)
                  </Typography>
                </Stack>
              </Box>
            )}

            {/* Parsed data preview */}
            {parsedData && (
              <Box sx={{ mt: 2 }}>
                <Divider sx={{ mb: 2 }} />
                <Typography variant="subtitle2" gutterBottom>
                  Preview
                </Typography>

                {parsedData.fixtures.length > 0 && (
                  <List dense>
                    {parsedData.fixtures.map((f, i) => (
                      <ListItem key={i}>
                        <ListItemIcon sx={{ minWidth: 36 }}>
                          {f.matched ? (
                            <CheckIcon color="success" fontSize="small" />
                          ) : (
                            <WarningIcon color="warning" fontSize="small" />
                          )}
                        </ListItemIcon>
                        <ListItemText
                          primary={f.name}
                          secondary={
                            f.matched
                              ? f.manufacturer || 'Matched in library'
                              : 'Unrecognized - will be created as custom fixture'
                          }
                        />
                      </ListItem>
                    ))}
                  </List>
                )}

                {parsedData.fixtureCount === 0 && (
                  <Typography variant="body2" color="text.secondary">
                    File will be parsed on import. Fixture details will be determined by the server.
                  </Typography>
                )}

                {parsedData.unrecognized.length > 0 && (
                  <Alert severity="warning" sx={{ mt: 1 }}>
                    {parsedData.unrecognized.length} unrecognized fixture type
                    {parsedData.unrecognized.length > 1 ? 's' : ''}:{' '}
                    {parsedData.unrecognized.join(', ')}
                  </Alert>
                )}
              </Box>
            )}

            {importing && <LinearProgress sx={{ mt: 2 }} />}
          </Box>
        )}

        {/* Export Tab */}
        {tab === 1 && rigId !== undefined && (
          <Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Export rig #{rigId} in your preferred format. The export will include all fixtures,
              patch assignments, positions, and configuration data.
            </Typography>

            <Stack spacing={2}>
              <Button
                variant="outlined"
                size="large"
                fullWidth
                startIcon={<JsonIcon />}
                onClick={handleExportJSON}
                disabled={exporting !== null}
                sx={{ justifyContent: 'flex-start', py: 2 }}
              >
                <Box sx={{ textAlign: 'left' }}>
                  <Typography variant="body1" fontWeight="bold">
                    Export as JSON
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Full rig data for backup or transfer between systems
                  </Typography>
                </Box>
              </Button>

              <Button
                variant="outlined"
                size="large"
                fullWidth
                startIcon={<CsvIcon />}
                onClick={handleExportCSV}
                disabled={exporting !== null}
                sx={{ justifyContent: 'flex-start', py: 2 }}
              >
                <Box sx={{ textAlign: 'left' }}>
                  <Typography variant="body1" fontWeight="bold">
                    Export as CSV
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Spreadsheet-compatible patch sheet for documentation
                  </Typography>
                </Box>
              </Button>

              <Button
                variant="outlined"
                size="large"
                fullWidth
                startIcon={<PdfIcon />}
                onClick={handleExportPDF}
                disabled={exporting !== null}
                sx={{ justifyContent: 'flex-start', py: 2 }}
              >
                <Box sx={{ textAlign: 'left' }}>
                  <Typography variant="body1" fontWeight="bold">
                    Export as PDF
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Printable patch sheet and rig documentation
                  </Typography>
                </Box>
              </Button>
            </Stack>

            {exporting && <LinearProgress sx={{ mt: 2 }} />}
          </Box>
        )}
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose} startIcon={<CloseIcon />}>
          Close
        </Button>
        {tab === 0 && (
          <Button
            variant="contained"
            onClick={handleImport}
            disabled={!selectedFile || importing}
            startIcon={<UploadIcon />}
          >
            {importing ? 'Importing...' : 'Import'}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
