import axios from 'axios';
import { useAuthStore } from '../stores/authStore';
import type {
  Show,
  ShowCreate,
  ShowUpdate,
  Track,
  TrackCreate,
  Cue,
  CueCreate,
  Rig,
  RigCreate,
  RigFixture,
  RigFixtureCreate,
  Fixture,
  AudioAnalysis,
  PaginatedResponse,
  PatchConflict,
  RigTemplate,
  RigTemplateCreate,
  VenuePreset,
  WizardData,
  Genre,
  ProLightingState,
} from '../types';

const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// The box reissues the session token on an active session and returns it here.
// Dropping it would freeze the stored token's expiry at issue time, so a box in
// daily use would log the operator out 30 days later, mid-show.
const OPERATOR_TOKEN_HEADER = 'x-operator-token';

api.interceptors.response.use(
  (response) => {
    const reissued = response.headers?.[OPERATOR_TOKEN_HEADER];
    if (typeof reissued === 'string' && reissued) {
      useAuthStore.getState().setSession(reissued);
    }
    return response;
  },
  (error) => {
    const status = error?.response?.status;
    const url: string = error?.config?.url ?? '';
    // A 401 from the login/setup call is a wrong password, not an expired session.
    if (status === 401 && !url.startsWith('/auth/')) {
      useAuthStore.getState().clearSession();
    }
    return Promise.reject(error);
  }
);

// Auth API
export interface AuthStatus {
  configured: boolean;
  authenticated: boolean;
  // false when the backend runs with AUTH_ENABLED=false (dev mode)
  enabled: boolean;
}

interface TokenPayload {
  token?: string;
  access_token?: string;
}

const readToken = (data: TokenPayload | undefined): string | null =>
  data?.token ?? data?.access_token ?? null;

export const authApi = {
  getStatus: async (): Promise<AuthStatus> => {
    const response = await api.get('/auth/status');
    return {
      configured: Boolean(response.data?.configured),
      authenticated: Boolean(response.data?.authenticated),
      // Absent field defaults to enabled=true (older backends were always gated).
      enabled: response.data?.enabled !== false,
    };
  },

  login: async (password: string): Promise<string> => {
    const response = await api.post('/auth/login', { password });
    const token = readToken(response.data);
    if (!token) {
      throw new Error('The server accepted the password but sent no session token.');
    }
    return token;
  },

  setup: async (setupCode: string, password: string): Promise<string | null> => {
    const response = await api.post('/auth/setup', {
      setup_code: setupCode,
      password,
    });
    return readToken(response.data);
  },
};

// Shows API
export const showsApi = {
  list: async (page = 1, size = 20, search?: string): Promise<PaginatedResponse<Show>> => {
    const params = new URLSearchParams({ page: String(page), size: String(size) });
    if (search) params.append('search', search);
    const response = await api.get(`/shows/?${params}`);
    return response.data;
  },

  get: async (id: number): Promise<Show> => {
    const response = await api.get(`/shows/${id}`);
    return response.data;
  },

  create: async (data: ShowCreate): Promise<Show> => {
    const response = await api.post('/shows/', data);
    return response.data;
  },

  update: async (id: number, data: ShowUpdate): Promise<Show> => {
    const response = await api.put(`/shows/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/shows/${id}`);
  },

  duplicate: async (id: number, newName?: string): Promise<Show> => {
    const params = newName ? `?new_name=${encodeURIComponent(newName)}` : '';
    const response = await api.post(`/shows/${id}/duplicate${params}`);
    return response.data;
  },
};

// Tracks API
export const tracksApi = {
  list: async (showId: number): Promise<Track[]> => {
    const response = await api.get(`/shows/${showId}/tracks`);
    return response.data;
  },

  create: async (showId: number, data: TrackCreate): Promise<Track> => {
    const response = await api.post(`/shows/${showId}/tracks`, data);
    return response.data;
  },

  update: async (showId: number, trackId: number, data: Partial<TrackCreate>): Promise<Track> => {
    const response = await api.put(`/shows/${showId}/tracks/${trackId}`, data);
    return response.data;
  },

  delete: async (showId: number, trackId: number): Promise<void> => {
    await api.delete(`/shows/${showId}/tracks/${trackId}`);
  },
};

