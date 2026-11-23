import { useState, useEffect, FormEvent } from "react";
import { authStatus, setup, login, Me } from "../api/client";

interface Props {
  onLogin: (user: Me) => void;
}

export default function LoginPage({ onLogin }: Props) {
  const [isSetup, setIsSetup] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [showForgot, setShowForgot] = useState(false);

  useEffect(() => {
    authStatus().then((s) => {
      setIsSetup(s.setup_required);
      setLoading(false);
    });
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const fn = isSetup ? setup : login;
      const user = await fn(username, password) as Me;
      onLogin(user);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  };

  if (loading) return null;

  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center">
      <div className="bg-gray-800 rounded-xl p-8 w-full max-w-sm shadow-xl border border-gray-700">
        <div className="flex items-center justify-center gap-2 mb-2">
          <img src="/favicon.svg" alt="" className="w-9 h-9" />
          <h1 className="text-2xl font-bold text-emerald-400">Budget Buddy</h1>
        </div>
        <p className="text-gray-400 text-center text-sm mb-6">
          {isSetup ? "Create your admin account" : "Sign in to continue"}
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="text"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2.5 text-gray-100 placeholder-gray-500 focus:outline-none focus:border-emerald-500"
            required
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2.5 text-gray-100 placeholder-gray-500 focus:outline-none focus:border-emerald-500"
            required
          />
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button
            type="submit"
            className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-medium py-2.5 rounded-lg transition-colors"
          >
            {isSetup ? "Create Account" : "Sign In"}
          </button>
        </form>
        {!isSetup && (
          <div className="mt-4 text-center">
            <button onClick={() => setShowForgot((v) => !v)} className="text-xs text-gray-400 hover:text-gray-200">
              Forgot your password?
            </button>
            {showForgot && (
              <div className="mt-3 text-left text-xs text-gray-300 bg-gray-900/60 border border-gray-700 rounded-lg p-3 space-y-2">
                <p>Budget Buddy doesn't send email, so a reset happens one of two ways:</p>
                <p>
                  <span className="font-medium text-white">Ask an admin</span> to open Settings → Users and send you a
                  reset link.
                </p>
                <p>
                  <span className="font-medium text-white">On the computer running Budget Buddy</span>, open Terminal
                  in the budget-buddy folder and run:
                </p>
                <code className="block bg-black/40 rounded px-2 py-1.5 text-[11px] text-emerald-300 break-all">
                  ./.venv/bin/python scripts/reset_password.py YOUR_USERNAME
                </code>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
