import React, { useState, useEffect } from 'react';

// --- [설정 및 상수] ---
// Dashboard와 동일한 API 주소 체계를 사용
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:5000/api";

// ==========================================================
// 상태 표시 매핑
// ==========================================================

const STATUS_MAP = {
  // 기존 상태
  'RUNNING': '⏳ 진행중',
  'COMPLETED': '✅ 완료됨',
  'ERROR': '🚨 오류',

  // STOP / RECOVERY 구조 추가 상태
  'STOP_REQUESTED': '🛑 정지 요청',
  'STOPPED': '⏹️ 정지됨',
  'RECOVERY_RUNNING': '🔄 복구 중',
  'RECOVERY_DONE': '✅ 복구 완료',
  'READY_TO_RETRY': '↩️ 재시작 대기',
  'FAILED': '❌ 실패',
  'IDLE': '🟦 대기',
  'TASK_RUNNING': '🤖 로봇 작업 중'
};

const TASK_MAP = {
  'SYSTEM_INIT': '🖥️ 시스템 대기',
  'SEASONING': '🧂 밑간 (시즈닝)',
  'TENDERIZING': '🥩 연육 (텐더라이징)',
  'BATTER_WAIT': '🥣 반죽 대기',
  'FRYING': '🍤 튀김 공정',
  'SAUCING': '🍯 소스 도포',

  // 예외/복구성 task가 DB에 기록될 경우 대비
  'STOP': '🛑 정지 요청',
  'RECOVERY': '🔄 복구 작업',
  'RETRY': '↩️ 재시작'
};

const HEADER_MAP = {
  'Job_ID': '작업 번호',
  'Start_Time': '시작 시간',
  'End_Time': '종료 시간',
  'Final_Status': '최종 상태',
  'Task_Name': '세부 공정명',
  'Status': '진행 상태',
  'Log_Time': '기록 시간',
  'Level': '로그 레벨',
  'Message': '상세 메시지'
};

const LOG_LEVEL_MAP = {
  'INFO': 'INFO',
  'WARN': 'WARN',
  'WARNING': 'WARN',
  'ERROR': 'ERROR',
  'DEBUG': 'DEBUG'
};

// ==========================================================
// 유틸 함수
// ==========================================================

const formatStatus = (status) => {
  if (!status) return '-';
  return STATUS_MAP[status] || status;
};

const formatTaskName = (taskName) => {
  if (!taskName) return '-';
  return TASK_MAP[taskName] || taskName;
};

const normalizeLogLevel = (level) => {
  const upper = (level || 'INFO').toUpperCase();
  return LOG_LEVEL_MAP[upper] || upper;
};

const getCellColor = (header, value) => {
  if (header === 'Job_ID') {
    return 'text-slate-100 font-black text-center';
  }

  if (header === 'Level') {
    if (value === 'ERROR') return 'text-red-400 font-black';
    if (value === 'WARN') return 'text-orange-400 font-black';
    if (value === 'DEBUG') return 'text-slate-500 font-bold';
    return 'text-blue-400 font-black';
  }

  if (typeof value !== 'string') {
    return 'text-slate-300';
  }

  if (
    value.includes('완료됨') ||
    value.includes('복구 완료')
  ) {
    return 'text-green-400 font-black';
  }

  if (
    value.includes('진행중') ||
    value.includes('로봇 작업 중') ||
    value.includes('복구 중')
  ) {
    return 'text-blue-400 font-black';
  }

  if (
    value.includes('정지 요청') ||
    value.includes('재시작 대기')
  ) {
    return 'text-orange-400 font-black';
  }

  if (
    value.includes('정지됨') ||
    value.includes('오류') ||
    value.includes('실패')
  ) {
    return 'text-red-400 font-black';
  }

  return 'text-slate-300';
};