// Cues API
export const cuesApi = {
  list: async (showId: number, trackId?: number): Promise<Cue[]> => {
    const params = trackId ? `?track_id=${trackId}` : '';
    const response = await api.get(`/shows/${showId}/cues${params}`);
    return response.data;
  },

  create: async (showId: number, data: CueCreate): Promise<Cue> => {
    const response = await api.post(`/shows/${showId}/cues`, data);
    return response.data;
  },

  update: async (showId: number, cueId: number, data: Partial<CueCreate>): Promise<Cue> => {
    const response = await api.put(`/shows/${showId}/cues/${cueId}`, data);
    return response.data;
  },

  delete: async (showId: number, cueId: number): Promise<void> => {
    await api.delete(`/shows/${showId}/cues/${cueId}`);
  },
};

// Rigs API
export const rigsApi = {
  list: async (page = 1, size = 20, search?: string): Promise<PaginatedResponse<Rig>> => {
    const params = new URLSearchParams({ page: String(page), size: String(size) });
    if (search) params.append('search', search);
    const response = await api.get(`/rigs/?${params}`);
    return response.data;
  },

  get: async (id: number): Promise<Rig> => {
    const response = await api.get(`/rigs/${id}`);
    return response.data;
  },

  create: async (data: RigCreate): Promise<Rig> => {
    const response = await api.post('/rigs/', data);
    return response.data;
  },

  update: async (id: number, data: Partial<RigCreate>): Promise<Rig> => {
    const response = await api.put(`/rigs/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/rigs/${id}`);
  },

  activate: async (id: number): Promise<Rig> => {
    const response = await api.post(`/rigs/${id}/activate`);
    return response.data;
  },

  getFixtures: async (rigId: number): Promise<RigFixture[]> => {
    const response = await api.get(`/rigs/${rigId}/fixtures`);
    return response.data;
  },

  addFixture: async (rigId: number, data: RigFixtureCreate): Promise<RigFixture> => {
    const response = await api.post(`/rigs/${rigId}/fixtures`, data);
    return response.data;
  },

  updateFixture: async (
    rigId: number,
    fixtureId: number,
    data: Partial<RigFixtureCreate>
  ): Promise<RigFixture> => {
    const response = await api.put(`/rigs/${rigId}/fixtures/${fixtureId}`, data);
    return response.data;
  },

  removeFixture: async (rigId: number, fixtureId: number): Promise<void> => {
    await api.delete(`/rigs/${rigId}/fixtures/${fixtureId}`);
  },

  getGroups: async (rigId: number): Promise<string[]> => {
    const response = await api.get(`/rigs/${rigId}/groups`);
    return response.data;
  },

  // Auto-patching
  autoPatch: async (rigId: number) => {
    const response = await api.post(`/rigs/${rigId}/auto-patch`);
    return response.data;
  },

  getConflicts: async (rigId: number): Promise<{ conflicts: PatchConflict[] }> => {
    const response = await api.get(`/rigs/${rigId}/patch-conflicts`);
    return response.data;
  },

  getNextAddress: async (rigId: number, universe = 0, channelCount = 16) => {
    const response = await api.get(`/rigs/${rigId}/next-address`, {
      params: { universe, channel_count: channelCount },
    });
    return response.data as { universe: number; address: number | null; channel_count: number };
  },

  // Fixture testing
  testFixture: async (rigId: number, fixtureId: number, testType = 'identify') => {
    const response = await api.post(
      `/rigs/${rigId}/fixtures/${fixtureId}/test`,
      null,
      { params: { test_type: testType } }
    );
    return response.data;
  },

  stopFixtureTest: async (rigId: number, fixtureId: number) => {
    const response = await api.post(`/rigs/${rigId}/fixtures/${fixtureId}/test/stop`);
    return response.data;
  },

  setFixtureChannels: async (rigId: number, fixtureId: number, values: Record<string, number>) => {
    const response = await api.post(`/rigs/${rigId}/fixtures/${fixtureId}/set-channels`, values);
    return response.data;
  },

  testAll: async (rigId: number) => {
    const response = await api.post(`/rigs/${rigId}/test-all`);
    return response.data;
  },

  stopTestAll: async (rigId: number) => {
    const response = await api.post(`/rigs/${rigId}/test-all/stop`);
    return response.data;
  },

  // Batch operations
  batchUpdateFixtures: async (rigId: number, fixtures: Array<Partial<RigFixtureCreate> & { id: number }>) => {
    const response = await api.put(`/rigs/${rigId}/fixtures/batch-update`, { fixtures });
    return response.data;
  },

  duplicateFixture: async (rigId: number, fixtureId: number) => {
    const response = await api.post(`/rigs/${rigId}/fixtures/duplicate/${fixtureId}`);
    return response.data;
  },

  /** Patch one or more fixtures by make and model, importing the profile if needed. */
  patchFromLibrary: async (rigId: number, request: LibraryPatchRequest): Promise<LibraryPatchResult> => {
    const response = await api.post(`/rigs/${rigId}/patch-from-library`, request);
    return response.data;
  },
};

