// Show Types
export interface Show {
  id: number;
  name: string;
  description?: string;
  duration?: number;
  bpm?: number;
  status: ShowStatus;
  base_valence: number;
  base_arousal: number;
  created_at: string;
  updated_at: string;
  created_by?: string;
  audio_fingerprint_id?: number;
  tracks: Track[];
  cues: Cue[];
}

export type ShowStatus = 'draft' | 'ready' | 'playing' | 'paused' | 'completed';

export interface ShowCreate {
  name: string;
  description?: string;
  duration?: number;
  bpm?: number;
  base_valence?: number;
  base_arousal?: number;
}

export interface ShowUpdate {
  name?: string;
  description?: string;
  duration?: number;
  bpm?: number;
  status?: ShowStatus;
  base_valence?: number;
  base_arousal?: number;
}

// Track Types
export interface Track {
  id: number;
  show_id: number;
  name: string;
  track_type: string;
  order: number;
  muted: boolean;
  solo: boolean;
  fixture_ids: number[];
  cues: Cue[];
}

export interface TrackCreate {
  name: string;
  track_type?: string;
  order?: number;
  fixture_ids?: number[];
}

// Cue Types
export interface Cue {
  id: number;
  show_id: number;
  track_id?: number;
  name?: string;
  cue_type: CueType;
  start_time: number;
  duration: number;
  fade_in: number;
  fade_out: number;
  dmx_values: Record<string, number>;
  effect_type?: string;
  effect_params: Record<string, unknown>;
  audio_reactive: boolean;
  audio_trigger?: string;
  audio_params: Record<string, unknown>;
  valence?: number;
  arousal?: number;
  created_at: string;
  updated_at: string;
}

export type CueType = 'static' | 'fade' | 'chase' | 'effect' | 'audio_reactive';

export interface CueCreate {
  name?: string;
  cue_type?: CueType;
  start_time: number;
  duration?: number;
  fade_in?: number;
  fade_out?: number;
  dmx_values?: Record<string, number>;
  effect_type?: string;
  effect_params?: Record<string, unknown>;
  audio_reactive?: boolean;
  audio_trigger?: string;
  track_id?: number;
  valence?: number;
  arousal?: number;
}

// Rig Types
export interface Rig {
  id: number;
  name: string;
  description?: string;
  venue?: string;
  stage_width: number;
  stage_depth: number;
  stage_height: number;
  universes: UniverseConfig[];
  created_at: string;
  updated_at: string;
  created_by?: string;
  is_active: boolean;
  fixtures: RigFixture[];
  /**
   * The room round the rig, where the rig describes one: scenery for the 3D
   * view. A demo venue preset carries one it was written with; a database rig
   * has one once a room scan has been applied to it (docs/ROOM_SCAN.md).
   */
  room_shell?: RoomShell | null;
  /**
   * Where fixtures stood before a room scan moved them, while that can still
   * be undone. Null when there is nothing to undo. Read-only: written by the
   * room-scan endpoint (docs/ROOM_SCAN.md).
   */
  room_scan_undo?: RoomScanUndoRecord | null;
}

export interface RoomScanUndoRecord {
  file?: string | null;
  applied_at?: string | null;
  moves?: Array<{
    rig_fixture_id: number;
    name?: string;
    from: { x: number; y: number; z: number };
    to: { x: number; y: number; z: number };
  }> | null;
}

/** A box standing on the floor (or `base_height` above it), sides square to the room. */
export interface RoomShellBox {
  center_x: number;
  center_z: number;
  /** Along X. */
  width: number;
  /** Along Z. */
  depth: number;
  height: number;
  base_height?: number;
  name?: string;
  basis?: string;
  /** From a room scan: what its size suggests it is ('stage', 'riser' or 'booth'). */
  kind?: string;
  /** True for anything a scan found: nobody has checked it against the room. */
  suggested?: boolean;
}

/** A truss or bar a room scan found overhead, as a line on the plan at a height. */
export interface RoomShellLine {
  name?: string;
  x1: number;
  z1: number;
  x2: number;
  z2: number;
  /** Height of its underside: where a fixture hangs from. */
  height: number;
  top?: number;
  length?: number;
  /** Its width across the line. */
  across?: number;
  /**
   * Which way it runs: 'x' is across the room, 'z' is upstage to downstage,
   * 'angled' is anything else. A reader should go by the line's two ends, which
   * every stored shell has; this and `heading_deg` are for wording.
   */
  axis?: string;
  /** Degrees clockwise from across the room, seen from above: 0 runs across, 90 upstage to downstage. */
  heading_deg?: number;
  suggested?: boolean;
  basis?: string;
}

