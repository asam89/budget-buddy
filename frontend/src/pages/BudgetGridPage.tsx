import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Plus, Maximize2 } from "lucide-react";
import {
  ActualCell,
  ActualLine,
  MonthTotals,
  YearGrid,
  bulkActuals,
  createCategory,
  deleteActual,
  fillForwardBudget,
  getActualsYear,
  getMonthTotals,
  upsertActual,
  upsertBudget,
} from "../api/client";
import EditableAmountCell from "../components/budget/EditableAmountCell";
import LineBreakdown from "../components/budget/LineBreakdown";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function fmt(n: number) {
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(n);
}

function ym(year: number, monthIdx: number) {
  return `${year}-${String(monthIdx + 1).padStart(2, "0")}`;
}

function parseRow(text: string): number[] {
  return text
    .split(/[\t\n\r]+/)
    .map((s) => parseFloat(s.replace(/[$,]/g, "").trim()))
    .filter((n) => !isNaN(n) && n >= 0);
}

interface Props {
  kind: "expense" | "income";
  title?: string;
  budgetLabel: string;
  actualLabel: string;
}

function readStored(key: string, fallback: number): number {
  const raw = sessionStorage.getItem(key);
  const n = raw === null ? NaN : parseInt(raw, 10);
  return Number.isFinite(n) ? n : fallback;
}

