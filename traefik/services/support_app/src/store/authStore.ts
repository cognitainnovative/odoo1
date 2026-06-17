/**
 * Authentication store.
 *
 * Session is kept in sessionStorage (not localStorage) so it is cleared when
 * the browser tab is closed — a deliberate security choice for an agent console.
 */

import { create } from 'zustand';
import { login as apiLogin, logout as apiLogout, getSessionInfo, registerUnauthorizedHandler } from '../api/odoo';
import type { OdooSession } from '../types';

const SESSION_KEY = 'support_app_session';

interface AuthState {
  session: OdooSession | null;
  loading: boolean;
  error: string | null;

  // Actions
  initialize: () => Promise<void>;
  login: (db: string, username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set) => {
  // Register the 401 → logout handler so the API client can trigger it
  registerUnauthorizedHandler(() => {
    sessionStorage.removeItem(SESSION_KEY);
    set({ session: null, loading: false });
  });

  return {
    session: null,
    loading: false,
    error: null,

    initialize: async () => {
      // Try to restore from sessionStorage first (fast path)
      const raw = sessionStorage.getItem(SESSION_KEY);
      if (raw) {
        try {
          const stored = JSON.parse(raw) as OdooSession;
          set({ session: stored });
          // Verify with server in the background
          getSessionInfo()
            .then((s) => {
              set({ session: s });
              sessionStorage.setItem(SESSION_KEY, JSON.stringify(s));
            })
            .catch(() => {
              sessionStorage.removeItem(SESSION_KEY);
              set({ session: null });
            });
          return;
        } catch {
          sessionStorage.removeItem(SESSION_KEY);
        }
      }

      // No stored session — check if there's already a live Odoo cookie
      set({ loading: true });
      try {
        const s = await getSessionInfo();
        set({ session: s, loading: false });
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(s));
      } catch {
        set({ session: null, loading: false });
      }
    },

    login: async (db, username, password) => {
      set({ loading: true, error: null });
      try {
        const session = await apiLogin(db, username, password);
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
        set({ session, loading: false });
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Login failed';
        set({ error: message, loading: false });
        throw err;
      }
    },

    logout: async () => {
      set({ loading: true });
      try {
        await apiLogout();
      } catch {
        // Ignore logout errors — clear local state regardless
      } finally {
        sessionStorage.removeItem(SESSION_KEY);
        set({ session: null, loading: false });
      }
    },

    clearError: () => set({ error: null }),
  };
});
