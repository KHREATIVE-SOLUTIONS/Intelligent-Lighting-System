import { useState, useEffect, useRef, useCallback } from 'react';
import type { FormEvent } from 'react';
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
  TextField,
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
import { rigsApi } from '../../services/api';
import type { QrScanAnswer } from '../../services/api';

interface QRScannerProps {
  rigId: number;
  /** After each code the server took: the rig fixture it added or named, and whether it was added. */
  onScan?: (rigFixtureId: number, added: boolean) => void;
  open: boolean;
  onClose: () => void;
}

/** One answered scan, from the route's own answer (`QrScanAnswer`). */
export interface ScanResult {
  rig_fixture_id: number;
  added: boolean;
  /** The server's sentence: "Added Spot 3 at address 17", or where it already is. */
  message: string;
  timestamp: number;
}

export function scanResultOf(answer: QrScanAnswer, now = Date.now()): ScanResult {
  // A printed label of a fixture already patched (by the UI, an import, RDM)
  // comes back `identified` with `already_patched`: nothing was added.
  const added = answer.action === 'added' && answer.already_patched !== true;
  return {
    rig_fixture_id: answer.rig_fixture_id,
    added,
    message: answer.message || (added ? 'Added to the rig' : 'Already in the rig'),
    timestamp: now,
  };
}

const LABELS_FAILED = 'Failed to generate labels.';

function blobText(blob: Blob): Promise<string> {
  if (typeof blob.text === 'function') return blob.text();
  // Older jsdom Blobs have no text(): FileReader reads them everywhere.
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

/**
 * The message for a failed label download. The request asks for a blob, so an
 * error answer arrives as a Blob too: read its text and take FastAPI's
 * `detail` (a string, or a list of validation errors), else the plain text.
 */
export async function labelsErrorOf(err: unknown): Promise<string> {
  if (!axios.isAxiosError(err)) return LABELS_FAILED;
  const data: unknown = err.response?.data;
  let text: string | undefined;
  if (data instanceof Blob) {
    try {
      text = await blobText(data);
    } catch {
      return LABELS_FAILED;
    }
  } else if (typeof data === 'string') {
    text = data;
  } else if (data && typeof data === 'object') {
    text = JSON.stringify(data);
  }
  if (!text) return LABELS_FAILED;
  try {
    const detail = (JSON.parse(text) as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail) return detail;
    if (Array.isArray(detail) && detail.length) {
      const msg = (detail[0] as { msg?: unknown })?.msg;
      if (typeof msg === 'string') return msg;
    }
    return LABELS_FAILED;
  } catch {
    const plain = text.trim();
    return plain && plain.length <= 200 ? plain : LABELS_FAILED;
  }
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
  const [typedCode, setTypedCode] = useState('');

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
    async (qrData: string, typed = false) => {
      // Debounce: the camera sees the same code on every frame. A code typed or
      // sent by a handheld scanner is meant every time.
      if (!typed) {
        if (qrData === lastScannedRef.current) return;
        lastScannedRef.current = qrData;

        // Clear the debounce after 3 seconds so the same code can be scanned again
        setTimeout(() => {
          if (lastScannedRef.current === qrData) {
            lastScannedRef.current = '';
          }
        }, 3000);
      }

      setProcessing(true);
      setError(null);

      try {
        // Through the app's client: it carries the token, and announces the
        // rig change so the focus table and 3D reach markers read again.
        const result = scanResultOf(await rigsApi.scanQr(rigId, qrData));

        setLastResult(result);
        setScanResults((prev) => {
          // One line per rig fixture: a second scan of it says so again on top.
          const rest = prev.filter((r) => r.rig_fixture_id !== result.rig_fixture_id);
          return [result, ...rest];
        });

        onScan?.(result.rig_fixture_id, result.added);
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
      const blob = await rigsApi.labelsPdf(rigId);
      // A printable PDF (qr_scanning.py, generate_label_sheet); JSON only if
      // asked for with ?format=json. Saved as what it is either way.
      const isPdf = blob.type.includes('pdf');
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `rig_${rigId}_labels.${isPdf ? 'pdf' : 'json'}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(await labelsErrorOf(err));
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
          <Alert severity={lastResult.added ? 'success' : 'info'} sx={{ mb: 2 }}>
            <Typography variant="body2" fontWeight="bold">
              {lastResult.added ? 'Added to the rig' : 'Already in the rig'}
            </Typography>
            <Typography variant="caption">{lastResult.message}</Typography>
          </Alert>
        )}

        {/* The camera only reads codes where the browser has BarcodeDetector
            (Chrome on Android and macOS; not Chrome or Edge on Windows, nor
            Firefox). Typing the code, or a USB handheld scanner, which types it
            and presses Enter, works everywhere. */}
        {!hasBarcodeDetector && (
          <Alert severity="info" sx={{ mb: 2 }}>
            This browser cannot read QR codes from the camera. Type the code below,
            or use a USB barcode scanner: click the box and scan.
          </Alert>
        )}
        <Box
          component="form"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            const code = typedCode.trim();
            if (!code || processing) return;
            setTypedCode('');
            void handleQRData(code, true);
          }}
          sx={{ display: 'flex', gap: 1, mb: 2 }}
        >
          <TextField
            size="small"
            fullWidth
            label="QR code or fixture ID"
            value={typedCode}
            onChange={(e) => setTypedCode(e.target.value)}
            autoFocus={!hasBarcodeDetector}
            inputProps={{ 'aria-label': 'QR code or fixture ID' }}
          />
          <Button type="submit" variant="outlined" disabled={!typedCode.trim() || processing}>
            Add
          </Button>
        </Box>

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
              <ListItem key={result.rig_fixture_id}>
                <ListItemIcon sx={{ minWidth: 36 }}>
                  <CheckIcon color={result.added ? 'success' : 'disabled'} fontSize="small" />
                </ListItemIcon>
                <ListItemText
                  primary={result.message}
                  secondary={result.added ? 'Added' : 'Already in the rig'}
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
