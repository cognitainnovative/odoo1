/**
 * Chat / queue store.
 *
 * Holds all chat sessions, the active session, its transcript,
 * AI suggestions, and visitor context.
 */

import { create } from 'zustand';
import {
  fetchSessions,
  fetchSession,
  fetchTranscript,
  sendAgentMessage as apiSend,
  assignSessionToMe as apiAssign,
  resolveSession as apiResolve,
  closeSession as apiClose,
  transferSession as apiTransfer,
  createLeadFromSession,
  createFollowUpTask,
  fetchAISuggestions,
  fetchKnowledgeSuggestions,
  fetchVisitorBySession,
  fetchAgents,
} from '../api/odoo';
import type {
  ChatSession,
  TranscriptLine,
  ChatVisitor,
  OdooUser,
  AISuggestion,
} from '../types';

export type QueueTab = 'queue' | 'mine' | 'all';

interface ChatState {
  // Queue / session list
  sessions: ChatSession[];
  sessionsLoading: boolean;
  sessionsError: string | null;
  activeTab: QueueTab;

  // Active session detail
  activeSessionId: number | null;
  activeSession: ChatSession | null;
  transcript: TranscriptLine[];
  transcriptLoading: boolean;

  // Visitor context
  visitor: ChatVisitor | null;
  visitorLoading: boolean;

  // AI suggestions
  aiSuggestions: AISuggestion[];
  aiSuggestionsLoading: boolean;
  aiPanelOpen: boolean;

  // Knowledge chips
  knowledgeSuggestions: string[];

  // Text to insert into the message input (set by AI suggestions / canned replies)
  pendingInsert: string;

  // Agents (for transfer)
  agents: OdooUser[];
  agentsLoading: boolean;

  // Global error banner
  globalError: string | null;

  // Actions
  setPendingInsert: (text: string) => void;
  clearPendingInsert: () => void;
  setActiveTab: (tab: QueueTab) => void;
  loadSessions: (currentUserId?: number) => Promise<void>;
  openSession: (id: number) => Promise<void>;
  closeActiveSession: () => void;
  sendMessage: (content: string) => Promise<void>;
  assignToMe: () => Promise<void>;
  resolve: () => Promise<void>;
  close: () => Promise<void>;
  transfer: (agentId: number) => Promise<void>;
  createLead: () => Promise<void>;
  createTask: () => Promise<{ taskId: number | null; mailtoUrl: string }>;
  loadAISuggestions: () => Promise<void>;
  toggleAIPanel: () => void;
  loadAgents: () => Promise<void>;
  refreshSession: (id: number) => Promise<void>;
  dismissGlobalError: () => void;
  /** Called by the bus handler when a new/updated session arrives */
  upsertSession: (session: ChatSession) => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  sessionsLoading: false,
  sessionsError: null,
  activeTab: 'queue',

  activeSessionId: null,
  activeSession: null,
  transcript: [],
  transcriptLoading: false,

  visitor: null,
  visitorLoading: false,

  aiSuggestions: [],
  aiSuggestionsLoading: false,
  aiPanelOpen: true,

  knowledgeSuggestions: [],

  pendingInsert: '',

  agents: [],
  agentsLoading: false,

  globalError: null,

  setPendingInsert: (text) => set({ pendingInsert: text }),
  clearPendingInsert: () => set({ pendingInsert: '' }),

  setActiveTab: (tab) => set({ activeTab: tab }),

  loadSessions: async (currentUserId) => {
    const { activeTab } = get();
    set({ sessionsLoading: true, sessionsError: null });
    try {
      let domain: unknown[][];
      if (activeTab === 'queue') {
        domain = [
          ['state', 'in', ['escalated', 'open']],
          ['assigned_agent_id', '=', false],
        ];
      } else if (activeTab === 'mine' && currentUserId) {
        domain = [
          ['state', 'in', ['assigned', 'escalated', 'open']],
          ['assigned_agent_id', '=', currentUserId],
        ];
      } else {
        domain = [['state', 'in', ['open', 'escalated', 'assigned']]];
      }
      const sessions = await fetchSessions(domain);
      set({ sessions, sessionsLoading: false });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load sessions';
      set({ sessionsError: msg, sessionsLoading: false });
    }
  },

