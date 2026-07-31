import { create } from 'zustand';

const TOKEN_STORAGE_KEY = 'ils_auth_token';

const readStoredToken = (): string | null => {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
};

const writeStoredToken = (token: string | null): void => {
  try {
    if (token) {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
    // A browser with storage disabled still works, it just forgets on refresh.
  }
};

interface AuthState {
  token: string | null;
  // null until GET /api/auth/status has answered
  configured: boolean | null;

  setSession: (token: string) => void;
  clearSession: () => void;
  setConfigured: (configured: boolean) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: readStoredToken(),
  configured: null,

  setSession: (token) => {
    writeStoredToken(token);
    set({ token, configured: true });
  },

  clearSession: () => {
    writeStoredToken(null);
    set({ token: null });
  },

  setConfigured: (configured) => set({ configured }),
}));

export const getAuthToken = (): string | null => useAuthStore.getState().token;
