import { ConversationQueue } from '../queue/ConversationQueue';

export function Sidebar() {
  return (
    <aside className="w-72 flex-shrink-0 h-full overflow-hidden flex flex-col bg-white dark:bg-gray-900">
      <div className="flex-1 overflow-hidden">
        <ConversationQueue />
      </div>
    </aside>
  );
}
