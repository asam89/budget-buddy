import { useEffect, useState } from "react";
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  Landmark,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { api, DashboardSummary } from "../api/client";

const COLORS = [
  "#22c55e", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6",
  "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16",
];

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500">{label}</p>
          <p className="text-2xl font-bold mt-1">{value}</p>
        </div>
        <div className={`p-3 rounded-full ${color}`}>
          <Icon className="w-6 h-6 text-white" />
        </div>
      </div>
    </div>
  );
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
  }).format(amount);
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [months, setMonths] = useState(1);

  useEffect(() => {
    setLoading(true);
    api
      .getDashboard(months)
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  }, [months]);

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center h-full">
        <div className="text-gray-400 text-lg">Loading dashboard...</div>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="p-8">
        <h2 className="text-2xl font-bold mb-4">Dashboard</h2>
        <div className="bg-white rounded-xl shadow-sm border p-8 text-center text-gray-500">
          <p className="text-lg mb-2">Welcome to Budget Buddy!</p>
          <p>
            Connect a bank account or add transactions manually to get started.
          </p>
        </div>
      </div>
    );
  }

  const pieData = Object.entries(summary.spending_by_category).map(
    ([category, amount]) => ({ name: category, value: amount })
  );

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold">Dashboard</h2>
        <select
          value={months}
          onChange={(e) => setMonths(Number(e.target.value))}
          className="border rounded-lg px-3 py-2 text-sm"
        >
          <option value={1}>Last month</option>
          <option value={3}>Last 3 months</option>
          <option value={6}>Last 6 months</option>
          <option value={12}>Last 12 months</option>
        </select>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          label="Total Balance"
          value={formatCurrency(summary.total_balance)}
          icon={Landmark}
          color="bg-blue-500"
        />
        <StatCard
          label="Income"
          value={formatCurrency(summary.total_income)}
          icon={TrendingUp}
          color="bg-green-500"
        />
        <StatCard
          label="Expenses"
          value={formatCurrency(summary.total_expenses)}
          icon={TrendingDown}
          color="bg-red-500"
        />
        <StatCard
          label="Net Cash Flow"
          value={formatCurrency(summary.net_cash_flow)}
          icon={DollarSign}
          color={summary.net_cash_flow >= 0 ? "bg-green-500" : "bg-red-500"}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Monthly trend */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h3 className="text-lg font-semibold mb-4">Monthly Trend</h3>
          {summary.monthly_trend.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={summary.monthly_trend}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis />
                <Tooltip formatter={(v: number) => formatCurrency(v)} />
                <Bar dataKey="income" fill="#22c55e" name="Income" />
                <Bar dataKey="expenses" fill="#ef4444" name="Expenses" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-gray-400 text-center py-12">No data yet</p>
          )}
        </div>

        {/* Spending breakdown */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h3 className="text-lg font-semibold mb-4">Spending by Category</h3>
          {pieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={100}
                  label={({ name, percent }) =>
                    `${name} (${(percent * 100).toFixed(0)}%)`
                  }
                >
                  {pieData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v: number) => formatCurrency(v)} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-gray-400 text-center py-12">No spending data</p>
          )}
        </div>
      </div>

      {/* Recent transactions */}
      <div className="bg-white rounded-xl shadow-sm border p-6">
        <h3 className="text-lg font-semibold mb-4">Recent Transactions</h3>
        {summary.recent_transactions.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="pb-2">Date</th>
                <th className="pb-2">Description</th>
                <th className="pb-2">Category</th>
                <th className="pb-2 text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {summary.recent_transactions.map((txn) => (
                <tr key={txn.id} className="border-b last:border-0">
                  <td className="py-3">
                    {new Date(txn.date).toLocaleDateString()}
                  </td>
                  <td className="py-3">
                    {txn.merchant_name || txn.name}
                  </td>
                  <td className="py-3">
                    <span className="bg-gray-100 text-gray-600 px-2 py-1 rounded text-xs">
                      {txn.category || "Uncategorized"}
                    </span>
                  </td>
                  <td
                    className={`py-3 text-right font-medium ${
                      txn.amount < 0 ? "text-green-600" : "text-red-600"
                    }`}
                  >
                    {txn.amount < 0 ? "+" : "-"}
                    {formatCurrency(Math.abs(txn.amount))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-gray-400 text-center py-8">
            No transactions yet. Connect an account or add one manually.
          </p>
        )}
      </div>
    </div>
  );
}
