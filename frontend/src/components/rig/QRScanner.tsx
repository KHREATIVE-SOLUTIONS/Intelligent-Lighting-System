import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  Alert,
  Chip,
  Stack,
  Divider,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  IconButton,
  LinearProgress,
} from '@mui/material';
import {
  QrCodeScanner as ScannerIcon,
  CheckCircle as CheckIcon,
  Close as CloseIcon,
  CameraAlt as CameraIcon,
  Label as LabelIcon,
  Videocam as VideocamIcon,
  VideocamOff as VideocamOffIcon,
} from '@mui/icons-material';
import axios from 'axios';

interface QRScannerProps {
  rigId: number;
  onScan?: (fixtureId: number) => void;
  open: boolean;
  onClose: () => void;
}

interface ScanResult {
  fixture_id: number;
  fixture_name: string;
  dmx_address: number;
  universe: number;
  timestamp: number;
}

export default function QRScanner({ rigId, onScan, open, onClose }: QRScannerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const animationRef = useRef<number | null>(null);
  const lastScannedRef = useRef<string>('');

  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [scanResults, setScanResults] = useState<ScanResult[]>([]);
  const [lastResult, setLastResult] = useState<ScanResult | null>(null);
  const [processing, setProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generatingLabels, setGeneratingLabels] = useState(false);

  // Check if BarcodeDetector is available
  const hasBarcodeDetector = typeof window !== 'undefined' && 'BarcodeDetector' in window;

  const startCamera = useCallback(async () => {
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: 'environment',
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });

      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        setCameraActive(true);
      }
    } catch (err) {
      const message =
        err instanceof DOMException && err.name === 'NotAllowedError'
          ? 'Camera permission denied. Please allow camera access in your browser settings.'
          : err instanceof DOMException && err.name === 'NotFoundError'
            ? 'No camera found. Please connect a camera and try again.'
            : 'Failed to access camera. Please check your camera settings.';
      setCameraError(message);
      setCameraActive(false);
    }
  }, []);

  const stopCamera = useCallback(() => {
    if (animationRef.current !== null) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    setCameraActive(false);
  }, []);

  // Start camera when dialog opens
  useEffect(() => {
    if (open) {
      // Small delay to allow dialog to render
      const timer = setTimeout(startCamera, 300);
      return () => clearTimeout(timer);
    } else {
      stopCamera();
    }
  }, [open, startCamera, stopCamera]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, [stopCamera]);

  const handleQRData = useCallback(
    async (qrData: string) => {
      // Debounce: don't scan the same code repeatedly
      if (qrData === lastScannedRef.current) return;
      lastScannedRef.current = qrData;

      // Clear the debounce after 3 seconds so the same code can be scanned again
      setTimeout(() => {
        if (lastScannedRef.current === qrData) {
          lastScannedRef.current = '';
        }
      }, 3000);

      setProcessing(true);
      setError(null);

      try {
        const response = await axios.post(`/api/rigs/${rigId}/scan`, {
          qr_data: qrData,
        });

        const result: ScanResult = {
          fixture_id: response.data.fixture_id,
          fixture_name: response.data.fixture_name || 'Unknown Fixture',
          dmx_address: response.data.dmx_address || 0,
          universe: response.data.universe || 0,
          timestamp: Date.now(),
        };

        setLastResult(result);
        setScanResults((prev) => {
          // Avoid duplicates
          const exists = prev.some((r) => r.fixture_id === result.fixture_id);
          if (exists) return prev;
          return [result, ...prev];
        });

        onScan?.(result.fixture_id);
      } catch (err) {
        if (axios.isAxiosError(err)) {
          setError(
            err.response?.data?.detail || 'Failed to process QR code. Fixture may not be in this rig.'
          );
        } else {
          setError('Failed to process QR code.');
        }
      } finally {
        setProcessing(false);
      }
    },
    [rigId, onScan]
  );

  // QR code scanning loop
  useEffect(() => {
    if (!cameraActive || !videoRef.current || !canvasRef.current) return;

    const video = videoRef.current;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let barcodeDetector: InstanceType<typeof BarcodeDetector> | null = null;
    if (hasBarcodeDetector) {
      try {
        // @ts-expect-error BarcodeDetector is not yet in all TS lib definitions
        barcodeDetector = new BarcodeDetector({ formats: ['qr_code'] });
      } catch {
        // BarcodeDetector not supported with qr_code format
      }
    }

    const scanFrame = async () => {
      if (!cameraActive || video.readyState !== video.HAVE_ENOUGH_DATA) {
        animationRef.current = requestAnimationFrame(scanFrame);
        return;
      }

      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      try {
        if (barcodeDetector) {
          // Use native BarcodeDetector API
          const barcodes = await barcodeDetector.detect(canvas);
          if (barcodes.length > 0) {
            const qrData = barcodes[0].rawValue;
            if (qrData) {
              handleQRData(qrData);
            }
          }
        } else {
          // Fallback: analyze canvas for QR-like patterns
          // In production, you would use a JS QR library like jsQR
          // This is a placeholder that checks image data
          const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
          const qrResult = fallbackQRDetect(imageData);
          if (qrResult) {
            handleQRData(qrResult);
          }
        }
      } catch {
        // Detection errors are non-fatal; just skip this frame
      }

      animationRef.current = requestAnimationFrame(scanFrame);
    };

    animationRef.current = requestAnimationFrame(scanFrame);

    return () => {
      if (animationRef.current !== null) {
        cancelAnimationFrame(animationRef.current);
        animationRef.current = null;
      }
    };
  }, [cameraActive, hasBarcodeDetector, handleQRData]);

  /**
   * Fallback QR detection using canvas image data analysis.
   * This is a simplified placeholder. In a production environment,
   * integrate a library like jsQR for reliable canvas-based detection.
   */
  const fallbackQRDetect = (_imageData: ImageData): string | null => {
    // Placeholder: real implementation would use jsQR or similar library.
    // e.g.: const code = jsQR(imageData.data, imageData.width, imageData.height);
    // return code?.data || null;
    return null;
  };

  const handleGenerateLabels = async () => {
    setGeneratingLabels(true);
    setError(null);
    try {
      const response = await axios.get(`/api/rigs/${rigId}/labels/pdf`, {
        responseType: 'blob',
      });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = `rig_${rigId}_labels.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || 'Failed to generate labels.');
      } else {
        setError('Failed to generate labels.');
      }
    } finally {
      setGeneratingLabels(false);
    }
  };

  const handleClose = () => {
    stopCamera();
    onClose();
  };

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <ScannerIcon />
          <span>QR Code Scanner</span>
        </Box>
        <IconButton onClick={handleClose} size="small">
          <CloseIcon />
        </IconButton>
      </DialogTitle>

      <DialogContent>
        {/* Camera feed */}
        <Box
          sx={{
            position: 'relative',
            width: '100%',
            bgcolor: 'black',
            borderRadius: 1,
            overflow: 'hidden',
            mb: 2,
            minHeight: 240,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <video
            ref={videoRef}
            playsInline
            muted
            style={{
              width: '100%',
              maxHeight: 360,
              objectFit: 'cover',
              display: cameraActive ? 'block' : 'none',
            }}
          />

          {/* Hidden canvas for frame analysis */}
          <canvas ref={canvasRef} style={{ display: 'none' }} />

          {/* Scanning overlay */}
          {cameraActive && (
            <Box
              sx={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                width: 200,
                height: 200,
                border: '2px solid rgba(255, 255, 255, 0.6)',
                borderRadius: 2,
                pointerEvents: 'none',
                '&::before': {
                  content: '""',
                  position: 'absolute',
                  top: -2,
                  left: -2,
                  width: 30,
                  height: 30,
                  borderTop: '3px solid #4caf50',
                  borderLeft: '3px solid #4caf50',
                  borderRadius: '4px 0 0 0',
                },
                '&::after': {
                  content: '""',
                  position: 'absolute',
                  top: -2,
                  right: -2,
                  width: 30,
                  height: 30,
                  borderTop: '3px solid #4caf50',
                  borderRight: '3px solid #4caf50',
                  borderRadius: '0 4px 0 0',
                },
              }}
            />
          )}

          {/* Camera inactive placeholder */}
          {!cameraActive && !cameraError && (
            <Box sx={{ textAlign: 'center', p: 4 }}>
              <CameraIcon sx={{ fontSize: 48, color: 'grey.500', mb: 1 }} />
              <Typography variant="body2" color="grey.500">
                Starting camera...
              </Typography>
            </Box>
          )}

          {/* Camera error */}
          {cameraError && (
            <Box sx={{ textAlign: 'center', p: 4 }}>
              <VideocamOffIcon sx={{ fontSize: 48, color: 'grey.500', mb: 1 }} />
              <Typography variant="body2" color="grey.400">
                {cameraError}
              </Typography>
              <Button
                variant="outlined"
                size="small"
                onClick={startCamera}
                sx={{ mt: 2, color: 'grey.300', borderColor: 'grey.600' }}
              >
                Retry
              </Button>
            </Box>
          )}
        </Box>

        {processing && <LinearProgress sx={{ mb: 1 }} />}

        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {/* Last scan result */}
        {lastResult && (
          <Alert severity="success" sx={{ mb: 2 }}>
            <Typography variant="body2" fontWeight="bold">
              {lastResult.fixture_name}
            </Typography>
            <Typography variant="caption">
              Universe {lastResult.universe}, Address {lastResult.dmx_address}
            </Typography>
          </Alert>
        )}

        {/* Camera toggle */}
        <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
          <Button
            size="small"
            variant="outlined"
            startIcon={cameraActive ? <VideocamOffIcon /> : <VideocamIcon />}
            onClick={cameraActive ? stopCamera : startCamera}
          >
            {cameraActive ? 'Stop Camera' : 'Start Camera'}
          </Button>
          <Chip
            label={`${scanResults.length} scanned`}
            color={scanResults.length > 0 ? 'primary' : 'default'}
            size="small"
          />
        </Stack>

        <Divider sx={{ mb: 2 }} />

        {/* Scanned fixtures list */}
        <Typography variant="subtitle2" gutterBottom>
          Scanned Fixtures
        </Typography>

        {scanResults.length > 0 ? (
          <List dense sx={{ maxHeight: 200, overflow: 'auto' }}>
            {scanResults.map((result) => (
              <ListItem key={result.fixture_id}>
                <ListItemIcon sx={{ minWidth: 36 }}>
                  <CheckIcon color="success" fontSize="small" />
                </ListItemIcon>
                <ListItemText
                  primary={result.fixture_name}
                  secondary={`Universe ${result.universe}, Address ${result.dmx_address}`}
                />
              </ListItem>
            ))}
          </List>
        ) : (
          <Typography variant="body2" color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
            No fixtures scanned yet. Point the camera at a fixture QR code.
          </Typography>
        )}
      </DialogContent>

      <DialogActions sx={{ justifyContent: 'space-between', px: 3, pb: 2 }}>
        <Button
          startIcon={<LabelIcon />}
          onClick={handleGenerateLabels}
          disabled={generatingLabels}
        >
          {generatingLabels ? 'Generating...' : 'Generate Labels'}
        </Button>
        <Button onClick={handleClose}>Done</Button>
      </DialogActions>
    </Dialog>
  );
}
