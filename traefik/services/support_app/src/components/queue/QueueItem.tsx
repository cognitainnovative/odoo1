import { formatDistanceToNow } from 'date-fns';
import { MessageCircle } from 'lucide-react';
import clsx from 'clsx';
import { EscalationBadge, SentimentBadge } from '../common/Badge';
import type { ChatSession } from '../../types';

interface QueueItemProps {
  session: ChatSession;
  active: boolean;
  onClick: () => void;
}

export function QueueItem({ session, active, onClick }: QueueItemProps) {
  const waitTime = formatDistanceToNow(new Date(session.create_date), {
    addSuffix: false,
  });

  return (
    <button
      onClick={onClick}
      className={clsx(
        'w-full text-left px-4 py-3 border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500',
        active && 'bg-brand-50 dark:bg-brand-900/20 border-l-4 border-l-brand-500',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-medium text-sm text-gray-900 dark:text-gray-100 truncate flex-1">
          {session.visitor_name || 'Anonymous Visitor'}
        </span>
        <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">{waitTime}</span>
      </div>

      {/* Badges row */}
      <div className="flex flex-wrap gap-1 mt-1.5">
        {session.escalation_reason && (
          <EscalationBadge reason={session.escalation_reason} />
        )}
        {session.sentiment && (
          <SentimentBadge sentiment={session.sentiment} />
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center gap-3 mt-1.5">
        <span className="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500">
          <MessageCircle size={12} />
          {session.message_count}
        </span>
        {session.visitor_company && (
          <span className="text-xs text-gray-400 dark:text-gray-500 truncate">
            {session.visitor_company}
          </span>
        )}
        {session.assigned_agent_id && (
          <span className="text-xs text-purple-600 truncate ml-auto">
            {session.assigned_agent_id[1]}
          </span>
        )}
      </div>
    </button>
  );
}
