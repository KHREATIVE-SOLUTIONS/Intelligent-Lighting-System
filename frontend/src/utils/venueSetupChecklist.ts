import type { HealthReading } from './showHealth';

// The New venue setup checklist: nine ordered steps from an empty box to a rig
// that can be demoed to an owner and handed to a console. Kept free of React
// (and of the network) so the status of every step can be tested from plain
// data. See docs/VENUE_SETUP.md.
//
// Not the same thing as utils/setupChecklist.ts, which is the four-line
// pre-show check on the dashboard (rig, output, audio, autopilot).

export type VenueStepKey =
  | 'venue'
  | 'patch'
  | 'layout'
  | 'locate'
  | 'readiness'
  | 'focus'
  | 'audio'
  | 'output'
  | 'export';

export const VENUE_STEP_ORDER: readonly VenueStepKey[] = [
  'venue',
  'patch',
  'layout',
  'locate',
  'readiness',
  'focus',
  'audio',
  'output',
  'export',
];

export type VenueStepStatus = 'done' | 'attention' | 'not_started' | 'skipped' | 'unavailable';

/**
 * Everything a step's buttons can do. The host passes the set it can actually
 * open; an action it cannot is shown as "Not available yet", never as a dead
 * button.
 */
export type VenueActionKey =
  | 'openDemo'
  | 'newRig'
  | 'importRig'
  | 'autoPatch'
  | 'patchSheetImport'
  | 'roomScan'
  | 'editRoom'
  | 'stagePlot'
  | 'locate'
  | 'readiness'
  | 'focusPresets'
  | 'audioInput'
  | 'outputTarget'
  | 'consoleExport'
  | 'handoffPack';

export const ACTION_LABELS: Record<VenueActionKey, string> = {
  openDemo: 'Open the LIV demo',
  newRig: 'New rig (wizard)',
  importRig: 'Import MVR / GDTF / MA2 / CSV',
  autoPatch: 'Auto patch addresses',
  patchSheetImport: 'Import a patch sheet',
  roomScan: 'Room scan',
  editRoom: 'Edit room',
  stagePlot: 'Stage plot underlay',
  locate: 'Flash and tap',
  readiness: 'Readiness checks',
  focusPresets: 'Focus presets',
  audioInput: 'Pick audio input',
  outputTarget: 'Set output target',
  consoleExport: 'Export to console',
  handoffPack: 'Handoff pack',
};

/** The buttons each step offers, in the order they are shown. */
export const STEP_ACTIONS: Record<VenueStepKey, readonly VenueActionKey[]> = {
  venue: ['openDemo', 'newRig', 'importRig'],
  patch: ['autoPatch', 'patchSheetImport'],
  layout: ['roomScan', 'editRoom', 'stagePlot'],
  locate: ['locate'],
  readiness: ['readiness'],
  focus: ['focusPresets'],
  audio: ['audioInput'],
  output: ['outputTarget'],
  export: ['consoleExport', 'handoffPack'],
};

const TITLES: Record<VenueStepKey, string> = {
  venue: 'Venue and rig',
  patch: 'Patch',
  layout: 'Layout',
  locate: 'Locate',
  readiness: 'Readiness checks',
  focus: 'Focus presets',
  audio: 'Audio input',
  output: 'Output target',
  export: 'Export to console',
};

/** Only what the checklist reads off a rig fixture. */
export interface SetupFixture {
  universe?: number | null;
  dmx_address?: number | null;
  is_active?: boolean;
  tags?: string[] | null;
}

export interface SetupRig {
  id: number;
  name: string;
  fixtures: SetupFixture[];
  /** A scanned room is stored on the rig (room_shell.source === 'scan'). */
  hasScannedRoom: boolean;
}

