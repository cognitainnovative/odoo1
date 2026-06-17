import { useState, useEffect } from 'react';
import { ChevronRight, ChevronLeft, X } from 'lucide-react';
import clsx from 'clsx';
import { Header, DARK_SIDEBAR_KEY } from './Header';
import { Sidebar } from './Sidebar';
import { ChatWindow } from '../chat/ChatWindow';
import { CustomerPanel } from '../context/CustomerPanel';
import { useChatStore } from '../../store/chatStore';
import { useBus } from '../../hooks/useBus';
import { useQueue } from '../../hooks/useQueue';

// Mobile tab type
type MobileTab = 'queue' | 'chat' | 'context';

export function AppLayout() {
  const [darkMode, setDarkMode] = useState(
    () => localStorage.getItem(DARK_SIDEBAR_KEY) === 'true',
  );

  useEffect(() => {
    document.documentElement.classList.toggle('dark', darkMode);
  }, [darkMode]);
  const [contextOpen, setContextOpen] = useState(true);
  const [mobileTab, setMobileTab] = useState<MobileTab>('queue');
  const { activeSession, globalError, dismissGlobalError, setPendingInsert } =
    useChatStore();

  // Start polling queue
  useQueue();
  // Connect bus
  useBus();

  function toggleDarkMode() {
    setDarkMode((v) => {
      const next = !v;
      localStorage.setItem(DARK_SIDEBAR_KEY, String(next));
      return next;
    });
  }

  // When a session is opened on mobile, switch to chat tab
  useEffect(() => {
    if (activeSession && mobileTab === 'queue') {
      setMobileTab('chat');
    }
  }, [activeSession, mobileTab]);

  // On mobile: when an AI suggestion is inserted, switch to chat tab
  function handleMobileInsert(text: string) {
    setPendingInsert(text);
    setMobileTab('chat');
  }

  return (
    <div className="flex flex-col h-screen bg-gray-100 dark:bg-gray-950 overflow-hidden">
      <Header darkMode={darkMode} onToggleDarkMode={toggleDarkMode} />

      {/* Global error banner */}
      {globalError && (
        <div className="bg-red-600 text-white text-sm px-4 py-2.5 flex items-center justify-between">
          <span>{globalError}</span>
          <button
            onClick={dismissGlobalError}
            className="ml-4 hover:opacity-80 transition-opacity"
            aria-label="Dismiss error"
          >
            <X size={15} />
          </button>
        </div>
      )}

      {/* ─── Desktop three-column layout (≥ 768px) ──────────────────── */}
      <div className="hidden md:flex flex-1 overflow-hidden">
        {/* Left: Queue sidebar */}
        <Sidebar />

        {/* Center: Chat window */}
        <main className="flex-1 overflow-hidden">
          <ChatWindow />
        </main>

        {/* Right: Context panel (collapsible) */}
        <div
          className={clsx(
            'flex-shrink-0 border-l border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 flex flex-col overflow-hidden transition-all duration-200',
            contextOpen ? 'w-80' : 'w-0',
          )}
          style={{ minWidth: contextOpen ? 320 : 0 }}
        >
          {contextOpen && <CustomerPanel />}
        </div>

        {/* Context toggle button */}
        <button
          onClick={() => setContextOpen((v) => !v)}
          className="absolute right-0 top-1/2 -translate-y-1/2 z-20 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-l-lg py-3 px-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm"
          style={{ position: 'fixed', right: contextOpen ? 320 : 0 }}
          aria-label={contextOpen ? 'Close context panel' : 'Open context panel'}
        >
          {contextOpen ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>

      {/* ─── Mobile single-column layout (< 768px) ──────────────────── */}
      <div className="flex md:hidden flex-col flex-1 overflow-hidden">
        {/* Content */}
        <div className="flex-1 overflow-hidden">
          {mobileTab === 'queue'   && <Sidebar />}
          {mobileTab === 'chat'    && <ChatWindow />}
          {mobileTab === 'context' && (
            <div onClick={() => handleMobileInsert('')}>
              <CustomerPanel />
            </div>
          )}
        </div>

        {/* Bottom nav */}
        <nav className="flex border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
          {([
            { tab: 'queue' as const,   label: 'Queue'   },
            { tab: 'chat' as const,    label: 'Chat'    },
            { tab: 'context' as const, label: 'Context' },
          ] as const).map(({ tab, label }) => (
            <button
              key={tab}
              onClick={() => setMobileTab(tab)}
              className={clsx(
                'flex-1 py-3 text-xs font-medium transition-colors',
                mobileTab === tab
                  ? 'text-brand-600 border-t-2 border-brand-500'
                  : 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300',
              )}
            >
              {label}
            </button>
          ))}
        </nav>
      </div>
    </div>
  );
}
