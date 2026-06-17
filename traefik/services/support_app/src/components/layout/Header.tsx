import { useState } from 'react';
import { Bell, LogOut, Moon, Sun, MessageSquare } from 'lucide-react';
import clsx from 'clsx';
import { useAuthStore } from '../../store/authStore';
import { useNotifications } from '../../hooks/useNotifications';
import { formatDistanceToNow } from 'date-fns';

const DARK_SIDEBAR_KEY = 'support_dark_sidebar';

interface HeaderProps {
  darkMode: boolean;
  onToggleDarkMode: () => void;
}

export function Header({ darkMode, onToggleDarkMode }: HeaderProps) {
  const { session, logout } = useAuthStore();
  const { unreadCount, notifications, markAllRead } = useNotifications();
  const [notifOpen, setNotifOpen] = useState(false);
  const [status, setStatus] = useState<'online' | 'away'>('online');

  function toggleNotif() {
    setNotifOpen((v) => !v);
    if (!notifOpen) markAllRead();
  }

  async function handleLogout() {
    await logout();
  }

  return (
    <header className="h-14 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 flex items-center px-4 gap-4 z-30 flex-shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2 font-semibold text-gray-900 dark:text-gray-100">
        <div className="w-7 h-7 bg-brand-500 rounded-lg flex items-center justify-center">
          <MessageSquare size={15} className="text-white" />
        </div>
        <span className="hidden sm:block text-sm">Support Console</span>
      </div>

      <div className="flex-1" />

      {/* Dark mode toggle */}
      <button
        onClick={onToggleDarkMode}
        className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
        aria-label="Toggle dark mode"
        title="Toggle dark mode"
      >
        {darkMode ? <Sun size={16} /> : <Moon size={16} />}
      </button>

      {/* Agent name + status */}
      {session && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => setStatus((s) => (s === 'online' ? 'away' : 'online'))}
            className="flex items-center gap-1.5 text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
            title="Toggle availability"
          >
            <span
              className={clsx(
                'w-2 h-2 rounded-full flex-shrink-0',
                status === 'online' ? 'bg-green-500' : 'bg-yellow-500',
              )}
            />
            <span className="hidden sm:block max-w-28 truncate">{session.name}</span>
          </button>
        </div>
      )}

      {/* Notification bell */}
      <div className="relative">
        <button
          onClick={toggleNotif}
          className="relative p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          aria-label={`Notifications (${unreadCount} unread)`}
        >
          <Bell size={16} />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </button>

        {/* Notification dropdown */}
        {notifOpen && (
          <>
            {/* Backdrop */}
            <div
              className="fixed inset-0 z-40"
              onClick={() => setNotifOpen(false)}
            />
            <div className="absolute right-0 top-10 z-50 w-80 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-xl">
              <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Notifications</h3>
              </div>
              <div className="max-h-64 overflow-y-auto">
                {notifications.length === 0 && (
                  <p className="text-sm text-gray-400 text-center py-6">
                    No notifications
                  </p>
                )}
                {notifications.map((n) => (
                  <div
                    key={n.id}
                    className={clsx(
                      'px-4 py-3 border-b border-gray-50 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors',
                      !n.read && 'bg-blue-50 dark:bg-blue-900/20',
                    )}
                  >
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                      {n.visitorName}
                    </p>
                    {n.escalationReason && (
                      <p className="text-xs text-gray-500 mt-0.5">
                        {n.escalationReason.replace(/_/g, ' ')}
                      </p>
                    )}
                    <p className="text-xs text-gray-400 mt-1">
                      {formatDistanceToNow(new Date(n.timestamp), { addSuffix: true })}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Logout */}
      <button
        onClick={() => void handleLogout()}
        className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors"
        aria-label="Logout"
        title="Logout"
      >
        <LogOut size={16} />
      </button>
    </header>
  );
}

// Re-export key so the toggle is stored consistently
export { DARK_SIDEBAR_KEY };
