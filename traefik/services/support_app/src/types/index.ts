// ─── Odoo session / auth ────────────────────────────────────────────────────

export interface OdooSession {
  uid: number;
  name: string;
  username: string;
  company_id: [number, string];
  db: string;
  partner_id: [number, string];
  session_id: string;
}

// ─── Chat session ───────────────────────────────────────────────────────────

export type SessionState =
  | 'open'
  | 'escalated'
  | 'assigned'
  | 'resolved'
  | 'closed';

export type EscalationReason =
  | 'low_confidence'
  | 'human_requested'
  | 'trigger_word'
  | 'sentiment'
  | 'high_risk';

export type Sentiment = 'positive' | 'neutral' | 'frustrated' | 'angry' | 'urgent';

export interface ChatSession {
  id: number;
  name: string;
  state: SessionState;
  escalation_reason: EscalationReason | false;
  assigned_agent_id: [number, string] | false;
  visitor_name: string;
  visitor_email: string | false;
  visitor_company: string | false;
  language_code: string | false;
  sentiment: Sentiment | false;
  ai_summary: string | false;
  suggested_next_action: string | false;
  lead_id: [number, string] | false;
  message_count: number;
  create_date: string;
  write_date: string;
  transcript_ids: number[];
}

// ─── Transcript lines ────────────────────────────────────────────────────────

export type MessageRole = 'user' | 'assistant' | 'agent';

export interface TranscriptLine {
  id: number;
  session_id: [number, string];
  role: MessageRole;
  content: string;
  ai_confidence: number | false;
  was_rag: boolean;
  create_date: string;
}

// ─── Chat visitor ─────────────────────────────────────────────────────────

export interface ChatVisitor {
  id: number;
  token: string;
  email: string | false;
  company_name: string | false;
  tracking_consent: boolean;
  first_seen: string | false;
  last_seen: string | false;
  page_view_count: number;
  referrer: string | false;
  utm_source: string | false;
  language_code: string | false;
  lead_id: [number, string] | false;
  chat_session_count: number;
}

// ─── Odoo user (for agent transfer list) ────────────────────────────────────

export interface OdooUser {
  id: number;
  name: string;
  login: string;
  share: boolean;
}

// ─── Canned replies ──────────────────────────────────────────────────────────

export interface CannedReply {
  id: string; // uuid-like key, generated client-side
  shortcut: string;
  content: string;
}

// ─── Notification store entry ────────────────────────────────────────────────

export interface AppNotification {
  id: string;
  sessionId: number;
  visitorName: string;
  escalationReason: EscalationReason | null;
  timestamp: number;
  read: boolean;
}

// ─── Odoo JSON-RPC envelope ──────────────────────────────────────────────────

export interface JsonRpcRequest {
  jsonrpc: '2.0';
  method: 'call';
  id: number;
  params: {
    model: string;
    method: string;
    args: unknown[];
    kwargs: Record<string, unknown>;
  };
}

export interface JsonRpcResponse<T = unknown> {
  jsonrpc: '2.0';
  id: number;
  result?: T;
  error?: {
    code: number;
    message: string;
    data: {
      name: string;
      message: string;
      debug?: string;
    };
  };
}

// ─── Bus message ────────────────────────────────────────────────────────────

export interface BusMessage {
  id: number;
  channel: string;
  message: Record<string, unknown>;
}

// ─── AI suggestion ──────────────────────────────────────────────────────────

export interface AISuggestion {
  text: string;
}
