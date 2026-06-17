import { useEffect, useRef } from 'react';
import { subscribeBus, FALLBACK_INTERVAL_MS } from '../api/bus';
import { useChatStore } from '../store/chatStore';
import { useNotificationStore } from '../store/notificationStore';
import { useAuthStore } from '../store/authStore';
import { fetchSession } from '../api/odoo';
import type { BusMessage, ChatSession } from '../types';

/**
 * Connects to the Odoo bus and listens for:
 *  - "support_queue" channel: new escalated sessions
 *  - "support_session_<id>" channel: transcript updates for the active session
 *
 * Falls back to polling every FALLBACK_INTERVAL_MS if the bus subscription fails.
 */
export function useBus() {
  const { activeSessionId, upsertSession, refreshSession } = useChatStore();
  const { addNotification } = useNotificationStore();
  const session = useAuthStore((s) => s.session);
  const busRef = useRef<{ stop(): void } | null>(null);
  const fallbackRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const upsertSessionRef = useRef(upsertSession);
  const refreshSessionRef = useRef(refreshSession);
  const addNotificationRef = useRef(addNotification);

  // Keep refs in sync without re-triggering the effect
  upsertSessionRef.current = upsertSession;
  refreshSessionRef.current = refreshSession;
  addNotificationRef.current = addNotification;

  useEffect(() => {
    if (!session) return;

    const channels = ['support_queue'];
    if (activeSessionId) {
      channels.push(`support_session_${activeSessionId}`);
    }

    function handleMessage(msg: BusMessage) {
      const { channel, message } = msg;

      if (channel === 'support_queue') {
        // message contains a partial or full ChatSession payload
        const payload = message as Partial<ChatSession> & { id: number };
        if (payload.id) {
          // Fetch full session so we have all fields
          fetchSession(payload.id)
            .then((s) => {
              upsertSessionRef.current(s);
              // Notify if newly escalated and not yet assigned
              if (
                s.state === 'escalated' &&
                !s.assigned_agent_id
              ) {
                addNotificationRef.current(
                  s.id,
                  s.visitor_name,
                  s.escalation_reason || null,
                );
              }
            })
            .catch(() => {/* non-critical */});
        }
      } else if (activeSessionId && channel === `support_session_${activeSessionId}`) {
        // Refresh transcript + session state for active session
        void refreshSessionRef.current(activeSessionId);
      }
    }

    function startFallback() {
      if (fallbackRef.current) return; // already running
      fallbackRef.current = setInterval(() => {
        if (activeSessionId) {
          void refreshSessionRef.current(activeSessionId);
        }
      }, FALLBACK_INTERVAL_MS);
    }

    busRef.current = subscribeBus(channels, handleMessage, () => {
      // Bus failed — switch to interval fallback
      startFallback();
    });

    return () => {
      busRef.current?.stop();
      busRef.current = null;
      if (fallbackRef.current) {
        clearInterval(fallbackRef.current);
        fallbackRef.current = null;
      }
    };
  }, [session, activeSessionId]);
}
