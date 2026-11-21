import { FormEvent, useState } from "react";
import { CheckCircle2, KeyRound } from "lucide-react";
import { Me, changePassword } from "../api/client";

export default function AccountSection({ me }: { me: Me }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setDone(false);
    if (next !== confirm) {
      setError("New passwords don't match");
      return;
    }
    setBusy(true);
    try {
      await changePassword(current, next);
      setDone(true);
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't change password");
    } finally {
      setBusy(false);
    }
  };

  const field = "bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm w-full";
  return (
    <section className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Your account</h3>
        <p className="text-sm text-gray-400">
          Signed in as <span className="text-gray-200 font-medium">{me.username}</span>
          {me.is_admin ? " (admin)" : ""}.
        </p>
      </div>
      <form onSubmit={submit} className="bg-gray-800 rounded-xl border border-gray-700 p-4 space-y-3 max-w-xl">
        <div className="flex items-center gap-2 text-sm font-medium">
          <KeyRound size={16} className="text-emerald-400" /> Change password
        </div>
        <input type="password" autoComplete="current-password" placeholder="Current password" value={current}
          onChange={(e) => setCurrent(e.target.value)} className={field} required />
        <div className="grid sm:grid-cols-2 gap-3">
          <input type="password" autoComplete="new-password" placeholder="New password (8+ characters)" value={next}
            onChange={(e) => setNext(e.target.value)} className={field} required minLength={8} />
          <input type="password" autoComplete="new-password" placeholder="Type it again" value={confirm}
            onChange={(e) => setConfirm(e.target.value)} className={field} required />
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <button type="submit" disabled={busy}
            className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm">
            {busy ? "Saving…" : "Change password"}
          </button>
          {done && (
            <span className="flex items-center gap-1.5 text-sm text-emerald-400">
              <CheckCircle2 size={15} /> Password changed. Other devices have been signed out.
            </span>
          )}
          {error && <span className="text-sm text-red-400">{error}</span>}
        </div>
      </form>
    </section>
  );
}
