import { useState, useEffect, FormEvent } from "react";
import { authStatus, setup, login } from "../api/client";

interface Props {
  onLogin: (user: { id: number; username: string }) => void;
}

export default function LoginPage({ onLogin }: Props) {
  const [isSetup, setIsSetup] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

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
      const user = await fn(username, password) as { id: number; username: string };
      onLogin(user);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  };

  if (loading) return null;

  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center">
      <div className="bg-gray-800 rounded-xl p-8 w-full max-w-sm shadow-xl border border-gray-700">
        <h1 className="text-2xl font-bold text-emerald-400 text-center mb-2">Budget Buddy</h1>
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
      </div>
    </div>
  );
}
