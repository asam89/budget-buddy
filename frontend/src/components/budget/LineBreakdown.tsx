import { useState } from "react";
import { X, ArrowRightToLine } from "lucide-react";
import { ActualLine, CellSource } from "../../api/client";
import EditableAmountCell from "./EditableAmountCell";

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function SourceBadge({ source }: { source: CellSource }) {
  if (source === "manual")
    return <span className="text-[10px] px-1 rounded bg-emerald-900 text-emerald-300">manual</span>;
  if (source === "transactions")
    return <span className="text-[10px] px-1 rounded bg-sky-900 text-sky-300">txns</span>;
  return <span className="text-[10px] px-1 rounded bg-gray-700 text-gray-400">empty</span>;
}

interface Props {
  line: ActualLine;
  year: number;
  budgetLabel: string;
  actualLabel: string;
  onCommitBudget: (monthIdx: number, amount: number) => Promise<void>;
  onCommitActual: (monthIdx: number, amount: number) => Promise<void>;
  onClearActual: (monthIdx: number) => Promise<void>;
  onFillForward: (monthIdx: number, amount: number) => Promise<void>;
  onPasteBudgets: (text: string) => void;
  onPasteActuals: (text: string) => void;
  onClose: () => void;
}

/** 12-month drill-down for one line, shared by Budgets and Income. */
export default function LineBreakdown({
  line,
  year,
  budgetLabel,
  actualLabel,
  onCommitBudget,
  onCommitActual,
  onClearActual,
  onFillForward,
  onPasteBudgets,
  onPasteActuals,
  onClose,
}: Props) {
  // "b-3" / "a-7" => which cell should auto-open (Enter moves down the column)
  const [active, setActive] = useState<string | null>(null);

  const budgetTotal = line.cells.reduce((s, c) => s + (c.budget ?? 0), 0);
  const actualTotal = line.cells.reduce((s, c) => s + (c.effective ?? 0), 0);

  const fmt = (n: number) =>
    new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(n);

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-xl border border-gray-700 w-full max-w-2xl max-h-[85vh] overflow-auto">
        <div className="flex items-center justify-between p-4 border-b border-gray-700 sticky top-0 bg-gray-800">
          <div>
            <h3 className="font-bold text-lg">{line.category_name}</h3>
            <p className="text-xs text-gray-400">{year} monthly breakdown</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white" aria-label="Close">
            <X size={20} />
          </button>
        </div>

        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 text-xs border-b border-gray-700">
              <th className="text-left px-4 py-2">Month</th>
              <th className="text-right px-2 py-2">{budgetLabel}</th>
              <th className="px-2 py-2"></th>
              <th className="text-right px-2 py-2">{actualLabel}</th>
              <th className="text-center px-2 py-2">Source</th>
              <th className="text-right px-4 py-2">Variance</th>
            </tr>
          </thead>
          <tbody>
            {line.cells.map((cell, i) => {
              const variance =
                cell.effective !== null && cell.budget !== null
                  ? cell.effective - cell.budget
                  : null;
              return (
                <tr key={cell.year_month} className="border-b border-gray-700/50">
                  <td className="px-4 py-1.5 text-gray-300">{MONTHS[i]}</td>
                  <td className="px-2 py-1.5 w-28">
                    <EditableAmountCell
                      value={cell.budget}
                      ariaLabel={`${MONTHS[i]} ${budgetLabel}`}
                      autoOpen={active === `b-${i}`}
                      onCommit={(amt) => onCommitBudget(i, amt)}
                      onEnterNext={() => setActive(i < 11 ? `b-${i + 1}` : null)}
                      onPaste={onPasteBudgets}
                    />
                  </td>
                  <td className="px-1 py-1.5 w-8 text-center">
                    <button
                      title="Fill this value to the rest of the year"
                      onClick={() => cell.budget !== null && onFillForward(i, cell.budget)}
                      className="text-gray-500 hover:text-emerald-400 disabled:opacity-30"
                      disabled={cell.budget === null}
                    >
                      <ArrowRightToLine size={13} />
                    </button>
                  </td>
                  <td className="px-2 py-1.5 w-28">
                    <EditableAmountCell
                      value={cell.effective}
                      ariaLabel={`${MONTHS[i]} ${actualLabel}`}
                      autoOpen={active === `a-${i}`}
                      onCommit={(amt) => onCommitActual(i, amt)}
                      onEnterNext={() => setActive(i < 11 ? `a-${i + 1}` : null)}
                      onPaste={onPasteActuals}
                    />
                  </td>
                  <td className="px-2 py-1.5 text-center">
                    <div className="flex items-center justify-center gap-1">
                      <SourceBadge source={cell.source} />
                      {cell.source === "manual" && (
                        <button
                          title="Clear manual value (revert to transactions)"
                          onClick={() => onClearActual(i)}
                          className="text-gray-500 hover:text-red-400"
                        >
                          <X size={12} />
                        </button>
                      )}
                    </div>
                  </td>
                  <td
                    className={`px-4 py-1.5 text-right ${
                      variance === null
                        ? "text-gray-600"
                        : variance > 0
                        ? "text-red-400"
                        : "text-emerald-400"
                    }`}
                  >
                    {variance === null ? "—" : fmt(variance)}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="font-semibold border-t border-gray-600">
              <td className="px-4 py-2">Year</td>
              <td className="px-2 py-2 text-right">{fmt(budgetTotal)}</td>
              <td></td>
              <td className="px-2 py-2 text-right">{fmt(actualTotal)}</td>
              <td></td>
              <td
                className={`px-4 py-2 text-right ${
                  actualTotal - budgetTotal > 0 ? "text-red-400" : "text-emerald-400"
                }`}
              >
                {fmt(actualTotal - budgetTotal)}
              </td>
            </tr>
          </tfoot>
        </table>
        <p className="text-xs text-gray-500 px-4 py-3">
          Tip: paste a 12-value row from Excel into any cell to fill the whole year. Enter commits and
          moves down; Esc cancels.
        </p>
      </div>
    </div>
  );
}
