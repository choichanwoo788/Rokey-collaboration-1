import React, { useState } from 'react';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import LogHistory from './components/LogHistory';

function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState('dashboard');

  const handleLoginSuccess = (username) => {
    setUser(username);
    setView('dashboard');
  };

  const handleLogout = () => {
    setUser(null);
    setView('dashboard');
  };

  // 1. 로그인 전이면 로그인 페이지 노출
  if (!user) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  // 2. 로그인 후: Dashboard는 언마운트하지 않고 CSS로 숨김
  //    → 다른 페이지로 이동해도 공정 interval/상태가 유지됨
  return (
    <div className="App">
      {/* Dashboard: 항상 마운트 상태 유지, history일 때만 숨김 */}
      <div style={{ display: view === 'dashboard' ? 'block' : 'none' }}>
        <Dashboard
          user={user}
          onLogout={handleLogout}
          onShowHistory={() => setView('history')}
        />
      </div>

      {/* LogHistory: history일 때만 마운트 */}
      {view === 'history' && (
        <LogHistory onBack={() => setView('dashboard')} />
      )}
    </div>
  );
}

export default App;
