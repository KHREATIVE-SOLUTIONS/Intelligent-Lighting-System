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
  tags: string[];
  is_active: boolean;
  is_inverted: boolean;
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
  tags?: string[];
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
