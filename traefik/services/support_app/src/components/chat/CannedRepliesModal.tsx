import { useState, useEffect } from 'react';
import { Plus, Pencil, Trash2, Check, X } from 'lucide-react';
import { Modal } from '../common/Modal';
import {
  loadCannedReplies,
  addCannedReply,
  updateCannedReply,
  deleteCannedReply,
} from '../../utils/cannedReplies';
import type { CannedReply } from '../../types';

interface CannedRepliesModalProps {
  open: boolean;
  onClose: () => void;
  onSelect: (content: string) => void;
}

interface EditingState {
  id: string | null; // null = new entry
  shortcut: string;
  content: string;
}

export function CannedRepliesModal({
  open,
  onClose,
  onSelect,
}: CannedRepliesModalProps) {
  const [replies, setReplies] = useState<CannedReply[]>([]);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<EditingState | null>(null);

  useEffect(() => {
    if (open) setReplies(loadCannedReplies());
  }, [open]);

  const filtered = replies.filter(
    (r) =>
      r.shortcut.toLowerCase().includes(search.toLowerCase()) ||
      r.content.toLowerCase().includes(search.toLowerCase()),
  );

  function startNew() {
    setEditing({ id: null, shortcut: '', content: '' });
  }

  function startEdit(reply: CannedReply) {
    setEditing({ id: reply.id, shortcut: reply.shortcut, content: reply.content });
  }

  function cancelEdit() {
    setEditing(null);
  }

  function saveEdit() {
    if (!editing) return;
    if (!editing.content.trim()) return;

    let updated: CannedReply[];
    if (editing.id === null) {
      updated = addCannedReply({
        shortcut: editing.shortcut.trim(),
        content: editing.content.trim(),
      });
    } else {
      updated = updateCannedReply(editing.id, {
        shortcut: editing.shortcut.trim(),
        content: editing.content.trim(),
      });
    }
    setReplies(updated);
    setEditing(null);
  }

  function handleDelete(id: string) {
    const updated = deleteCannedReply(id);
    setReplies(updated);
  }

  return (
    <Modal open={open} onClose={onClose} title="Canned Replies" maxWidth="lg">
      {/* Search + add */}
      <div className="flex gap-2 mb-4">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search replies…"
          className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <button
          onClick={startNew}
          className="flex items-center gap-1.5 px-3 py-2 bg-brand-600 text-white text-sm font-medium rounded-lg hover:bg-brand-700 transition-colors"
        >
          <Plus size={14} />
          New
        </button>
      </div>

      {/* Edit form */}
      {editing !== null && (
        <div className="mb-4 p-3 bg-gray-50 border border-gray-200 rounded-lg space-y-2">
          <input
            type="text"
            value={editing.shortcut}
            onChange={(e) => setEditing({ ...editing, shortcut: e.target.value })}
            placeholder="Shortcut (e.g. /hello)"
            className="w-full px-3 py-1.5 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          <textarea
            value={editing.content}
            onChange={(e) => setEditing({ ...editing, content: e.target.value })}
            placeholder="Reply content…"
            rows={3}
            className="w-full px-3 py-1.5 border border-gray-300 rounded text-sm resize-none focus:outline-none focus:ring-2 focus:ring-brand-500"
          />
          <div className="flex gap-2 justify-end">
            <button
              onClick={cancelEdit}
              className="flex items-center gap-1 px-3 py-1 text-sm text-gray-600 hover:bg-gray-200 rounded transition-colors"
            >
              <X size={13} /> Cancel
            </button>
            <button
              onClick={saveEdit}
              disabled={!editing.content.trim()}
              className="flex items-center gap-1 px-3 py-1 text-sm text-white bg-brand-600 hover:bg-brand-700 rounded disabled:opacity-50 transition-colors"
            >
              <Check size={13} /> Save
            </button>
          </div>
        </div>
      )}

      {/* Reply list */}
      <div className="space-y-1 max-h-72 overflow-y-auto">
        {filtered.length === 0 && (
          <p className="text-sm text-gray-400 text-center py-6">
            {search ? 'No matching replies.' : 'No canned replies yet.'}
          </p>
        )}
        {filtered.map((reply) => (
          <div
            key={reply.id}
            className="flex items-start gap-2 p-2.5 hover:bg-gray-50 rounded-lg group cursor-pointer"
            onClick={() => {
              onSelect(reply.content);
              onClose();
            }}
          >
            <div className="flex-1 min-w-0">
              {reply.shortcut && (
                <span className="text-xs font-mono text-brand-600 block mb-0.5">
                  {reply.shortcut}
                </span>
              )}
              <p className="text-sm text-gray-700 truncate">{reply.content}</p>
            </div>
            <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  startEdit(reply);
                }}
                className="p-1 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded"
                aria-label="Edit"
              >
                <Pencil size={13} />
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete(reply.id);
                }}
                className="p-1 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded"
                aria-label="Delete"
              >
                <Trash2 size={13} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </Modal>
  );
}
