import clsx from 'clsx';
import type { EscalationReason, Sentiment, SessionState } from '../../types';

// ─── Session State Badge ──────────────────────────────────────────────────

const STATE_STYLES: Record<SessionState, string> = {
  open:      'bg-blue-100 text-blue-800',
  escalated: 'bg-orange-100 text-orange-800',
  assigned:  'bg-purple-100 text-purple-800',
  resolved:  'bg-green-100 text-green-800',
  closed:    'bg-gray-100 text-gray-600',
};

const STATE_LABELS: Record<SessionState, string> = {
  open:      'Open',
  escalated: 'Escalated',
  assigned:  'Assigned',
  resolved:  'Resolved',
  closed:    'Closed',
};

interface StateBadgeProps {
  state: SessionState;
  className?: string;
}

export function StateBadge({ state, className }: StateBadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
        STATE_STYLES[state],
        className,
      )}
    >
      {STATE_LABELS[state]}
    </span>
  );
}

// ─── Escalation Reason Badge ──────────────────────────────────────────────

const ESCALATION_LABELS: Record<EscalationReason, string> = {
  low_confidence:  'Low Confidence',
  human_requested: 'Human Request',
  trigger_word:    'Trigger Word',
  sentiment:       'Sentiment',
  high_risk:       'High Risk',
};

const ESCALATION_STYLES: Record<EscalationReason, string> = {
  low_confidence:  'bg-yellow-100 text-yellow-800',
  human_requested: 'bg-blue-100 text-blue-800',
  trigger_word:    'bg-red-100 text-red-800',
  sentiment:       'bg-pink-100 text-pink-800',
  high_risk:       'bg-red-200 text-red-900',
};

interface EscalationBadgeProps {
  reason: EscalationReason | false;
  className?: string;
}

export function EscalationBadge({ reason, className }: EscalationBadgeProps) {
  if (!reason) return null;
  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
        ESCALATION_STYLES[reason],
        className,
      )}
    >
      {ESCALATION_LABELS[reason]}
    </span>
  );
}

// ─── Sentiment Badge ──────────────────────────────────────────────────────

const SENTIMENT_LABELS: Record<Sentiment, string> = {
  positive:   '😊 Positive',
  neutral:    '😐 Neutral',
  frustrated: '😤 Frustrated',
  angry:      '😠 Angry',
  urgent:     '🚨 Urgent',
};

const SENTIMENT_STYLES: Record<Sentiment, string> = {
  positive:   'bg-green-100 text-green-800',
  neutral:    'bg-gray-100 text-gray-700',
  frustrated: 'bg-orange-100 text-orange-800',
  angry:      'bg-red-100 text-red-800',
  urgent:     'bg-red-200 text-red-900 font-semibold',
};

// Dot colors for sentiment history
export const SENTIMENT_DOT: Record<Sentiment, string> = {
  positive:   'bg-green-400',
  neutral:    'bg-gray-400',
  frustrated: 'bg-orange-400',
  angry:      'bg-red-500',
  urgent:     'bg-red-700',
};

interface SentimentBadgeProps {
  sentiment: Sentiment | false;
  className?: string;
}

export function SentimentBadge({ sentiment, className }: SentimentBadgeProps) {
  if (!sentiment) return null;
  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
        SENTIMENT_STYLES[sentiment],
        className,
      )}
    >
      {SENTIMENT_LABELS[sentiment]}
    </span>
  );
}
