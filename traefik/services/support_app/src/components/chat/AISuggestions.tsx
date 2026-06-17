import { RefreshCw, ChevronRight, Sparkles } from 'lucide-react';
import { useChatStore } from '../../store/chatStore';
import { Spinner } from '../common/Spinner';

export function AISuggestions() {
  const {
    aiSuggestions,
    aiSuggestionsLoading,
    loadAISuggestions,
    transcript,
    setPendingInsert,
  } = useChatStore();

  const hasTranscript = transcript.length > 0;

  return (
    <div className="bg-white border-b border-gray-200">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-purple-500" />
          <span className="text-sm font-semibold text-gray-800">AI Suggestions</span>
        </div>
        <div className="flex items-center gap-1">
          {aiSuggestionsLoading && <Spinner size="sm" />}
          <button
            onClick={() => void loadAISuggestions()}
            disabled={!hasTranscript || aiSuggestionsLoading}
            className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors disabled:opacity-40"
            aria-label="Refresh AI suggestions"
          >
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        {!hasTranscript && (
          <p className="text-xs text-gray-400 text-center py-2">
            Open a session to get AI suggestions.
          </p>
        )}

        {hasTranscript && !aiSuggestionsLoading && aiSuggestions.length === 0 && (
          <button
            onClick={() => void loadAISuggestions()}
            className="w-full py-2 text-sm text-brand-600 hover:text-brand-700 font-medium flex items-center justify-center gap-1.5 hover:bg-brand-50 rounded-lg transition-colors"
          >
            <Sparkles size={14} />
            Get AI Suggestions
          </button>
        )}

        {aiSuggestionsLoading && aiSuggestions.length === 0 && (
          <div className="flex items-center justify-center py-4">
            <Spinner size="md" />
          </div>
        )}

        {aiSuggestions.length > 0 && (
          <div className="space-y-2">
            {aiSuggestions.map((s, i) => (
              <button
                key={i}
                onClick={() => setPendingInsert(s.text)}
                className="w-full text-left px-3 py-2.5 bg-purple-50 hover:bg-purple-100 border border-purple-100 rounded-lg text-sm text-gray-700 transition-colors group flex items-start gap-2"
              >
                <ChevronRight
                  size={14}
                  className="text-purple-400 mt-0.5 flex-shrink-0 group-hover:text-purple-600 transition-colors"
                />
                <span className="leading-snug">{s.text}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
