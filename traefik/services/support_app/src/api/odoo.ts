/**
 * Odoo JSON-RPC API client.
 *
 * All calls go through this module so that:
 *  - Session cookies are attached automatically (withCredentials)
 *  - 401 / session-expired errors trigger a global logout
 *  - Odoo-level errors (code 200 but result.error set) are surfaced uniformly
 */

import axios, { AxiosError } from 'axios';
import type {
  JsonRpcResponse,
  OdooSession,
  ChatSession,
  TranscriptLine,
  ChatVisitor,
  OdooUser,
  AISuggestion,
  EscalationReason,
} from '../types';

// Base URL comes from env; in dev the Vite proxy rewrites /web/* to Odoo
const BASE_URL = (import.meta.env.VITE_ODOO_URL as string | undefined) ?? '';

let _rpcId = 1;

// Callback registered by authStore so that any 401 triggers a logout
let onUnauthorized: (() => void) | null = null;

export function registerUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

// ─── Low-level axios instance ─────────────────────────────────────────────

const http = axios.create({
  baseURL: BASE_URL,
  withCredentials: true, // send session cookie cross-origin
  headers: { 'Content-Type': 'application/json' },
});

http.interceptors.response.use(
  (res) => res,
  (err: AxiosError) => {
    if (err.response?.status === 401) {
      onUnauthorized?.();
    }
    return Promise.reject(err);
  },
);

// ─── JSON-RPC helper ──────────────────────────────────────────────────────

async function callKw<T>(
  model: string,
  method: string,
  args: unknown[],
  kwargs: Record<string, unknown> = {},
): Promise<T> {
  const id = _rpcId++;
  const body = {
    jsonrpc: '2.0',
    method: 'call',
    id,
    params: { model, method, args, kwargs },
  };

  const response = await http.post<JsonRpcResponse<T>>(
    '/web/dataset/call_kw',
    body,
  );

  const data = response.data;

  // Odoo wraps business errors inside result.error even on HTTP 200
  if (data.error) {
    throw new Error(
      data.error.data?.message ?? data.error.message ?? 'Odoo RPC error',
    );
  }

  return data.result as T;
}

// ─── Auth ─────────────────────────────────────────────────────────────────

export async function login(
  db: string,
  login: string,
  password: string,
): Promise<OdooSession> {
  const res = await http.post<JsonRpcResponse<OdooSession>>(
    '/web/session/authenticate',
    {
      jsonrpc: '2.0',
      method: 'call',
      id: _rpcId++,
      params: { db, login, password },
    },
  );

  if (res.data.error) {
    throw new Error(res.data.error.data?.message ?? 'Login failed');
  }

  const session = res.data.result;
  if (!session || !session.uid) {
    throw new Error('Invalid credentials');
  }

  return session;
}

export async function getSessionInfo(): Promise<OdooSession> {
  const res = await http.post<JsonRpcResponse<OdooSession>>(
    '/web/session/get_session_info',
    {
      jsonrpc: '2.0',
      method: 'call',
      id: _rpcId++,
      params: {},
    },
  );

  if (res.data.error || !res.data.result?.uid) {
    throw new Error('Not authenticated');
  }

  return res.data.result as OdooSession;
}

export async function logout(): Promise<void> {
  await http.post('/web/session/destroy', {
    jsonrpc: '2.0',
    method: 'call',
    id: _rpcId++,
    params: {},
  });
}

// ─── Chat sessions ────────────────────────────────────────────────────────

const SESSION_FIELDS = [
  'id',
  'name',
  'state',
  'escalation_reason',
  'assigned_agent_id',
  'visitor_name',
  'visitor_email',
  'visitor_company',
  'language_code',
  'sentiment',
  'ai_summary',
  'suggested_next_action',
  'lead_id',
  'message_count',
  'create_date',
  'write_date',
  'transcript_ids',
];

export async function fetchSessions(
  domain: unknown[][],
): Promise<ChatSession[]> {
  return callKw<ChatSession[]>('chat.session', 'search_read', [domain], {
    fields: SESSION_FIELDS,
    order: 'create_date asc',
    limit: 200,
  });
}

export async function fetchSession(id: number): Promise<ChatSession> {
  const results = await callKw<ChatSession[]>(
    'chat.session',
    'search_read',
    [[[['id', '=', id]]]],
    { fields: SESSION_FIELDS, limit: 1 },
  );
  if (!results.length) throw new Error(`Session ${id} not found`);
  return results[0];
}

export async function assignSessionToMe(sessionId: number): Promise<void> {
  await callKw('chat.session', 'action_assign_to_me', [[sessionId]]);
}

export async function resolveSession(sessionId: number): Promise<void> {
  await callKw('chat.session', 'action_resolve', [[sessionId]]);
}

export async function closeSession(sessionId: number): Promise<void> {
  await callKw('chat.session', 'action_close', [[sessionId]]);
}

export async function createLeadFromSession(sessionId: number): Promise<void> {
  await callKw('chat.session', 'action_create_lead', [[sessionId]]);
}