/** A ring of truss a room scan found overhead: a circle on the plan at a height. */
export interface RoomShellRing {
  name?: string;
  center_x: number;
  center_z: number;
  /** To the middle of the truss. */
  radius: number;
  /** Height of its underside: where a fixture hangs from. */
  height: number;
  top?: number;
  /** Its width across the ring, inside edge to outside edge. */
  across?: number;
  suggested?: boolean;
  basis?: string;
}

/**
 * The room around a rig, in metres and in the rig's own axes: origin at the
 * centre of the floor, X across, Y up, -Z upstage. Mirrors `RoomShell` in
 * backend/app/services/demo/venue_presets.py. Angles are degrees clockwise
 * from upstage seen from above: 0 is -Z, 90 is +X, 180 is +Z.
 */
export interface RoomShell {
  basis?: string;
  /** A shallow dome ceiling: a spherical cap over a circle on the plan. */
  dome?: {
    radius: number;
    center_x: number;
    center_z: number;
    rim_height: number;
    apex_height: number;
    diameter_ft?: number;
    basis?: string;
  } | null;
  dance_floor?: { center_x: number; center_z: number; radius: number; basis?: string } | null;
  /** Part of a flat ring at one height: a balcony or mezzanine. */
  balcony?: {
    center_x: number;
    center_z: number;
    inner_radius: number;
    outer_radius: number;
    soffit_height: number;
    deck_height: number;
    start_deg: number;
    end_deg: number;
    basis?: string;
  } | null;
  dj_booth?: RoomShellBox | null;
  rear_stage?: RoomShellBox | null;
  led_walls?: RoomShellBox[] | null;

  // --- What a room scan writes (backend/app/services/room_scan/extract.py) ---
  /** 'scan' when the shell was read from a phone scan of the room. */
  source?: string;
  /** True for a scanned shell: every part of it is a suggestion. */
  suggested?: boolean;
  /**
   * The room's own box: wall to wall, floor to ceiling, centred on the origin.
   * A room that is not a box also carries `outline`: the corners of its floor
   * in order, clockwise seen from above, the last joined back to the first.
   * Its walls are the segments between them, and width and depth are then the
   * box round the outline. A shell with no outline is a box.
   */
  room?: {
    width: number;
    depth: number;
    height: number;
    outline?: Array<{ x: number; z: number }> | null;
    suggested?: boolean;
    basis?: string;
  } | null;
  /** Raised areas: a stage, a riser, a booth. */
  risers?: RoomShellBox[] | null;
  /** Trusses and bars found overhead, at any heading on the plan. */
  truss_lines?: RoomShellLine[] | null;
  /** Rings of truss found overhead. Absent from a shell stored before rings were read. */
  truss_rings?: RoomShellRing[] | null;
  hanging_bands?: Array<{
    height: number; top?: number; lines?: number; rings?: number; suggested?: boolean; basis?: string;
  }> | null;
  /** How the scan was read: file, units, up axis, turns. */
  scan?: {
    file?: string | null;
    format?: string;
    points?: number;
    triangles?: number;
    point_cloud?: boolean;
    units?: string;
    up_axis?: string;
    wall_turn_deg?: number;
    quarter_turns?: number;
    walls_found?: number;
    other_overhead_objects?: number;
  } | null;
}

export interface UniverseConfig {
  universe: number;
  protocol: string;
  ip_address?: string;
  port: number;
}

export interface RigCreate {
  name: string;
  description?: string;
  venue?: string;
  stage_width?: number;
  stage_depth?: number;
  stage_height?: number;
  universes?: UniverseConfig[];
}

// Fixture Types
export interface Fixture {
  id: number;
  manufacturer: string;
  model: string;
  fixture_type: FixtureType;
  gdtf_id?: string;
  weight?: number;
  power?: number;
  beam_angle?: number;
  pan_range: number;
  tilt_range: number;
  has_rgb: boolean;
  has_cmy: boolean;
  has_color_wheel: boolean;
  color_temp_range?: number[];
  thumbnail_url?: string;
  model_3d_url?: string;
  source?: string;
  source_id?: string;
  categories?: string[];
  popularity_score?: number;
  is_bundled?: boolean;
  modes: FixtureMode[];
}

