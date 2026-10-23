// Turns raw status from the box into the three things a booth tech needs to
// read at a glance: is light leaving the box, is audio coming in, and is this
// screen still talking to the engine. Kept free of React so it can be tested.

export type HealthLevel = 'ok' | 'warn' | 'down' | 'unknown';

export interface HealthReading {
  level: HealthLevel;
  label: string;
  detail: string;
}

export interface DmxStatusPayload {
  status?: string;
  fps?: number;
  connected?: boolean;
  transmitting?: boolean;
  target_ip?: string | null;
  last_send_error?: string | null;
  failing_universes?: number[];
}

export type AudioInputState = 'live' | 'lost' | 'waiting';

// The box's own health report (/api/health). Only a signed-in screen gets
// services and dmx_detail; older boxes do not send the newer fields at all.
export interface BoxHealthPayload {
  status?: 'healthy' | 'degraded';
  services?: {
    database?: 'connected' | 'unavailable';
    audio_input?: AudioInputState;
    [service: string]: string | undefined;
  };
  dmx_detail?: {
    output_held_until_rig_patched?: boolean;
    [key: string]: unknown;
  };
}

export interface CaptureStatusPayload {
  running?: boolean;
  available?: boolean;
  device_name?: string | null;
  last_rms?: number;
  effects_engine_running?: boolean;
  effects_engine_auto_mode?: boolean;
}

// Below this RMS the room is silent or the feed is unplugged.
export const SIGNAL_FLOOR = 0.001;

// Analysis frames normally arrive many times a second; past this the audio
// path has stalled even if capture still says it is running.
export const ANALYSIS_STALE_MS = 3000;

export function readDmxHealth(
  status: DmxStatusPayload | null,
  reachable: boolean,
  box: BoxHealthPayload | null = null
): HealthReading {
  if (!reachable) {
    return { level: 'unknown', label: 'DMX ?', detail: 'Cannot reach the lighting box to check DMX output.' };
  }
  if (!status || status.status === 'not_initialized') {
    return { level: 'down', label: 'DMX off', detail: 'DMX output is not set up on the box.' };
  }
  // A fresh box runs the demo rig on screen but keeps it off the network, so
  // nothing is sent on purpose. That is a setup step, not a fault.
  if (box?.dmx_detail?.output_held_until_rig_patched) {
    return {
      level: 'warn',
      label: 'Waiting for rig',
      detail:
        'Waiting for a rig to be patched. The demo show runs on screen, but nothing goes out to the lights until this venue’s rig is patched and activated.',
    };
  }
  const where = status.target_ip ? ` to ${status.target_ip}` : '';
  if (status.connected === false || status.status === 'disconnected') {
    return { level: 'down', label: 'DMX off', detail: `ArtNet is not connected${where}.` };
  }
  if (status.last_send_error) {
    const universes = status.failing_universes?.length
      ? ` (universe ${status.failing_universes.join(', ')})`
      : '';
    return {
      level: 'down',
      label: 'DMX error',
      detail: `Sending failed${universes}: ${status.last_send_error}`,
    };
  }
  if (status.transmitting === false) {
    return { level: 'warn', label: 'DMX stalled', detail: `Connected${where} but no frames are going out.` };
  }
  const fps = Math.round(status.fps ?? 0);
  return { level: 'ok', label: fps > 0 ? `DMX ${fps} fps` : 'DMX live', detail: `Sending ArtNet${where}.` };
}

export function readAudioHealth(
  capture: CaptureStatusPayload | null,
  reachable: boolean,
  lastAnalysisAt: number | null,
  now: number,
  box: BoxHealthPayload | null = null
): HealthReading {
  if (!reachable) {
    return { level: 'unknown', label: 'Audio ?', detail: 'Cannot reach the lighting box to check audio.' };
  }
  // What the engine itself is hearing, which is the final word on whether the
  // lights follow the music. Absent on boxes that do not report it.
  const input = box?.services?.audio_input ?? null;
  if (input === 'live' && !capture?.running) {
    return { level: 'ok', label: 'Audio live', detail: 'Following an audio feed sent to the box.' };
  }
  if (!capture || capture.available === false) {
    return { level: 'down', label: 'No audio', detail: 'Audio capture is not available on the box.' };
  }
  if (!capture.running) {
    return {
      level: 'down',
      label: 'Audio off',
      detail: 'No audio feed is being captured, so the lights are not following the music.',
    };
  }
  const device = capture.device_name ? ` from ${capture.device_name}` : '';
  if ((capture.last_rms ?? 0) < SIGNAL_FLOOR) {
    return { level: 'warn', label: 'No signal', detail: `Capturing${device} but the feed is silent.` };
  }
  if (input === 'lost') {
    return {
      level: 'down',
      label: 'Audio lost',
      detail: `Capturing${device} but audio stopped reaching the engine. The lights have settled to a calm look until it comes back.`,
    };
  }
  if (input === 'waiting') {
    return { level: 'warn', label: 'Audio stalled', detail: `Signal${device} but none has reached the engine yet.` };
  }
  if (lastAnalysisAt !== null && now - lastAnalysisAt > ANALYSIS_STALE_MS) {
    return { level: 'warn', label: 'Audio stalled', detail: `Signal${device} but analysis stopped updating.` };
  }
  return { level: 'ok', label: 'Audio live', detail: `Following the music${device}.` };
}

// Only worth a pill when it is missing: a box without its database cannot load
// or patch the venue rig, though the demo show keeps running.
export function readDatabaseHealth(box: BoxHealthPayload | null, reachable: boolean): HealthReading | null {
  if (!reachable || box?.services?.database !== 'unavailable') return null;
  return {
    level: 'down',
    label: 'No database',
    detail:
      'The box started without its database, so this venue’s rig cannot load and changes cannot be saved. The demo show still runs. Restart the box.',
  };
}

export type LinkState = 'connected' | 'connecting' | 'reconnecting' | 'lost' | 'idle';

export function readLinkHealth(state: LinkState, reachable: boolean): HealthReading {
  if (!reachable) {
    return {
      level: 'down',
      label: 'Box offline',
      detail: 'This screen cannot reach the lighting box. The lights hold whatever the box last sent.',
    };
  }
  switch (state) {
    case 'connected':
      return { level: 'ok', label: 'Linked', detail: 'Live updates from the engine.' };
    case 'connecting':
    case 'reconnecting':
      return { level: 'warn', label: 'Reconnecting', detail: 'Live updates dropped; retrying.' };
    case 'lost':
      return { level: 'down', label: 'Link lost', detail: 'Live updates stopped. Tap to retry.' };
    default:
      return { level: 'unknown', label: 'Not linked', detail: 'Live updates are not running.' };
  }
}
