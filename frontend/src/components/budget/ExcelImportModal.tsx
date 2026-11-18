import { useRef, useState } from "react";
import { FileSpreadsheet, X } from "lucide-react";
import {
  BudgetExcelPreview,
  BudgetExcelResult,
  applyBudgetExcel,
  previewBudgetExcel,
} from "../../api/client";

interface Props {
  onClose: () => void;
  onApplied: (year: number) => void;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const money = (v: number | null) =>
  v === null ? "—" : v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const monthLabel = (ym: string) => MONTHS[parseInt(ym.slice(5, 7), 10) - 1] ?? ym;

/** Pick an exported workbook, preview every change, then apply. */
export default function ExcelImportModal({ onClose, onApplied }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<BudgetExcelPreview | null>(null);
  const [result, setResult] = useState<BudgetExcelResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pick = async (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    setPreview(null);
    setResult(null);
    setError(null);
    setBusy(true);
    try {
      setPreview(await previewBudgetExcel(f));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const apply = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const r = await applyBudgetExcel(file);
      setResult(r);
      onApplied(r.year);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const nothingToDo = preview && preview.change_count === 0 && preview.new_lines.length === 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true">
      <div className="bg-gray-800 rounded-2xl border border-gray-700 w-full max-w-3xl max-h-[90vh] flex flex-col">
        <div className="flex items-start justify-between p-5 border-b border-gray-700">
          <div className="flex items-center gap-3">
            <FileSpreadsheet className="text-emerald-400 shrink-0" size={22} />
            <div>
              <h2 className="text-lg font-bold">Import from Excel</h2>
              <p className="text-sm text-gray-400">
                Use a file exported from Budget Buddy. You'll see every change before anything is saved.
              </p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white" aria-label="Close">
            <X size={20} />
          </button>
        </div>

        <div className="p-5 space-y-4 overflow-y-auto">
          <div className="flex items-center gap-3">
            <input
              ref={inputRef}
              type="file"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              className="hidden"
              onChange={(e) => pick(e.target.files?.[0])}
            />
            <button
              onClick={() => inputRef.current?.click()}
              disabled={busy}
              className="bg-gray-700 hover:bg-gray-600 border border-gray-600 rounded-lg px-4 py-2 text-sm disabled:opacity-50"
            >
              {file ? "Choose a different file" : "Choose file"}
            </button>
            {file && <span className="text-sm text-gray-300 truncate">{file.name}</span>}
          </div>

          {busy && <p className="text-sm text-gray-400">Working…</p>}
          {error && <p className="text-sm text-red-400">{error}</p>}

          {result ? (
            <div className="rounded-lg border border-emerald-700 bg-emerald-900/30 p-4 text-sm">
              <p className="font-medium text-emerald-300">Imported into {result.year}.</p>
              <p className="text-gray-300 mt-1">
                {result.expected_written} expected and {result.actual_written} actual value
                {result.expected_written + result.actual_written === 1 ? "" : "s"} saved
                {result.lines_created > 0 && `, ${result.lines_created} new line${result.lines_created === 1 ? "" : "s"} created`}.
              </p>
            </div>
          ) : (
            preview && (
              <>
                <p className="text-sm">
                  <span className="font-semibold">{preview.year}</span>:{" "}
                  {nothingToDo
                    ? "no changes. The file matches what's already in Budget Buddy."
                    : `${preview.change_count} value${preview.change_count === 1 ? "" : "s"} will change` +
                      (preview.new_lines.length
                        ? `, ${preview.new_lines.length} new line${preview.new_lines.length === 1 ? "" : "s"} will be created`
                        : "") + "."}
                </p>

                {preview.new_lines.length > 0 && (
                  <div>
                    <h3 className="text-xs uppercase tracking-wide text-gray-400 mb-1">New lines</h3>
                    <ul className="text-sm space-y-0.5">
                      {preview.new_lines.map((l) => (
                        <li key={l.line}>
                          {l.line} <span className="text-gray-400">· {l.kind} · {l.business}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {preview.changes.length > 0 && (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-gray-400 border-b border-gray-700">
                          <th className="py-1.5 pr-3 font-medium">Line</th>
                          <th className="py-1.5 pr-3 font-medium">Business</th>
                          <th className="py-1.5 pr-3 font-medium">Month</th>
                          <th className="py-1.5 pr-3 font-medium">Field</th>
                          <th className="py-1.5 pr-3 font-medium text-right">Now</th>
                          <th className="py-1.5 font-medium text-right">New</th>
                        </tr>
                      </thead>
                      <tbody>
                        {preview.changes.map((c, i) => (
                          <tr key={i} className="border-b border-gray-700/50">
                            <td className="py-1.5 pr-3">{c.line}</td>
                            <td className="py-1.5 pr-3 text-gray-300">{c.business}</td>
                            <td className="py-1.5 pr-3 text-gray-300">{monthLabel(c.month)}</td>
                            <td className="py-1.5 pr-3 text-gray-300 capitalize">{c.field}</td>
                            <td className="py-1.5 pr-3 text-right tabular-nums text-gray-400">{money(c.old)}</td>
                            <td className="py-1.5 text-right tabular-nums">{money(c.new)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {preview.change_count > preview.changes.length && (
                      <p className="text-xs text-gray-400 mt-2">
                        Showing the first {preview.changes.length} of {preview.change_count} changes.
                      </p>
                    )}
                  </div>
                )}
              </>
            )
          )}

          {(preview?.errors.length ?? 0) > 0 && !result && (
            <div className="rounded-lg border border-amber-700 bg-amber-900/20 p-3 text-sm">
              <p className="font-medium text-amber-300 mb-1">
                {preview!.errors.length} row{preview!.errors.length === 1 ? "" : "s"} will be skipped:
              </p>
              <ul className="list-disc pl-5 space-y-0.5 text-gray-300">
                {preview!.errors.map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 p-5 border-t border-gray-700">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-300 hover:text-white">
            {result ? "Done" : "Cancel"}
          </button>
          {!result && (
            <button
              onClick={apply}
              disabled={busy || !preview || !!nothingToDo}
              className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm disabled:opacity-40"
            >
              Apply changes
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
