import { useState, useRef, useEffect, type KeyboardEvent } from 'react';
import { Send, Settings2, HelpCircle } from 'lucide-react';
import clsx from 'clsx';
import { CannedRepliesModal } from './CannedRepliesModal';
import { useChatStore } from '../../store/chatStore';

const MAX_CHARS = 2000;

interface MessageInputProps {
  disabled?: boolean;
}

export function MessageInput({ disabled = false }: MessageInputProps) {
  const [text, setText] = useState('');
  const [cannedOpen, setCannedOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const {
    sendMessage,
    knowledgeSuggestions,
    pendingInsert,
    clearPendingInsert,
  } = useChatStore();

  // When the AI panel or canned replies pushes text to insert, apply it
  useEffect(() => {
    if (pendingInsert) {
      setText(pendingInsert);
      clearPendingInsert();
      setTimeout(() => textareaRef.current?.focus(), 0);
    }
  }, [pendingInsert, clearPendingInsert]);

  async function handleSend() {
    const trimmed = text.trim();
    if (!trimmed || sending || disabled) return;
    setSending(true);
    setText('');
    try {
      await sendMessage(trimmed);
    } finally {
      setSending(false);
      textareaRef.current?.focus();
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Ctrl+Enter or Cmd+Enter sends
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      void handleSend();
    }
  }

  function handleCannedSelect(content: string) {
    setText(content);
    setTimeout(() => textareaRef.current?.focus(), 0);
  }

  function handleKnowledgeChip(topic: string) {
    setText((prev) => (prev ? `${prev} ${topic}` : topic));
    textareaRef.current?.focus();
  }

  const remaining = MAX_CHARS - text.length;
  const overLimit = remaining < 0;

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
      {/* Knowledge suggestion chips */}
      {knowledgeSuggestions.length > 0 && (
        <div className="px-4 pt-3 flex flex-wrap gap-1.5 items-center">
          <span className="text-xs text-gray-400 flex items-center gap-1">
            <HelpCircle size={11} />
            Topics:
          </span>
          {knowledgeSuggestions.map((chip, i) => (
            <button
              key={i}
              onClick={() => handleKnowledgeChip(chip)}
              className="px-2 py-0.5 text-xs bg-indigo-50 text-indigo-700 border border-indigo-200 rounded-full hover:bg-indigo-100 transition-colors"
            >
              {chip}
            </button>
          ))}
        </div>
      )}

      {/* Text area row */}
      <div className="p-4">
        <div className={clsx(
          'border rounded-xl overflow-hidden transition-colors',
          overLimit ? 'border-red-400' : 'border-gray-300 dark:border-gray-600 focus-within:border-brand-500',
          disabled && 'opacity-60',
        )}>
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled || sending}
            placeholder={disabled ? 'Assign this session to reply…' : 'Type a message… (Ctrl+Enter to send)'}
            rows={3}
            className="w-full px-4 py-3 text-sm resize-none focus:outline-none disabled:bg-gray-50 bg-white dark:bg-gray-900 dark:text-gray-100 dark:placeholder-gray-500 dark:disabled:bg-gray-800"
          />

          {/* Toolbar */}
          <div className="flex items-center justify-between px-3 py-2 border-t border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
            <div className="flex items-center gap-1">
              {/* Canned replies */}
              <button
                onClick={() => setCannedOpen(true)}
                disabled={disabled}
                className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-40"
                title="Canned replies"
                aria-label="Open canned replies"
              >
                <Settings2 size={15} />
              </button>
            </div>

            <div className="flex items-center gap-3">
              {/* Character count */}
              <span
                className={clsx(
                  'text-xs',
                  overLimit
                    ? 'text-red-500 font-medium'
                    : remaining < 200
                    ? 'text-orange-500'
                    : 'text-gray-400',
                )}
              >
                {remaining}
              </span>

              {/* Send button */}
              <button
                onClick={() => void handleSend()}
                disabled={!text.trim() || overLimit || sending || disabled}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-brand-600 text-white text-sm font-medium rounded-lg hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {sending ? (
                  <span className="h-3.5 w-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                ) : (
                  <Send size={13} />
                )}
                Send
              </button>
            </div>
          </div>
        </div>
      </div>

      <CannedRepliesModal
        open={cannedOpen}
        onClose={() => setCannedOpen(false)}
        onSelect={handleCannedSelect}
      />
    </div>
  );
}