export async function escalateSession(
  sessionId: number,
  reason: EscalationReason,
): Promise<void> {
  await callKw('chat.session', 'escalate', [[sessionId], reason]);
}

/**
 * Transfer a session to a different agent: write assigned_agent_id and flip to assigned.
 * There is no dedicated transfer RPC on the backend so we do a direct write.
 */
export async function transferSession(
  sessionId: number,
  agentId: number,
): Promise<void> {
  await callKw('chat.session', 'write', [
    [sessionId],
    { assigned_agent_id: agentId, state: 'assigned' },
  ]);
}

// ─── Transcript lines ─────────────────────────────────────────────────────

export async function fetchTranscript(
  sessionId: number,
): Promise<TranscriptLine[]> {
  return callKw<TranscriptLine[]>('chat.transcript.line', 'search_read', [
    [[['session_id', '=', sessionId]]],
  ], {
    fields: [
      'id',
      'session_id',
      'role',
      'content',
      'ai_confidence',
      'was_rag',
      'create_date',
    ],
    order: 'create_date asc',
    limit: 500,
  });
}

export async function sendAgentMessage(
  sessionId: number,
  content: string,
): Promise<TranscriptLine> {
  // Create a transcript line with role "agent"
  const id = await callKw<number>('chat.transcript.line', 'create', [
    { session_id: sessionId, role: 'agent', content },
  ]);
  // Re-fetch the created line so we get all fields including create_date
  const lines = await callKw<TranscriptLine[]>(
    'chat.transcript.line',
    'search_read',
    [[[['id', '=', id]]]],
    {
      fields: ['id', 'session_id', 'role', 'content', 'ai_confidence', 'was_rag', 'create_date'],
    },
  );
  return lines[0];
}

// ─── Chat visitor ─────────────────────────────────────────────────────────

export async function fetchVisitorBySession(
  sessionId: number,
): Promise<ChatVisitor | null> {
  // The visitor is linked via the session; we search by session's visitor_name
  // The backend model uses token-based lookup; we search by related session
  const results = await callKw<ChatVisitor[]>('chat.visitor', 'search_read', [
    [[['chat_session_ids', 'in', [sessionId]]]],
  ], {
    fields: [
      'id',
      'token',
      'email',
      'company_name',
      'tracking_consent',
      'first_seen',
      'last_seen',
      'page_view_count',
      'referrer',
      'utm_source',
      'language_code',
      'lead_id',
      'chat_session_count',
    ],
    limit: 1,
  });
  return results[0] ?? null;
}

// ─── Agents (for transfer modal) ─────────────────────────────────────────

export async function fetchAgents(): Promise<OdooUser[]> {
  return callKw<OdooUser[]>('res.users', 'search_read', [
    [[['share', '=', false], ['active', '=', true]]],
  ], {
    fields: ['id', 'name', 'login'],
    order: 'name asc',
    limit: 200,
  });
}

// ─── AI service ───────────────────────────────────────────────────────────

/**
 * Ask the AI service for reply suggestions given a conversation snippet.
 * The backend expects a plain-text prompt.
 */
export async function fetchAISuggestions(
  lastMessages: TranscriptLine[],
): Promise<AISuggestion[]> {
  const transcript = lastMessages
    .map((m) => `${m.role === 'user' ? 'Visitor' : m.role === 'agent' ? 'Agent' : 'AI'}: ${m.content}`)
    .join('\n');

  const prompt =
    'Suggest 3 concise reply options for this support conversation. Return as numbered list:\n\n' +
    transcript;

  const raw = await callKw<string>('ai.service', 'call', [prompt]);

  // Parse numbered list "1. ...\n2. ...\n3. ..."
  const lines = raw
    .split('\n')
    .map((l) => l.replace(/^\d+\.\s*/, '').trim())
    .filter((l) => l.length > 0)
    .slice(0, 3);

  return lines.map((text) => ({ text }));
}

/**
 * Ask the AI service for knowledge-base topic suggestions for the latest message.
 */
export async function fetchKnowledgeSuggestions(
  lastMessage: string,
): Promise<string[]> {
  const prompt =
    'What knowledge base topics are relevant to: ' +
    lastMessage +
    '? List 3 short topic titles.';

  const raw = await callKw<string>('ai.service', 'call', [prompt]);

  return raw
    .split('\n')
    .map((l) => l.replace(/^\d+\.\s*[-–]?\s*/, '').trim())
    .filter((l) => l.length > 0)
    .slice(0, 3);
}

// ─── Follow-up task ───────────────────────────────────────────────────────

export async function createFollowUpTask(
  sessionId: number,
  visitorName: string,
): Promise<number | null> {
  try {
    const id = await callKw<number>('project.task', 'create', [
      {
        name: `Follow-up: ${visitorName}`,
        description: `Follow-up required for chat session #${sessionId}`,
        // Use default project if available; Odoo won't error without project_id
        // if no mandatory constraint is set on the model
      },
    ]);
    return id;
  } catch {
    // project.task may not be installed; caller should fall back to mailto
    return null;
  }
}
