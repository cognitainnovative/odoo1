import clsx from 'clsx';
import { RefreshCw, AlertCircle } from 'lucide-react';
import { useChatStore, type QueueTab } from '../../store/chatStore';
import { useAuthStore } from '../../store/authStore';
import { QueueItem } from './QueueItem';
import { Spinner } from '../common/Spinner';

const TABS: { id: QueueTab; label: string }[] = [
  { id: 'queue', label: 'Queue' },
  { id: 'mine',  label: 'Mine'  },
  { id: 'all',   label: 'All'   },
];

export function ConversationQueue() {
  const {
    sessions,
    sessionsLoading,
    sessionsError,
    activeTab,
    activeSessionId,
    setActiveTab,
    openSession,
    loadSessions,
  } = useChatStore();
  const session = useAuthStore((s) => s.session);

  function handleTabChange(tab: QueueTab) {
    setActiveTab(tab);
    void loadSessions(session?.uid);
  }

  function handleRefresh() {
    void loadSessions(session?.uid);
  }

  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700">
      {/* Panel header */}
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">Conversations</h2>
          <button
            onClick={handleRefresh}
            disabled={sessionsLoading}
            className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-50"
            aria-label="Refresh queue"
          >
            <RefreshCw size={14} className={sessionsLoading ? 'animate-spin' : ''} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={clsx(
                'flex-1 py-1 text-xs font-medium rounded-md transition-colors',
                activeTab === tab.id
                  ? 'bg-white dark:bg-gray-700 text-brand-600 shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200',
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto">
        {sessionsLoading && sessions.length === 0 && (
          <div className="flex items-center justify-center h-32">
            <Spinner size="md" />
          </div>
        )}

        {sessionsError && (
          <div className="p-4 text-center">
            <AlertCircle size={20} className="text-red-400 mx-auto mb-2" />
            <p className="text-xs text-red-600">{sessionsError}</p>
            <button
              onClick={handleRefresh}
              className="mt-2 text-xs text-brand-600 hover:underline"
            >
              Retry
            </button>
          </div>
        )}

        {!sessionsLoading && !sessionsError && sessions.length === 0 && (
          <div className="p-8 text-center">
            <p className="text-sm text-gray-400 dark:text-gray-500">No conversations</p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
              {activeTab === 'queue'
                ? 'The queue is empty.'
                : activeTab === 'mine'
                ? 'No sessions assigned to you.'
                : 'No open sessions.'}
            </p>
          </div>
        )}

        {sessions.map((sess) => (
          <QueueItem
            key={sess.id}
            session={sess}
            active={activeSessionId === sess.id}
            onClick={() => void openSession(sess.id)}
          />
        ))}
      </div>

      {/* Count footer */}
      {sessions.length > 0 && (
        <div className="px-4 py-2 border-t border-gray-100 dark:border-gray-700 text-xs text-gray-400 dark:text-gray-500">
          {sessions.length} conversation{sessions.length !== 1 ? 's' : ''}
          {sessionsLoading && (
            <span className="ml-2">
              <Spinner size="sm" className="inline-block align-middle" />
            </span>
          )}
        </div>
      )}
    </div>
  );
}
