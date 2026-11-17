/**
 * A local beat clock for the crowd and the DJ.
 *
 * The backend reports the beat about 20 times a second: a tempo and a phase
 * that runs 0 to 1 inside each beat. Drawing straight from those reports would
 * step, so the clock free-runs at the reported tempo every frame and is only
 * nudged toward each report. It lives in a ref and never touches React state,
 * so a message does not re-render anything.
 */

export type BeatClock = {
  /** Beats elapsed, continuous. The fractional part is the phase in the beat. */
  beat: number;
  bpm: number;
  /** True while reports show a beat actually running. */
  running: boolean;
  /** Lower-case section name from the engine, '' if none yet. */
  section: string;
  /** 0 to 1: how hard the room should be going, eased toward `targetEnergy`. */
  energy: number;
  targetEnergy: number;
  // Last report, for the phase correction.
  reportedPhase: number;
  reportedAtMs: number;
  /** When the reported phase last changed; a stuck phase means no music. */
  phaseMovedAtMs: number;
};

const DEFAULT_BPM = 120;
/** No change in reported phase for this long means the beat has stopped. */
const STALE_AFTER_MS = 1500;
/** Fraction of the phase error taken out per second. */
const PHASE_PULL_PER_SEC = 6;
const ENERGY_EASE_PER_SEC = 1.6;

/** How energetic each section is, 0 to 1. A drop is the top. */
const SECTION_ENERGY: Record<string, number> = {
  drop: 1.0,
  chorus: 0.78,
  buildup: 0.7,
  solo: 0.65,
  instrumental: 0.55,
  verse: 0.5,
  pre_chorus: 0.58,
  bridge: 0.45,
  intro: 0.36,
  outro: 0.34,
  breakdown: 0.3,
};
const UNKNOWN_SECTION_ENERGY = 0.48;
/** With no beat running the room just stands and shifts about. */
const IDLE_ENERGY = 0;

export function createBeatClock(): BeatClock {
  return {
    beat: 0,
    bpm: DEFAULT_BPM,
    running: false,
    section: '',
    energy: 0,
    targetEnergy: IDLE_ENERGY,
    reportedPhase: 0,
    reportedAtMs: -Infinity,
    phaseMovedAtMs: -Infinity,
  };
}

export function sectionEnergy(section: string): number {
  return SECTION_ENERGY[section] ?? UNKNOWN_SECTION_ENERGY;
}

/** Shortest signed distance from phase `from` to phase `to`, in -0.5..0.5. */
export function phaseDelta(from: number, to: number): number {
  const d = (to - from) % 1;
  if (d > 0.5) return d - 1;
  if (d < -0.5) return d + 1;
  return d;
}

/** Take one `analysis` message. Anything missing or malformed is ignored. */
export function ingestAnalysis(clock: BeatClock, message: unknown, nowMs: number): void {
  const msg = message as { beat?: { bpm?: unknown; phase?: unknown }; lighting?: { section?: unknown } } | null;
  if (!msg || typeof msg !== 'object') return;

  const section = msg.lighting?.section;
  if (typeof section === 'string' && section) clock.section = section.toLowerCase();

  const bpm = Number(msg.beat?.bpm);
  if (Number.isFinite(bpm) && bpm >= 40 && bpm <= 260) clock.bpm = bpm;

  // Only a number inside 0..1 is a beat phase. The demo simulation has another
  // field called `phase` that holds a name, and that must not steer the clock.
  const phase = msg.beat?.phase;
  if (typeof phase === 'number' && Number.isFinite(phase) && phase >= 0 && phase <= 1) {
    if (Math.abs(phaseDelta(clock.reportedPhase, phase)) > 1e-4) clock.phaseMovedAtMs = nowMs;
    clock.reportedPhase = phase;
    clock.reportedAtMs = nowMs;
  }
}

/** Advance the clock by one frame. */
export function advanceBeatClock(clock: BeatClock, deltaSec: number, nowMs: number): void {
  const dt = Math.min(Math.max(deltaSec, 0), 0.25);
  clock.running = nowMs - clock.phaseMovedAtMs < STALE_AFTER_MS;

  if (clock.running) {
    const beatsPerSec = clock.bpm / 60;
    clock.beat += dt * beatsPerSec;

    // Where the last report says the phase should be by now, and how far the
    // free-running clock has drifted from it.
    const expected = clock.reportedPhase + ((nowMs - clock.reportedAtMs) / 1000) * beatsPerSec;
    const current = clock.beat - Math.floor(clock.beat);
    const error = phaseDelta(current, expected - Math.floor(expected));
    clock.beat += error * Math.min(1, dt * PHASE_PULL_PER_SEC);
  }

  clock.targetEnergy = clock.running ? sectionEnergy(clock.section) : IDLE_ENERGY;
  clock.energy += (clock.targetEnergy - clock.energy) * Math.min(1, dt * ENERGY_EASE_PER_SEC);
}
