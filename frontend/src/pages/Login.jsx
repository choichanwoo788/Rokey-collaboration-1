import React, { useState } from 'react';

const Login = ({ onLoginSuccess }) => {
  const [credentials, setCredentials] = useState({ username: '', password: '' });
  const [error, setError] = useState('');

  const handleChange = (e) => {
    setCredentials({ ...credentials, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    try {
      const res = await fetch("http://localhost:5000/api/login", {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials),
        // [핵심] 서버가 보내주는 세션 쿠키를 브라우저에 저장하도록 허용합니다.
        credentials: 'include' 
      });

      const data = await res.json();

      if (res.ok) {
        onLoginSuccess(data.username);
      } else {
        setError(data.message || "로그인에 실패했습니다.");
      }
    } catch (err) {
      setError("서버와 통신할 수 없습니다.");
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-slate-950 font-sans">
      <div className="w-full max-w-md p-8 bg-slate-900 border border-slate-800 rounded-[2rem] shadow-2xl">
        <div className="text-center mb-10">
          <h1 className="text-4xl font-black text-white mb-2 italic tracking-tighter">ROBOT OPS</h1>
          <p className="text-slate-500 font-bold tracking-widest uppercase text-[10px]">Command Center Access</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-2">
            <label className="block text-slate-500 text-xs font-black uppercase ml-1">Username</label>
            <input
              type="text" name="username" required
              onChange={handleChange}
              className="w-full bg-slate-800 border border-slate-700 text-white px-5 py-4 rounded-2xl focus:outline-none focus:border-blue-500 transition-all placeholder:text-slate-600"
              placeholder="Operator ID"
            />
          </div>

          <div className="space-y-2">
            <label className="block text-slate-500 text-xs font-black uppercase ml-1">Password</label>
            <input
              type="password" name="password" required
              onChange={handleChange}
              className="w-full bg-slate-800 border border-slate-700 text-white px-5 py-4 rounded-2xl focus:outline-none focus:border-blue-500 transition-all placeholder:text-slate-600"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <div className="bg-red-500/10 border border-red-500/50 p-4 rounded-xl">
              <p className="text-red-400 text-xs font-bold text-center">{error}</p>
            </div>
          )}

          <button
            type="submit"
            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-black py-5 rounded-2xl shadow-lg shadow-blue-900/40 transition-all active:scale-95 uppercase tracking-widest text-sm"
          >
            Authenticate
          </button>
        </form>
      </div>
    </div>
  );
};

export default Login;