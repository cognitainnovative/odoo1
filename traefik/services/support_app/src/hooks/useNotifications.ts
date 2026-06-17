import { useEffect } from 'react';
import { useNotificationStore } from '../store/notificationStore';

/**
 * Requests browser notification permission on page load (once per session).
 * Returns the notification state so components can display the bell badge.
 */
export function useNotifications() {
  const { permission, requestPermission, unreadCount, notifications, markAllRead, clearAll } =
    useNotificationStore();

  useEffect(() => {
    // Request permission automatically when the component mounts
    if (permission === 'default') {
      void requestPermission();
    }
  }, [permission, requestPermission]);

  return { permission, unreadCount, notifications, markAllRead, clearAll };
}
