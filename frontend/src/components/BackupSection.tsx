import { useState } from "react";
import { Archive, CheckCircle2, AlertCircle } from "lucide-react";
import { downloadBackup } from "../api/client";

export default function BackupSection() {
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setSaved(null);
    setError(null);
    try {
      setSaved(await downloadBackup());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Backup</h3>
        <p className="text-sm text-gray-400">
          Download everything as one zip you can keep somewhere safe.
        </p>
      </div>

      <div className="bg-gray-800 rounded-xl border border-gray-700 p-4 space-y-3">
        <ul className="text-sm text-gray-300 space-y-1.5">
          <li>
            <span className="font-medium text-white">budget_buddy.db</span>: a full copy you can restore from.
            It stays encrypted, so it only opens with your <span className="font-mono">DB_PASSPHRASE</span>.
            Keep that passphrase safe too.
          </li>
          <li>
            <span className="font-medium text-white">budget-buddy-data.xlsx</span>: the same data as a spreadsheet,
            one sheet per table. It isn't encrypted, so store it privately. Bank tokens and passwords are left out.
          </li>
          <li>
            <span className="font-medium text-white">RESTORE.txt</span>: how to restore.
          </li>
        </ul>

        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={run}
            disabled={busy}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm"
          >
            <Archive size={16} />
            {busy ? "Preparing backup…" : "Download backup"}
          </button>
          {saved && (
            <span className="flex items-center gap-1.5 text-sm text-emerald-400">
              <CheckCircle2 size={15} /> Saved {saved}
            </span>
          )}
          {error && (
            <span className="flex items-center gap-1.5 text-sm text-red-400">
              <AlertCircle size={15} /> {error}
            </span>
          )}
        </div>
      </div>
    </section>
  );
}
