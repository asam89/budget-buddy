import { X } from "lucide-react";
import { ActualLine } from "../../api/client";

interface Props {
  title: string;
  monthLabel: string;
  lines: ActualLine[];
  monthIdx: number;
  onOpenLine: (categoryId: number) => void;
  onClose: () => void;
}

const fmt = (n: number) =>
  new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(n);

/** Which lines make up a month's budget total, biggest first. */
export default function BudgetBreakdownModal({ title, monthLabel, lines, monthIdx, onOpenLine, onClose }: Props) {
  const rows = lines
    .map((l) => ({ line: l, budget: l.cells[monthIdx].budget ?? 0, actual: l.cells[monthIdx].effective }))
    .filter((r) => r.budget > 0)
    .sort((a, b) => b.budget - a.budget);
  const total = rows.reduce((s, r) => s + r.budget, 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true">
      <div className="bg-gray-800 rounded-2xl border border-gray-700 w-full max-w-2xl max-h-[85vh] flex flex-col">
        <div className="flex items-start justify-between p-5 border-b border-gray-700">
          <div>
            <h2 className="text-lg font-bold">
              {title} for {monthLabel}: {fmt(total)}
            </h2>
            <p className="text-sm text-gray-400">
              {rows.length} line{rows.length === 1 ? "" : "s"}, biggest first. Click a line to open and edit it.
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white" aria-label="Close">
            <X size={20} />
          </button>
        </div>
        <div className="overflow-y-auto p-2">
          {rows.length === 0 ? (
            <p className="p-4 text-sm text-gray-400">No budget set for {monthLabel}.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-400">
                  <th className="px-3 py-2 font-medium">Line</th>
                  <th className="px-3 py-2 font-medium text-right">Budget</th>
                  <th className="px-3 py-2 font-medium text-right">Share</th>
                  <th className="px-3 py-2 font-medium text-right">Actual</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ line, budget, actual }) => {
                  const share = total ? budget / total : 0;
                  return (
                    <tr
                      key={line.category_id}
                      onClick={() => onOpenLine(line.category_id)}
                      className="border-t border-gray-700/60 hover:bg-gray-700/50 cursor-pointer"
                    >
                      <td className="px-3 py-2">{line.category_name}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{fmt(budget)}</td>
                      <td className="px-3 py-2 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <div className="w-16 h-1.5 rounded-full bg-gray-700 overflow-hidden">
                            <div className="h-full bg-emerald-500" style={{ width: `${Math.round(share * 100)}%` }} />
                          </div>
                          <span className={`tabular-nums w-10 text-right ${share >= 0.4 ? "text-amber-400 font-medium" : "text-gray-400"}`}>
                            {Math.round(share * 100)}%
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums text-gray-300">
                        {actual === null ? "—" : fmt(actual)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
