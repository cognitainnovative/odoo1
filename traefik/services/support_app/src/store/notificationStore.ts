/**
 * Browser notification store.
 *
 * Tracks unread count and the list of app-level notifications.
 * Also manages the browser Notification API permission state.
 */

import { create } from 'zustand';
import type { AppNotification, EscalationReason } from '../types';

interface NotificationState {
  permission: NotificationPermission;
  notifications: AppNotification[];
  unreadCount: number;

  requestPermission: () => Promise<void>;
  addNotification: (
    sessionId: number,
    visitorName: string,
    escalationReason: EscalationReason | null,
  ) => void;
  markAllRead: () => void;
  clearAll: () => void;
}

let _idCounter = 0;

export const useNotificationStore = create<NotificationState>((set, get) => ({
  permission:
    typeof Notification !== 'undefined'
      ? Notification.permission
      : 'default',
  notifications: [],
  unreadCount: 0,

  requestPermission: async () => {
    if (typeof Notification === 'undefined') return;
    if (Notification.permission === 'granted') return;
    const result = await Notification.requestPermission();
    set({ permission: result });
  },

  addNotification: (sessionId, visitorName, escalationReason) => {
    const notification: AppNotification = {
      id: String(++_idCounter),
      sessionId,
      visitorName,
      escalationReason,
      timestamp: Date.now(),
      read: false,
    };

    set((s) => ({
      notifications: [notification, ...s.notifications].slice(0, 50), // keep last 50
      unreadCount: s.unreadCount + 1,
    }));

    // Fire browser push notification if permission granted
    if (get().permission === 'granted') {
      const reason = escalationReason
        ? escalationReason.replace(/_/g, ' ')
        : 'new escalation';
      try {
        new Notification(`New chat: ${visitorName}`, {
          body: `Reason: ${reason}`,
          icon: '/favicon.svg',
          tag: `session-${sessionId}`, // deduplicate same session
        });
      } catch {
        // Notification constructor can throw in some browser contexts
      }
    }
  },

  markAllRead: () =>
    set((s) => ({
      notifications: s.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    })),

  clearAll: () => set({ notifications: [], unreadCount: 0 }),
}));
