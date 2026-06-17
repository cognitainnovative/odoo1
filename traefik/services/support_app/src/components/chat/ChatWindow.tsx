import { useState } from 'react';
import {
  UserCheck,
  CheckCircle,
  ArrowLeftRight,
  Link,
  ClipboardList,
  MessageSquare,
} from 'lucide-react';
import clsx from 'clsx';
import { useChatStore } from '../../store/chatStore';
import { useAuthStore } from '../../store/authStore';
import { StateBadge, EscalationBadge, SentimentBadge } from '../common/Badge';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { Modal } from '../common/Modal';
import { Spinner } from '../common/Spinner';

const ODOO_BASE =
  (import.meta.env.VITE_ODOO_URL as string | undefined) ?? '';

export function ChatWindow() {
  const {
    activeSession,
    transcript,
    transcriptLoading,
    agents,
    agentsLoading,
    assignToMe,
    resolve,
    transfer,
    createLead,
    createTask,
    loadAgents,
  } = useChatStore();
  const session = useAuthStore((s) => s.session);

  // Dialog states
  const [resolveOpen, setResolveOpen] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [transferOpen, setTransferOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<number | null>(null);
  const [transferring, setTransferring] = useState(false);
  const [agentSearch, setAgentSearch] = useState('');
  const [creatingLead, setCreatingLead] = useState(false);
  const [taskResult, setTaskResult] = useState<{
    taskId: number | null;
    mailtoUrl: string;
  } | null>(null);

  if (!activeSession) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 dark:text-gray-600 bg-white dark:bg-gray-900 gap-3">
        <MessageSquare size={40} strokeWidth={1.5} />
        <p className="text-sm">Select a conversation to start</p>
      </div>
    );
  }

  const agentId = activeSession.assigned_agent_id;
  const isAssigned = !!agentId;
  const isMySession =
    isAssigned && Array.isArray(agentId) && agentId[0] === session?.uid;
  const canReply = isMySession;

  async function handleAssign() {
    await assignToMe();
  }

  async function handleResolve() {
    setResolving(true);
    try {
      await resolve();
      setResolveOpen(false);
    } finally {
      setResolving(false);
    }
  }

  async function handleTransfer() {
    if (!selectedAgent) return;
    setTransferring(true);
    try {
      await transfer(selectedAgent);
      setTransferOpen(false);
    } finally {
      setTransferring(false);
    }
  }

  function openTransfer() {
    setSelectedAgent(null);
    setAgentSearch('');
    setTransferOpen(true);
    void loadAgents();
  }

  async function handleCreateLead() {
    setCreatingLead(true);
    try {
      await createLead();
    } finally {
      setCreatingLead(false);
    }
  }

  async function handleCreateTask() {
    const result = await createTask();
    setTaskResult(result);
  }

  const filteredAgents = agents.filter(
    (a) =>
      a.id !== session?.uid &&
      a.name.toLowerCase().includes(agentSearch.toLowerCase()),
  );

  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-900">
      {/* Session header */}
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-sm">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <h2 className="font-semibold text-gray-900 dark:text-gray-100 text-sm truncate">
              {activeSession.visitor_name || 'Anonymous Visitor'}
            </h2>
            {activeSession.visitor_email && (
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{activeSession.visitor_email}</p>
            )}
          </div>

          {/* Badges */}
          <div className="flex flex-wrap items-center gap-1.5 flex-shrink-0">
            <StateBadge state={activeSession.state} />
            {activeSession.escalation_reason && (
              <EscalationBadge reason={activeSession.escalation_reason} />
            )}
            {activeSession.sentiment && (
              <SentimentBadge sentiment={activeSession.sentiment} />
            )}
          </div>
        </div>

        {/* Action bar */}
        <div className="flex items-center gap-2 mt-3 flex-wrap dark:text-gray-300">
          {!isAssigned && (
            <button
              onClick={() => void handleAssign()}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-brand-600 text-white rounded-lg hover:bg-brand-700 transition-colors"
            >
              <UserCheck size={13} />
              Assign to me
            </button>
          )}

          {isAssigned && (
            <>
              <button
                onClick={() => setResolveOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
              >
                <CheckCircle size={13} />
                Resolve
              </button>
              <button
                onClick={openTransfer}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
              >
                <ArrowLeftRight size={13} />
                Transfer
              </button>
            </>
          )}

          {!activeSession.lead_id && (
            <button
              onClick={() => void handleCreateLead()}
              disabled={creatingLead}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 transition-colors"
            >
              {creatingLead ? <Spinner size="sm" /> : <Link size={13} />}
              Create Lead
            </button>
          )}

          {activeSession.lead_id && (
            <a
              href={`${ODOO_BASE}/web#model=crm.lead&id=${activeSession.lead_id[0]}`}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-indigo-50 text-indigo-700 rounded-lg hover:bg-indigo-100 transition-colors"
            >
              <Link size={13} />
              View Lead
            </a>
          )}

          <button
            onClick={() => void handleCreateTask()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
          >
            <ClipboardList size={13} />
            Follow-up Task
          </button>

          {isAssigned && (
            <span
              className={clsx(
                'ml-auto text-xs',
                isMySession ? 'text-green-600' : 'text-gray-400',
              )}
            >
              {isMySession
                ? 'Assigned to you'
                : `Assigned to ${Array.isArray(agentId) ? agentId[1] : ''}`}
            </span>
          )}
        </div>
      </div>

      {/* Message list */}
      <MessageList
        lines={transcript}
        loading={transcriptLoading}
        agentName={session?.name}
      />

      {/* Input */}
      <MessageInput disabled={!canReply} />

      {/* Resolve confirm */}
      <ConfirmDialog
        open={resolveOpen}
        onClose={() => setResolveOpen(false)}
        onConfirm={() => void handleResolve()}
        title="Resolve Session"
        message="Are you sure you want to mark this session as resolved? The AI will generate a summary."
        confirmLabel="Resolve"
        confirmVariant="primary"
        loading={resolving}
      />

      {/* Transfer modal */}
      <Modal
        open={transferOpen}
        onClose={() => setTransferOpen(false)}
        title="Transfer to Agent"
        maxWidth="sm"
      >
        <input
          type="text"
          value={agentSearch}
          onChange={(e) => setAgentSearch(e.target.value)}
          placeholder="Search agents…"
          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm mb-3 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <div className="max-h-52 overflow-y-auto space-y-1 mb-4">
          {agentsLoading && (
            <div className="flex justify-center py-4">
              <Spinner size="md" />
            </div>
          )}
          {!agentsLoading &&
            filteredAgents.map((agent) => (
              <button
                key={agent.id}
                onClick={() => setSelectedAgent(agent.id)}
                className={clsx(
                  'w-full text-left px-3 py-2 rounded-lg text-sm transition-colors',
                  selectedAgent === agent.id
                    ? 'bg-brand-600 text-white'
                    : 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200',
                )}
              >
                {agent.name}
                <span className="text-xs opacity-60 ml-2">{agent.login}</span>
              </button>
            ))}
          {!agentsLoading && filteredAgents.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-3">No agents found</p>
          )}
        </div>
        <div className="flex justify-end gap-2">
          <button
            onClick={() => setTransferOpen(false)}
            disabled={transferring}
            className="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => void handleTransfer()}
            disabled={!selectedAgent || transferring}
            className="px-4 py-2 text-sm font-medium text-white bg-brand-600 hover:bg-brand-700 rounded-lg disabled:opacity-50 transition-colors flex items-center gap-2"
          >
            {transferring && <Spinner size="sm" />}
            Transfer
          </button>
        </div>
      </Modal>

      {/* Follow-up task result */}
      {taskResult !== null && (
        <Modal
          open={true}
          onClose={() => setTaskResult(null)}
          title="Follow-up Task"
          maxWidth="sm"
        >
          {taskResult.taskId !== null ? (
            <p className="text-sm text-gray-700">
              Task created successfully (ID:{' '}
              <span className="font-mono font-medium">{taskResult.taskId}</span>).
            </p>
          ) : (
            <div className="text-sm text-gray-700">
              <p className="mb-3">
                Project Tasks module is not available. Use email to create a follow-up:
              </p>
              <a
                href={taskResult.mailtoUrl}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 transition-colors text-sm font-medium"
              >
                Open Email Client
              </a>
            </div>
          )}
          <div className="flex justify-end mt-4">
            <button
              onClick={() => setTaskResult(null)}
              className="px-4 py-2 text-sm text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              Close
            </button>
          </div>
        </Modal>
      )}

    </div>
  );
}
