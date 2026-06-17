/**
 * Canned replies are stored in localStorage under key "canned_replies_v1".
 * The key includes a version suffix so we can migrate in future if needed.
 */

import type { CannedReply } from '../types';

const STORAGE_KEY = 'canned_replies_v1';

const DEFAULTS: CannedReply[] = [
  {
    id: 'default_1',
    shortcut: '/hello',
    content: 'Thank you for contacting us. How can I help you today?',
  },
  {
    id: 'default_2',
    shortcut: '/understand',
    content: 'I understand your concern. Let me look into this for you.',
  },
  {
    id: 'default_3',
    shortcut: '/details',
    content: 'Could you please provide more details about the issue?',
  },
  {
    id: 'default_4',
    shortcut: '/follow',
    content: "I've raised this with our team and will follow up shortly.",
  },
  {
    id: 'default_5',
    shortcut: '/anything',
    content: 'Is there anything else I can assist you with?',
  },
];

export function loadCannedReplies(): CannedReply[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as CannedReply[];
      if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    }
  } catch {
    // Corrupt storage — fall through to defaults
  }
  // First load: persist defaults and return them
  saveCannedReplies(DEFAULTS);
  return DEFAULTS;
}

export function saveCannedReplies(replies: CannedReply[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(replies));
}

export function addCannedReply(reply: Omit<CannedReply, 'id'>): CannedReply[] {
  const all = loadCannedReplies();
  const newReply: CannedReply = {
    ...reply,
    id: `cr_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
  };
  const updated = [...all, newReply];
  saveCannedReplies(updated);
  return updated;
}

export function updateCannedReply(
  id: string,
  patch: Partial<Omit<CannedReply, 'id'>>,
): CannedReply[] {
  const all = loadCannedReplies();
  const updated = all.map((r) => (r.id === id ? { ...r, ...patch } : r));
  saveCannedReplies(updated);
  return updated;
}

export function deleteCannedReply(id: string): CannedReply[] {
  const all = loadCannedReplies();
  const updated = all.filter((r) => r.id !== id);
  saveCannedReplies(updated);
  return updated;
}