const LogHistory = ({ onBack }) => {
  const [activeSheet, setActiveSheet] = useState('jobs');
  const [tableData, setTableData] = useState({ jobs: [], tasks: [], logs: [] });
  const [selectedJobId, setSelectedJobId] = useState('ALL');
  const [jobIds, setJobIds] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  // ==========================================================
  // History 데이터 로드
  // ==========================================================

  useEffect(() => {
    const loadHistory = async () => {
      setIsLoading(true);
      setLoadError(null);

      try {
        const res = await fetch(`${API_BASE_URL}/history`, {
          credentials: 'include'
        });

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }

        const data = await res.json();

        if (!Array.isArray(data)) {
          throw new Error('history 응답이 배열 형식이 아닙니다.');
        }

        // Job ID 오름차순 정렬
        const sortedData = [...data].sort((a, b) => a.job_id - b.job_id);

        // 같은 job_id가 중복으로 올 경우 1개만 사용
        const uniqueHistory = sortedData.filter(
          (v, i, a) => a.findIndex(t => t.job_id === v.job_id) === i
        );

        const flatJobs = [];
        const flatTasks = [];
        const flatLogs = [];
        const ids = [];

        uniqueHistory.forEach((job) => {
          ids.push(job.job_id);

          flatJobs.push({
            Job_ID: job.job_id,
            Start_Time: job.start_time || '-',
            End_Time: job.end_time || '-',
            Final_Status: formatStatus(job.final_status)
          });

          const tasks = Array.isArray(job.tasks) ? job.tasks : [];

          tasks.forEach((task) => {
            flatTasks.push({
              Job_ID: job.job_id,
              Task_Name: formatTaskName(task.task_name),
              Status: formatStatus(task.status)
            });

            const logs = Array.isArray(task.logs) ? task.logs : [];

            logs.forEach((log) => {
              flatLogs.push({
                Job_ID: job.job_id,
                Task_Name: formatTaskName(task.task_name),
                Log_Time: log.time || '-',
                Level: normalizeLogLevel(log.level),
                Message: log.msg || '-'
              });
            });
          });
        });

        // 최신 데이터가 위로 오도록 reverse
        setTableData({
          jobs: [...flatJobs].reverse(),
          tasks: [...flatTasks].reverse(),
          logs: [...flatLogs].reverse()
        });

        setJobIds([...ids].reverse());
      } catch (err) {
        console.error('데이터 로드 실패:', err);
        setLoadError('작업 이력 데이터를 불러오지 못했습니다. app.py 또는 /api/history 상태를 확인하세요.');
      } finally {
        setIsLoading(false);
      }
    };

    loadHistory();
  }, []);

  // ==========================================================
  // 테이블 렌더링
  // ==========================================================

  const renderTable = (dataArray) => {
    const filteredData = selectedJobId === 'ALL'
      ? dataArray
      : dataArray.filter(row => row.Job_ID.toString() === selectedJobId);

    if (filteredData.length === 0) {
      return (
        <div className="p-8 text-slate-500 font-bold text-center">
          데이터가 없습니다.
        </div>
      );
    }

    const headers = Object.keys(filteredData[0]);

    return (
      <div className="overflow-auto max-h-[70vh] border border-slate-700 bg-slate-900">
        <table className="w-full text-left text-sm border-collapse whitespace-nowrap">
          <thead className="bg-slate-800 sticky top-0 z-10 shadow-md">
            <tr>
              <th className="border border-slate-700 px-4 py-3 text-slate-400 font-black bg-slate-800 w-12 text-center">
                #
              </th>
              {headers.map(header => (
                <th
                  key={header}
                  className="border border-slate-700 px-5 py-3 text-blue-400 font-black tracking-wider uppercase"
                >
                  {HEADER_MAP[header] || header}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {filteredData.map((row, idx) => (
              <tr
                key={idx}
                className="hover:bg-slate-800/80 transition-colors"
              >
                <td className="border border-slate-700 px-4 py-2 text-slate-500 font-mono text-center bg-slate-900/50">
                  {filteredData.length - idx}
                </td>

                {headers.map(header => {
                  const cellValue = row[header];
                  const cellColor = getCellColor(header, cellValue);

                  return (
                    <td
                      key={header}
                      className={`border border-slate-700 px-5 py-2 ${cellColor}`}
                    >
                      {cellValue}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  // ==========================================================
  // 렌더링
  // ==========================================================

  if (isLoading) {
    return (
      <div className="p-6 bg-slate-950 min-h-screen text-slate-100 flex items-center justify-center font-sans">
        <div className="text-center">
          <div className="w-14 h-14 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-6"></div>
          <p className="text-slate-400 font-bold animate-pulse">
            작업 이력 데이터를 불러오는 중...
          </p>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="p-6 bg-slate-950 min-h-screen text-slate-100 flex items-center justify-center font-sans">
        <div className="text-center">
          <p className="text-red-400 text-5xl mb-6">⚠️</p>
          <p className="text-red-400 font-bold mb-6">{loadError}</p>
          <button
            onClick={onBack}
            className="px-6 py-2 bg-slate-800 text-slate-200 border border-slate-700 rounded-lg font-black hover:bg-slate-700 transition-all text-sm"
          >
            대시보드로 돌아가기
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 bg-slate-950 min-h-screen text-slate-100 flex flex-col font-sans">
      <div className="flex justify-between items-end mb-6 shrink-0">
        <div>
          <span className="text-emerald-500 font-black tracking-widest text-xs uppercase">
            Robot Analytics
          </span>
          <h2 className="text-3xl font-black tracking-tight">
            작업 이력 데이터베이스
          </h2>
          <p className="text-slate-500 text-xs font-bold mt-2">
            STOP / RECOVERY 상태까지 포함하여 공정 이력을 표시합니다.
          </p>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 bg-slate-900 border border-slate-700 px-3 py-1.5 rounded-lg">
            <span className="text-slate-400 text-xs font-black uppercase tracking-widest">
              Filter:
            </span>
            <select
              value={selectedJobId}
              onChange={(e) => setSelectedJobId(e.target.value)}
              className="bg-transparent text-white text-sm font-bold focus:outline-none cursor-pointer"
            >
              <option value="ALL">전체 보기 (All Jobs)</option>
              {jobIds.map(id => (
                <option key={id} value={id}>
                  Job #{id}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={onBack}
            className="px-6 py-2 bg-slate-800 text-slate-200 border border-slate-700 rounded-lg font-black hover:bg-slate-700 transition-all text-sm"
          >
            닫기
          </button>
        </div>
      </div>

      <div className="flex-grow bg-slate-900 border border-slate-800 flex flex-col overflow-hidden shadow-2xl rounded-xl">
        <div className="flex-grow overflow-hidden bg-slate-950">
          {activeSheet === 'jobs' && renderTable(tableData.jobs)}
          {activeSheet === 'tasks' && renderTable(tableData.tasks)}
          {activeSheet === 'logs' && renderTable(tableData.logs)}
        </div>

        <div className="flex bg-slate-800 border-t border-slate-700 text-sm font-black shrink-0">
          <button
            onClick={() => setActiveSheet('jobs')}
            className={`px-8 py-4 border-r border-slate-700 ${
              activeSheet === 'jobs'
                ? 'bg-slate-900 text-blue-400 border-t-2 border-t-blue-500'
                : 'text-slate-400'
            }`}
          >
            📋 작업 요약 [{tableData.jobs.length}]
          </button>

          <button
            onClick={() => setActiveSheet('tasks')}
            className={`px-8 py-4 border-r border-slate-700 ${
              activeSheet === 'tasks'
                ? 'bg-slate-900 text-blue-400 border-t-2 border-t-blue-500'
                : 'text-slate-400'
            }`}
          >
            ⚙️ 세부 공정 목록 [{tableData.tasks.length}]
          </button>

          <button
            onClick={() => setActiveSheet('logs')}
            className={`px-8 py-4 border-r border-slate-700 ${
              activeSheet === 'logs'
                ? 'bg-slate-900 text-blue-400 border-t-2 border-t-blue-500'
                : 'text-slate-400'
            }`}
          >
            📡 로봇 통신 로그 [{tableData.logs.length}]
          </button>
        </div>
      </div>
    </div>
  );
};

export default LogHistory;