export type FixtureType =
  | 'moving_head'
  | 'led_par'
  | 'led_bar'
  | 'wash'
  | 'spot'
  | 'beam'
  | 'strobe'
  | 'laser'
  | 'effect'
  | 'dimmer'
  | 'other';

export interface FixtureMode {
  id: number;
  fixture_id: number;
  name: string;
  channel_count: number;
  description?: string;
  channels: FixtureChannel[];
}

export interface FixtureChannel {
  id: number;
  mode_id: number;
  channel_number: number;
  channel_type: ChannelType;
  name: string;
  default_value: number;
  min_value: number;
  max_value: number;
  is_fine: boolean;
  coarse_channel?: number;
  /** Named spans of this channel's values, where the profile gives them. */
  value_ranges?: Array<{ name?: string | null; min_value: number; max_value: number }> | null;
}

export type ChannelType =
  | 'dimmer'
  | 'red'
  | 'green'
  | 'blue'
  | 'white'
  | 'amber'
  | 'uv'
  | 'pan'
  | 'pan_fine'
  | 'tilt'
  | 'tilt_fine'
  | 'zoom'
  | 'focus'
  | 'gobo'
  | 'gobo_rotation'
  | 'prism'
  | 'color_wheel'
  | 'shutter'
  | 'strobe'
  | 'speed'
  | 'effect'
  | 'macro'
  | 'cyan'
  | 'magenta'
  | 'yellow'
  | 'cto'
  | 'ctb'
  | 'iris'
  | 'frost'
  | 'animation'
  | 'framing'
  | 'gobo2'
  | 'gobo2_rotation'
  | 'lime'
  | 'indigo'
  | 'other';

export interface RigFixture {
  id: number;
  rig_id: number;
  fixture_id: number;
  name?: string;
  fixture_number?: number;
  universe: number;
  dmx_address: number;
  mode_id?: number;
  position_x: number;
  position_y: number;
  position_z: number;
  rotation_x: number;
  rotation_y: number;
  rotation_z: number;
  group_name?: string;
  /**
   * What this light points at, in the key-lighting vocabulary. Optional: a rig
   * that names no zones behaves exactly as it did before zones existed.
   */
  zone?: string | null;
  tags: string[];
  is_active: boolean;
  is_inverted: boolean;
  is_address_locked: boolean;
  serial_number?: string;
  qr_code_data?: string;
  fixture?: Fixture;
}

export interface RigFixtureCreate {
  fixture_id: number;
  name?: string;
  fixture_number?: number;
  universe?: number;
  dmx_address: number;
  mode_id?: number;
  position_x?: number;
  position_y?: number;
  position_z?: number;
  rotation_x?: number;
  rotation_y?: number;
  rotation_z?: number;
  group_name?: string;
  /** Empty string clears it; that is the only way to take a zone back off. */
  zone?: string | null;
  tags?: string[];
  is_address_locked?: boolean;
}

// Professional Lighting Types
export type Genre = 'EDM' | 'ROCK' | 'POP' | 'HIP_HOP' | 'JAZZ';

export type SongSection =
  | 'INTRO'
  | 'VERSE'
  | 'PRE_CHORUS'
  | 'CHORUS'
  | 'DROP'
  | 'BREAKDOWN'
  | 'BRIDGE'
  | 'BUILDUP'
  | 'OUTRO'
  | 'INSTRUMENTAL'
  | 'SOLO'
  | 'UNKNOWN';

export type StrobeMode = 'off' | 'slow' | 'medium' | 'fast' | 'random' | 'beat_sync';
export type ChaseType = 'off' | 'left_right' | 'right_left' | 'center_out' | 'converge' | 'random';
export type MovementType =
  | 'none'
  | 'circle'
  | 'figure_8'
  | 'sweep_lr'
  | 'sweep_fb'
  | 'chase_lr'
  | 'chase_rl'
  | 'converge'
  | 'diverge'
  | 'random'
  | 'ballyhoo'
  | 'tilt_wave'
  | 'pan_wave'
  | 'focus_track';

export interface ProEffect {
  strobeMode: StrobeMode;
  chaseType: ChaseType;
  movementType: MovementType;
  colorWash: { r: number; g: number; b: number } | null;
  intensity: number;
  speed: number;
}

export type StageZone =
  | 'USL' | 'USC' | 'USR'
  | 'MSL' | 'MSC' | 'MSR'
  | 'DSL' | 'DSC' | 'DSR'
  | 'AUDIENCE' | 'ALL';

export interface KeyLightingZone {
  zone: StageZone;
  active: boolean;
  intensity: number;
  color: { r: number; g: number; b: number };
  performerLabel?: string;
}