export interface VenueSetupInput {
  /** The rig being set up; null when none is open. */
  rig: SetupRig | null;
  /** The engine is running a built-in demo preset rather than a patched rig. */
  demoRunning?: boolean | null;
  /** Address clashes in the rig's patch; null when not known. */
  conflictCount?: number | null;
  /** The rig's stage plot underlay; null when not known. */
  stagePlot?: { present: boolean; calibrated: boolean } | null;
  /** The readiness report's counts; null when not fetched (or it failed). */
  readiness?: { ok: number; warn: number; fail: number } | null;
  /** The focus preset table: moving heads aimed and targets offered; null when not fetched. */
  focus?: { heads: number; targets: number } | null;
  /** The status bar's audio reading (readAudioHealth). */
  audio: HealthReading;
  /** The tempo the engine hears, when it reports one. */
  bpm?: number | null;
  /** The status bar's output reading (readDmxHealth). */
  output: HealthReading;
  /** Steps the operator chose to skip for this rig. */
  skipped?: ReadonlySet<VenueStepKey>;
  /** The actions the host can open. */
  available: ReadonlySet<VenueActionKey>;
}

export interface VenueStep {
  key: VenueStepKey;
  number: number;
  title: string;
  status: VenueStepStatus;
  /** One plain line: what was found and what to do next. */
  detail: string;
  /** The step's buttons the host can open. */
  actions: VenueActionKey[];
  /** The step's buttons that do not exist on this build. */
  missing: VenueActionKey[];
}

type Judged = { status: Exclude<VenueStepStatus, 'skipped' | 'unavailable'>; detail: string };

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

const activeFixtures = (rig: SetupRig) => rig.fixtures.filter((f) => f.is_active !== false);

const isUnconfirmed = (f: SetupFixture) => (f.tags ?? []).includes('position_unconfirmed');

const hasAddress = (f: SetupFixture) => typeof f.dmx_address === 'number' && f.dmx_address >= 1 && f.dmx_address <= 512;

const NO_RIG: Judged = { status: 'not_started', detail: 'Open or create a rig first (step 1).' };
const NO_FIXTURES: Judged = { status: 'not_started', detail: 'The rig has no fixtures yet (step 1).' };

function judgeVenue(input: VenueSetupInput): Judged {
  const { rig, demoRunning } = input;
  if (!rig) {
    return {
      status: 'not_started',
      detail: demoRunning
        ? 'The LIV demo can show the owner the system now. Create or import this venue’s rig next.'
        : 'Load the LIV demo to show the owner, or create or import this venue’s rig.',
    };
  }
  const count = activeFixtures(rig).length;
  if (count === 0) {
    return { status: 'attention', detail: `"${rig.name}" has no fixtures yet. Add them, or import the venue’s file.` };
  }
  return { status: 'done', detail: `"${rig.name}", ${plural(count, 'fixture')}.` };
}

function judgePatch(input: VenueSetupInput): Judged {
  const { rig, conflictCount } = input;
  if (!rig) return NO_RIG;
  const active = activeFixtures(rig);
  if (active.length === 0) return NO_FIXTURES;
  const unaddressed = active.filter((f) => !hasAddress(f)).length;
  if (unaddressed > 0) {
    return { status: 'attention', detail: `${plural(unaddressed, 'fixture has', 'fixtures have')} no DMX address. Auto patch gives them one.` };
  }
  if (conflictCount && conflictCount > 0) {
    return { status: 'attention', detail: `${plural(conflictCount, 'address clash', 'address clashes')} in the patch. Auto patch, or re-address them in the patch table.` };
  }
  const universes = new Set(active.map((f) => f.universe ?? 0)).size;
  return { status: 'done', detail: `All ${plural(active.length, 'fixture')} addressed over ${plural(universes, 'universe')}, no clashes.` };
}

function judgeLayout(input: VenueSetupInput): Judged {
  const { rig, stagePlot } = input;
  if (!rig) return NO_RIG;
  if (activeFixtures(rig).length === 0) return NO_FIXTURES;
  if (rig.hasScannedRoom && stagePlot?.calibrated) {
    return { status: 'done', detail: 'The room is scanned and the stage plot is calibrated under the plan.' };
  }
  if (rig.hasScannedRoom) return { status: 'done', detail: 'The room is scanned; trusses and walls are on the plan.' };
  if (stagePlot?.calibrated) return { status: 'done', detail: 'The stage plot is calibrated under the plan.' };
  if (stagePlot?.present) {
    return { status: 'attention', detail: 'A stage plot is uploaded but not calibrated yet. Pick two points on it to scale it.' };
  }
  return {
    status: 'not_started',
    detail: 'Fixtures sit where they were placed. Scan the room or lay the venue’s stage plot under the plan.',
  };
}

