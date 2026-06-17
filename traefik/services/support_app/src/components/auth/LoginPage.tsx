import { useState, type FormEvent } from 'react';
import { MessageSquare, AlertCircle } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';

const DEFAULT_DB =
  (import.meta.env.VITE_ODOO_DB as string | undefined) ?? 'v19_platform_dev';

export function LoginPage() {
  const { login, loading, error, clearError } = useAuthStore();

  const [db, setDb] = useState(DEFAULT_DB);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    clearError();
    try {
      await login(db, username, password);
    } catch {
      // Error already set in store
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-brand-50 to-brand-100 p-4">
      <div className="w-full max-w-sm">
        {/* Logo / brand */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-16 h-16 bg-brand-500 rounded-2xl flex items-center justify-center shadow-lg mb-4">
            <MessageSquare size={32} className="text-white" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Support Console</h1>
          <p className="text-sm text-gray-500 mt-1">Sign in to your agent workspace</p>
        </div>

        <form
          onSubmit={(e) => void handleSubmit(e)}
          className="bg-white rounded-2xl shadow-xl p-8 space-y-5"
        >
          {/* Error banner */}
          {error && (
            <div className="flex items-start gap-3 p-3 bg-red-50 border border-red-200 rounded-lg">
              <AlertCircle size={16} className="text-red-500 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          <div>
            <label
              htmlFor="db"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Database
            </label>
            <input
              id="db"
              type="text"
              value={db}
              onChange={(e) => setDb(e.target.value)}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition"
              placeholder="platform_dev"
            />
          </div>

          <div>
            <label
              htmlFor="username"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Username / Email
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition"
              placeholder="admin"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition"
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-brand-600 hover:bg-brand-700 text-white font-semibold rounded-lg text-sm transition-colors disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <span className="h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Signing in…
              </>
            ) : (
              'Sign in'
            )}
          </button>
        </form>

        <p className="text-center text-xs text-gray-400 mt-6">
          Support Console v1.0 · Odoo 19 Community
        </p>
      </div>
    </div>
  );
}
