import type { EffectsStatus } from '../services/api';
import type { HealthReading } from './showHealth';

// The four things that must be true before the box can run a night on its
// own. Kept free of React so the wording and order can be tested.

export type StepState = 'done' | 'todo' | 'warn';

export interface SetupStep {
  key: 'rig' | 'dmx' | 'audio' | 'autopilot';
  title: string;
  state: StepState;
  detail: string;
  // Where to go to fix it; absent when the fix is on this page or off-screen.
  link?: { to: string; label: string };
}

export interface ActiveRigSummary {
  id: number;
  name: string;
}

export function buildSetupSteps(input: {
  effects: EffectsStatus | null;
  activeRig: ActiveRigSummary | null;
  dmx: HealthReading;
  audio: HealthReading;
}): SetupStep[] {
  const { effects, activeRig, dmx, audio } = input;
  return [rigStep(effects, activeRig), dmxStep(dmx), audioStep(audio), autopilotStep(effects)];
}

function rigStep(effects: EffectsStatus | null, activeRig: ActiveRigSummary | null): SetupStep {
  const title = 'Venue rig';
  if (!effects) {
    return { key: 'rig', title, state: 'warn', detail: 'Cannot tell which rig the engine is running.' };
  }
  if (effects.live_rig_demo) {
    if (activeRig) {
      return {
        key: 'rig',
        title,
        state: 'warn',
        detail: `"${activeRig.name}" is marked active, but the engine is still running the demo rig. Restart the box to load it.`,
      };
    }
    return {
      key: 'rig',
      title,
      state: 'todo',
      detail: 'Running the built-in demo rig. Build or import this venue’s rig.',
      link: { to: '/rigs/new/wizard', label: 'Set up rig' },
    };
  }
  // The engine reads the active rig once at boot, so a later switch only lands
  // after a restart. Say so instead of letting the patch look wrong.
  if (activeRig && effects.live_rig_id != null && activeRig.id !== effects.live_rig_id) {
    return {
      key: 'rig',
      title,
      state: 'warn',
      detail: `"${activeRig.name}" is marked active, but the engine is running "${effects.live_rig_name}". Restart the box to switch.`,
    };
  }
  const count = effects.live_rig_fixtures ?? 0;
  return {
    key: 'rig',
    title,
    state: 'done',
    detail: `${effects.live_rig_name ?? 'Active rig'}, ${count} fixture${count === 1 ? '' : 's'}.`,
    link: { to: '/rigs', label: 'Rigs' },
  };
}

function dmxStep(dmx: HealthReading): SetupStep {
  return {
    key: 'dmx',
    title: 'Light output',
    state: dmx.level === 'ok' ? 'done' : dmx.level === 'warn' ? 'warn' : 'todo',
    detail: dmx.detail,
  };
}

function audioStep(audio: HealthReading): SetupStep {
  return {
    key: 'audio',
    title: 'Audio feed',
    state: audio.level === 'ok' ? 'done' : audio.level === 'warn' ? 'warn' : 'todo',
    detail: audio.level === 'ok' ? audio.detail : `${audio.detail} Pick the desk feed under Audio input.`,
  };
}

function autopilotStep(effects: EffectsStatus | null): SetupStep {
  const title = 'Autopilot';
  if (!effects) {
    return { key: 'autopilot', title, state: 'warn', detail: 'Cannot reach the effects engine.' };
  }
  if (!effects.running) {
    return { key: 'autopilot', title, state: 'todo', detail: 'The effects engine is stopped.' };
  }
  if (!effects.auto_mode) {
    return { key: 'autopilot', title, state: 'warn', detail: 'In manual. Tap Manual at the top to hand back to the autopilot.' };
  }
  return { key: 'autopilot', title, state: 'done', detail: 'Following the music.' };
}

export const isReadyForShow = (steps: SetupStep[]) => steps.every((s) => s.state === 'done');
