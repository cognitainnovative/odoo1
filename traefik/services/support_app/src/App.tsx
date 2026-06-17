import { useEffect } from 'react';
import { useAuthStore } from './store/authStore';
import { LoginPage } from './pages/LoginPage';
import { WorkspacePage } from './pages/WorkspacePage';
import { Spinner } from './components/common/Spinner';

export default function App() {
  const { session, loading, initialize } = useAuthStore();

  useEffect(() => {
    void initialize();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!session) {
    return <LoginPage />;
  }

  return <WorkspacePage />;
}
