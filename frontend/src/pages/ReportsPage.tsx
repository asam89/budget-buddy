import { useState, useEffect, useCallback } from "react";
import {
  getEntities,
  Entity,
} from "../api/client";
import { BarChart3, TrendingUp, GitCompare } from "lucide-react";

const BASE = "/api";

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { credentials: "same-origin" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function fmt(n: number) {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
  }).format(n);
}

type Tab = "pivot" | "pnl" | "comparison";

// ---- Types ----
interface PivotRow {
  category_id: number | null;
  category: string;
  parent_category: string | null;
  months: Record<string, number>;
  total: number;
  average: number;
}

interface PivotData {
  months: string[];
  mode: string;
  entity_id: number | null;
  rows: PivotRow[];
}

interface PnlLine {
  category: string;
  amount: number;
}

interface PnlData {
  entity_id: number;
  entity_name: string;
  start_date: string;
  end_date: string;
  income: PnlLine[];
  expenses: PnlLine[];
  total_income: number;
  total_expenses: number;
  net: number;
}

interface ComparisonEntity {
  entity_id: number;
  entity_name: string;
  months: Record<string, { income: number; expenses: number; net: number }>;
}

interface ComparisonData {
  month_labels: string[];
  entities: ComparisonEntity[];
}

export default function ReportsPage() {
  const [tab, setTab] = useState<Tab>("pivot");
  const [entities, setEntities] = useState<Entity[]>([]);
  const [entityId, setEntityId] = useState<string>("");
  const [months, setMonths] = useState(6);
  const [mode, setMode] = useState<"expense" | "income" | "net">("expense");

  // Pivot data
  const [pivotData, setPivotData] = useState<PivotData | null>(null);
  // P&L data
  const [pnlData, setPnlData] = useState<PnlData | null>(null);
  // Comparison data
  const [compData, setCompData] = useState<ComparisonData | null>(null);

  useEffect(() => {
    getEntities().then(setEntities);
  }, []);

  const loadPivot = useCallback(() => {
    const params = new URLSearchParams({ months: String(months), mode });
    if (entityId) params.set("entity_id", entityId);
    fetchJSON<PivotData>(`/reports/category-month?${params}`).then(
      setPivotData
    );
  }, [entityId, months, mode]);

  const loadPnl = useCallback(() => {
    if (!entityId) return;
    fetchJSON<PnlData>(`/reports/entity-pnl?entity_id=${entityId}`).then(
      setPnlData
    );
  }, [entityId]);

  const loadComparison = useCallback(() => {
    fetchJSON<ComparisonData>(
      `/reports/entity-comparison?months=${months}`
    ).then(setCompData);
  }, [months]);

  useEffect(() => {
    if (tab === "pivot") loadPivot();
    else if (tab === "pnl") loadPnl();
    else if (tab === "comparison") loadComparison();
  }, [tab, loadPivot, loadPnl, loadComparison]);

  const tabs: { id: Tab; label: string; icon: typeof BarChart3 }[] = [
    { id: "pivot", label: "Category × Month", icon: BarChart3 },
    { id: "pnl", label: "Entity P&L", icon: TrendingUp },
    { id: "comparison", label: "Entity Comparison", icon: GitCompare },
  ];

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Reports</h2>

      {/* Tab bar */}
      <div className="flex gap-1 bg-gray-800 rounded-lg p-1 w-fit">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm transition-colors ${
              tab === id
                ? "bg-emerald-500/20 text-emerald-400"
                : "text-gray-400 hover:text-gray-200 hover:bg-gray-700"
            }`}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        {(tab === "pivot" || tab === "pnl") && (
          <select
            value={entityId}
            onChange={(e) => setEntityId(e.target.value)}
            className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm"
          >
            <option value="">All entities</option>
            {entities.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        )}
        {(tab === "pivot" || tab === "comparison") && (
          <select
            value={months}
            onChange={(e) => setMonths(Number(e.target.value))}
            className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm"
          >
            {[3, 6, 12].map((n) => (
              <option key={n} value={n}>
                {n} months
              </option>
            ))}
          </select>
        )}
        {tab === "pivot" && (
          <select
            value={mode}
            onChange={(e) =>
              setMode(e.target.value as "expense" | "income" | "net")
            }
            className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm"
          >
            <option value="expense">Expenses</option>
            <option value="income">Income</option>
            <option value="net">Net</option>
          </select>
        )}
      </div>

      {/* Pivot table */}
      {tab === "pivot" && pivotData && (
        <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-gray-700 bg-gray-800/50">
                <th className="text-left py-3 px-4 sticky left-0 bg-gray-800/90 z-10">
                  Category
                </th>
                {pivotData.months.map((m) => (
                  <th key={m} className="text-right py-3 px-4 whitespace-nowrap">
                    {m}
                  </th>
                ))}
                <th className="text-right py-3 px-4 font-bold">Total</th>
                <th className="text-right py-3 px-4">Avg</th>
              </tr>
            </thead>
            <tbody>
              {pivotData.rows.map((row) => (
                <tr
                  key={row.category}
                  className="border-b border-gray-700/50 hover:bg-gray-700/30"
                >
                  <td className="py-2 px-4 sticky left-0 bg-gray-800/90 z-10">
                    {row.parent_category && (
                      <span className="text-gray-500 text-xs mr-1">
                        {row.parent_category} /
                      </span>
                    )}
                    {row.category}
                  </td>
                  {pivotData.months.map((m) => (
                    <td
                      key={m}
                      className={`py-2 px-4 text-right ${
                        row.months[m]
                          ? mode === "income"
                            ? "text-emerald-400"
                            : mode === "expense"
                            ? "text-red-400"
                            : row.months[m] < 0
                            ? "text-red-400"
                            : "text-emerald-400"
                          : "text-gray-600"
                      }`}
                    >
                      {row.months[m] ? fmt(row.months[m]) : "—"}
                    </td>
                  ))}
                  <td className="py-2 px-4 text-right font-bold">
                    {fmt(row.total)}
                  </td>
                  <td className="py-2 px-4 text-right text-gray-400">
                    {fmt(row.average)}
                  </td>
                </tr>
              ))}
              {pivotData.rows.length === 0 && (
                <tr>
                  <td
                    colSpan={pivotData.months.length + 3}
                    className="text-center py-8 text-gray-500"
                  >
                    No data for this period
                  </td>
                </tr>
              )}
            </tbody>
            {pivotData.rows.length > 0 && (
              <tfoot>
                <tr className="border-t border-gray-600 bg-gray-800/80 font-bold">
                  <td className="py-3 px-4 sticky left-0 bg-gray-800/90 z-10">
                    Total
                  </td>
                  {pivotData.months.map((m) => {
                    const colTotal = pivotData.rows.reduce(
                      (sum, r) => sum + (r.months[m] || 0),
                      0
                    );
                    return (
                      <td key={m} className="py-3 px-4 text-right">
                        {fmt(colTotal)}
                      </td>
                    );
                  })}
                  <td className="py-3 px-4 text-right">
                    {fmt(pivotData.rows.reduce((s, r) => s + r.total, 0))}
                  </td>
                  <td className="py-3 px-4 text-right text-gray-400">
                    {fmt(pivotData.rows.reduce((s, r) => s + r.average, 0))}
                  </td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}

      {/* P&L */}
      {tab === "pnl" && !entityId && (
        <div className="bg-gray-800 rounded-xl border border-gray-700 p-8 text-center text-gray-500">
          Select an entity to view its P&L statement
        </div>
      )}
      {tab === "pnl" && pnlData && (
        <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
          <div className="p-4 border-b border-gray-700">
            <h3 className="text-lg font-semibold">{pnlData.entity_name}</h3>
            <p className="text-sm text-gray-400">
              {pnlData.start_date} to {pnlData.end_date}
            </p>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-gray-700 bg-gray-800/50">
                <th className="text-left py-3 px-4">Line Item</th>
                <th className="text-right py-3 px-4">Amount</th>
              </tr>
            </thead>
            <tbody>
              {/* Income section */}
              <tr className="bg-emerald-500/5">
                <td className="py-2 px-4 font-semibold text-emerald-400" colSpan={2}>
                  Income
                </td>
              </tr>
              {pnlData.income.map((line) => (
                <tr
                  key={`inc-${line.category}`}
                  className="border-b border-gray-700/30"
                >
                  <td className="py-2 px-4 pl-8">{line.category}</td>
                  <td className="py-2 px-4 text-right text-emerald-400">
                    {fmt(line.amount)}
                  </td>
                </tr>
              ))}
              {pnlData.income.length === 0 && (
                <tr className="border-b border-gray-700/30">
                  <td className="py-2 px-4 pl-8 text-gray-500">No income</td>
                  <td className="py-2 px-4 text-right text-gray-500">
                    {fmt(0)}
                  </td>
                </tr>
              )}
              <tr className="border-b border-gray-600 font-medium">
                <td className="py-2 px-4">Total Income</td>
                <td className="py-2 px-4 text-right text-emerald-400">
                  {fmt(pnlData.total_income)}
                </td>
              </tr>

              {/* Expense section */}
              <tr className="bg-red-500/5">
                <td className="py-2 px-4 font-semibold text-red-400" colSpan={2}>
                  Expenses
                </td>
              </tr>
              {pnlData.expenses.map((line) => (
                <tr
                  key={`exp-${line.category}`}
                  className="border-b border-gray-700/30"
                >
                  <td className="py-2 px-4 pl-8">{line.category}</td>
                  <td className="py-2 px-4 text-right text-red-400">
                    {fmt(line.amount)}
                  </td>
                </tr>
              ))}
              {pnlData.expenses.length === 0 && (
                <tr className="border-b border-gray-700/30">
                  <td className="py-2 px-4 pl-8 text-gray-500">
                    No expenses
                  </td>
                  <td className="py-2 px-4 text-right text-gray-500">
                    {fmt(0)}
                  </td>
                </tr>
              )}
              <tr className="border-b border-gray-600 font-medium">
                <td className="py-2 px-4">Total Expenses</td>
                <td className="py-2 px-4 text-right text-red-400">
                  {fmt(pnlData.total_expenses)}
                </td>
              </tr>

              {/* Net */}
              <tr className="bg-gray-700/30 font-bold text-lg">
                <td className="py-3 px-4">Net</td>
                <td
                  className={`py-3 px-4 text-right ${
                    pnlData.net >= 0 ? "text-emerald-400" : "text-red-400"
                  }`}
                >
                  {fmt(pnlData.net)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* Entity comparison */}
      {tab === "comparison" && compData && (
        <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-gray-700 bg-gray-800/50">
                <th className="text-left py-3 px-4 sticky left-0 bg-gray-800/90 z-10">
                  Entity
                </th>
                {compData.month_labels.map((m) => (
                  <th
                    key={m}
                    className="text-right py-3 px-4 whitespace-nowrap"
                  >
                    {m}
                  </th>
                ))}
                <th className="text-right py-3 px-4 font-bold">Total</th>
              </tr>
            </thead>
            <tbody>
              {compData.entities.map((ent) => {
                const total = Object.values(ent.months).reduce(
                  (s, m) => s + m.net,
                  0
                );
                return (
                  <tr
                    key={ent.entity_id}
                    className="border-b border-gray-700/50 hover:bg-gray-700/30"
                  >
                    <td className="py-2 px-4 sticky left-0 bg-gray-800/90 z-10 font-medium">
                      {ent.entity_name}
                    </td>
                    {compData.month_labels.map((m) => {
                      const net = ent.months[m]?.net || 0;
                      return (
                        <td
                          key={m}
                          className={`py-2 px-4 text-right ${
                            net > 0
                              ? "text-emerald-400"
                              : net < 0
                              ? "text-red-400"
                              : "text-gray-600"
                          }`}
                        >
                          {fmt(net)}
                        </td>
                      );
                    })}
                    <td
                      className={`py-2 px-4 text-right font-bold ${
                        total > 0
                          ? "text-emerald-400"
                          : total < 0
                          ? "text-red-400"
                          : ""
                      }`}
                    >
                      {fmt(total)}
                    </td>
                  </tr>
                );
              })}
              {compData.entities.length === 0 && (
                <tr>
                  <td
                    colSpan={compData.month_labels.length + 2}
                    className="text-center py-8 text-gray-500"
                  >
                    No entities found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