// Fixture library catalog (offline Open Fixture Library + the local library)
export interface CatalogMode {
  id?: number;
  name: string;
  channel_count: number;
  features: string[];
  recommended: boolean;
}

export interface CatalogFixture {
  key: string;
  manufacturer_key: string | null;
  fixture_key: string | null;
  manufacturer: string;
  name: string;
  fixture_type: string;
  categories: string[];
  modes: CatalogMode[];
  recommended_mode: string | null;
  source: string;
  fixture_id: number | null;
  in_library: boolean;
}

export interface OfflineLibraryInfo {
  available: boolean;
  fixture_count: number;
  manufacturer_count: number;
  commit?: string | null;
  generated?: string | null;
}

export interface CatalogSearchResult {
  results: CatalogFixture[];
  offline_library: OfflineLibraryInfo;
}

export interface LibraryPatchRequest {
  library_key?: string;
  fixture_id?: number;
  mode_name?: string;
  quantity: number;
  universe: number;
  start_address?: number;
  group_name?: string;
  mounting_position?: string;
}

export interface LibraryPatchResult {
  rig_id: number;
  fixture: {
    id: number;
    manufacturer: string;
    model: string;
    fixture_type: string;
    imported: boolean;
  };
  mode: { id: number; name: string; channel_count: number; features: string[]; chosen_by: string };
  group_name: string | null;
  mounting_position: string;
  patched: Array<{
    id: number;
    name: string;
    fixture_number: number;
    universe: number;
    dmx_address: number;
    last_address: number;
  }>;
  applied_live: boolean;
  notes: string[];
}

// Flash-to-identify walkthrough API
export interface IdentifyStep {
  fixture_id: number;
  label: string;
  universe: number;
  dmx_address: number;
  position_x: number;
  position_y: number;
  position_z: number;
  /** False when the patch does not tell us how to light this fixture. */
  can_flash: boolean;
  blocked_reason: string | null;
  flashing: boolean;
}

export interface IdentifyUnresponsive {
  fixture_id: number;
  label: string;
  universe: number;
  dmx_address: number;
  reason: string;
}

export interface IdentifySession {
  session_id: string;
  rig_id: number;
  rig_name: string;
  stage_width: number;
  stage_depth: number;
  total: number;
  step_number: number;
  complete: boolean;
  flash_level: number;
  current: IdentifyStep | null;
  placed: number;
  kept: number;
  no_response: number;
  unresponsive: IdentifyUnresponsive[];
  heartbeat_timeout_s: number;
  flash_max_s: number;
}

const identifyPath = (rigId: number, sessionId?: string) =>
  sessionId ? `/rigs/${rigId}/identify/${sessionId}` : `/rigs/${rigId}/identify`;

