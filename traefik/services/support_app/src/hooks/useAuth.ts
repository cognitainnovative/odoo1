import { useEffect } from 'react';
import { useAuthStore } from '../store/authStore';

/**
 * Initializes the auth state once on mount by checking sessionStorage
 * and validating against the Odoo session endpoint.
 */
export function useAuth() {
  const { initialize, session, loading, error, login, logout, clearError } =
    useAuthStore();

  useEffect(() => {
    void initialize();
    // Only run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { session, loading, error, login, logout, clearError };
}
