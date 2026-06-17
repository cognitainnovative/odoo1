import { format } from 'date-fns';
import clsx from 'clsx';
import type { TranscriptLine } from '../../types';

interface MessageBubbleProps {
  line: TranscriptLine;
  agentName?: string;
}

export function MessageBubble({ line, agentName }: MessageBubbleProps) {
  const isAgent = line.role === 'agent';
  const isUser  = line.role === 'user';
  // assistant = AI bot responses

  const roleLabel =
    isUser  ? 'Visitor' :
    isAgent ? (agentName ?? 'You') :
    'AI';

  const timestamp = format(new Date(line.create_date), 'HH:mm');

  return (
    <div
      className={clsx(
        'flex flex-col max-w-xs md:max-w-sm lg:max-w-md xl:max-w-lg',
        isAgent || isUser ? 'self-end items-end' : 'self-start items-start',
        isUser && 'self-start items-start', // visitor = left side
      )}
    >
      {/* Role label */}
      <span className="text-xs text-gray-400 dark:text-gray-500 mb-1 px-1">{roleLabel}</span>

      {/* Bubble */}
      <div
        className={clsx(
          'px-4 py-2.5 rounded-2xl text-sm leading-relaxed break-words',
          isUser      && 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-100 rounded-tl-sm',
          line.role === 'assistant' && 'bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-200 rounded-tl-sm',
          isAgent     && 'bg-brand-500 text-white rounded-tr-sm',
        )}
      >
        {line.content}
      </div>

      {/* Timestamp + confidence indicator */}
      <div className="flex items-center gap-2 mt-0.5 px-1">
        <span className="text-xs text-gray-400 dark:text-gray-500">{timestamp}</span>
        {line.was_rag && (
          <span className="text-xs text-indigo-500" title="Answered via RAG knowledge base">
            RAG
          </span>
        )}
        {line.ai_confidence !== false && line.ai_confidence < 0.7 && (
          <span className="text-xs text-orange-500" title={`AI confidence: ${Math.round((line.ai_confidence as number) * 100)}%`}>
            Low confidence
          </span>
        )}
      </div>
    </div>
  );
}