export const identifyApi = {
  start: async (rigId: number): Promise<IdentifySession> => {
    const response = await api.post(`${identifyPath(rigId)}/start`);
    return response.data;
  },

  get: async (rigId: number, sessionId: string): Promise<IdentifySession> => {
    const response = await api.get(identifyPath(rigId, sessionId));
    return response.data;
  },

  heartbeat: async (rigId: number, sessionId: string): Promise<IdentifySession> => {
    const response = await api.post(`${identifyPath(rigId, sessionId)}/heartbeat`);
    return response.data;
  },

  flash: async (
    rigId: number,
    sessionId: string,
    fixtureId?: number
  ): Promise<IdentifySession> => {
    const response = await api.post(
      `${identifyPath(rigId, sessionId)}/flash`,
      null,
      { params: fixtureId === undefined ? undefined : { fixture_id: fixtureId } }
    );
    return response.data;
  },

  /** Canonical stage coordinates: x across (0 centre), z depth (+z toward the audience). */
  recordPosition: async (
    rigId: number,
    sessionId: string,
    position: {
      position_x: number;
      position_z: number;
      position_y?: number;
      /** Which light this answer is about; the server refuses any other. */
      fixture_id?: number;
    }
  ): Promise<IdentifySession> => {
    const response = await api.post(`${identifyPath(rigId, sessionId)}/position`, position);
    return response.data;
  },

  skip: async (
    rigId: number,
    sessionId: string,
    reason?: string,
    fixtureId?: number
  ): Promise<IdentifySession> => {
    const response = await api.post(`${identifyPath(rigId, sessionId)}/skip`, {
      reason: reason ?? null,
      fixture_id: fixtureId ?? null,
    });
    return response.data;
  },

  keep: async (
    rigId: number,
    sessionId: string,
    fixtureId?: number
  ): Promise<IdentifySession> => {
    const response = await api.post(
      `${identifyPath(rigId, sessionId)}/advance`,
      null,
      { params: fixtureId === undefined ? undefined : { fixture_id: fixtureId } }
    );
    return response.data;
  },

  end: async (rigId: number, sessionId: string): Promise<void> => {
    await api.post(`${identifyPath(rigId, sessionId)}/end`);
  },

  /**
   * Release the rig from a tab that is going away. A normal request is abandoned
   * when the document unloads, which would leave a fixture latched at full until
   * the server's own watchdog fires.
   */
  endOnUnload: (rigId: number, sessionId: string): void => {
    const token = useAuthStore.getState().token;
    try {
      void fetch(`${API_BASE_URL}${identifyPath(rigId, sessionId)}/end`, {
        method: 'POST',
        keepalive: true,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
    } catch {
      // The server watchdog is the guarantee; this is only the fast path.
    }
  },
};

// Fixtures API
export interface OnlineFixtureResult {
  manufacturer_key: string;
  fixture_key: string;
  manufacturer?: string;
  name?: string;
  categories?: string[];
}

export interface OnlineFixtureSearchResult {
  results: OnlineFixtureResult[];
  error?: string;
}

export interface GdtfImportResult {
  message: string;
  fixture_id: number;
  manufacturer?: string;
  model?: string;
  modes?: number;
  /** False when the GDTF ID was already in the library and nothing was written. */
  created?: boolean;
}

/**
 * OFL search results arrive either as flat "manufacturer/fixture" strings
 * (the shape of the upstream OFL API) or as pre-expanded objects.
 */
const normalizeOnlineFixture = (entry: unknown): OnlineFixtureResult[] => {
  const split = (combined: string): [string, string] => {
    const separator = combined.indexOf('/');
    if (separator <= 0) return ['', ''];
    return [combined.slice(0, separator), combined.slice(separator + 1)];
  };

  if (typeof entry === 'string') {
    const [manufacturerKey, fixtureKey] = split(entry);
    return manufacturerKey && fixtureKey
      ? [{ manufacturer_key: manufacturerKey, fixture_key: fixtureKey }]
      : [];
  }

  if (entry && typeof entry === 'object') {
    const raw = entry as Record<string, unknown>;
    const combined = typeof raw.source_id === 'string' ? raw.source_id : '';
    const [fallbackManufacturer, fallbackFixture] = split(combined);
    const manufacturerKey =
      (raw.manufacturer_key as string) || (raw.manufacturerKey as string) || fallbackManufacturer;
    const fixtureKey =
      (raw.fixture_key as string) || (raw.fixtureKey as string) || fallbackFixture;

    if (!manufacturerKey || !fixtureKey) return [];

    return [
      {
        manufacturer_key: manufacturerKey,
        fixture_key: fixtureKey,
        manufacturer: typeof raw.manufacturer === 'string' ? raw.manufacturer : undefined,
        name:
          typeof raw.name === 'string'
            ? raw.name
            : typeof raw.model === 'string'
              ? raw.model
              : undefined,
        categories: Array.isArray(raw.categories) ? (raw.categories as string[]) : undefined,
      },
    ];
  }

  return [];
};

export const fixturesApi = {
  list: async (
    page = 1,
    size = 20,
    search?: string,
    manufacturer?: string
  ): Promise<PaginatedResponse<Fixture>> => {
    const params = new URLSearchParams({ page: String(page), size: String(size) });
    if (search) params.append('search', search);
    if (manufacturer) params.append('manufacturer', manufacturer);
    const response = await api.get(`/fixtures/?${params}`);
    return response.data;
  },

  get: async (id: number): Promise<Fixture> => {
    const response = await api.get(`/fixtures/${id}`);
    return response.data;
  },

  getManufacturers: async (): Promise<string[]> => {
    const response = await api.get('/fixtures/manufacturers/list');
    return response.data;
  },

  getTypes: async (): Promise<string[]> => {
    const response = await api.get('/fixtures/types/list');
    return response.data;
  },

  // Library operations
  searchOnline: async (
    query: string,
    manufacturer?: string
  ): Promise<OnlineFixtureSearchResult> => {
    const params = new URLSearchParams({ query });
    if (manufacturer) params.append('manufacturer', manufacturer);
    const response = await api.get(`/fixtures/library/search?${params}`);
    const payload = response.data;
    const raw = Array.isArray(payload) ? payload : payload?.results;
    return {
      results: Array.isArray(raw) ? raw.flatMap(normalizeOnlineFixture) : [],
      error: typeof payload?.error === 'string' ? payload.error : undefined,
    };
  },

  searchCatalog: async (
    query: string,
    fixtureType?: string,
    limit = 30
  ): Promise<CatalogSearchResult> => {
    const params = new URLSearchParams({ q: query, limit: String(limit) });
    if (fixtureType) params.append('fixture_type', fixtureType);
    const response = await api.get(`/fixtures/library/catalog?${params}`);
    return response.data;
  },

  importFromLibrary: async (manufacturerKey: string, fixtureKey: string) => {
    const response = await api.post('/fixtures/library/import', null, {
      params: { manufacturer_key: manufacturerKey, fixture_key: fixtureKey },
    });
    return response.data;
  },

  importBulk: async (fixtures: Array<{ manufacturer_key: string; fixture_key: string }>) => {
    const response = await api.post('/fixtures/library/import-bulk', fixtures);
    return response.data;
  },

  getPopular: async (limit = 20, fixtureType?: string) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (fixtureType) params.append('fixture_type', fixtureType);
    const response = await api.get(`/fixtures/library/popular?${params}`);
    return response.data;
  },

  getOFLManufacturers: async () => {
    const response = await api.get('/fixtures/library/manufacturers');
    return response.data;
  },

  importGDTF: async (file: File): Promise<GdtfImportResult> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/fixtures/import/gdtf', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  create: async (data: Partial<Fixture>): Promise<Fixture> => {
    const response = await api.post('/fixtures/', data);
    return response.data;
  },

  update: async (id: number, data: Partial<Fixture>): Promise<Fixture> => {
    const response = await api.put(`/fixtures/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/fixtures/${id}`);
  },

  getChannelTemplates: async (fixtureType: string) => {
    const response = await api.get(`/fixtures/channel-templates/${fixtureType}`);
    return response.data;
  },
};

