import { useState } from "react";
import { Sparkles, Upload, ClipboardPaste, Check, Trash2 } from "lucide-react";
import ModelBadge from "../components/ModelBadge";
import {
  analyzeBudgetFile,
  analyzeBudgetPaste,
  commitBudgetSetup,
  BudgetProposal,
  BudgetProposalItem,
  BudgetCommitResult,
} from "../api/client";

const PERIODS = ["monthly", "annual", "quarterly", "weekly", "biweekly", "daily", "unknown"];

function fmt(n: number) {
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(n);
}

function confColor(c: number) {
  if (c >= 0.75) return "text-emerald-400";
  if (c >= 0.5) return "text-amber-400";
  return "text-red-400";
}

export default function BudgetSetupPage() {
  const [mode, setMode] = useState<"upload" | "paste">("upload");
  const [pasteText, setPasteText] = useState("");
  const [proposal, setProposal] = useState<BudgetProposal | null>(null);
  const [rows, setRows] = useState<BudgetProposalItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<BudgetCommitResult | null>(null);

  const runAnalyze = async (p: Promise<BudgetProposal>) => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const data = await p;
      setProposal(data);
      setRows(data.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed");
      setProposal(null);
      setRows([]);
    } finally {
      setBusy(false);
    }
  };

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) runAnalyze(analyzeBudgetFile(file));
  };

  const onPaste = () => {
    if (pasteText.trim()) runAnalyze(analyzeBudgetPaste(pasteText));
  };

  const updateRow = (i: number, patch: Partial<BudgetProposalItem>) => {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  };

  const removeRow = (i: number) => setRows((prev) => prev.filter((_, idx) => idx !== i));

  const commit = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await commitBudgetSetup(
        rows.map((r) => ({ category: r.category, monthly_amount: r.monthly_amount, kind: r.kind })),
      );
      setResult(res);
      setProposal(null);
      setRows([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Commit failed");
    } finally {
      setBusy(false);
    }
  };

  const totalMonthly = rows
    .filter((r) => r.kind === "expense")
    .reduce((s, r) => s + (r.monthly_amount || 0), 0);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Sparkles className="text-emerald-400" size={22} />
          <h2 className="text-2xl font-bold">Budget Setup</h2>
        </div>
        <ModelBadge override={proposal?.assisting_model} />
      </div>

      <p className="text-sm text-gray-400 max-w-2xl">
        Upload or paste a budget summary (line items with totals). The local model proposes a
        category and normalizes each amount to a monthly figure. Review everything below before
        creating budget targets — no transactions are created.
      </p>

      {result && (
        <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-4 text-sm">
          <p className="text-emerald-400 font-medium">Budget targets saved.</p>
          <p className="text-gray-300 mt-1">
            {result.categories_budgeted} categories budgeted · {result.budgets_created} created ·{" "}
            {result.budgets_updated} updated · {result.categories_created} new categories
            {result.income_items_skipped > 0 && ` · ${result.income_items_skipped} income rows skipped`}
          </p>
        </div>
      )}

      {!proposal && (
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 space-y-4">
          <div className="flex gap-2">
            <button
              onClick={() => setMode("upload")}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${
                mode === "upload" ? "bg-emerald-600 text-white" : "bg-gray-700 text-gray-300"
              }`}
            >
              <Upload size={15} /> Upload file
            </button>
            <button
              onClick={() => setMode("paste")}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${
                mode === "paste" ? "bg-emerald-600 text-white" : "bg-gray-700 text-gray-300"
              }`}
            >
              <ClipboardPaste size={15} /> Paste from Sheets
            </button>
          </div>

          {mode === "upload" ? (
            <div>
              <input
                type="file"
                accept=".xlsx,.xls,.csv,.tsv"
                onChange={onFile}
                disabled={busy}
                className="block text-sm text-gray-300 file:mr-3 file:rounded-lg file:border-0 file:bg-emerald-600 file:px-4 file:py-2 file:text-white hover:file:bg-emerald-500"
              />
              <p className="text-xs text-gray-500 mt-2">Accepts .xlsx, .xls, .csv, .tsv</p>
            </div>
          ) : (
            <div className="space-y-2">
              <textarea
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
                placeholder={"Rent\t2200\nGroceries\t800\nInsurance\t1200\tannual"}
                rows={6}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm font-mono"
              />
              <button
                onClick={onPaste}
                disabled={busy || !pasteText.trim()}
                className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm"
              >
                Analyze
              </button>
            </div>
          )}
          {busy && <p className="text-sm text-gray-400">Analyzing with the local model…</p>}
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {proposal && (
        <div className="space-y-4">
          {!proposal.ai_used && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 text-sm text-amber-400">
              The local model wasn't reachable, so these are rule-based guesses. Review carefully —
              start Ollama for smarter suggestions.
            </div>
          )}

          <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-gray-400 border-b border-gray-700">
                <tr>
                  <th className="p-3">Label</th>
                  <th className="p-3">Source</th>
                  <th className="p-3">Period</th>
                  <th className="p-3">Monthly</th>
                  <th className="p-3">Category</th>
                  <th className="p-3">Type</th>
                  <th className="p-3">Confidence</th>
                  <th className="p-3">Note</th>
                  <th className="p-3"></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="border-b border-gray-700/50">
                    <td className="p-2">
                      <input
                        value={r.label}
                        onChange={(e) => updateRow(i, { label: e.target.value })}
                        className="bg-gray-700 border border-gray-600 rounded px-2 py-1 w-36"
                      />
                    </td>
                    <td className="p-2 text-gray-400 whitespace-nowrap">{fmt(r.source_amount)}</td>
                    <td className="p-2">
                      <select
                        value={r.period}
                        onChange={(e) => updateRow(i, { period: e.target.value })}
                        className="bg-gray-700 border border-gray-600 rounded px-2 py-1"
                      >
                        {PERIODS.map((p) => (
                          <option key={p} value={p}>{p}</option>
                        ))}
                      </select>
                    </td>
                    <td className="p-2">
                      <input
                        type="number"
                        step="0.01"
                        value={r.monthly_amount}
                        onChange={(e) => updateRow(i, { monthly_amount: parseFloat(e.target.value) || 0 })}
                        className="bg-gray-700 border border-gray-600 rounded px-2 py-1 w-24"
                      />
                    </td>
                    <td className="p-2">
                      <input
                        list="budget-categories"
                        value={r.category}
                        onChange={(e) => updateRow(i, { category: e.target.value })}
                        className="bg-gray-700 border border-gray-600 rounded px-2 py-1 w-36"
                      />
                    </td>
                    <td className="p-2">
                      <select
                        value={r.kind}
                        onChange={(e) => updateRow(i, { kind: e.target.value })}
                        className="bg-gray-700 border border-gray-600 rounded px-2 py-1"
                      >
                        <option value="expense">expense</option>
                        <option value="income">income</option>
                      </select>
                    </td>
                    <td className={`p-2 font-medium ${confColor(r.confidence)}`}>
                      {Math.round(r.confidence * 100)}%
                    </td>
                    <td className="p-2 text-gray-400 max-w-[200px] truncate" title={r.note}>
                      {r.note}
                    </td>
                    <td className="p-2">
                      <button
                        onClick={() => removeRow(i)}
                        className="text-gray-500 hover:text-red-400"
                        title="Remove row"
                      >
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <datalist id="budget-categories">
            {proposal.existing_categories.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>

          <div className="flex items-center justify-between flex-wrap gap-3">
            <p className="text-sm text-gray-400">
              Total monthly (expenses):{" "}
              <span className="text-emerald-400 font-semibold">{fmt(totalMonthly)}</span>
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  setProposal(null);
                  setRows([]);
                }}
                className="bg-gray-700 hover:bg-gray-600 text-gray-200 px-4 py-2 rounded-lg text-sm"
              >
                Cancel
              </button>
              <button
                onClick={commit}
                disabled={busy || rows.length === 0}
                className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm"
              >
                <Check size={16} /> Create budget targets
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