export interface SectionIntensityState {
  section: SongSection;
  intensity: number;
  targetIntensity: number;
  color: { h: number; s: number; l: number };
  startedAt: number;
}

export interface SectionHistoryEntry {
  section: SongSection;
  startTime: number;
  endTime?: number;
  intensity: number;
}

export interface EmotionVector {
  valence: number;
  arousal: number;
  dominance: number;
  tension: number;
  energy_trajectory: number;
  groove: number;
  darkness: number;
  confidence: number;
}

export interface ProLightingState {
  genre: Genre | null;
  section: SongSection;
  sectionIntensity: number;
  sectionHistory: SectionHistoryEntry[];
  activeEffects: ProEffect;
  keyLightingZones: KeyLightingZone[];
  emotionVector: EmotionVector | null;
  beatPhrase: number;
  beatsPerPhrase: number;
}

// Audio Analysis Types
export interface AudioAnalysis {
  timestamp: string;
  beat: BeatInfo;
  mood: MoodInfo;
  frequency: FrequencyInfo;
}

export interface BeatInfo {
  bpm: number;
  beat_confidence: number;
  is_beat: boolean;
  is_downbeat: boolean;
  beat_position: number;
  time_signature: string;
  phase: number;
}

export interface MoodInfo {
  valence: number;
  arousal: number;
  confidence: number;
  primary_emotion: string;
  emotion_scores: Record<string, number>;
}

export interface FrequencyBand {
  name: string;
  frequency_range: number[];
  energy: number;
  peak_frequency?: number;
}

export interface FrequencyInfo {
  bands: FrequencyBand[];
  spectral_centroid: number;
  spectral_rolloff: number;
  spectral_flux: number;
  rms_energy: number;
  peak_amplitude: number;
}

// DMX Types
export interface DMXFrame {
  universe: number;
  channels: Record<number, number>;
  timestamp?: number;
}

export interface DMXUniverse {
  universe: number;
  data: number[];
}

// API Response Types
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

// Fixture Library Types
export interface OFLFixtureResult {
  manufacturer_key: string;
  fixture_key: string;
  name: string;
  manufacturer: string;
  categories: string[];
}

// Patching Types
export interface PatchConflict {
  fixture_a_id: number;
  fixture_b_id: number;
  universe: number;
  overlap_start: number;
  overlap_end: number;
}

// Rig Template Types
export interface RigTemplate {
  id: number;
  name: string;
  description?: string;
  venue_type?: string;
  stage_width: number;
  stage_depth: number;
  stage_height: number;
  fixture_slots: FixtureSlot[];
  thumbnail_url?: string;
  is_system: boolean;
  is_public: boolean;
  created_by?: string;
  created_at: string;
  usage_count: number;
}

export interface FixtureSlot {
  fixture_type: string;
  count: number;
  group_name?: string;
  positions?: Array<{ x: number; y: number; z: number; rotation_y?: number }>;
  mode_channel_count?: number;
}

export interface RigTemplateCreate {
  name: string;
  description?: string;
  venue_type?: string;
  stage_width?: number;
  stage_depth?: number;
  stage_height?: number;
  fixture_slots?: FixtureSlot[];
  is_public?: boolean;
}

// Wizard Types
export interface VenuePreset {
  key: string;
  name: string;
  description: string;
  stage_width: number;
  stage_depth: number;
  stage_height: number;
  suggested_fixtures: Array<{
    fixture_type: string;
    count: number;
    group_name: string;
    /** Where the preset says this group hangs; the wizard never infers it. */
    mounting_position?: string;
  }>;
}

/** One fixture the wizard is about to create, as POST /api/wizard/create-rig reads it. */
export interface WizardPlacement {
  fixture_id: number;
  mode_id?: number;
  name?: string;
  universe?: number;
  dmx_address: number;
  position_x?: number;
  position_y?: number;
  position_z?: number;
  rotation_y?: number;
  group_name?: string;
  mounting_position?: string;
  /** What this light points at, in the key-lighting vocabulary. */
  zone?: string;
}

export interface WizardData {
  venue_preset?: string;
  stage_width: number;
  stage_depth: number;
  stage_height: number;
  fixtures?: Array<{
    fixture_id: number;
    count: number;
    mode_id?: number;
    group_name?: string;
  }>;
  /** The endpoint creates a rig from these; the fixture list is only the input to placement. */
  placements?: WizardPlacement[];
  rig_name: string;
  venue?: string;
}