function judgeLocate(input: VenueSetupInput): Judged {
  const { rig } = input;
  if (!rig) return NO_RIG;
  const active = activeFixtures(rig);
  if (active.length === 0) return NO_FIXTURES;
  const unconfirmed = active.filter(isUnconfirmed).length;
  if (unconfirmed === 0) return { status: 'done', detail: `All ${plural(active.length, 'position')} confirmed.` };
  if (unconfirmed === active.length) {
    return { status: 'not_started', detail: `None of the ${plural(active.length, 'position')} are confirmed. Flash each light and tap where it is.` };
  }
  return {
    status: 'attention',
    detail: `${unconfirmed} of ${plural(active.length, 'position')} still unconfirmed. Flash and tap them.`,
  };
}

function judgeReadiness(input: VenueSetupInput): Judged {
  const { rig, readiness } = input;
  if (!rig) return NO_RIG;
  if (!readiness) return { status: 'not_started', detail: 'Not checked yet. Run the readiness checks.' };
  if (readiness.fail > 0) {
    const warn = readiness.warn > 0 ? ` and ${plural(readiness.warn, 'warning')}` : '';
    return { status: 'attention', detail: `${plural(readiness.fail, 'check fails', 'checks fail')}${warn}. Open the checks; most have a one-press fix.` };
  }
  if (readiness.warn > 0) {
    return { status: 'done', detail: `No failures. ${plural(readiness.warn, 'warning')} worth a look.` };
  }
  return { status: 'done', detail: 'Every check passes.' };
}

function judgeFocus(input: VenueSetupInput): Judged {
  const { rig, focus } = input;
  if (!rig) return NO_RIG;
  if (!focus) return { status: 'not_started', detail: 'Not read yet. Open the focus presets.' };
  if (focus.heads === 0) return { status: 'done', detail: 'No moving heads in the rig, so there is nothing to aim.' };
  if (focus.targets === 0) {
    return { status: 'attention', detail: `${plural(focus.heads, 'moving head')} but no focus targets. Add the stage and booth positions.` };
  }
  return { status: 'done', detail: `${plural(focus.targets, 'focus target')} for ${plural(focus.heads, 'moving head')}.` };
}

function judgeAudio(input: VenueSetupInput): Judged {
  const { audio, bpm } = input;
  if (audio.level === 'ok') {
    const beat = bpm && bpm > 0 ? ` Beat at about ${Math.round(bpm)} BPM.` : '';
    return { status: 'done', detail: `${audio.detail}${beat}` };
  }
  if (audio.level === 'down') {
    return { status: 'not_started', detail: `${audio.detail} Pick the desk feed and play some music.` };
  }
  return { status: 'attention', detail: audio.detail };
}

function judgeOutput(input: VenueSetupInput): Judged {
  const { output } = input;
  if (output.level === 'ok') return { status: 'done', detail: output.detail };
  if (output.level === 'down') return { status: 'not_started', detail: output.detail };
  return { status: 'attention', detail: output.detail };
}

function judgeExport(input: VenueSetupInput): Judged {
  const { rig, readiness } = input;
  if (!rig) return NO_RIG;
  if (activeFixtures(rig).length === 0) return NO_FIXTURES;
  // Nothing on the box records that an export was taken, so this step never
  // claims to be done: it says whether the rig is fit to export.
  if (readiness && readiness.fail > 0) {
    return {
      status: 'attention',
      detail: `You can export, but ${plural(readiness.fail, 'readiness check fails', 'readiness checks fail')}. The handoff pack will list them.`,
    };
  }
  if (!readiness) {
    return { status: 'not_started', detail: 'Run the readiness checks first, then take an MA2 or MVR file and the handoff pack.' };
  }
  return { status: 'not_started', detail: 'Ready to export: an MA2 or MVR file for the house console, and the handoff pack.' };
}

