import { useEffect, useState } from "react";
import { Check, Copy, KeyRound, ShieldCheck, UserPlus, X } from "lucide-react";
import {
  AccountRow, InviteRow, createInvite, createResetLink, listAccounts, revokeInvite, updateAccount,
} from "../api/client";

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : "");

function LinkBox({ title, url, expires, onClose }: { title: string; url: string; expires: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked: the link is selectable below */
    }
  };
  return (
    <div className="rounded-lg border border-emerald-700 bg-emerald-900/20 p-3 space-y-2" role="status">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-emerald-300">{title}</p>
        <button onClick={onClose} className="text-gray-400 hover:text-white" aria-label="Dismiss"><X size={16} /></button>
      </div>
      <div className="flex items-center gap-2">
        <input readOnly value={url} onFocus={(e) => e.target.select()}
          className="flex-1 min-w-0 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs font-mono text-gray-200" />
        <button onClick={copy} className="flex items-center gap-1.5 bg-gray-700 hover:bg-gray-600 px-3 py-1.5 rounded text-sm shrink-0">
          {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <p className="text-[11px] text-gray-400">
        Works once, until {when(expires)}. Send it privately. Whoever opens it needs to be able to reach this
        Budget Buddy (e.g. on your Tailscale network).
      </p>
    </div>
  );
}

export default function UsersSection() {
  const [users, setUsers] = useState<AccountRow[]>([]);
  const [invites, setInvites] = useState<InviteRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [makeAdmin, setMakeAdmin] = useState(false);
  const [link, setLink] = useState<{ title: string; url: string; expires: string } | null>(null);

  const load = () =>
    listAccounts()
      .then((r) => {
        setUsers(r.users);
        setInvites(r.invites);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load users"));

  useEffect(() => {
    load();
  }, []);

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    }
  };

  const invite = () =>
    run(async () => {
      const r = await createInvite(note, makeAdmin);
      setLink({
        title: `Invite link${note.trim() ? ` for ${note.trim()}` : ""}${makeAdmin ? " (admin)" : ""}. Copy it and send it to them.`,
        url: window.location.origin + r.path,
        expires: r.expires_at,
      });
      setNote("");
      setMakeAdmin(false);
    });

  const reset = (u: AccountRow) =>
    run(async () => {
      const r = await createResetLink(u.id);
      setLink({ title: `Password reset link for ${r.username}. Copy it and send it to them.`, url: window.location.origin + r.path, expires: r.expires_at });
    });

  return (
    <section className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Users</h3>
        <p className="text-sm text-gray-400">
          Everyone you invite sees and edits the same books. Admins can also manage users.
        </p>
      </div>

      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 space-y-4">
        <div className="flex items-center gap-2 flex-wrap">
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Who is it for? (optional)"
            className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm w-64" />
          <label className="flex items-center gap-2 text-sm text-gray-300">
            <input type="checkbox" checked={makeAdmin} onChange={(e) => setMakeAdmin(e.target.checked)} /> Make admin
          </label>
          <button onClick={invite} className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-2 rounded-lg text-sm">
            <UserPlus size={15} /> Create invite link
          </button>
        </div>

        {link && <LinkBox {...link} onClose={() => setLink(null)} />}
        {error && <p className="text-sm text-red-400">{error}</p>}

        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-400 border-b border-gray-700">
              <th className="py-2 pr-3 font-medium">User</th>
              <th className="py-2 pr-3 font-medium">Role</th>
              <th className="py-2 pr-3 font-medium">Status</th>
              <th className="py-2 font-medium text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-gray-700/50">
                <td className="py-2 pr-3">{u.username}{u.is_you && <span className="text-gray-500"> (you)</span>}</td>
                <td className="py-2 pr-3">
                  {u.is_admin ? (
                    <span className="inline-flex items-center gap-1 text-emerald-400"><ShieldCheck size={14} /> Admin</span>
                  ) : (
                    <span className="text-gray-400">Member</span>
                  )}
                </td>
                <td className="py-2 pr-3">{u.is_active ? <span className="text-gray-300">Active</span> : <span className="text-amber-400">Deactivated</span>}</td>
                <td className="py-2 text-right space-x-2 whitespace-nowrap">
                  {u.is_active && (
                    <button onClick={() => reset(u)} title="Create a one-time link to set a new password"
                      className="inline-flex items-center gap-1 text-xs text-gray-300 hover:text-white">
                      <KeyRound size={13} /> Reset link
                    </button>
                  )}
                  {!u.is_you && (
                    <>
                      <button onClick={() => run(() => updateAccount(u.id, { is_admin: !u.is_admin }))}
                        className="text-xs text-gray-300 hover:text-white">
                        {u.is_admin ? "Remove admin" : "Make admin"}
                      </button>
                      <button
                        onClick={() => {
                          if (u.is_active && !window.confirm(`Deactivate ${u.username}? They'll be signed out and can't sign in.`)) return;
                          run(() => updateAccount(u.id, { is_active: !u.is_active }));
                        }}
                        className={`text-xs ${u.is_active ? "text-red-400 hover:text-red-300" : "text-emerald-400 hover:text-emerald-300"}`}
                      >
                        {u.is_active ? "Deactivate" : "Reactivate"}
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {invites.length > 0 && (
          <div>
            <h4 className="text-xs uppercase tracking-wide text-gray-400 mb-1">Pending invites</h4>
            <ul className="text-sm divide-y divide-gray-700/50">
              {invites.map((i) => (
                <li key={i.id} className="flex items-center justify-between py-1.5">
                  <span>
                    {i.note || "Unnamed invite"}{i.make_admin && <span className="text-emerald-400"> · admin</span>}
                    <span className="text-gray-500 text-xs"> · expires {when(i.expires_at)}</span>
                  </span>
                  <button onClick={() => run(() => revokeInvite(i.id))} className="text-xs text-red-400 hover:text-red-300">Revoke</button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}
