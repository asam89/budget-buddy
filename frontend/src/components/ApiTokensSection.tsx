import { useEffect, useState } from "react";
import { Check, Copy, KeyRound, X } from "lucide-react";
import { ApiTokenRow, createApiToken, listApiTokens, revokeApiToken } from "../api/client";

const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : "never");

/** Tokens that let outside tools (Muse, an iPhone Shortcut) send spending in. */
export default function ApiTokensSection() {
  const [rows, setRows] = useState<ApiTokenRow[]>([]);
  const [name, setName] = useState("");
  const [fresh, setFresh] = useState<{ name: string; token: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => listApiTokens().then(setRows).catch((e) => setError(e instanceof Error ? e.message : "Couldn't load tokens"));
  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    setError(null);
    try {
      const t = await createApiToken(name);
      setFresh({ name: t.name, token: t.token });
      setName("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't create token");
    }
  };

  const copy = async () => {
    if (!fresh) return;
    try {
      await navigator.clipboard.writeText(fresh.token);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* select the field instead */
    }
  };

  const endpoint = `${window.location.origin}/api/ingest/spending`;
  const active = rows.filter((r) => !r.revoked);

  return (
    <section className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Connected tools (API tokens)</h3>
        <p className="text-sm text-gray-400">
          Let tools like Muse or an iPhone Shortcut send spending in. Everything they send waits on the
          Review page for your approval.
        </p>
      </div>
      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 space-y-4">
        <div className="flex items-center gap-2 flex-wrap">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, e.g. Muse or iPhone"
            className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm w-64" />
          <button onClick={create} disabled={!name.trim()}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white px-3 py-2 rounded-lg text-sm">
            <KeyRound size={15} /> Create token
          </button>
        </div>

        {fresh && (
          <div className="rounded-lg border border-emerald-700 bg-emerald-900/20 p-3 space-y-2" role="status">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm text-emerald-300">
                Token for {fresh.name}. Copy it now: it won't be shown again.
              </p>
              <button onClick={() => setFresh(null)} className="text-gray-400 hover:text-white" aria-label="Dismiss"><X size={16} /></button>
            </div>
            <div className="flex items-center gap-2">
              <input readOnly value={fresh.token} onFocus={(e) => e.target.select()}
                className="flex-1 min-w-0 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs font-mono" />
              <button onClick={copy} className="flex items-center gap-1.5 bg-gray-700 hover:bg-gray-600 px-3 py-1.5 rounded text-sm">
                {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Copied" : "Copy"}
              </button>
            </div>
          </div>
        )}
        {error && <p className="text-sm text-red-400">{error}</p>}

        {rows.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-400 border-b border-gray-700">
                <th className="py-2 pr-3 font-medium">Name</th>
                <th className="py-2 pr-3 font-medium">Token</th>
                <th className="py-2 pr-3 font-medium">Last used</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-gray-700/50">
                  <td className="py-2 pr-3">{r.name}</td>
                  <td className="py-2 pr-3 font-mono text-xs text-gray-400">{r.prefix}…</td>
                  <td className="py-2 pr-3 text-gray-400">{r.revoked ? <span className="text-amber-400">Revoked</span> : when(r.last_used_at)}</td>
                  <td className="py-2 text-right">
                    {!r.revoked && (
                      <button
                        onClick={() => {
                          if (window.confirm(`Revoke the ${r.name} token? Anything using it stops working.`))
                            revokeApiToken(r.id).then(load);
                        }}
                        className="text-xs text-red-400 hover:text-red-300"
                      >
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <details className="text-sm text-gray-300">
          <summary className="cursor-pointer text-gray-400">How to connect a tool</summary>
          <div className="pt-2 space-y-2 text-xs">
            <p>Send a <span className="font-mono">POST</span> with JSON to:</p>
            <code className="block bg-black/40 rounded px-2 py-1.5 break-all text-emerald-300">{endpoint}</code>
            <p>with the header <span className="font-mono">Authorization: Bearer YOUR_TOKEN</span> and a body like:</p>
            <pre className="bg-black/40 rounded px-2 py-1.5 overflow-x-auto text-gray-200">{`{
  "amount": 24.50,
  "merchant": "Cineplex",
  "date": "2026-11-25",
  "category": "Leisure & Misc",
  "business": "Personal",
  "external_id": "your-own-id-123"
}`}</pre>
            <p>
              Only <span className="font-mono">amount</span> and a <span className="font-mono">merchant</span> or{" "}
              <span className="font-mono">description</span> are required. <span className="font-mono">category</span> and{" "}
              <span className="font-mono">business</span> are matched by name. Sending the same{" "}
              <span className="font-mono">external_id</span> again never creates a duplicate. Optionally attach a receipt
              as <span className="font-mono">receipt_base64</span>. Full guide: docs/INGEST.md.
            </p>
            {active.length === 0 && <p className="text-gray-500">Create a token above to get started.</p>}
          </div>
        </details>
      </div>
    </section>
  );
}