// Audio API
export interface AudioCaptureDevice {
  index: number;
  name: string;
  max_input_channels: number;
  max_output_channels: number;
  default_samplerate?: number;
  hostapi: string;
  is_loopback: boolean;
  is_input?: boolean;
  device_type?: string;
  platform?: string;
}

export interface AudioCaptureStatus {
  running: boolean;
  device_index: number | null;
  device_name: string | null;
  capture_method: string;
  available: boolean;
  platform?: string;
  chunk_count?: number;
  last_rms?: number;
  last_peak?: number;
}

export const audioApi = {
  getStatus: async (): Promise<{ status: string; sample_rate: number }> => {
    const response = await api.get('/audio/status');
    return response.data;
  },

  start: async (): Promise<void> => {
    await api.post('/audio/start');
  },

  stop: async (): Promise<void> => {
    await api.post('/audio/stop');
  },

  getCurrent: async (): Promise<AudioAnalysis> => {
    const response = await api.get('/audio/current');
    return response.data;
  },

  getCaptureDevices: async (): Promise<AudioCaptureDevice[]> => {
    const response = await api.get('/audio/capture/devices');
    return response.data.devices ?? [];
  },

  getCaptureStatus: async (): Promise<AudioCaptureStatus> => {
    const response = await api.get('/audio/capture/status');
    return response.data;
  },

  startCapture: async (deviceIndex: number): Promise<{ status: string; device?: string }> => {
    const response = await api.post('/audio/capture/start', null, {
      params: { device_index: deviceIndex },
    });
    return response.data;
  },

  stopCapture: async (): Promise<{ status: string }> => {
    const response = await api.post('/audio/capture/stop');
    return response.data;
  },
};

