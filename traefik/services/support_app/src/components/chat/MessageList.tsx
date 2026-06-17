import { useEffect, useRef } from 'react';
import { MessageBubble } from './MessageBubble';
import { Spinner } from '../common/Spinner';
import type { TranscriptLine } from '../../types';

interface MessageListProps {
  lines: TranscriptLine[];
  loading: boolean;
  agentName?: string;
}

export function MessageList({ lines, loading, agentName }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [lines.length]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  if (lines.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-600 bg-white dark:bg-gray-900 text-sm">
        No messages yet
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3 bg-gray-50 dark:bg-gray-950">
      {lines.map((line) => (
        <MessageBubble key={line.id} line={line} agentName={agentName} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
