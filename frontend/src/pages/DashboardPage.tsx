import { useState, useEffect } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import {
  getDashboard, getEntities, getEntityBreakdown,
  DashboardSummary, Entity, EntityBreakdown,
} from "../api/client";
import { entityColor } from "../lib/entityColors";

const COLORS = [
  "#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6",
  "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16",
];

// Shared with the Expenses/Income grids so an entity choice carries across pages.
const GRID_ENTITY_KEY = "grid.entity";
const DASH_ENTITY_KEY = "dashboard.entity";

function fmt(n: number) {
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(n);
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [months, setMonths] = useState(3);
  const [reloadKey, setReloadKey] = useState(0);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [entityId, setEntityId] = useState<number | null>(() => {
    const raw = sessionStorage.getItem(DASH_ENTITY_KEY);
    if (raw === null || raw === "all") return null;
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? n : null;
  });
  const [breakdown, setBreakdown] = useState<EntityBreakdown[]>([]);

  useEffect(() => {
    getEntities().then((all) => setEntities(all.filter((e) => e.is_active)));
  }, []);

  useEffect(() => {
    sessionStorage.setItem(DASH_ENTITY_KEY, entityId === null ? "all" : String(entityId));
    // Propagate a concrete entity choice to the Expenses/Income grids.
    if (entityId !== null) sessionStorage.setItem(GRID_ENTITY_KEY, String(entityId));
  }, [entityId]);

  useEffect(() => {
    if (entityId !== null) {
      setBreakdown([]);
      return;
    }
    let cancelled = false;
    getEntityBreakdown(months).then((b) => {
      if (!cancelled) setBreakdown(b);
    });
    return () => {
      cancelled = true;
    };
  }, [months, entityId, reloadKey]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getDashboard(months, entityId)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load dashboard");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [months, entityId, reloadKey]);

  if (loading && !data) return <div className="text-gray-400">Loading dashboard...</div>;

  if (error && !data) {
    return (
      <div className="max-w-lg space-y-3">
        <h2 className="text-2xl font-bold">Dashboard</h2>
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-sm text-red-400">
          <p className="font-medium">Couldn't load the dashboard.</p>
          <p className="mt-1 text-red-300/90 break-words">{error}</p>
        </div>
        <button
          onClick={() => setReloadKey((k) => k + 1)}
          className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) return <div className="text-gray-400">Loading dashboard...</div>;

  const pieData = Object.entries(data.spending_by_category).map(([name, value]) => ({
    name,
    value,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Dashboard</h2>
        <select
          value={months}
          onChange={(e) => setMonths(Number(e.target.value))}
          className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-1.5 text-sm"
        >
          <option value={1}>Last month</option>
          <option value={3}>Last 3 months</option>
          <option value={6}>Last 6 months</option>
          <option value={12}>Last 12 months</option>
        </select>
      </div>

      {/* Entity switcher: All + each active entity */}
      {entities.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <EntityPill
            label="All"
            color="#6b7280"
            active={entityId === null}
            onClick={() => setEntityId(null)}
          />
          {entities.map((e) => (
            <EntityPill
              key={e.id}
              label={e.name}
              color={entityColor(e)}
              active={entityId === e.id}
              onClick={() => setEntityId(e.id)}
            />
          ))}
        </div>
      )}

      {/* All view: per-entity comparison */}
      {entityId === null && breakdown.length > 0 && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {breakdown.map((b) => {
              const color = entityColor({ id: b.entity_id, color: b.color });
              return (
                <button
                  key={b.entity_id}
                  onClick={() => setEntityId(b.entity_id)}
                  className="text-left bg-gray-800 rounded-xl p-4 border border-gray-700 hover:border-gray-500 transition-colors"
                  style={{ borderLeft: `4px solid ${color}` }}
                >
                  <p className="text-sm font-medium" style={{ color }}>{b.entity_name}</p>
                  <p className="text-lg font-bold mt-1">{fmt(b.net)}</p>
                  <p className="text-xs text-blue-400 mt-1">In {fmt(b.income)}</p>
                  <p className="text-xs text-red-400">Out {fmt(b.expenses)}</p>
                </button>
              );
            })}
          </div>
          <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
            <h3 className="font-semibold mb-4">Income vs Expenses by Entity</h3>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={breakdown}>
                <XAxis dataKey="entity_name" tick={{ fill: "#9ca3af", fontSize: 12 }} />
                <YAxis tick={{ fill: "#9ca3af", fontSize: 12 }} />
                <Tooltip contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }} />
                <Legend />
                <Bar dataKey="income" fill="#3b82f6" name="Income" />
                <Bar dataKey="expenses" fill="#ef4444" name="Expenses" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card label="Total Balance" value={fmt(data.total_balance)} color="text-emerald-400" />
        <Card label="Income" value={fmt(data.total_income)} color="text-blue-400" />
        <Card label="Expenses" value={fmt(data.total_expenses)} color="text-red-400" />
        <Card label="Net Cash Flow" value={fmt(data.net_cash_flow)} color={data.net_cash_flow >= 0 ? "text-emerald-400" : "text-red-400"} />
      </div>

      {/* Total Saved (from manual actuals + transactions via the shared aggregation) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <SavedCard label={`Saved this month (${data.saved.year_month})`} value={data.saved.month_saved_actual} />
        <Card
          label="Saved this month (budget)"
          value={fmt(data.saved.month_saved_budget)}
          color="text-gray-300"
        />
        <SavedCard
          label={`Saved YTD (Jan–month ${data.saved.ytd_through_month})`}
          value={data.saved.ytd_saved_actual}
        />
        <Card
          label="Saved full year (budget)"
          value={fmt(data.saved.year_saved_budget)}
          color="text-gray-300"
        />
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Monthly Trend */}
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <h3 className="font-semibold mb-4">Monthly Trend</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={data.monthly_trend}>
              <XAxis dataKey="month" tick={{ fill: "#9ca3af", fontSize: 12 }} />
              <YAxis tick={{ fill: "#9ca3af", fontSize: 12 }} />
              <Tooltip contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }} />
              <Bar dataKey="income" fill="#3b82f6" name="Income" />
              <Bar dataKey="expenses" fill="#ef4444" name="Expenses" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Spending by Category */}
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <h3 className="font-semibold mb-4">Spending by Category</h3>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                  {pieData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-gray-500 text-center py-8">No spending data yet</p>
          )}
        </div>
      </div>

      {/* Budget Status */}
      {data.budget_status.length > 0 && (
        <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
          <h3 className="font-semibold mb-4">Budget Status</h3>
          <div className="space-y-3">
            {data.budget_status.map((b) => (
              <div key={b.category}>
                <div className="flex justify-between text-sm mb-1">
                  <span>{b.category}</span>
                  <span className={b.percent_used > 100 ? "text-red-400" : "text-gray-400"}>
                    {fmt(b.spent)} / {fmt(b.budget)} ({b.percent_used}%)
                  </span>
                </div>
                <div className="w-full bg-gray-700 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${b.percent_used > 100 ? "bg-red-500" : b.percent_used > 80 ? "bg-yellow-500" : "bg-emerald-500"}`}
                    style={{ width: `${Math.min(b.percent_used, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Transactions */}
      <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
        <h3 className="font-semibold mb-4">Recent Transactions</h3>
        {data.recent_transactions.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-gray-700">
                <th className="text-left py-2">Date</th>
                <th className="text-left py-2">Description</th>
                <th className="text-right py-2">Amount</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_transactions.map((t) => (
                <tr key={t.id} className="border-b border-gray-700/50">
                  <td className="py-2 text-gray-400">{t.date}</td>
                  <td className="py-2">{t.merchant_name || t.name}</td>
                  <td className={`py-2 text-right ${t.amount < 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {fmt(t.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-gray-500 text-center py-4">No transactions yet</p>
        )}
      </div>
    </div>
  );
}

function EntityPill({
  label, color, active, onClick,
}: { label: string; color: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm border transition-colors ${
        active
          ? "border-transparent text-white font-medium"
          : "border-gray-700 text-gray-300 hover:border-gray-500"
      }`}
      style={active ? { backgroundColor: color } : undefined}
    >
      <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </button>
  );
}

function Card({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
      <p className="text-xs text-gray-400 uppercase tracking-wide">{label}</p>
      <p className={`text-xl font-bold mt-1 ${color}`}>{value}</p>
    </div>
  );
}

// Actual saved: negative shows as overspent (not clamped to zero).
function SavedCard({ label, value }: { label: string; value: number }) {
  const negative = value < 0;
  return (
    <div className="bg-gray-800 rounded-xl p-4 border border-gray-700">
      <p className="text-xs text-gray-400 uppercase tracking-wide">{label}</p>
      <p className={`text-xl font-bold mt-1 ${negative ? "text-red-400" : "text-emerald-400"}`}>
        {fmt(value)}
      </p>
      {negative && <p className="text-[11px] text-red-400/80 mt-0.5">overspent</p>}
    </div>
  );
}
