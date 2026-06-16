import React, { useState, useEffect, useRef, useCallback } from 'react';

// --- [설정 및 상수] ---
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:5000/api";

const ACTIONS = [
  { id: 'SEASONING', title: '🧂 시즈닝 공정', desc: '고기에 소금과 후추를 도포합니다.' },
  { id: 'TENDERIZING', title: '🥩 연육 공정', desc: '고기를 롤링하여 부드럽게 만듭니다.' },
  { id: 'FRYING', title: '🍤 튀김 공정', desc: '거름망을 이용해 고기를 튀깁니다.' },
  { id: 'SAUCING', title: '🍯 소스 공정', desc: '튀겨진 돈까스에 소스를 도포합니다.' }
];

const STATE_LABELS = {
  IDLE: '대기 중',
  TASK_RUNNING: '작업 진행 중',
  STOP_REQUESTED: '정지 요청 처리 중',
  STOPPED: '시스템 정지됨',
  RECOVERY_RUNNING: '안전 복구 중',
  RECOVERY_DONE: '복구 완료',
  READY_TO_RETRY: '작업 선택 대기',
  ERROR: '시스템 오류',
  UNKNOWN: '연결 확인 중'
};

const STATE_BADGE_CLASS = {
  IDLE: 'bg-slate-700 text-slate-200',
  TASK_RUNNING: 'bg-blue-600 text-white animate-pulse',
  STOP_REQUESTED: 'bg-orange-600 text-white animate-pulse',
  STOPPED: 'bg-red-600 text-white',
  RECOVERY_RUNNING: 'bg-purple-600 text-white animate-pulse',
  RECOVERY_DONE: 'bg-green-700 text-white',
  READY_TO_RETRY: 'bg-green-600 text-white shadow-[0_0_15px_rgba(22,163,74,0.5)]',
  ERROR: 'bg-red-700 text-white',
  UNKNOWN: 'bg-slate-700 text-slate-300'
};

const normalizeSystemState = (data) => {
  if (!data) return { state: 'UNKNOWN', current_task: null, stopped_task: null, robot_busy: false, last_error: '', message: '' };
  return {
    state: data.state || 'UNKNOWN',
    current_task: data.current_task ?? null,
    stopped_task: data.stopped_task ?? null,
    robot_busy: data.robot_busy === 'true' || data.robot_busy === true,
    last_error: data.last_error || '',
    message: data.message || data.raw_message || ''
  };
};

