import { format } from 'date-fns';
import {
  User,
  Mail,
  Building2,
  Globe,
  Eye,
  Clock,
  Link,
  Zap,
  BookOpen,
} from 'lucide-react';
import { useChatStore } from '../../store/chatStore';
import { AISuggestions } from '../chat/AISuggestions';
import { SENTIMENT_DOT } from '../common/Badge';
import { Spinner } from '../common/Spinner';
import type { Sentiment } from '../../types';

const ODOO_BASE = import.meta.env.VITE_ODOO_URL ?? '';

export function CustomerPanel() {
  const {
    activeSession,
    visitor,
    visitorLoading,
  } = useChatStore();

  if (!activeSession) {
    return (
      <div className="flex items-center justify-center h-32 text-gray-400 text-sm">
        No session selected
      </div>
    );
  }

  const currentSentiment = activeSession.sentiment;

  return (
    <div className="flex flex-col h-full overflow-y-auto bg-white divide-y divide-gray-100">
      {/* AI Suggestions — inserts via store pendingInsert */}
      <AISuggestions />

      {/* Visitor info */}
      <div className="px-4 py-4">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
          Visitor
        </h3>

        {visitorLoading && (
          <div className="flex justify-center py-4">
            <Spinner size="sm" />
          </div>
        )}

        <div className="space-y-2.5 text-sm">
          <InfoRow icon={<User size={14} />} label="Name">
            {activeSession.visitor_name || '—'}
          </InfoRow>

          {(activeSession.visitor_email || visitor?.email) && (
            <InfoRow icon={<Mail size={14} />} label="Email">
              <a
                href={`mailto:${activeSession.visitor_email || visitor?.email}`}
                className="text-brand-600 hover:underline truncate"
              >
                {activeSession.visitor_email || visitor?.email}
              </a>
            </InfoRow>
          )}

          {(activeSession.visitor_company || visitor?.company_name) && (
            <InfoRow icon={<Building2 size={14} />} label="Company">
              {activeSession.visitor_company || visitor?.company_name}
            </InfoRow>
          )}

          {(activeSession.language_code || visitor?.language_code) && (
            <InfoRow icon={<Globe size={14} />} label="Language">
              {activeSession.language_code || visitor?.language_code}
            </InfoRow>
          )}

          {visitor && (
            <>
              <InfoRow icon={<Eye size={14} />} label="Page Views">
                {visitor.page_view_count}
              </InfoRow>

              {visitor.first_seen && (
                <InfoRow icon={<Clock size={14} />} label="First Seen">
                  {format(new Date(visitor.first_seen), 'MMM d, yyyy')}
                </InfoRow>
              )}

              {visitor.chat_session_count > 1 && (
                <InfoRow icon={<BookOpen size={14} />} label="Sessions">
                  {visitor.chat_session_count}
                </InfoRow>
              )}

              {visitor.utm_source && (
                <InfoRow icon={<Zap size={14} />} label="Source">
                  {visitor.utm_source}
                </InfoRow>
              )}
            </>
          )}
        </div>

        {/* Linked lead */}
        {activeSession.lead_id && (
          <div className="mt-3 pt-3 border-t border-gray-100">
            <a
              href={`${ODOO_BASE}/web#model=crm.lead&id=${activeSession.lead_id[0]}`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 hover:underline"
            >
              <Link size={13} />
              {activeSession.lead_id[1]}
            </a>
          </div>
        )}
      </div>

      {/* Sentiment history */}
      {currentSentiment && (
        <div className="px-4 py-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Sentiment
          </h3>
          <div className="flex items-center gap-1.5">
            {/* Five dots — rightmost = current */}
            {Array.from({ length: 5 }).map((_, i) => {
              const isCurrent = i === 4;
              const dotClass = isCurrent
                ? SENTIMENT_DOT[currentSentiment as Sentiment]
                : 'bg-gray-200';
              return (
                <span
                  key={i}
                  className={`w-3 h-3 rounded-full ${dotClass}${isCurrent ? ' ring-2 ring-offset-1 ring-gray-300' : ''}`}
                  title={isCurrent ? (currentSentiment || 'neutral') : undefined}
                />
              );
            })}
            <span className="text-xs text-gray-500 ml-1 capitalize">
              {currentSentiment}
            </span>
          </div>
        </div>
      )}

      {/* AI summary */}
      {activeSession.ai_summary && (
        <div className="px-4 py-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            AI Summary
          </h3>
          <p className="text-sm text-gray-700 leading-relaxed">
            {activeSession.ai_summary}
          </p>
        </div>
      )}

      {/* Suggested next action */}
      {activeSession.suggested_next_action && (
        <div className="px-4 py-4">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Suggested Action
          </h3>
          <p className="text-sm text-brand-700 leading-relaxed">
            {activeSession.suggested_next_action}
          </p>
        </div>
      )}
    </div>
  );
}

// ─── Helper component ─────────────────────────────────────────────────────

interface InfoRowProps {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}

function InfoRow({ icon, label, children }: InfoRowProps) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-gray-400 mt-0.5 flex-shrink-0">{icon}</span>
      <div className="flex-1 min-w-0">
        <span className="text-xs text-gray-400 block">{label}</span>
        <span className="text-gray-700 block truncate">{children}</span>
      </div>
    </div>
  );
}
