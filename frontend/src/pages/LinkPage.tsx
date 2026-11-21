import { FormEvent, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { LinkInfo, Me, getLinkInfo, redeemLink } from "../api/client";

interface Props {
  onDone: (user: Me) => void;
}

/** Opened from an invite (/invite/:token) or reset (/reset/:token) link. */
export default function LinkPage({ onDone }: Props) {
  const { token = "" } = useParams();
  const [info, setInfo] = useState<LinkInfo | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getLinkInfo(token).then(setInfo).catch(() => setInfo({ valid: false }));
  }, [token]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("Passwords don't match");
      return;
    }
    setBusy(true);
    try {
      const user = await redeemLink(token, password, info?.purpose === "invite" ? username : undefined);
      window.history.replaceState(null, "", "/");
      onDone(user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  const shell = (children: React.ReactNode) => (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
      <div className="bg-gray-800 rounded-xl p-8 w-full max-w-sm shadow-xl border border-gray-700">
        <div className="flex items-center justify-center gap-2 mb-4">
          <img src="/favicon.svg" alt="" className="w-9 h-9" />
          <h1 className="text-2xl font-bold text-emerald-400">Budget Buddy</h1>
        </div>
        {children}
      </div>
    </div>
  );

  if (info === null) return shell(<p className="text-center text-gray-400 text-sm">Checking your link…</p>);

  if (!info.valid) {
    return shell(
      <div className="text-center space-y-3">
        <p className="text-gray-200">This link has expired or was already used.</p>
        <p className="text-sm text-gray-400">Ask whoever sent it for a new one.</p>
        <a href="/" className="inline-block text-sm text-emerald-400 hover:underline">Go to sign in</a>
      </div>,
    );
  }

  const isInvite = info.purpose === "invite";
  return shell(
    <form onSubmit={submit} className="space-y-4">
      <p className="text-gray-300 text-center text-sm">
        {isInvite
          ? "You've been invited to Budget Buddy. Pick a username and password."
          : `Set a new password for ${info.username}.`}
      </p>
      {isInvite && (
        <input
          type="text"
          placeholder="Username"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2.5 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          required
        />
      )}
      <input
        type="password"
        placeholder="New password (8+ characters)"
        autoComplete="new-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2.5 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        required
        minLength={8}
      />
      <input
        type="password"
        placeholder="Type it again"
        autoComplete="new-password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2.5 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        required
      />
      {error && <p className="text-red-400 text-sm">{error}</p>}
      <button
        type="submit"
        disabled={busy}
        className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium py-2.5 rounded-lg transition-colors"
      >
        {busy ? "Saving…" : isInvite ? "Create my account" : "Set password and sign in"}
      </button>
    </form>,
  );
}