const Dashboard = ({ user, onLogout, onShowHistory }) => {
  const [sessionId, setSessionId] = useState(null);
  const [logs, setLogs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [initError, setInitError] = useState(null);
  const [isCommandSending, setIsCommandSending] = useState(false);
  const [systemState, setSystemState] = useState(normalizeSystemState(null));

  const sessionIdRef = useRef(null);
  const currentActionIdRef = useRef(null);
  const activeRobotTaskRef = useRef(null);
  const isInitialized = useRef(false);
  
  // [추가됨] 이전 로봇 상태와 공정명을 기억하기 위한 Ref
  const prevStateRef = useRef('UNKNOWN');
  const prevTaskRef = useRef(null);

  useEffect(() => { sessionIdRef.current = sessionId; }, [sessionId]);

  const addLog = useCallback((msg, type = 'INFO', actionId = null) => {
    const time = new Date().toLocaleTimeString();
    setLogs(prev => [{ time, msg, type }, ...prev].slice(0, 10));
    const aid = actionId ?? currentActionIdRef.current;
    if (!aid) return;
    fetch(`${API_BASE_URL}/log`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action_id: aid, log_level: type.toLowerCase(), message: msg }),
      credentials: 'include'
    }).catch(e => console.error('로그 전송 실패:', e));
  }, []);

  const fetchSystemState = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/system/state`, { credentials: 'include' });
      const data = await res.json();
      const normalized = normalizeSystemState(data);
      setSystemState(normalized);
    } catch (e) {
      setSystemState(normalizeSystemState(null));
    }
  }, []);

  const initSession = useCallback(async () => {
    setIsLoading(true); setInitError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/session/start`, { method: 'POST', credentials: 'include' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSessionId(data.session_id);
      addLog(`✅ 시스템 온라인 (세션 ID: ${data.session_id})`, 'INFO');
      await fetchSystemState();
    } catch (e) {
      setInitError('서버 연결 실패. 백엔드를 확인하세요.');
    } finally {
      setIsLoading(false);
    }
  }, [addLog, fetchSystemState]);

  useEffect(() => {
    if (!isInitialized.current) { initSession(); isInitialized.current = true; }
  }, [initSession]);

  useEffect(() => {
    const timer = setInterval(() => fetchSystemState(), 1000);
    return () => clearInterval(timer);
  }, [fetchSystemState]);

  // 버튼/UI 상태 변경 감지
  useEffect(() => {
    if (['IDLE', 'READY_TO_RETRY', 'STOPPED', 'ERROR'].includes(systemState.state)) {
      setIsCommandSending(false);
      activeRobotTaskRef.current = null;
    }
  }, [systemState.state]);

  // [핵심 변경됨] 로봇이 작업을 끝내고 IDLE 상태로 돌아왔을 때 DB 상태 업데이트 및 세션 리셋
  useEffect(() => {
    const prev = prevStateRef.current;
    const current = systemState.state;

    // 로봇이 작업(TASK_RUNNING)을 마치고 대기(IDLE) 상태로 돌아왔을 때
    if (prev === 'TASK_RUNNING' && current === 'IDLE') {
      const finishedTask = prevTaskRef.current;
      const currentActionId = currentActionIdRef.current;

      // 1. 방금 끝난 공정(Action)을 DB에서 완료(COMPLETED) 처리 요청
      if (currentActionId) {
        fetch(`${API_BASE_URL}/action/end`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action_id: currentActionId, status: 'COMPLETED' }),
          credentials: 'include'
        }).catch(e => console.error(e));
      }

      // 2. 방금 끝난 작업이 'SAUCING'(소스) 라면 세션도 완료 처리 및 리셋
      if (finishedTask === 'SAUCING') {
        fetch(`${API_BASE_URL}/session/end`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionIdRef.current, status: "COMPLETED" }),
          credentials: 'include'
        }).catch(e => console.error(e));

        addLog('✅ 소스 도포가 완료되었습니다. 3초 후 새 세션을 준비합니다.', 'INFO');
        setTimeout(() => {
          setLogs([]);
          isInitialized.current = false;
          initSession(); // 새 세션 번호 발급 및 UI 초기화
        }, 3000);
      } else {
        // 소스가 아닌 중간 공정이 끝났을 때의 로그 표시
        if (finishedTask) {
          addLog(`✅ [${finishedTask}] 공정이 성공적으로 완료되었습니다.`, 'INFO');
        }
      }
    }

    // 다음 비교를 위해 현재 상태 저장
    prevStateRef.current = systemState.state;
    prevTaskRef.current = systemState.current_task;
  }, [systemState.state, systemState.current_task, initSession, addLog]);

  const canStartTask = () => {
    if (!sessionIdRef.current || isCommandSending) return false;
    return ['IDLE', 'READY_TO_RETRY'].includes(systemState.state);
  };

  const handleStartAction = async (actionName) => {
    if (!canStartTask()) return;
    setIsCommandSending(true);
    activeRobotTaskRef.current = actionName;

    try {
      const res = await fetch(`${API_BASE_URL}/action/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionIdRef.current, action_name: actionName }),
        credentials: 'include'
      });
      const data = await res.json();
      if (res.ok) {
        currentActionIdRef.current = data.action_id;
        addLog(`▶️ [${actionName}] 공정 전송 완료`, 'INFO', data.action_id);
      } else {
        addLog(`🚨 [${actionName}] 시작 거부됨: ${data.message}`, 'ERROR');
        setIsCommandSending(false);
        activeRobotTaskRef.current = null;
      }
    } catch (e) {
      addLog(`🚨 서버 통신 실패`, 'ERROR');
      setIsCommandSending(false);
      activeRobotTaskRef.current = null;
    }
    await fetchSystemState();
  };

  const handleStop = async () => {
    if (!['TASK_RUNNING', 'STOP_REQUESTED'].includes(systemState.state)) return;
    try {
      await fetch(`${API_BASE_URL}/action/stop`, { method: 'POST', credentials: 'include' });
      addLog('🛑 STOP 요청 전송 완료', 'ERROR');
      await fetchSystemState();
    } catch (e) {}
  };

  const handleRecovery = async () => {
    if (!['STOPPED', 'ERROR', 'STOP_REQUESTED'].includes(systemState.state)) return;
    try {
      await fetch(`${API_BASE_URL}/recovery/start`, { method: 'POST', credentials: 'include' });
      addLog('🔄 RECOVERY 요청 전송 완료', 'INFO');
      await fetchSystemState();
    } catch (e) {}
  };

  const handleSessionEnd = async () => {
    if (confirm("현재 로봇 세션을 종료하고 새 세션을 시작하시겠습니까?")) {
      await fetch(`${API_BASE_URL}/session/end`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionIdRef.current, status: "COMPLETED" }),
        credentials: 'include'
      });
      setLogs([]); isInitialized.current = false; initSession();
    }
  };

  if (isLoading) return <div className="min-h-screen bg-slate-950 flex items-center justify-center text-blue-400 font-bold">시스템 초기화 중...</div>;
  if (initError) return <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center text-red-400 font-bold"><p className="text-4xl mb-4">⚠️</p><p>{initError}</p></div>;

  const isStopEnabled = ['TASK_RUNNING', 'STOP_REQUESTED'].includes(systemState.state);
  const isRecoveryEnabled = ['STOPPED', 'ERROR', 'STOP_REQUESTED'].includes(systemState.state);

  return (
    <div className="p-8 bg-slate-950 min-h-screen text-slate-100 font-sans">
      <div className="max-w-7xl mx-auto flex justify-between items-center mb-8 border-b border-slate-800 pb-6">
        <div>
          <h1 className="text-2xl font-black italic text-blue-500 tracking-tighter">ROBOT OPS CENTER</h1>
          <p className="text-slate-500 text-xs font-bold uppercase tracking-widest">On-Demand Mode</p>
        </div>
        <div className="flex gap-3">
          <button onClick={onShowHistory} className="px-5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-black uppercase">History</button>
          <button onClick={handleSessionEnd} className="px-5 py-2 bg-green-900/40 hover:bg-green-800/60 text-green-400 border border-green-900 rounded-xl text-xs font-black uppercase">New Session</button>
          <button onClick={onLogout} className="px-5 py-2 bg-slate-900 hover:bg-red-900/30 text-slate-400 hover:text-red-400 rounded-xl text-xs font-black uppercase">Logout</button>
        </div>
      </div>

      <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-4 gap-8">
        <div className="lg:col-span-3 flex flex-col gap-6">
          {/* 상태 패널 */}
          <div className="bg-slate-900 border border-slate-800 p-8 rounded-3xl flex justify-between items-center shadow-xl">
            <div>
              <div className={`inline-block px-5 py-2 rounded-xl text-sm font-black ${STATE_BADGE_CLASS[systemState.state]}`}>
                {STATE_LABELS[systemState.state]}
              </div>
              <div className="mt-3 text-sm text-slate-400 font-bold">
                {systemState.state === 'IDLE' && "모든 시스템 정상. 원하는 공정을 선택하세요."}
                {systemState.state === 'READY_TO_RETRY' && "복구가 완료되었습니다. 원하는 공정을 자유롭게 선택하세요."}
                {systemState.state === 'TASK_RUNNING' && <span className="text-blue-400">⚡ [{systemState.current_task}] 공정이 진행 중입니다...</span>}
                {['STOPPED', 'ERROR'].includes(systemState.state) && <span className="text-red-400">⚠️ 로봇이 정지되었습니다. 복구(RECOVERY)를 먼저 진행하세요.</span>}
              </div>
            </div>
            <div className="flex gap-3">
              <button onClick={handleStop} disabled={!isStopEnabled} className={`px-8 py-4 rounded-2xl text-lg font-black transition-all ${!isStopEnabled ? 'bg-slate-800 text-slate-600' : 'bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-900/30'}`}>🛑 STOP</button>
              <button onClick={handleRecovery} disabled={!isRecoveryEnabled} className={`px-8 py-4 rounded-2xl text-lg font-black transition-all ${!isRecoveryEnabled ? 'bg-slate-800 text-slate-600' : 'bg-purple-600 hover:bg-purple-500 text-white shadow-lg shadow-purple-900/30'}`}>🔄 RECOVERY</button>
            </div>
          </div>

          {/* 작업 카드 Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-grow">
            {ACTIONS.map(action => {
              const isAllowed = canStartTask();
              const isThisRunning = activeRobotTaskRef.current === action.id || systemState.current_task === action.id;
              
              return (
                <div key={action.id} className={`p-8 rounded-[2rem] border transition-all flex flex-col justify-between ${isThisRunning ? 'bg-blue-900/20 border-blue-500/50' : 'bg-slate-900 border-slate-800'}`}>
                  <div>
                    <h3 className="text-2xl font-black text-slate-200 mb-2">{action.title}</h3>
                    <p className="text-slate-500 font-bold text-sm">{action.desc}</p>
                  </div>
                  <button 
                    onClick={() => handleStartAction(action.id)} 
                    disabled={!isAllowed} 
                    className={`mt-8 py-4 rounded-2xl font-black text-lg transition-all ${isThisRunning ? 'bg-blue-600 text-white animate-pulse' : !isAllowed ? 'bg-slate-800 text-slate-600 cursor-not-allowed' : 'bg-slate-800 hover:bg-slate-700 text-blue-400 border border-slate-700 hover:border-blue-500'}`}
                  >
                    {isThisRunning ? '진행 중...' : '실행하기'}
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* 로그 패널 */}
        <div className="bg-slate-900 border border-slate-800 p-8 rounded-[2rem] shadow-xl flex flex-col">
          <h3 className="text-lg font-black mb-6 text-slate-400 uppercase flex items-center"><span className="mr-2">📋</span> System Logs</h3>
          <div className="space-y-4 flex-grow overflow-hidden font-mono text-[13px]">
            {logs.map((log, i) => (
              <div key={i} className="border-l-2 border-slate-800 pl-4 py-1">
                <div className="text-slate-600 text-[10px]">{log.time}</div>
                <div className={`text-sm ${log.type === 'ERROR' ? 'text-red-400' : 'text-slate-300'}`}>{log.msg}</div>
              </div>
            ))}
          </div>
          <div className="mt-6 pt-4 border-t border-slate-800 text-[10px] text-slate-600 font-bold uppercase">
            SESSION: {sessionId ? `#${sessionId}` : 'OFFLINE'}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;