// DMX API
export const dmxApi = {
  getStatus: async (): Promise<{
    status: string;
    universes: number[];
    fps: number;
    packets_sent: number;
  }> => {
    const response = await api.get('/dmx/status');
    return response.data;
  },

  connect: async (): Promise<void> => {
    await api.post('/dmx/connect');
  },

  disconnect: async (): Promise<void> => {
    await api.post('/dmx/disconnect');
  },

  blackout: async (fadeTime = 0): Promise<void> => {
    await api.post('/dmx/blackout', { fade_time: fadeTime });
  },

  restore: async (fadeTime = 0): Promise<void> => {
    await api.post('/dmx/restore', null, { params: { fade_time: fadeTime } });
  },

  setChannel: async (universe: number, channel: number, value: number): Promise<void> => {
    await api.post('/dmx/channel', null, {
      params: { universe, channel, value },
    });
  },

  runTestPattern: async (universe: number, pattern: string): Promise<void> => {
    await api.get('/dmx/test/pattern', { params: { universe, pattern } });
  },

  stopTestPattern: async (): Promise<void> => {
    await api.post('/dmx/test/stop');
  },
};

// Wizard API
export const wizardApi = {
  getVenuePresets: async (): Promise<{ presets: VenuePreset[] }> => {
    const response = await api.get('/wizard/venue-presets');
    return response.data;
  },

  getVenueSuggestions: async (key: string) => {
    const response = await api.get(`/wizard/venue-presets/${key}/suggestions`);
    return response.data;
  },

  autoPlace: async (data: {
    stage_width: number;
    stage_depth: number;
    stage_height: number;
    fixtures: Array<{ fixture_id: number; count: number; group_name?: string }>;
  }) => {
    const response = await api.post('/wizard/auto-place', data);
    return response.data;
  },

  createRig: async (data: WizardData): Promise<Rig> => {
    const response = await api.post('/wizard/create-rig', data);
    return response.data;
  },
};

// Templates API
export interface AppliedTemplate {
  id: number;
  name: string;
  fixture_count: number;
  message: string;
}

