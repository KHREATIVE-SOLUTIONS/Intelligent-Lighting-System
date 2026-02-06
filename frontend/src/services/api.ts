import axios from 'axios';
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
} from '../types';

const API_BASE_URL = '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

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
};

// Fixtures API
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
};

// Audio API
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

export default api;
