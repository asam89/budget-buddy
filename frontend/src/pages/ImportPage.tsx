import { useState, useEffect, useRef } from "react";
import { Upload, FileText, CheckCircle, XCircle } from "lucide-react";
import { getAccounts, uploadFile, getImportHistory, Account, ImportSource } from "../api/client";

export default function ImportPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccount, setSelectedAccount] = useState("");
  const [history, setHistory] = useState<ImportSource[]>([]);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getAccounts().then(setAccounts);
    getImportHistory().then(setHistory);
  }, []);

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file || !selectedAccount) return;

    setUploading(true);
    setResult(null);

    try {
      const ext = file.name.split(".").pop()?.toLowerCase() || "";
      let endpoint = "/import/statement";
      if (ext === "csv") endpoint = "/import/csv";
      else if (ext === "xlsx" || ext === "xls") endpoint = "/import/excel";

      const source = await uploadFile(endpoint, file, parseInt(selectedAccount));
      setResult(`Imported ${source.record_count} transactions from ${file.name}`);
      getImportHistory().then(setHistory);
    } catch (err: unknown) {
      setResult(`Error: ${err instanceof Error ? err.message : "Upload failed"}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Import Data</h2>

      <div className="bg-gray-800 rounded-xl p-6 border border-gray-700 space-y-4">
        <p className="text-sm text-gray-400">
          Upload CSV, Excel (.xlsx), or PDF bank statements. CSV and Excel files are parsed
          deterministically. PDF statements use AI parsing and all extracted transactions are
          flagged for review before they affect analytics.
        </p>

        <div className="grid md:grid-cols-3 gap-3 items-end">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Account</label>
            <select
              value={selectedAccount}
              onChange={(e) => setSelectedAccount(e.target.value)}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm"
            >
              <option value="">Select account...</option>
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">File</label>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,.xlsx,.xls,.pdf"
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm file:mr-3 file:bg-gray-600 file:border-0 file:rounded file:px-3 file:py-1 file:text-sm file:text-gray-200"
            />
          </div>
          <button
            onClick={handleUpload}
            disabled={uploading || !selectedAccount}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg text-sm"
          >
            <Upload size={16} />
            {uploading ? "Uploading..." : "Import"}
          </button>
        </div>

        {result && (
          <p className={`text-sm ${result.startsWith("Error") ? "text-red-400" : "text-emerald-400"}`}>
            {result}
          </p>
        )}
      </div>

      {/* Import History */}
      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
        <h3 className="font-semibold mb-4">Import History</h3>
        {history.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-gray-700">
                <th className="text-left py-2">File</th>
                <th className="text-left py-2">Type</th>
                <th className="text-left py-2">Status</th>
                <th className="text-right py-2">Records</th>
                <th className="text-right py-2">Date</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h) => (
                <tr key={h.id} className="border-b border-gray-700/50">
                  <td className="py-2 flex items-center gap-2">
                    <FileText size={14} className="text-gray-400" />
                    {h.filename || "Unknown"}
                  </td>
                  <td className="py-2 capitalize">{h.source_type}</td>
                  <td className="py-2">
                    {h.status === "completed" ? (
                      <span className="flex items-center gap-1 text-emerald-400">
                        <CheckCircle size={14} /> Done
                      </span>
                    ) : h.status === "failed" ? (
                      <span className="flex items-center gap-1 text-red-400" title={h.error_message || ""}>
                        <XCircle size={14} /> Failed
                      </span>
                    ) : (
                      <span className="text-yellow-400">{h.status}</span>
                    )}
                  </td>
                  <td className="py-2 text-right">{h.record_count}</td>
                  <td className="py-2 text-right text-gray-400">
                    {new Date(h.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-gray-500 text-center py-4">No imports yet</p>
        )}
      </div>
    </div>
  );
}