  openSession: async (id) => {
    set({
      activeSessionId: id,
      transcript: [],
      transcriptLoading: true,
      visitor: null,
      aiSuggestions: [],
      knowledgeSuggestions: [],
    });

    try {
      const [session, transcript] = await Promise.all([
        fetchSession(id),
        fetchTranscript(id),
      ]);
      set({ activeSession: session, transcript, transcriptLoading: false });

      // Load visitor context in background
      set({ visitorLoading: true });
      fetchVisitorBySession(id)
        .then((v) => set({ visitor: v, visitorLoading: false }))
        .catch(() => set({ visitor: null, visitorLoading: false }));

      // Auto-fetch knowledge suggestions for the last user message
      const lastUserMsg = [...transcript].reverse().find((m) => m.role === 'user');
      if (lastUserMsg) {
        fetchKnowledgeSuggestions(lastUserMsg.content)
          .then((chips) => set({ knowledgeSuggestions: chips }))
          .catch(() => {/* non-critical */});
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load session';
      set({ transcriptLoading: false, globalError: msg });
    }
  },

  closeActiveSession: () =>
    set({
      activeSessionId: null,
      activeSession: null,
      transcript: [],
      visitor: null,
      aiSuggestions: [],
      knowledgeSuggestions: [],
    }),

  sendMessage: async (content) => {
    const { activeSessionId } = get();
    if (!activeSessionId) return;
    try {
      const line = await apiSend(activeSessionId, content);
      set((state) => ({ transcript: [...state.transcript, line] }));

      // Fetch new knowledge suggestions based on outgoing message context
      fetchKnowledgeSuggestions(content)
        .then((chips) => set({ knowledgeSuggestions: chips }))
        .catch(() => {/* non-critical */});
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to send message';
      set({ globalError: msg });
    }
  },

  assignToMe: async () => {
    const { activeSessionId } = get();
    if (!activeSessionId) return;
    try {
      await apiAssign(activeSessionId);
      const updated = await fetchSession(activeSessionId);
      set({ activeSession: updated });
      // Update in list
      set((s) => ({
        sessions: s.sessions.map((sess) =>
          sess.id === activeSessionId ? updated : sess,
        ),
      }));
    } catch (err) {
      set({ globalError: err instanceof Error ? err.message : 'Failed to assign' });
    }
  },

  resolve: async () => {
    const { activeSessionId } = get();
    if (!activeSessionId) return;
    try {
      await apiResolve(activeSessionId);
      const updated = await fetchSession(activeSessionId);
      set({ activeSession: updated });
      set((s) => ({
        sessions: s.sessions.map((sess) =>
          sess.id === activeSessionId ? updated : sess,
        ),
      }));
    } catch (err) {
      set({ globalError: err instanceof Error ? err.message : 'Failed to resolve' });
    }
  },

  close: async () => {
    const { activeSessionId } = get();
    if (!activeSessionId) return;
    try {
      await apiClose(activeSessionId);
      set((s) => ({
        sessions: s.sessions.filter((sess) => sess.id !== activeSessionId),
        activeSessionId: null,
        activeSession: null,
        transcript: [],
      }));
    } catch (err) {
      set({ globalError: err instanceof Error ? err.message : 'Failed to close' });
    }
  },

  transfer: async (agentId) => {
    const { activeSessionId } = get();
    if (!activeSessionId) return;
    try {
      await apiTransfer(activeSessionId, agentId);
      const updated = await fetchSession(activeSessionId);
      set({ activeSession: updated });
      set((s) => ({
        sessions: s.sessions.map((sess) =>
          sess.id === activeSessionId ? updated : sess,
        ),
      }));
    } catch (err) {
      set({ globalError: err instanceof Error ? err.message : 'Failed to transfer' });
    }
  },

  createLead: async () => {
    const { activeSessionId } = get();
    if (!activeSessionId) return;
    try {
      await createLeadFromSession(activeSessionId);
      const updated = await fetchSession(activeSessionId);
      set({ activeSession: updated });
    } catch (err) {
      set({ globalError: err instanceof Error ? err.message : 'Failed to create lead' });
    }
  },

  createTask: async () => {
    const { activeSessionId, activeSession } = get();
    if (!activeSessionId || !activeSession) {
      return { taskId: null, mailtoUrl: '' };
    }
    const taskId = await createFollowUpTask(
      activeSessionId,
      activeSession.visitor_name,
    );
    const mailtoUrl =
      taskId === null
        ? `mailto:?subject=Follow-up:%20${encodeURIComponent(activeSession.visitor_name)}&body=Session%20ID%3A%20${activeSessionId}`
        : '';
    return { taskId, mailtoUrl };
  },

  loadAISuggestions: async () => {
    const { transcript } = get();
    if (!transcript.length) return;
    set({ aiSuggestionsLoading: true });
    try {
      const last5 = transcript.slice(-5);
      const suggestions = await fetchAISuggestions(last5);
      set({ aiSuggestions: suggestions, aiSuggestionsLoading: false });
    } catch (err) {
      set({
        aiSuggestionsLoading: false,
        globalError: err instanceof Error ? err.message : 'AI suggestions failed',
      });
    }
  },

  toggleAIPanel: () => set((s) => ({ aiPanelOpen: !s.aiPanelOpen })),

  loadAgents: async () => {
    if (get().agents.length) return; // already loaded
    set({ agentsLoading: true });
    try {
      const agents = await fetchAgents();
      set({ agents, agentsLoading: false });
    } catch {
      set({ agentsLoading: false });
    }
  },

  refreshSession: async (id) => {
    try {
      const [session, transcript] = await Promise.all([
        fetchSession(id),
        fetchTranscript(id),
      ]);
      if (get().activeSessionId === id) {
        set({ activeSession: session, transcript });
      }
      set((s) => ({
        sessions: s.sessions.map((sess) => (sess.id === id ? session : sess)),
      }));
    } catch {
      // non-critical background refresh
    }
  },

  dismissGlobalError: () => set({ globalError: null }),

  upsertSession: (session) => {
    set((s) => {
      const exists = s.sessions.some((sess) => sess.id === session.id);
      const sessions = exists
        ? s.sessions.map((sess) => (sess.id === session.id ? session : sess))
        : [session, ...s.sessions];
      const activeSession =
        s.activeSessionId === session.id ? session : s.activeSession;
      return { sessions, activeSession };
    });
  },
}));