const JUDGES: Record<VenueStepKey, (input: VenueSetupInput) => Judged> = {
  venue: judgeVenue,
  patch: judgePatch,
  layout: judgeLayout,
  locate: judgeLocate,
  readiness: judgeReadiness,
  focus: judgeFocus,
  audio: judgeAudio,
  output: judgeOutput,
  export: judgeExport,
};

/** The steps that mean something before any rig is open. */
const RIGLESS_STEPS: ReadonlySet<VenueStepKey> = new Set<VenueStepKey>(['venue', 'audio', 'output']);

export function buildVenueSetupSteps(input: VenueSetupInput): VenueStep[] {
  const skipped = input.skipped ?? new Set<VenueStepKey>();
  return VENUE_STEP_ORDER.map((key, index) => {
    const judged = JUDGES[key](input);
    const actions = STEP_ACTIONS[key].filter((a) => input.available.has(a));
    const missing = STEP_ACTIONS[key].filter((a) => !input.available.has(a));
    let status: VenueStepStatus = judged.status;
    let detail = judged.detail;
    // Done is done, whatever was skipped. Otherwise a skip wins, then a step
    // with nothing to judge and nothing to open says so. With no rig open, a
    // rig's step is waiting on step 1, not missing from the build.
    const waitsOnRig = !input.rig && !RIGLESS_STEPS.has(key);
    if (status !== 'done' && skipped.has(key)) {
      status = 'skipped';
    } else if (status === 'not_started' && actions.length === 0 && !waitsOnRig) {
      status = 'unavailable';
      detail = `Not available yet on this build. ${detail}`;
    }
    return { key, number: index + 1, title: TITLES[key], status, detail, actions, missing };
  });
}

export interface VenueSetupSummary {
  total: number;
  done: number;
  attention: number;
  skipped: number;
  /** The first step still to do: not done, not skipped, and something to open. */
  next: VenueStep | null;
}

export function summarizeVenueSetup(steps: VenueStep[]): VenueSetupSummary {
  const count = (status: VenueStepStatus) => steps.filter((s) => s.status === status).length;
  return {
    total: steps.length,
    done: count('done'),
    attention: count('attention'),
    skipped: count('skipped'),
    next: steps.find((s) => (s.status === 'attention' || s.status === 'not_started') && s.actions.length > 0) ?? null,
  };
}

// Skipped steps are remembered per rig, in the browser that skipped them.

/** The minimum of localStorage the checklist uses, so tests can pass a map. */
export interface KeyValueStore {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export const skippedStorageKey = (rigId: number | null) => `venueSetup.skipped.${rigId ?? 'none'}`;

const isStepKey = (value: unknown): value is VenueStepKey =>
  typeof value === 'string' && (VENUE_STEP_ORDER as readonly string[]).includes(value);

export function loadSkipped(store: KeyValueStore | null | undefined, rigId: number | null): Set<VenueStepKey> {
  if (!store) return new Set();
  try {
    const raw = store.getItem(skippedStorageKey(rigId));
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    return new Set(Array.isArray(parsed) ? parsed.filter(isStepKey) : []);
  } catch {
    // A hand-edited or corrupt entry is treated as nothing skipped.
    return new Set();
  }
}

export function saveSkipped(
  store: KeyValueStore | null | undefined,
  rigId: number | null,
  skipped: ReadonlySet<VenueStepKey>,
): void {
  if (!store) return;
  try {
    const key = skippedStorageKey(rigId);
    if (skipped.size === 0) {
      store.removeItem(key);
    } else {
      store.setItem(key, JSON.stringify(VENUE_STEP_ORDER.filter((k) => skipped.has(k))));
    }
  } catch {
    // Private mode or a full quota: the skip still holds for this session.
  }
}

export function toggleSkipped(skipped: ReadonlySet<VenueStepKey>, key: VenueStepKey): Set<VenueStepKey> {
  const next = new Set(skipped);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
}
