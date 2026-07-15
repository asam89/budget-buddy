import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { ActualCell, ActualLine, YearGrid, getActualsYear } from "../../api/client";
import { MONTHS_SHORT, fmt, expenseLines } from "./trendUtils";

interface Props {
  year: number;
  setYear: (y: number) => void;
}

// Heat class for an actual vs its budget. No budget => neutral, never an error.
function heatClass(cell: ActualCell): string {
  const actual = cell.effective ?? 0;
  if (actual === 0) return "";
  if (cell.budget === null || cell.budget <= 0) return "bg-gray-700/30";
  const ratio = actual / cell.budget;
  if (ratio <= 0.8) return "bg-emerald-500/20";
  if (ratio <= 1.0) return "bg-emerald-500/10";
  if (ratio <= 1.2) return "bg-red-500/15";
  return "bg-red-500/30";
}

export default function YearlyTrendView({ year, setYear }: Props) {
  const [grid, setGrid] = useState<YearGrid | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getActualsYear(year)
      .then(setGrid)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [year]);

  const lines = useMemo<ActualLine[]>(() => {
    return expenseLines(grid?.lines ?? []).filter((l) =>
      l.cells.some((c) => (c.effective ?? 0) !== 0 || c.budget !== null),
    );
  }, [grid]);

  const rowTotals = lines.map((l) => l.cells.reduce((s, c) => s + (c.effective ?? 0), 0));
  const colTotals = MONTHS_SHORT.map((_, i) =>
    lines.reduce((s, l) => s + (l.cells[i].effective ?? 0), 0),
  );
  const grandTotal = rowTotals.reduce((s, n) => s + n, 0);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1 bg-gray-800 rounded-lg border border-gray-700">
          <button onClick={() => setYear(year - 1)} className="p-2 hover:text-emerald-400" aria-label="Previous year">
            <ChevronLeft size={16} />
          </button>
          <span className="px-2 font-semibold">{year}</span>
          <button onClick={() => setYear(year + 1)} className="p-2 hover:text-emerald-400" aria-label="Next year">
            <ChevronRight size={16} />
          </button>
        </div>
        <span className="text-sm text-gray-400 ml-auto">
          Year total: <span className="text-gray-100 font-semibold">{fmt(grandTotal)}</span>
        </span>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}
      {loading && <p className="text-gray-500">Loading…</p>}

      {!loading && lines.length === 0 && (
        <div className="bg-gray-800 rounded-xl p-8 border border-gray-700 text-center text-gray-500">
          No expense activity in {year}.
        </div>
      )}

      {lines.length > 0 && (
        <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-gray-400 border-b border-gray-700">
              <tr>
                <th className="p-2 text-left sticky left-0 bg-gray-800">Category</th>
                {MONTHS_SHORT.map((m) => (
                  <th key={m} className="p-2 text-right">{m}</th>
                ))}
                <th className="p-2 text-right font-semibold">Total</th>
              </tr>
            </thead>
            <tbody>
              {lines.map((l, li) => (
                <tr key={l.category_id} className="border-b border-gray-700/40">
                  <td className="p-2 text-left sticky left-0 bg-gray-800 font-medium whitespace-nowrap">
                    {l.category_name}
                  </td>
                  {l.cells.map((c, ci) => (
                    <td key={ci} className={`p-2 text-right tabular-nums ${heatClass(c)}`}>
                      {(c.effective ?? 0) !== 0 ? fmt(c.effective ?? 0) : ""}
                    </td>
                  ))}
                  <td className="p-2 text-right font-semibold tabular-nums">{fmt(rowTotals[li])}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-gray-600 font-semibold">
                <td className="p-2 text-left sticky left-0 bg-gray-800">Total</td>
                {colTotals.map((t, i) => (
                  <td key={i} className="p-2 text-right tabular-nums">{t !== 0 ? fmt(t) : ""}</td>
                ))}
                <td className="p-2 text-right tabular-nums">{fmt(grandTotal)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
