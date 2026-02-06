/**
 * Utility helper functions
 */

/**
 * Clamp a value between min and max
 */
export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

/**
 * Linear interpolation
 */
export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

/**
 * Convert DMX value (0-255) to percentage (0-1)
 */
export function dmxToPercent(value: number): number {
  return value / 255;
}

/**
 * Convert percentage (0-1) to DMX value (0-255)
 */
export function percentToDmx(value: number): number {
  return Math.round(clamp(value, 0, 1) * 255);
}

/**
 * Format seconds as timecode (MM:SS)
 */
export function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Format seconds as timecode with frames (MM:SS:FF)
 */
export function formatTimecode(seconds: number, fps = 30): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const frames = Math.floor((seconds % 1) * fps);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}:${frames.toString().padStart(2, '0')}`;
}

/**
 * Convert HSV to RGB
 */
export function hsvToRgb(
  h: number,
  s: number,
  v: number
): [number, number, number] {
  let r: number, g: number, b: number;

  const i = Math.floor(h * 6);
  const f = h * 6 - i;
  const p = v * (1 - s);
  const q = v * (1 - f * s);
  const t = v * (1 - (1 - f) * s);

  switch (i % 6) {
    case 0:
      r = v;
      g = t;
      b = p;
      break;
    case 1:
      r = q;
      g = v;
      b = p;
      break;
    case 2:
      r = p;
      g = v;
      b = t;
      break;
    case 3:
      r = p;
      g = q;
      b = v;
      break;
    case 4:
      r = t;
      g = p;
      b = v;
      break;
    case 5:
      r = v;
      g = p;
      b = q;
      break;
    default:
      r = 0;
      g = 0;
      b = 0;
  }

  return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
}

/**
 * Convert RGB to HSV
 */
export function rgbToHsv(
  r: number,
  g: number,
  b: number
): [number, number, number] {
  r /= 255;
  g /= 255;
  b /= 255;

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const d = max - min;

  let h = 0;
  const s = max === 0 ? 0 : d / max;
  const v = max;

  if (max !== min) {
    switch (max) {
      case r:
        h = (g - b) / d + (g < b ? 6 : 0);
        break;
      case g:
        h = (b - r) / d + 2;
        break;
      case b:
        h = (r - g) / d + 4;
        break;
    }
    h /= 6;
  }

  return [h, s, v];
}

/**
 * Debounce a function
 */
export function debounce<T extends (...args: unknown[]) => unknown>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout>;

  return (...args: Parameters<T>) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}

/**
 * Throttle a function
 */
export function throttle<T extends (...args: unknown[]) => unknown>(
  func: T,
  limit: number
): (...args: Parameters<T>) => void {
  let inThrottle: boolean;

  return (...args: Parameters<T>) => {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  };
}

/**
 * Generate a unique ID
 */
export function generateId(): string {
  return Math.random().toString(36).substring(2) + Date.now().toString(36);
}

/**
 * Get color for emotion
 */
export function getEmotionColor(emotion: string): string {
  const colors: Record<string, string> = {
    happy: '#ffeb3b',
    excited: '#ff9800',
    energetic: '#f44336',
    angry: '#d32f2f',
    sad: '#2196f3',
    calm: '#4caf50',
    relaxed: '#8bc34a',
    melancholic: '#9c27b0',
    neutral: '#9e9e9e',
  };

  return colors[emotion] || colors.neutral;
}
