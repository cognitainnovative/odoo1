/**
 * Odoo bus long-polling client.
 *
 * Odoo's bus works by repeatedly POSTing to /web/dataset/call_kw with
 * model=bus.bus, method=poll.  The server holds the connection open until
 * a new message is available (or the timeout fires) and then returns an
 * array of BusMessage objects.
 *
 * We keep track of the highest message id seen (lastId) so that each
 * subsequent call only fetches newer messages.
 */

import axios from 'axios';
import type { BusMessage, JsonRpcResponse } from '../types';

const BASE_URL = (import.meta.env.VITE_ODOO_URL as string | undefined) ?? '';
let _rpcId = 1000; // separate counter from odoo.ts to avoid collisions

// Server-side long-poll timeout Odoo uses is ~50 s; we add 5 s buffer
const POLL_TIMEOUT_MS = 55_000;
// Fallback polling interval when long-poll is not available / fails
export const FALLBACK_INTERVAL_MS = 5_000;

export interface BusSubscription {
  stop(): void;
}

/**
 * Subscribe to a set of bus channels.
 *
 * @param channels  Array of channel names, e.g. ["support_queue", "support_session_42"]
 * @param onMessage Called for each message received
 * @param onError   Called when polling encounters a non-recoverable error
 */
export function subscribeBus(
  channels: string[],
  onMessage: (msg: BusMessage) => void,
  onError?: (err: Error) => void,
): BusSubscription {
  let lastId = 0;
  let stopped = false;
  let consecutiveErrors = 0;

  const http = axios.create({
    baseURL: BASE_URL,
    withCredentials: true,
    timeout: POLL_TIMEOUT_MS,
    headers: { 'Content-Type': 'application/json' },
  });

  async function poll(): Promise<void> {
    if (stopped) return;

    try {
      const body = {
        jsonrpc: '2.0',
        method: 'call',
        id: _rpcId++,
        params: {
          model: 'bus.bus',
          method: 'poll',
          // Odoo bus.poll signature: poll(channels, last)
          args: [channels, lastId],
          kwargs: {},
        },
      };

      const res = await http.post<JsonRpcResponse<BusMessage[]>>(
        '/web/dataset/call_kw',
        body,
      );

      if (stopped) return;

      const data = res.data;
      if (data.error) {
        throw new Error(data.error.data?.message ?? 'Bus poll error');
      }

      const messages = data.result ?? [];
      consecutiveErrors = 0;

      for (const msg of messages) {
        if (msg.id > lastId) {
          lastId = msg.id;
          onMessage(msg);
        }
      }

      // Immediately long-poll again
      void poll();
    } catch (err) {
      if (stopped) return;
      consecutiveErrors++;

      const error = err instanceof Error ? err : new Error(String(err));

      // After 3 consecutive failures signal the caller so they can switch to fallback
      if (consecutiveErrors >= 3) {
        onError?.(error);
        return; // stop auto-retrying — caller switches to setInterval
      }

      // Exponential backoff: 1s, 2s, 4s
      const delay = Math.min(1000 * Math.pow(2, consecutiveErrors - 1), 8000);
      setTimeout(() => void poll(), delay);
    }
  }

  void poll();

  return {
    stop() {
      stopped = true;
    },
  };
}
