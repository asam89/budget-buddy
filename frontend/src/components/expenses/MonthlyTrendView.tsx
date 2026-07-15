import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { ActualCell, ActualLine, YearGrid, getActualsYear } from "../../api/client";
import { MONTHS, fmt, expenseLines } from "./trendUtils";
import CategoryDrilldown from "./CategoryDrilldown";
import TrendOverlay from "./TrendOverlay";

interface Props {
  year: number;
  monthIdx: number;
  setYear: (y: number) => void;
  setMonthIdx: (m: number) => void;
}

interface Row {
  categoryId: number;
  name: string;
  actual: number;
  budget: number;
  cell: ActualCell;
}

export default function MonthlyTrendView({ year, monthIdx, setYear, setMonthIdx }: Props) {
  const [grid, setGrid] = useState<YearGrid | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [drill, setDrill] = useState<Row | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getActualsYear(year)
      .then(setGrid)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [year]);

  const expLines: ActualLine[] = useMemo(() => expenseLines(grid?.lines ?? []), [grid]);

  const rows = useMemo<Row[]>(() => {
    return expLines
      .map((l) => {
        const cell = l.cells[monthIdx];
        return {
          categoryId: l.category_id,
          name: l.category_name,
          actual: cell.effective ?? 0,
          budget: cell.budget ?? 0,
          cell,
        };
      })
      .filter((r) => r.actual !== 0 || r.budget !== 0)
      .sort((a, b) => b.actual - a.actual);
  }, [expLines, monthIdx]);

  const totalActual = rows.reduce((s, r) => s + r.actual, 0);
  const maxActual = rows.reduce((m, r) => Math.max(m, r.actual), 0);

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
        <select
          value={monthIdx}
          onChange={(e) => setMonthIdx(parseInt(e.target.value))}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
        >
          {MONTHS.map((m, i) => (
            <option key={m} value={i}>{m}</option>
          ))}
        </select>
        <span className="text-sm text-gray-400 ml-auto">
          Total spend: <span className="text-gray-100 font-semibold">{fmt(totalActual)}</span>
        </span>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}
      {loading && <p className="text-gray-500">Loading…</p>}

      {!loading && rows.length === 0 && (
        <div className="bg-gray-800 rounded-xl p-8 border border-gray-700 text-center text-gray-500">
          No expense activity in {MONTHS[monthIdx]} {year}.
        </div>
      )}

      {rows.length > 0 && (
        <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="text-left text-gray-400 border-b border-gray-700">
              <tr>
                <th className="p-3">Category</th>
                <th className="p-3 text-right">Actual</th>
                <th className="p-3 text-right">Budget</th>
                <th className="p-3 text-right">Variance</th>
                <th className="p-3 text-right">Share</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const variance = r.actual - r.budget;
                const share = totalActual > 0 ? r.actual / totalActual : 0;
                return (
                  <tr
                    key={r.categoryId}
                    onClick={() => setDrill(r)}
                    className="border-b border-gray-700/40 hover:bg-gray-700/30 cursor-pointer"
                  >
                    <td className="p-3">
                      <div className="font-medium">{r.name}</div>
                      <div className="mt-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-emerald-500"
                          style={{ width: `${maxActual > 0 ? (r.actual / maxActual) * 100 : 0}%` }}
                        />
                      </div>
                    </td>
                    <td className="p-3 text-right font-medium">{fmt(r.actual)}</td>
                    <td className="p-3 text-right text-gray-400">{r.budget ? fmt(r.budget) : "—"}</td>
                    <td className={`p-3 text-right ${variance > 0 ? "text-red-400" : "text-emerald-400"}`}>
                      {r.budget ? fmt(variance) : "—"}
                    </td>
                    <td className="p-3 text-right text-gray-400">{(share * 100).toFixed(1)}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {expLines.length > 0 && <TrendOverlay year={year} lines={expLines} />}

      {drill && (
        <CategoryDrilldown
          categoryId={drill.categoryId}
          categoryName={drill.name}
          year={year}
          monthIdx={monthIdx}
          cell={drill.cell}
          onClose={() => setDrill(null)}
        />
      )}
    </div>
  );
}
