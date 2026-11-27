/**
 * A local beat clock for the crowd and the DJ.
 *
 * The backend reports the beat about 45 times a second: a tempo, and a phase
 * that runs up from 0 and falls back each time the detector hears a beat. The
 * tempo is steady. The phase is not a clean ramp: the detector also fires on
 * off-beat hits, so on a four-on-the-floor track the phase falls back about
 * twice a beat, and not evenly. A crowd that followed it directly bounced at
 * double time.
 *
 * So the clock is a flywheel. It free-runs at the reported tempo every frame,
 * and each fall of the reported phase is a tick that nudges it. Ticks are
 * folded onto a half-beat grid, so an off-beat hit corrects the clock as well
 * as a beat does instead of dragging it.
 *
 * What that cannot tell is which half is which: the clock's beat may be the
 * music's beat or its off-beat. Nothing in the reports settles it (the band
 * energies are shares of the total, and the bass share is the same on both),
 * so the crowd is in time with the music but may land between the kicks. A
 * phase that ran once per beat at the trusted tempo would fix that at source.
 *
 * The clock lives in a ref and never touches React state, so a message does
 * not re-render anything.
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
  // Last report.
  reportedPhase: number;
  /** When the reported phase last changed; a stuck phase means no music. */
  phaseMovedAtMs: number;
  // Flywheel state.
  /** Beats still to be added to (or taken from) `beat`, bled in smoothly. */
  correction: number;
  lastTickAtMs: number;
  /** Ticks taken since the beat started running. */
  ticks: number;
};

const DEFAULT_BPM = 120;
/** No change in reported phase for this long means the beat has stopped. */
const STALE_AFTER_MS = 1500;
/** A fall in reported phase bigger than this is the detector hearing a beat. */
const TICK_FALL = 0.3;
/** Two ticks closer than this fraction of a beat are one hit reported twice. */
const TICK_REFRACTORY_BEATS = 0.2;
/** How much of a tick's error is taken out, once the clock has found the beat.
 *  Small, because the tempo is trusted and the ticks are ragged. */
const TICK_GAIN = 0.15;
/** The first few ticks are taken whole, to find the beat quickly. */
const TICKS_TO_LOCK = 3;
/** Fastest the clock may be pulled, in beats per second. Under the slowest
 *  tempo, so the beat never runs backwards. */
const MAX_PULL_PER_SEC = 0.6;
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
    phaseMovedAtMs: -Infinity,
    correction: 0,
    lastTickAtMs: -Infinity,
    ticks: 0,
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

/** The detector heard a hit `agoBeats` ago. */
function tick(clock: BeatClock, agoBeats: number, nowMs: number): void {
  const beatMs = 60000 / clock.bpm;
  if (nowMs - clock.lastTickAtMs < TICK_REFRACTORY_BEATS * beatMs) return;
  clock.lastTickAtMs = nowMs;

  // Where the clock stood when the hit landed, counting what it already owes.
  const at = clock.beat + clock.correction - agoBeats;
  const phase = at - Math.floor(at);
  // Distance to the nearest half-beat line, -0.25..0.25.
  let error = phase % 0.5;
  if (error > 0.25) error -= 0.5;
  clock.correction -= error * (clock.ticks < TICKS_TO_LOCK ? 1 : TICK_GAIN);
  clock.ticks += 1;
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
  if (typeof phase !== 'number' || !Number.isFinite(phase) || phase < 0 || phase > 1) return;

  if (Math.abs(phaseDelta(clock.reportedPhase, phase)) > 1e-4) clock.phaseMovedAtMs = nowMs;
  const fell = phase < clock.reportedPhase - TICK_FALL;
  clock.reportedPhase = phase;
  // The phase left over after the fall is how long ago the hit was.
  if (fell) tick(clock, phase, nowMs);
}

/** Advance the clock by one frame. */
export function advanceBeatClock(clock: BeatClock, deltaSec: number, nowMs: number): void {
  const dt = Math.min(Math.max(deltaSec, 0), 0.25);
  const wasRunning = clock.running;
  clock.running = nowMs - clock.phaseMovedAtMs < STALE_AFTER_MS;

  if (clock.running) {
    clock.beat += dt * (clock.bpm / 60);
    // Bleed the owed correction in, so the beat speeds up or eases off for a
    // moment rather than jumping.
    const pull = Math.min(Math.abs(clock.correction), dt * MAX_PULL_PER_SEC) * Math.sign(clock.correction);
    clock.beat += pull;
    clock.correction -= pull;
  } else if (wasRunning) {
    // The music stopped: forget the lock, so the next track is found afresh.
    clock.correction = 0;
    clock.ticks = 0;
  }

  clock.targetEnergy = clock.running ? sectionEnergy(clock.section) : IDLE_ENERGY;
  clock.energy += (clock.targetEnergy - clock.energy) * Math.min(1, dt * ENERGY_EASE_PER_SEC);
}
