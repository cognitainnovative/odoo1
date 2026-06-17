import { useEffect, useRef } from 'react';
import { useChatStore } from '../store/chatStore';
import { useAuthStore } from '../store/authStore';

const REFRESH_INTERVAL_MS = 5_000;

/**
 * Refreshes the session queue on an interval.
 * Used as the fallback when bus long-polling fails.
 */
export function useQueue() {
  const { loadSessions, activeTab, sessions, sessionsLoading, sessionsError } =
    useChatStore();
  const session = useAuthStore((s) => s.session);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!session) return;

    // Initial load
    void loadSessions(session.uid);

    // Set up interval
    intervalRef.current = setInterval(() => {
      void loadSessions(session.uid);
    }, REFRESH_INTERVAL_MS);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [activeTab, session, loadSessions]);

  return { sessions, loading: sessionsLoading, error: sessionsError };
}