export default function BudgetGridPage({ kind, title, budgetLabel, actualLabel }: Props) {
  const now = new Date();
  const yearKey = `grid.${kind}.year`;
  const monthKey = `grid.${kind}.month`;
  const [year, setYear] = useState(() => readStored(yearKey, now.getFullYear()));
  const [monthIdx, setMonthIdx] = useState(() => readStored(monthKey, now.getMonth()));

  useEffect(() => {
    sessionStorage.setItem(yearKey, String(year));
  }, [year, yearKey]);
  useEffect(() => {
    sessionStorage.setItem(monthKey, String(monthIdx));
  }, [monthIdx, monthKey]);
  const [grid, setGrid] = useState<YearGrid | null>(null);
  const [totals, setTotals] = useState<MonthTotals | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [openCatId, setOpenCatId] = useState<number | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [justAdded, setJustAdded] = useState<Set<number>>(new Set());

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setGrid(await getActualsYear(year));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  const refreshTotals = async () => {
    try {
      setTotals(await getMonthTotals(ym(year, monthIdx)));
    } catch {
      setTotals(null);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  useEffect(() => {
    refreshTotals();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, monthIdx]);

  const lines: ActualLine[] = (grid?.lines ?? []).filter((l) => l.kind === kind);
  const qualifying = lines.filter(
    (l) => l.cells.some((c) => c.budget !== null || c.source !== "none") || justAdded.has(l.category_id),
  );

  const patchCell = (catId: number, mIdx: number, patch: Partial<ActualCell>) => {
    setGrid((g) =>
      g
        ? {
            ...g,
            lines: g.lines.map((l) =>
              l.category_id === catId
                ? { ...l, cells: l.cells.map((c, i) => (i === mIdx ? { ...c, ...patch } : c)) }
                : l,
            ),
          }
        : g,
    );
  };

  const commitActual = async (catId: number, mIdx: number, amount: number) => {
    const cell = await upsertActual({ category_id: catId, year_month: ym(year, mIdx), amount });
    patchCell(catId, mIdx, {
      effective: cell.effective,
      source: cell.source,
      transaction_sum: cell.transaction_sum,
      manual_amount: cell.manual_amount,
    });
    if (mIdx === monthIdx) refreshTotals();
  };

  const commitBudget = async (catId: number, mIdx: number, amount: number) => {
    await upsertBudget({ category_id: catId, year_month: ym(year, mIdx), monthly_limit: amount });
    patchCell(catId, mIdx, { budget: amount });
    if (mIdx === monthIdx) refreshTotals();
  };

  const clearActual = async (catId: number, mIdx: number) => {
    await deleteActual(catId, ym(year, mIdx));
    await load();
    refreshTotals();
  };

  const fillForward = async (catId: number, mIdx: number, amount: number) => {
    await fillForwardBudget({ category_id: catId, from_year_month: ym(year, mIdx), monthly_limit: amount });
    await load();
    refreshTotals();
  };

  const pasteBudgets = async (catId: number, text: string) => {
    const vals = parseRow(text).slice(0, 12);
    for (let i = 0; i < vals.length; i++) {
      await upsertBudget({ category_id: catId, year_month: ym(year, i), monthly_limit: vals[i] });
    }
    await load();
    refreshTotals();
  };

  const pasteActuals = async (catId: number, text: string) => {
    const vals = parseRow(text).slice(0, 12);
    await bulkActuals(vals.map((v, i) => ({ category_id: catId, year_month: ym(year, i), amount: v })));
    await load();
    refreshTotals();
  };

  const handleAdd = async () => {
    const name = newName.trim();
    if (!name) return;
    const cat = await createCategory({ name, kind });
    setJustAdded((s) => new Set(s).add(cat.id));
    setNewName("");
    setAddOpen(false);
    await load();
  };

  // month totals for the summary strip (this kind only)
  const budgetTotal = qualifying.reduce((s, l) => s + (l.cells[monthIdx].budget ?? 0), 0);
  const actualTotal = qualifying.reduce((s, l) => s + (l.cells[monthIdx].effective ?? 0), 0);
  const diff = actualTotal - budgetTotal;

  const openLine = openCatId !== null ? lines.find((l) => l.category_id === openCatId) : undefined;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        {title ? <h2 className="text-2xl font-bold">{title}</h2> : <span />}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 bg-gray-800 rounded-lg border border-gray-700">
            <button onClick={() => setYear((y) => y - 1)} className="p-2 hover:text-emerald-400" aria-label="Previous year">
              <ChevronLeft size={16} />
            </button>
            <span className="px-2 font-semibold">{year}</span>
            <button onClick={() => setYear((y) => y + 1)} className="p-2 hover:text-emerald-400" aria-label="Next year">
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
          <button
            onClick={() => setAddOpen(!addOpen)}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-2 rounded-lg text-sm"
          >
            <Plus size={16} /> Add {kind === "income" ? "Income Line" : "Category"}
          </button>
        </div>
      </div>

      {addOpen && (
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700 flex gap-3">
          <input
            autoFocus
            placeholder={kind === "income" ? "Income line name (e.g. Salary)" : "Category name"}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-sm"
          />
          <button onClick={handleAdd} className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm">
            Create
          </button>
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <p className="text-xs text-gray-400">{budgetLabel} ({MONTHS[monthIdx]})</p>
          <p className="text-xl font-bold">{fmt(budgetTotal)}</p>
        </div>
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <p className="text-xs text-gray-400">{actualLabel} ({MONTHS[monthIdx]})</p>
          <p className="text-xl font-bold">{fmt(actualTotal)}</p>
        </div>
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <p className="text-xs text-gray-400">{kind === "income" ? "Over/Under Expected" : "Over/Under Budget"}</p>
          <p className={`text-xl font-bold ${diff > 0 ? "text-red-400" : "text-emerald-400"}`}>{fmt(diff)}</p>
        </div>
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <p className="text-xs text-gray-400">Total Saved ({MONTHS[monthIdx]})</p>
          {totals ? (
            <>
              <p className={`text-xl font-bold ${totals.saved_actual < 0 ? "text-red-400" : "text-emerald-400"}`}>
                {fmt(totals.saved_actual)}
              </p>
              <p className="text-[11px] text-gray-500">budget {fmt(totals.saved_budget)}</p>
            </>
          ) : (
            <p className="text-xl font-bold text-gray-500">—</p>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 rounded-lg p-3 text-red-300 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={load} className="underline">Retry</button>
        </div>
      )}
      {loading && <p className="text-gray-500">Loading…</p>}

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
        {qualifying.map((l) => {
          const cell = l.cells[monthIdx];
          const over = cell.effective !== null && cell.budget !== null && cell.effective - cell.budget;
          return (
            <div key={l.category_id} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
              <div className="flex items-center justify-between mb-3">
                <p className="font-medium">{l.category_name}</p>
                <button
                  onClick={() => setOpenCatId(l.category_id)}
                  className="text-gray-500 hover:text-emerald-400"
                  aria-label="Open 12-month breakdown"
                >
                  <Maximize2 size={15} />
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <p className="text-[11px] text-gray-400 mb-1">{budgetLabel}</p>
                  <EditableAmountCell
                    value={cell.budget}
                    ariaLabel={`${l.category_name} ${budgetLabel}`}
                    onCommit={(amt) => commitBudget(l.category_id, monthIdx, amt)}
                    onPaste={(t) => pasteBudgets(l.category_id, t)}
                  />
                </div>
                <div>
                  <p className="text-[11px] text-gray-400 mb-1">
                    {actualLabel}
                    <span className="ml-1 text-gray-600">
                      {cell.source === "manual" ? "· manual" : cell.source === "transactions" ? "· txns" : ""}
                    </span>
                  </p>
                  <EditableAmountCell
                    value={cell.effective}
                    ariaLabel={`${l.category_name} ${actualLabel}`}
                    onCommit={(amt) => commitActual(l.category_id, monthIdx, amt)}
                    onPaste={(t) => pasteActuals(l.category_id, t)}
                  />
                </div>
              </div>
              {over !== false && (
                <p className={`text-xs mt-2 ${over > 0 ? "text-red-400" : "text-emerald-400"}`}>
                  {over > 0 ? "Over" : "Under"} by {fmt(Math.abs(over))}
                </p>
              )}
            </div>
          );
        })}
        {!loading && qualifying.length === 0 && (
          <p className="text-gray-500 col-span-full text-center py-8">
            No {kind === "income" ? "income lines" : "budgeted categories"} for {year} yet. Add one, or set a
            {" "}{budgetLabel.toLowerCase()} to get started.
          </p>
        )}
      </div>

      {openLine && (
        <LineBreakdown
          line={openLine}
          year={year}
          budgetLabel={budgetLabel}
          actualLabel={actualLabel}
          onCommitBudget={(i, amt) => commitBudget(openLine.category_id, i, amt)}
          onCommitActual={(i, amt) => commitActual(openLine.category_id, i, amt)}
          onClearActual={(i) => clearActual(openLine.category_id, i)}
          onFillForward={(i, amt) => fillForward(openLine.category_id, i, amt)}
          onPasteBudgets={(t) => pasteBudgets(openLine.category_id, t)}
          onPasteActuals={(t) => pasteActuals(openLine.category_id, t)}
          onClose={() => setOpenCatId(null)}
        />
      )}
    </div>
  );
}