export const templatesApi = {
  list: async (venueType?: string): Promise<{ items: RigTemplate[]; total: number }> => {
    const params = venueType ? `?venue_type=${venueType}` : '';
    const response = await api.get(`/templates/${params}`);
    return response.data;
  },

  get: async (id: number): Promise<RigTemplate> => {
    const response = await api.get(`/templates/${id}`);
    return response.data;
  },

  create: async (data: RigTemplateCreate): Promise<RigTemplate> => {
    const response = await api.post('/templates/', data);
    return response.data;
  },

  apply: async (
    id: number,
    data: { rig_name: string; venue?: string }
  ): Promise<AppliedTemplate> => {
    const response = await api.post(`/templates/${id}/apply`, null, {
      params: { rig_name: data.rig_name, venue: data.venue },
    });
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/templates/${id}`);
  },
};

// Effects Engine API
export const effectsApi = {
  getStatus: async () => {
    const response = await api.get('/effects/status');
    return response.data;
  },

  start: async () => {
    const response = await api.post('/effects/start');
    return response.data;
  },

  stop: async () => {
    const response = await api.post('/effects/stop');
    return response.data;
  },

  setAutoMode: async (enabled: boolean) => {
    const response = await api.post('/effects/auto-mode', { enabled });
    return response.data;
  },

  // Movement
  getMovementPatterns: async () => {
    const response = await api.get('/effects/movement/patterns');
    return response.data;
  },

  setMovement: async (pattern: string, baseLook?: string) => {
    const response = await api.post('/effects/movement', { pattern, base_look: baseLook });
    return response.data;
  },

  // Dimmer
  getDimmerEffects: async () => {
    const response = await api.get('/effects/dimmer/effects');
    return response.data;
  },

  setDimmer: async (effect: string, speed?: number) => {
    const response = await api.post('/effects/dimmer', { effect, speed });
    return response.data;
  },

  // Strobe
  getStrobeModes: async () => {
    const response = await api.get('/effects/strobe/modes');
    return response.data;
  },

  setStrobe: async (mode: string, frequency?: number) => {
    const response = await api.post('/effects/strobe', { mode, frequency });
    return response.data;
  },

  triggerStrobeBurst: async (duration = 2.0, frequency = 12.0) => {
    const response = await api.post('/effects/strobe/burst', null, {
      params: { duration, frequency },
    });
    return response.data;
  },

  // Color
  getColorPalettes: async () => {
    const response = await api.get('/effects/color/palettes');
    return response.data;
  },

  setColorPalette: async (palette: string) => {
    const response = await api.post('/effects/color/palette', { palette });
    return response.data;
  },

  // State
  getStates: async () => {
    const response = await api.get('/effects/states');
    return response.data;
  },

  forceState: async (state: string) => {
    const response = await api.post('/effects/state', { state });
    return response.data;
  },

  // Triggers
  triggerDrop: async () => {
    const response = await api.post('/effects/trigger/drop');
    return response.data;
  },

  triggerBuildup: async (duration = 4.0) => {
    const response = await api.post('/effects/trigger/buildup', null, {
      params: { duration },
    });
    return response.data;
  },

  triggerBlackout: async () => {
    const response = await api.post('/effects/trigger/blackout');
    return response.data;
  },

  triggerRestore: async () => {
    const response = await api.post('/effects/trigger/restore');
    return response.data;
  },

  // Presets
  getPresets: async () => {
    const response = await api.get('/effects/presets');
    return response.data;
  },

  loadPreset: async (presetName: string) => {
    const response = await api.post(`/effects/preset/${presetName}`);
    return response.data;
  },

  // Layer control
  setLayerEnabled: async (layer: 'movement' | 'dimmer' | 'strobe' | 'color', enabled: boolean) => {
    const response = await api.post(`/effects/layers/${layer}/${enabled}`);
    return response.data;
  },
};

// Professional Lighting API (effects/pro/*)
export interface MasterState {
  grand_master: number;
  blackout: boolean;
  output_master: number;
}

export const masterApi = {
  get: async (): Promise<MasterState> => {
    const response = await api.get('/effects/master');
    return response.data;
  },

  setGrandMaster: async (level: number): Promise<MasterState> => {
    const response = await api.post('/effects/master', { level });
    return response.data;
  },

  blackout: async (): Promise<void> => {
    await api.post('/effects/trigger/blackout');
  },

  restore: async (): Promise<void> => {
    await api.post('/effects/trigger/restore');
  },
};

export const proLightingApi = {
  enable: async (enabled = true) => {
    const response = await api.post('/effects/pro/enable', null, { params: { enabled } });
    return response.data;
  },

  getStatus: async (): Promise<ProLightingState> => {
    const response = await api.get('/effects/pro/status');
    return response.data;
  },

  // Genre
  getGenres: async () => {
    const response = await api.get('/effects/pro/genres');
    return response.data;
  },

  setGenre: async (genre: Genre, crossfade = true) => {
    const response = await api.post('/effects/pro/genre', { genre: genre.toLowerCase(), crossfade });
    return response.data;
  },

  // Sections
  getSections: async () => {
    const response = await api.get('/effects/pro/sections');
    return response.data;
  },

  setSection: async (section: string, immediate = false) => {
    const response = await api.post('/effects/pro/section', { section, immediate });
    return response.data;
  },

  // Pro Movement
  getProMovementPatterns: async () => {
    const response = await api.get('/effects/pro/movement/patterns');
    return response.data;
  },

  setProMovement: async (pattern: string, params?: Record<string, number>) => {
    const response = await api.post('/effects/pro/movement', { pattern, ...params });
    return response.data;
  },

  setProMovementPreset: async (presetName: string) => {
    const response = await api.post(`/effects/pro/movement/preset/${presetName}`);
    return response.data;
  },

  // Pro Strobe
  triggerProStrobe: async (mode: string, frequency?: number, duration?: number) => {
    const response = await api.post('/effects/pro/strobe', { mode, frequency, duration });
    return response.data;
  },

  stopProStrobe: async () => {
    const response = await api.post('/effects/pro/strobe/stop');
    return response.data;
  },

  // Build-up
  triggerBuild: async (durationBeats = 16, curve = 'quadratic') => {
    const response = await api.post('/effects/pro/build', { duration_beats: durationBeats, curve });
    return response.data;
  },

  // Flash & Blackout
  triggerFlash: async (duration = 0.1) => {
    const response = await api.post('/effects/pro/flash', null, { params: { duration } });
    return response.data;
  },

  triggerProBlackout: async () => {
    const response = await api.post('/effects/pro/blackout');
    return response.data;
  },

  // Key Lighting
  getKeyLighting: async () => {
    const response = await api.get('/effects/pro/key-lighting');
    return response.data;
  },

  configureKeyLighting: async (zone: string, active: boolean, minIntensity?: number, fixtureIds?: string[]) => {
    const response = await api.post('/effects/pro/key-lighting', {
      zone,
      active,
      min_intensity: minIntensity,
      fixture_ids: fixtureIds,
    });
    return response.data;
  },
};

// Import/Export API
export interface RigImportResult {
  rig_id: number;
  rig_name: string;
  fixtures_imported: number;
  gdtf_fixtures_parsed?: number;
}

export const importExportApi = {
  importMVR: async (file: File): Promise<RigImportResult> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/rigs/import/mvr', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  importConsolePatch: async (file: File, format = 'auto'): Promise<RigImportResult> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/rigs/import/console-patch', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { format },
    });
    return response.data;
  },

  exportJSON: async (rigId: number) => {
    const response = await api.get(`/rigs/${rigId}/export/json`);
    return response.data;
  },

  exportCSV: async (rigId: number) => {
    const response = await api.get(`/rigs/${rigId}/export/csv`, { responseType: 'blob' });
    return response.data;
  },
};

export const demoApi = {
  getRig: async (preset: string): Promise<Rig> => {
    const response = await api.get('/demo/rig', {
      params: { preset, t: Date.now() },
    });
    return response.data;
  },
};

export default api;
