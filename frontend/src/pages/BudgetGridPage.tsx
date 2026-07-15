import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Plus, Maximize2, Trash2, Pencil, Check, X } from "lucide-react";
import {
  ActualCell,
  ActualLine,
  MonthTotals,
  YearGrid,
  bulkActuals,
  createCategory,
  deleteActual,
  deleteCategory,
  fillForwardBudget,
  getActualsYear,
  getMonthTotals,
  updateCategory,
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
  const [deleting, setDeleting] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");

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
  // Excel-style planning grid: show every line of this kind (including empty
  // ones you just added) so you can enter budget/actual and add/remove rows.
  const qualifying = [...lines].sort((a, b) =>
    a.category_name.localeCompare(b.category_name),
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
    try {
      await createCategory({ name, kind });
      setNewName("");
      setAddOpen(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add");
    }
  };

  const startEdit = (catId: number, name: string) => {
    setEditingId(catId);
    setEditName(name);
    setError(null);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditName("");
  };

  const saveEdit = async (catId: number) => {
    const name = editName.trim();
    if (!name) return;
    try {
      await updateCategory(catId, { name });
      cancelEdit();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not rename");
    }
  };

  const handleDelete = async (catId: number, name: string) => {
    if (!window.confirm(`Remove "${name}"? This clears its budgets and actuals.`))
      return;
    setDeleting(catId);
    setError(null);
    try {
      await deleteCategory(catId);
      await load();
      refreshTotals();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not remove");
    } finally {
      setDeleting(null);
    }
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

      <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 border-b border-gray-700 text-xs">
              <th className="text-left font-medium px-4 py-3">
                {kind === "income" ? "Income Line" : "Category"}
              </th>
              <th className="text-right font-medium px-4 py-3 w-40">{budgetLabel}</th>
              <th className="text-right font-medium px-4 py-3 w-40">{actualLabel}</th>
              <th className="text-right font-medium px-4 py-3 w-32">Variance</th>
              <th className="px-2 py-3 w-20"></th>
            </tr>
          </thead>
          <tbody>
            {qualifying.map((l) => {
              const cell = l.cells[monthIdx];
              const variance =
                cell.effective !== null && cell.budget !== null
                  ? cell.effective - cell.budget
                  : null;
              return (
                <tr key={l.category_id} className="border-b border-gray-700/60 last:border-0 hover:bg-gray-700/20">
                  <td className="px-4 py-2 font-medium">
                    {editingId === l.category_id ? (
                      <div className="flex items-center gap-1">
                        <input
                          autoFocus
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") saveEdit(l.category_id);
                            if (e.key === "Escape") cancelEdit();
                          }}
                          className="flex-1 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm"
                        />
                        <button
                          onClick={() => saveEdit(l.category_id)}
                          className="p-1 text-gray-400 hover:text-emerald-400"
                          aria-label="Save name"
                        >
                          <Check size={15} />
                        </button>
                        <button
                          onClick={cancelEdit}
                          className="p-1 text-gray-400 hover:text-red-400"
                          aria-label="Cancel rename"
                        >
                          <X size={15} />
                        </button>
                      </div>
                    ) : (
                      <div className="group flex items-center gap-2">
                        <span>{l.category_name}</span>
                        <button
                          onClick={() => startEdit(l.category_id, l.category_name)}
                          className="p-1 text-gray-600 hover:text-emerald-400 opacity-0 group-hover:opacity-100 transition-opacity"
                          aria-label={`Rename ${l.category_name}`}
                        >
                          <Pencil size={13} />
                        </button>
                        {cell.source === "manual" && (
                          <span className="text-[10px] text-gray-500">manual</span>
                        )}
                        {cell.source === "transactions" && (
                          <span className="text-[10px] text-gray-500">txns</span>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <EditableAmountCell
                      value={cell.budget}
                      ariaLabel={`${l.category_name} ${budgetLabel}`}
                      onCommit={(amt) => commitBudget(l.category_id, monthIdx, amt)}
                      onPaste={(t) => pasteBudgets(l.category_id, t)}
                    />
                  </td>
                  <td className="px-4 py-2">
                    <EditableAmountCell
                      value={cell.effective}
                      ariaLabel={`${l.category_name} ${actualLabel}`}
                      onCommit={(amt) => commitActual(l.category_id, monthIdx, amt)}
                      onPaste={(t) => pasteActuals(l.category_id, t)}
                    />
                  </td>
                  <td className="px-4 py-2 text-right">
                    {variance === null ? (
                      <span className="text-gray-600">—</span>
                    ) : (
                      <span className={variance > 0 ? "text-red-400" : "text-emerald-400"}>
                        {fmt(variance)}
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        onClick={() => setOpenCatId(l.category_id)}
                        className="p-1.5 text-gray-500 hover:text-emerald-400"
                        aria-label={`Open 12-month breakdown for ${l.category_name}`}
                      >
                        <Maximize2 size={15} />
                      </button>
                      <button
                        onClick={() => handleDelete(l.category_id, l.category_name)}
                        disabled={deleting === l.category_id}
                        className="p-1.5 text-gray-500 hover:text-red-400 disabled:opacity-40"
                        aria-label={`Remove ${l.category_name}`}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
            {!loading && qualifying.length === 0 && (
              <tr>
                <td colSpan={5} className="text-gray-500 text-center py-8">
                  No {kind === "income" ? "income lines" : "expense categories"} for {year} yet — add one with the
                  {" "}<span className="text-emerald-400">Add {kind === "income" ? "Income Line" : "Category"}</span>{" "}
                  button above.
                </td>
              </tr>
            )}
          </tbody>
          {qualifying.length > 0 && (
            <tfoot>
              <tr className="border-t border-gray-700 font-semibold">
                <td className="px-4 py-3">Total</td>
                <td className="px-4 py-3 text-right">{fmt(budgetTotal)}</td>
                <td className="px-4 py-3 text-right">{fmt(actualTotal)}</td>
                <td className={`px-4 py-3 text-right ${diff > 0 ? "text-red-400" : "text-emerald-400"}`}>
                  {fmt(diff)}
                </td>
                <td></td>
              </tr>
            </tfoot>
          )}
        </table>
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
